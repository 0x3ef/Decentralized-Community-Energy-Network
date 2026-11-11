"""Governance preparation and user transaction validation; no transaction submission."""

from sqlmodel import select
from src.modules.community.models import CommunityMembership, EnergyCommunity
from src.modules.community.service import CommunityService
from src.modules.device.models import Device
from src.modules.settlement.chain import NativeSettlementChain
from src.modules.settlement.engine import key
from src.modules.settlement.models import NativeWalletTransaction
from web3 import Web3


class GovernanceService:
    async def prepare(self, community_id, payload, user, session):
        community = await session.get(EnergyCommunity, community_id)
        if not community or not community.registry_address:
            raise LookupError("Confirmed community registry required")
        chain = NativeSettlementChain()
        registry = chain.contract("CommunityRegistry", community.registry_address)
        wallet = await CommunityService().wallet(session, user.uid)
        cid = key(community_id)
        timelock = None
        if payload.action == "apply_membership":
            function = registry.functions.applyMembership(cid)
        else:
            # Return calldata for an authorized timelock/multisig, never execute as operator.
            role = (
                registry.functions.METER_REGISTRAR_ROLE().call()
                if payload.action in ("node", "meter")
                else registry.functions.REGISTRAR_ROLE().call()
            )
            authorized = registry.functions.hasRole(role, wallet).call()
            # Timelock proposers may prepare its privileged target call.
            from src.core.config import Config

            if not authorized and Config.GOVERNANCE_TIMELOCK_ADDRESS:
                timelock = chain.contract(
                    "TimelockController", Config.GOVERNANCE_TIMELOCK_ADDRESS
                )
                authorized = (
                    timelock.functions.hasRole(
                        timelock.functions.PROPOSER_ROLE().call(), wallet
                    ).call()
                    and registry.functions.hasRole(role, timelock.address).call()
                )
            if not authorized:
                raise PermissionError(
                    "Registrar or configured timelock proposer required"
                )
            if payload.action == "transition":
                function = registry.functions.transition(
                    cid, payload.status, Web3.to_checksum_address(payload.address)
                )
            elif payload.action == "membership":
                function = registry.functions.setMembership(
                    cid, Web3.to_checksum_address(payload.address), payload.status
                )
            elif payload.action == "price":
                if not 0 < int(payload.price_wei_per_kwh) < 2**256:
                    raise ValueError("Price must be positive uint256 wei per kWh")
                function = registry.functions.configurePrice(
                    cid, int(payload.price_wei_per_kwh)
                )
            elif payload.action == "node" and payload.node_id:
                function = registry.functions.registerNode(
                    cid, key(payload.node_id), Web3.to_checksum_address(payload.address)
                )
            elif payload.action == "meter" and payload.node_id and payload.meter_id:
                device = await session.get(Device, payload.meter_id)
                if not device:
                    raise LookupError("Device not found")
                function = registry.functions.authorizeMeter(
                    cid, key(payload.node_id), key(device.device_id), payload.active
                )
            else:
                raise ValueError("Required node/meter identifiers missing")
        prepared = {
            "chain_id": chain.web3.eth.chain_id,
            "to": registry.address,
            "data": function._encode_transaction_data(),
            "value": "0",
            "status": "AWAITING_GOVERNANCE_EXECUTION"
            if payload.action != "apply_membership"
            else "AWAITING_USER_SIGNATURE",
        }
        if timelock is not None:
            salt = Web3.to_bytes(hexstr=payload.salt)
            delay = timelock.functions.getMinDelay().call()
            data = function._encode_transaction_data()
            prepared["timelock"] = timelock.address
            prepared["delay_seconds"] = delay
            prepared["operation_id"] = Web3.to_hex(
                timelock.functions.hashOperation(
                    registry.address, 0, data, bytes(32), salt
                ).call()
            )
            prepared["schedule"] = {
                "to": timelock.address,
                "value": "0",
                "data": timelock.functions.schedule(
                    registry.address, 0, data, bytes(32), salt, delay
                )._encode_transaction_data(),
            }
            prepared["execute"] = {
                "to": timelock.address,
                "value": "0",
                "data": timelock.functions.execute(
                    registry.address, 0, data, bytes(32), salt
                )._encode_transaction_data(),
            }
        return prepared

    async def apply(self, community_id, user, session):
        community = await session.get(EnergyCommunity, community_id)
        if not community:
            raise LookupError("Community not found")
        row = (
            await session.exec(
                select(CommunityMembership).where(
                    CommunityMembership.community_id == community_id,
                    CommunityMembership.user_id == user.uid,
                )
            )
        ).first()
        if not row:
            row = CommunityMembership(
                community_id=community_id,
                user_id=user.uid,
                status="PENDING",
                role="member",
            )
            session.add(row)
        await session.commit()
        return row

    async def sync(self, community_id, user, session):
        community = await session.get(EnergyCommunity, community_id)
        if not community or not community.registry_address:
            raise ValueError("Governed registry required")
        chain = NativeSettlementChain()
        registry = chain.contract("CommunityRegistry", community.registry_address)
        wallet = await CommunityService().wallet(session, user.uid)
        height = chain.confirmed_height()
        status = registry.functions.memberships(key(community_id), wallet).call(
            block_identifier=height
        )
        if not status:
            raise ValueError("No confirmed on-chain membership application")
        row = (
            await session.exec(
                select(CommunityMembership).where(
                    CommunityMembership.community_id == community_id,
                    CommunityMembership.user_id == user.uid,
                )
            )
        ).first()
        if not row:
            row = CommunityMembership(
                community_id=community_id, user_id=user.uid, role="member"
            )
            session.add(row)
        row.status = ["NONE", "PENDING", "APPROVED", "ACTIVE", "SUSPENDED", "REVOKED"][
            status
        ]
        await session.commit()
        return row


