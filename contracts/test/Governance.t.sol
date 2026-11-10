// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Test} from "forge-std/Test.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {CommunityRegistry} from "../src/CommunityRegistry.sol";
import {CommunitySettlement} from "../src/CommunitySettlement.sol";
import {NativeSettlementVault, IApprovedSettlement} from "../src/NativeSettlementVault.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {SUNToken} from "../src/SUNToken.sol";

contract GovernanceTest is Test {
    TimelockController governor;
    CommunityRegistry registry;
    CommunitySettlement settlement;
    SUNToken sun;
    bytes32 community = keccak256("physical-boundary");
    bytes32 policy = keccak256("policy-v2");
    uint256 sequence;
    address member = address(0x1234);
    bytes32 node = keccak256("node");
    bytes32 meter = keccak256("meter");

    function gov(address target, bytes memory data) internal {
        bytes32 salt = bytes32(++sequence);
        governor.schedule(target, 0, data, 0, salt, 1);
        vm.warp(block.timestamp + 1);
        governor.execute(target, 0, data, 0, salt);
    }

    function setUp() public {
        vm.warp(100000);
        address[] memory signers = new address[](1);
        signers[0] = address(this);
        governor = new TimelockController(1, signers, signers, address(0));
        registry = new CommunityRegistry(address(governor));
        sun = new SUNToken(address(governor), address(governor));
        settlement = new CommunitySettlement(registry, sun, address(governor), 10, community);
        gov(address(sun), abi.encodeCall(sun.grantRole, (sun.MINTER_ROLE(), address(settlement))));
        gov(address(sun), abi.encodeCall(sun.revokeRole, (sun.MINTER_ROLE(), address(governor))));
        registry.propose(community, keccak256("grid-connected Cali installation"), policy, 900);
    }

    function activate() internal {
        gov(
            address(registry),
            abi.encodeCall(registry.transition, (community, CommunityRegistry.Status.UNDER_REVIEW, address(0)))
        );
        gov(
            address(registry),
            abi.encodeCall(registry.transition, (community, CommunityRegistry.Status.APPROVED, address(0)))
        );
        gov(address(registry), abi.encodeCall(registry.configurePrice, (community, 1e15)));
        gov(
            address(registry),
            abi.encodeCall(registry.transition, (community, CommunityRegistry.Status.ACTIVE, address(this)))
        );
        vm.prank(member);
        registry.applyMembership(community);
        gov(
            address(registry),
            abi.encodeCall(registry.setMembership, (community, member, CommunityRegistry.Membership.APPROVED))
        );
        gov(
            address(registry),
            abi.encodeCall(registry.setMembership, (community, member, CommunityRegistry.Membership.ACTIVE))
        );
        gov(address(registry), abi.encodeCall(registry.registerNode, (community, node, member)));
        gov(address(registry), abi.encodeCall(registry.authorizeMeter, (community, node, meter, true)));
        gov(address(registry), abi.encodeCall(registry.grantRole, (registry.ORACLE_ROLE(), address(this))));
    }

    function testUserCannotActivateOrGrantRoles() public {
        vm.expectRevert();
        registry.transition(community, CommunityRegistry.Status.ACTIVE, member);
        bytes32 role = registry.REGISTRAR_ROLE();
        vm.prank(member);
        vm.expectRevert();
        registry.grantRole(role, member);
        assertFalse(registry.isActive(community));
    }

    function testGovernanceCanApproveAndSuspend() public {
        activate();
        assertTrue(registry.isMember(community, member));
        gov(
            address(registry),
            abi.encodeCall(registry.transition, (community, CommunityRegistry.Status.SUSPENDED, address(0)))
        );
        assertFalse(registry.isMember(community, member));
    }

    function batch(bytes32 id, bytes32 root) internal {
        settlement.submit(id, community, root, 97200, 98100, policy, 5000, 3000, 3000);
        vm.expectRevert();
        settlement.finalize(id);
        vm.warp(block.timestamp + 10);
        gov(address(settlement), abi.encodeCall(settlement.finalize, (id)));
    }

    function testApprovedCommitmentMintAndReplayProtection() public {
        activate();
        bytes32 id = keccak256("batch");
        bytes32 claim = keccak256("issuance");
        bytes32 root = settlement.leaf(0, id, claim, node, meter, member, 5000);
        batch(id, root);
        bytes32[] memory proof = new bytes32[](0);
        settlement.issue(id, claim, node, meter, member, 5000, proof);
        assertEq(sun.balanceOf(member), 5e18);
        vm.expectRevert();
        settlement.issue(id, claim, node, meter, member, 5000, proof);
        vm.expectRevert();
        settlement.submit(id, community, root, 97200, 98100, policy, 5000, 3000, 3000);
    }

    function testUnauthorizedMeterCannotClaimEvenWithCommittedLeaf() public {
        activate();
        bytes32 id = keccak256("batch");
        bytes32 claim = keccak256("claim");
        bytes32 wrong = keccak256("unapproved");
        batch(id, settlement.leaf(0, id, claim, node, wrong, member, 5000));
        vm.expectRevert();
        settlement.issue(id, claim, node, wrong, member, 5000, new bytes32[](0));
        assertEq(sun.totalSupply(), 0);
    }

    function testSuspendedCommunityCannotIssue() public {
        activate();
        bytes32 id = keccak256("batch");
        bytes32 claim = keccak256("claim");
        batch(id, settlement.leaf(0, id, claim, node, meter, member, 5000));
        gov(
            address(registry),
            abi.encodeCall(registry.transition, (community, CommunityRegistry.Status.SUSPENDED, address(0)))
        );
        vm.expectRevert();
        settlement.issue(id, claim, node, meter, member, 5000, new bytes32[](0));
    }

    function testSecondBatchCannotFinalizeSameInterval() public {
        activate();
        batch(keccak256("one"), keccak256("root"));
        settlement.submit(keccak256("two"), community, keccak256("root2"), 97200, 98100, policy, 5000, 3000, 3000);
        vm.warp(block.timestamp + 10);
        bytes memory data = abi.encodeCall(settlement.finalize, (keccak256("two")));
        bytes32 salt = bytes32(++sequence);
        governor.schedule(address(settlement), 0, data, 0, salt, 1);
        vm.warp(block.timestamp + 1);
        vm.expectRevert();
        governor.execute(address(settlement), 0, data, 0, salt);
    }

    address consumer = address(0x4567);
    bytes32 consumerNode = keccak256("consumer-node");
    bytes32 consumerMeter = keccak256("consumer-meter");
    bytes32 financialBatch = keccak256("native-settlement");
    bytes32 issuance = keccak256("verified-injection");
    bytes32 retirement = keccak256("eligible-consumption");
    bytes32 allocation = keccak256("native-allocation");
    bytes32 a;
    bytes32 b;
    bytes32 c;
    NativeSettlementVault vault;

    function hashPair(bytes32 x, bytes32 y) internal pure returns (bytes32) {
        return x < y ? keccak256(abi.encodePacked(x, y)) : keccak256(abi.encodePacked(y, x));
    }

    function nativeFixture() internal {
        activate();
        vm.prank(consumer);
        registry.applyMembership(community);
        gov(
            address(registry),
            abi.encodeCall(registry.setMembership, (community, consumer, CommunityRegistry.Membership.APPROVED))
        );
        gov(
            address(registry),
            abi.encodeCall(registry.setMembership, (community, consumer, CommunityRegistry.Membership.ACTIVE))
        );
        gov(address(registry), abi.encodeCall(registry.registerNode, (community, consumerNode, consumer)));
        gov(address(registry), abi.encodeCall(registry.authorizeMeter, (community, consumerNode, consumerMeter, true)));
        gov(address(registry), abi.encodeCall(registry.grantRole, (registry.SETTLEMENT_ROLE(), address(this))));
        vault = new NativeSettlementVault(registry, IApprovedSettlement(address(settlement)), IERC20(address(sun)));
        gov(address(settlement), abi.encodeCall(settlement.bindVault, (address(vault))));
        a = settlement.leaf(0, financialBatch, issuance, node, meter, member, 5000);
        b = settlement.leaf(1, financialBatch, retirement, consumerNode, consumerMeter, consumer, 3000);
        c = vault.leaf(financialBatch, allocation, member, consumer, consumerNode, 3000, 3000, 1e15);
        batch(financialBatch, hashPair(hashPair(a, b), hashPair(c, c)));
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = b;
        proof[1] = hashPair(c, c);
        settlement.issue(financialBatch, issuance, node, meter, member, 5000, proof);
        vm.startPrank(member);
        sun.approve(address(vault), 3e18);
        vault.depositSUN(3e18);
        vm.stopPrank();
        vm.deal(consumer, 1 ether);
    }

    function reserveNative() internal {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = c;
        proof[1] = hashPair(a, b);
        vault.reserve(financialBatch, allocation, member, consumer, consumerNode, 3000, 3000, proof);
    }

    function testNativeDepositReservedSettlementAndRetirement() public {
        nativeFixture();
        vm.prank(consumer);
        vault.deposit{value: 0.01 ether}(1e15);
        reserveNative();
        assertEq(vault.reserved(consumer), 0.003 ether);
        assertEq(vault.available(consumer), 0.007 ether);
        vm.prank(consumer);
        vm.expectRevert();
        vault.withdraw(0.008 ether, payable(consumer));
        vault.execute(allocation);
        assertEq(sun.balanceOf(consumer), 3e18);
        assertEq(vault.earnings(member), 0.003 ether);
        vm.expectRevert();
        vault.execute(allocation);
        vm.expectRevert();
        reserveNative();
        vm.prank(member);
        vault.withdrawEarnings(0.003 ether, payable(member));
        assertEq(member.balance, 0.003 ether);
        uint256 beforeBalance = address(vault).balance;
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = a;
        proof[1] = hashPair(c, c);
        vm.startPrank(consumer);
        sun.approve(address(settlement), 3e18);
        settlement.retire(financialBatch, retirement, consumerNode, consumerMeter, 3000, proof);
        vm.expectRevert();
        settlement.retire(financialBatch, retirement, consumerNode, consumerMeter, 3000, proof);
        vm.stopPrank();
        assertEq(address(vault).balance, beforeBalance);
        assertEq(sun.totalSupply(), 2e18);
        assertEq(sun.balanceOf(member), 2e18);
        vm.prank(consumer);
        vault.withdraw(0.007 ether, payable(consumer));
        assertEq(vault.totalLiabilities(), 0);
        assertEq(address(vault).balance, 0);
    }

    function testUnpaidConsumptionCannotRetire() public {
        nativeFixture();
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = a;
        proof[1] = hashPair(c, c);
        vm.prank(consumer);
        vm.expectRevert("financial allocation not delivered");
        settlement.retire(financialBatch, retirement, consumerNode, consumerMeter, 3000, proof);
        assertEq(sun.totalSupply(), 5e18);
    }

    function testReservedBatchCannotBeSupersededWithoutIssuance() public {
        nativeFixture();
        bytes32 nextBatch = keccak256("next interval");
        bytes32 nextAllocation = keccak256("next allocation");
        bytes32 replacement = keccak256("replacement");
        bytes32 root = vault.leaf(nextBatch, nextAllocation, member, consumer, consumerNode, 3000, 3000, 1e15);
        settlement.submit(nextBatch, community, root, 98100, 99000, policy, 5000, 3000, 3000);
        vm.warp(block.timestamp + 10);
        gov(address(settlement), abi.encodeCall(settlement.finalize, (nextBatch)));
        vm.prank(consumer);
        vault.deposit{value: 0.01 ether}(1e15);
        vault.reserve(nextBatch, nextAllocation, member, consumer, consumerNode, 3000, 3000, new bytes32[](0));
        settlement.submit(replacement, community, keccak256("replacement root"), 98100, 99000, policy, 5000, 3000, 3000);
        vm.warp(block.timestamp + 10);
        bytes memory data = abi.encodeCall(settlement.supersede, (nextBatch, replacement));
        bytes32 salt = bytes32(++sequence);
        governor.schedule(address(settlement), 0, data, 0, salt, 1);
        vm.warp(block.timestamp + 1);
        vm.expectRevert("explicit reversal required");
        governor.execute(address(settlement), 0, data, 0, salt);
        vault.execute(nextAllocation);
        assertEq(vault.earnings(member), 0.003 ether);
    }

    function testUnderfundedPortionNeverBecomesPaid() public {
        nativeFixture();
        vm.prank(consumer);
        vault.deposit{value: 0.001 ether}(1e15);
        vm.expectRevert();
        reserveNative();
        assertEq(vault.earnings(member), 0);
        assertEq(sun.balanceOf(consumer), 0);
        assertEq(vault.reserved(consumer), 0);
    }

    function testInvalidAllocationProofCannotReserveFunds() public {
        nativeFixture();
        vm.prank(consumer);
        vault.deposit{value: 0.01 ether}(1e15);
        vm.expectRevert();
        vault.reserve(financialBatch, allocation, member, consumer, consumerNode, 3000, 3000, new bytes32[](0));
        assertEq(vault.available(consumer), 0.01 ether);
    }

    function testSuspensionBlocksSettlementButPreservesExit() public {
        nativeFixture();
        vm.prank(consumer);
        vault.deposit{value: 0.01 ether}(1e15);
        reserveNative();
        gov(
            address(registry),
            abi.encodeCall(registry.transition, (community, CommunityRegistry.Status.SUSPENDED, address(0)))
        );
        vm.expectRevert();
        vault.execute(allocation);
        vm.prank(consumer);
        vault.cancel(allocation);
        vm.prank(consumer);
        vault.withdraw(0.01 ether, payable(consumer));
        assertEq(vault.totalLiabilities(), 0);
    }

    function testOrdinaryUserCannotSubmitBatch() public {
        activate();
        vm.prank(consumer);
        vm.expectRevert();
        settlement.submit(
            keccak256("unauthorized"), community, keccak256("root"), 97200, 98100, policy, 5000, 3000, 3000
        );
    }

    function testWithdrawalFailureRestoresAccounting() public {
        nativeFixture();
        vm.prank(consumer);
        vault.deposit{value: 0.01 ether}(1e15);
        RejectedReceiver receiver = new RejectedReceiver();
        vm.prank(consumer);
        vm.expectRevert();
        vault.withdraw(0.005 ether, payable(address(receiver)));
        assertEq(vault.available(consumer), 0.01 ether);
        assertEq(vault.totalLiabilities(), 0.01 ether);
        assertEq(address(vault).balance, 0.01 ether);
    }

    function testCrossCommunityBatchRejected() public {
        activate();
        vm.expectRevert();
        settlement.submit(
            keccak256("cross"),
            keccak256("another-community"),
            keccak256("root"),
            97200,
            98100,
            policy,
            5000,
            3000,
            3000
        );
    }

    function testReservedSUNCannotBeDoubleSpent() public {
        nativeFixture();
        vm.prank(member);
        vm.expectRevert();
        sun.transfer(consumer, 3e18);
        vm.prank(consumer);
        vault.deposit{value: 0.01 ether}(1e15);
        reserveNative();
        vm.prank(member);
        vm.expectRevert();
        vault.withdrawSUN(1);
    }

    function testFuzzVaultLiabilitiesAreBacked(uint96 amount) public {
        nativeFixture();
        uint256 value = bound(uint256(amount), 1, 1 ether);
        vm.prank(consumer);
        vault.deposit{value: value}(1e15);
        assertGe(address(vault).balance, vault.totalLiabilities());
        vm.prank(consumer);
        vault.withdraw(value, payable(consumer));
        assertEq(vault.totalLiabilities(), 0);
    }

    function testWithdrawalReentrancyIsBlocked() public {
        nativeFixture();
        ReenterMember attacker = new ReenterMember(vault);
        attacker.applyTo(registry, community);
        gov(
            address(registry),
            abi.encodeCall(
                registry.setMembership, (community, address(attacker), CommunityRegistry.Membership.APPROVED)
            )
        );
        gov(
            address(registry),
            abi.encodeCall(registry.setMembership, (community, address(attacker), CommunityRegistry.Membership.ACTIVE))
        );
        vm.deal(address(this), 1 ether);
        attacker.fund{value: 0.01 ether}();
        attacker.attack();
        assertFalse(attacker.reentered());
        assertEq(vault.available(address(attacker)), 0.005 ether);
        assertEq(address(vault).balance, vault.totalLiabilities());
    }
}

contract RejectedReceiver {
    receive() external payable {
        revert("recipient rejects");
    }
}

contract ReenterMember {
    NativeSettlementVault public vault;
    bool public reentered;

    constructor(NativeSettlementVault vault_) {
        vault = vault_;
    }

    function applyTo(CommunityRegistry registry, bytes32 community) external {
        registry.applyMembership(community);
    }

    function fund() external payable {
        vault.deposit{value: msg.value}(1e15);
    }

    function attack() external {
        vault.withdraw(0.005 ether, payable(address(this)));
    }

    receive() external payable {
        (reentered,) = address(vault).call(abi.encodeCall(vault.withdraw, (0.005 ether, payable(address(this)))));
    }
}
