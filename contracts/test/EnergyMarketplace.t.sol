// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Test} from "forge-std/Test.sol";
import {SUNToken} from "../src/SUNToken.sol";
import {MockUSD} from "../src/MockUSD.sol";
import {EnergyMarketplace} from "../src/EnergyMarketplace.sol";
import {EnergyCompensation} from "../src/EnergyCompensation.sol";

contract CommunityLifecycleTest is Test {
    SUNToken sun; MockUSD usd; EnergyMarketplace market; EnergyCompensation compensation;
    address producer = address(0x111); address consumer = address(0x222);
    bytes32 community = keccak256("community-a");
    function setUp() public {
        vm.chainId(31337);
        sun = new SUNToken(address(this), address(this)); usd = new MockUSD(address(this));
        market = new EnergyMarketplace(address(sun), address(usd), community, address(this));
        compensation = new EnergyCompensation(address(sun), community, address(this));
        market.setMember(producer, true); market.setMember(consumer, true);
        sun.mint(producer, 5e18, keccak256("verified-injection-5-kwh"));
        usd.faucet(consumer, 2000e6);
    }
    function order() internal returns (uint256 id) {
        vm.startPrank(producer); sun.approve(address(market), 3e18);
        id = market.placeSellOrder(3e18, 450e6, block.timestamp + 3600); vm.stopPrank();
    }
    function testCompleteDualTokenLifecycle() public {
        uint256 id = order();
        vm.startPrank(consumer); usd.approve(address(market), 1350e6); market.fillOrder(id, 3e18); vm.stopPrank();
        bytes32 retirement = keccak256("allocation-3-kwh");
        compensation.authorize(retirement, consumer, 3e18, keccak256("withdrawal-and-source-interval"));
        vm.startPrank(consumer); sun.approve(address(compensation), 3e18); compensation.retire(retirement); vm.stopPrank();
        assertEq(sun.balanceOf(producer), 2e18); assertEq(sun.balanceOf(consumer), 0);
        assertEq(sun.totalSupply(), 2e18); assertEq(usd.balanceOf(producer), 1350e6); assertEq(usd.balanceOf(consumer), 650e6);
        vm.prank(consumer); vm.expectRevert(); compensation.retire(retirement);
    }
    function testPaymentFailureRollsBackEscrow() public {
        uint256 id = order(); vm.prank(consumer); vm.expectRevert(); market.fillOrder(id, 3e18);
        assertEq(market.getOrder(id).remaining, 3e18); assertEq(sun.balanceOf(address(market)), 3e18);
    }
    function testPartialFillAndCancellation() public {
        uint256 id = order(); vm.startPrank(consumer); usd.approve(address(market), 450e6); market.fillOrder(id, 1e18); vm.stopPrank();
        vm.prank(producer); market.cancelOrder(id); assertEq(sun.balanceOf(producer), 4e18);
    }
    function testExpiredOrderCannotFill() public {
        uint256 id = order(); vm.warp(block.timestamp + 3601);
        vm.prank(consumer); vm.expectRevert(); market.fillOrder(id, 1e18);
        market.expireOrder(id); assertEq(sun.balanceOf(producer), 5e18);
    }
    function testCommunityMembershipRequired() public {
        uint256 id = order(); market.setMember(consumer, false);
        vm.prank(consumer); vm.expectRevert(); market.fillOrder(id, 1e18);
    }
    function testRetirementRequiresConsumerAndAllowance() public {
        bytes32 id = keccak256("retirement"); compensation.authorize(id, producer, 1e18, keccak256("evidence"));
        vm.expectRevert(); compensation.retire(id);
        vm.prank(producer); vm.expectRevert(); compensation.retire(id);
        assertEq(sun.totalSupply(), 5e18);
    }
    function testDuplicateIssuanceRejected() public {
        vm.expectRevert(); sun.mint(producer, 5e18, keccak256("verified-injection-5-kwh"));
    }
    function testProductionFaucetDeploymentRejected() public {
        vm.chainId(1); vm.expectRevert(); new MockUSD(address(this));
    }
    function testFuzzNoOverfill(uint96 amount) public {
        uint256 id = order(); uint256 fill = bound(uint256(amount), 1, 3e18);
        vm.startPrank(consumer); usd.approve(address(market), type(uint256).max); market.fillOrder(id, fill); vm.stopPrank();
        assertEq(market.getOrder(id).remaining, 3e18 - fill);
        assertEq(sun.balanceOf(consumer), fill); assertEq(sun.totalSupply(), 5e18);
    }
    function testPriceTimeMatching() public {
        vm.startPrank(producer);
        sun.approve(address(market), 3e18);
        market.placeSellOrder(1e18, 450e6, block.timestamp + 3600);
        market.placeSellOrder(1e18, 400e6, block.timestamp + 3600);
        market.placeSellOrder(1e18, 400e6, block.timestamp + 3600);
        vm.stopPrank();
        (uint256 best, bool found) = market.bestOrder(consumer);
        assertTrue(found); assertEq(best, 1);
        vm.startPrank(consumer);
        usd.approve(address(market), 800e6);
        market.fillBestOrder(1e18, 400e6);
        vm.stopPrank();
        (best, found) = market.bestOrder(consumer);
        assertTrue(found); assertEq(best, 2);
        assertEq(usd.balanceOf(producer), 400e6);
    }
}
