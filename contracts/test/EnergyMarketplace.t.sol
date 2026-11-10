// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SUNToken} from "../src/SUNToken.sol";
import {EnergyMarketplace} from "../src/EnergyMarketplace.sol";

contract EnergyMarketplaceTest is Test {
    SUNToken internal token;
    EnergyMarketplace internal market;

    address internal seller = address(0x5E11E);
    address internal buyer = address(0xB0B);

    function setUp() public {
        token = new SUNToken();
        market = new EnergyMarketplace(address(token));

        token.mint(seller, 100e18);
        vm.prank(seller);
        token.approve(address(market), type(uint256).max);

        vm.deal(buyer, 10 ether);
    }

    function test_PlaceSellOrder() public {
        vm.prank(seller);
        uint256 orderId = market.placeSellOrder(50e18, 0.01 ether);

        EnergyMarketplace.Order memory order = market.getOrder(orderId);
        assertEq(order.maker, seller);
        assertEq(order.remaining, 50e18);
        assertTrue(order.active);
        assertEq(token.balanceOf(address(market)), 50e18);
    }

    function test_FillOrder() public {
        vm.prank(seller);
        uint256 orderId = market.placeSellOrder(50e18, 0.01 ether);

        uint256 cost = (10e18 * 0.01 ether) / 1e18; // 10 SUN
        vm.prank(buyer);
        market.fillOrder{value: cost}(orderId, 10e18, buyer);

        assertEq(token.balanceOf(buyer), 10e18);
        assertEq(market.getOrder(orderId).remaining, 40e18);
        assertEq(seller.balance, cost);
    }

    function test_FillOrderInsufficientPayment() public {
        vm.prank(seller);
        uint256 orderId = market.placeSellOrder(50e18, 0.01 ether);

        vm.prank(buyer);
        vm.expectRevert(EnergyMarketplace.InsufficientPayment.selector);
        market.fillOrder{value: 1 wei}(orderId, 10e18, buyer);
    }

    function test_CancelOrderRefunds() public {
        vm.prank(seller);
        uint256 orderId = market.placeSellOrder(50e18, 0.01 ether);

        uint256 before = token.balanceOf(seller);
        vm.prank(seller);
        market.cancelOrder(orderId);

        assertEq(token.balanceOf(seller) - before, 50e18);
        assertFalse(market.isActive(orderId));
    }

    function test_OnlyMakerCanCancel() public {
        vm.prank(seller);
        uint256 orderId = market.placeSellOrder(10e18, 0.01 ether);

        vm.prank(buyer);
        vm.expectRevert(EnergyMarketplace.NotMaker.selector);
        market.cancelOrder(orderId);
    }
}