class NativeTransactionService:
    async def track(self, community_id, payload, user, session):
        chain = NativeSettlementChain()
        _, deployment, _, settlement, vault = await chain.service.contracts(
            session, community_id
        )
        wallet = await CommunityService().wallet(session, user.uid)
        payload.transaction_hash = payload.transaction_hash.lower()
        tx = chain.web3.eth.get_transaction(payload.transaction_hash)
        target = (
            settlement.address
            if payload.action == "retire"
            else deployment.sun_address
            if payload.action.startswith("approve_")
            else vault.address
        )
        if (
            tx["from"].lower() != wallet.lower()
            or not tx["to"]
            or tx["to"].lower() != target.lower()
        ):
            raise PermissionError(
                "Transaction does not belong to this wallet and protocol action"
            )
        contract = (
            chain.contract("SUNToken", target)
            if payload.action.startswith("approve_")
            else settlement
            if payload.action == "retire"
            else vault
        )
        function, arguments = contract.decode_function_input(tx["input"])
        if (
            payload.action.startswith("approve_")
            and arguments["spender"].lower()
            != (
                vault.address if payload.action == "approve_sun" else settlement.address
            ).lower()
        ):
            raise ValueError("SUN allowance targets a different spender")
        expected = {
            "deposit": "deposit",
            "withdraw": "withdraw",
            "withdraw_earnings": "withdrawEarnings",
            "escrow_sun": "depositSUN",
            "withdraw_sun": "withdrawSUN",
            "retire": "retire",
            "cancel": "cancel",
            "approve_sun": "approve",
            "approve_retirement": "approve",
        }[payload.action]
        if function.fn_name != expected:
            raise ValueError("Transaction function differs from declared action")
        row = (
            await session.exec(
                select(NativeWalletTransaction).where(
                    NativeWalletTransaction.chain_id == deployment.chain_id,
                    NativeWalletTransaction.transaction_hash
                    == payload.transaction_hash,
                )
            )
        ).first()
        if row and (
            row.user_id != user.uid
            or row.community_id != community_id
            or row.action != payload.action
        ):
            raise PermissionError("Transaction already linked to another operation")
        if not row:
            row = NativeWalletTransaction(
                community_id=community_id,
                user_id=user.uid,
                chain_id=deployment.chain_id,
                transaction_hash=payload.transaction_hash,
                action=payload.action,
            )
            session.add(row)
        await session.commit()
        return row
