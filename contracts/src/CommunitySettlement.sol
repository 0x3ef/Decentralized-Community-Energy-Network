// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {CommunityRegistry} from "./CommunityRegistry.sol";
import {SUNToken} from "./SUNToken.sol";

/// @notice Commitment integrity and bounded claims; not proof of measurement truth.
contract CommunitySettlement is AccessControl, ReentrancyGuard {
    enum State {
        NONE,
        CHALLENGEABLE,
        FINALIZED,
        REJECTED,
        SUPERSEDED
    }

    struct Batch {
        bytes32 community;
        bytes32 policy;
        bytes32 root;
        uint64 start;
        uint64 end;
        uint64 submitted;
        uint256 injectionWh;
        uint256 consumptionWh;
        uint256 allocatedWh;
        uint256 issuedWh;
        uint256 retiredWh;
        State state;
        address verifier;
        uint256 priceWeiPerKwh;
    }
    CommunityRegistry public immutable registry;
    SUNToken public immutable sun;
    address public vault;
    uint64 public immutable challengePeriod;
    bytes32 public immutable communityId;
    mapping(bytes32 => Batch) public batches;
    mapping(bytes32 => bytes32) public canonicalBatch;
    mapping(bytes32 => bool) public claims;
    mapping(bytes32 => bool) public retiredConsumption;
    event BatchSubmitted(bytes32 indexed id, bytes32 indexed community, bytes32 root, address verifier);
    event BatchState(bytes32 indexed id, State state, bytes32 replacement);
    event CreditClaimed(bytes32 indexed batch, bytes32 indexed claim, address indexed beneficiary, uint256 energyWh);
    event ConsumptionRetired(
        bytes32 indexed batch, bytes32 indexed claim, address indexed consumer, bytes32 node, uint256 energyWh
    );

    constructor(CommunityRegistry registry_, SUNToken sun_, address governor, uint64 delay_, bytes32 community_) {
        require(
            address(registry_) != address(0) && address(sun_) != address(0) && governor.code.length > 0 && delay_ > 0
                && community_ != 0,
            "invalid configuration"
        );
        registry = registry_;
        sun = sun_;
        challengePeriod = delay_;
        communityId = community_;
        _grantRole(DEFAULT_ADMIN_ROLE, governor);
    }

    function submit(
        bytes32 id,
        bytes32 community,
        bytes32 root,
        uint64 start,
        uint64 end,
        bytes32 policy,
        uint256 injectionWh,
        uint256 consumptionWh,
        uint256 allocatedWh
    ) external {
        require(
            registry.hasRole(registry.ORACLE_ROLE(), msg.sender) && registry.isActive(community)
                && community == communityId,
            "unauthorized verifier"
        );
        (,,,, bytes32 currentPolicy, uint32 intervalSeconds) = registry.communities(community);
        require(
            id != 0 && root != 0 && batches[id].state == State.NONE && end > start && end - start == intervalSeconds
                && start % intervalSeconds == 0 && end <= block.timestamp && policy == currentPolicy,
            "invalid batch"
        );
        require(allocatedWh <= injectionWh && allocatedWh <= consumptionWh, "energy not conserved");
        batches[id] = Batch(
            community,
            policy,
            root,
            start,
            end,
            uint64(block.timestamp),
            injectionWh,
            consumptionWh,
            allocatedWh,
            0,
            0,
            State.CHALLENGEABLE,
            msg.sender,
            registry.priceWeiPerKwh(community)
        );
        emit BatchSubmitted(id, community, root, msg.sender);
    }

    function finalize(bytes32 id) external onlyRole(DEFAULT_ADMIN_ROLE) {
        Batch storage b = batches[id];
        require(
            b.state == State.CHALLENGEABLE && block.timestamp >= b.submitted + challengePeriod
                && registry.isActive(b.community),
            "unresolved batch"
        );
        bytes32 key = keccak256(abi.encode(b.community, b.start, b.end));
        require(canonicalBatch[key] == 0, "interval already finalized");
        canonicalBatch[key] = id;
        b.state = State.FINALIZED;
        emit BatchState(id, b.state, 0);
    }

    function reject(bytes32 id) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(batches[id].state == State.CHALLENGEABLE, "not challengeable");
        batches[id].state = State.REJECTED;
        emit BatchState(id, State.REJECTED, 0);
    }

    function supersede(bytes32 id, bytes32 replacement) external onlyRole(DEFAULT_ADMIN_ROLE) {
        Batch storage old = batches[id];
        Batch memory next = batches[replacement];
        require(
            old.state == State.FINALIZED && old.issuedWh == 0 && old.retiredWh == 0 && !_financiallyUsed(id)
                && next.state == State.CHALLENGEABLE && block.timestamp >= next.submitted + challengePeriod
                && registry.isActive(next.community) && next.community == old.community && next.start == old.start
                && next.end == old.end && id != replacement,
            "explicit reversal required"
        );
        batches[replacement].state = State.FINALIZED;
        canonicalBatch[keccak256(abi.encode(old.community, old.start, old.end))] = replacement;
        old.state = State.SUPERSEDED;
        emit BatchState(id, State.SUPERSEDED, replacement);
    }

    function _financiallyUsed(bytes32 id) private view returns (bool) {
        if (vault == address(0)) return false;
        (bool ok, bytes memory result) = vault.staticcall(abi.encodeWithSignature("allocatedEnergy(bytes32)", id));
        require(ok, "vault accounting unavailable");
        return abi.decode(result, (uint256)) > 0;
    }

    /// @dev Sorted-pair double-keccak ABI leaf; kind 0=issuance, 1=retirement.
    function leaf(
        uint8 kind,
        bytes32 batch,
        bytes32 claim,
        bytes32 node,
        bytes32 meter,
        address beneficiary,
        uint256 wh
    ) public pure returns (bytes32) {
        return keccak256(bytes.concat(keccak256(abi.encode(kind, batch, claim, node, meter, beneficiary, wh))));
    }

    function issue(
        bytes32 batch,
        bytes32 claim,
        bytes32 node,
        bytes32 meter,
        address beneficiary,
        uint256 wh,
        bytes32[] calldata proof
    ) external nonReentrant {
        Batch storage b = batches[batch];
        _check(b, claim, node, meter, beneficiary, wh);
        require(MerkleProof.verify(proof, b.root, leaf(0, batch, claim, node, meter, beneficiary, wh)), "invalid proof");
        require(b.issuedWh + wh <= b.injectionWh, "issuance exceeds injection");
        claims[claim] = true;
        b.issuedWh += wh;
        sun.mint(beneficiary, wh * 1e15, claim);
        emit CreditClaimed(batch, claim, beneficiary, wh);
    }

    function retire(bytes32 batch, bytes32 claim, bytes32 node, bytes32 meter, uint256 wh, bytes32[] calldata proof)
        external
        nonReentrant
    {
        Batch storage b = batches[batch];
        _check(b, claim, node, meter, msg.sender, wh);
        bytes32 consumption = keccak256(abi.encode(b.community, node, b.start, b.end));
        require(!retiredConsumption[consumption], "consumption already retired");
        require(MerkleProof.verify(proof, b.root, leaf(1, batch, claim, node, meter, msg.sender, wh)), "invalid proof");
        require(b.retiredWh + wh <= b.allocatedWh, "retirement exceeds allocation");
        require(vault != address(0), "financial settlement vault required");
        (bool ok, bytes memory result) =
            vault.staticcall(abi.encodeWithSignature("deliveredEnergyByNode(bytes32,bytes32)", batch, node));
        require(ok && abi.decode(result, (uint256)) >= wh, "financial allocation not delivered");
        (bool capOk, bytes memory capResult) =
            vault.staticcall(abi.encodeWithSignature("retirementCap(bytes32,bytes32)", batch, node));
        require(capOk && abi.decode(capResult, (uint256)) == wh, "retire complete approved node allocation");
        claims[claim] = true;
        retiredConsumption[consumption] = true;
        b.retiredWh += wh;
        sun.burnFrom(msg.sender, wh * 1e15);
        emit ConsumptionRetired(batch, claim, msg.sender, node, wh);
    }

    function _check(Batch storage b, bytes32 claim, bytes32 node, bytes32 meter, address owner, uint256 wh)
        private
        view
    {
        require(b.state == State.FINALIZED && registry.isActive(b.community), "community or batch inactive");
        require(claim != 0 && !claims[claim] && wh > 0, "duplicate or empty claim");
        require(
            registry.isMember(b.community, owner) && registry.nodes(b.community, node) == owner
                && registry.meters(b.community, meter) == node,
            "unauthorized physical node"
        );
    }

    function bindVault(address vault_) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(vault == address(0) && vault_.code.length > 0, "one-time vault binding");
        (bool ok, bytes memory result) = vault_.staticcall(abi.encodeWithSignature("communityId()"));
        require(ok && abi.decode(result, (bytes32)) == communityId, "wrong community");
        vault = vault_;
    }

    function allocationRoot(bytes32 id) external view returns (bytes32, uint256, uint256, uint64, uint64) {
        Batch memory b = batches[id];
        require(b.state == State.FINALIZED && registry.isActive(b.community), "unresolved settlement");
        return (b.root, b.allocatedWh, b.priceWeiPerKwh, b.start, b.end);
    }
}
