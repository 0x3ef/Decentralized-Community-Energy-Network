// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SUNToken} from "../src/SUNToken.sol";
import {RedemptionManager} from "../src/RedemptionManager.sol";

contract RedemptionManagerTest is Test {
    SUNToken internal token;
    RedemptionManager internal manager;

    address internal user = address(0xA11CE);
    uint256 internal constant WEI_PER_TOKEN = 0.001 ether; // 1000 SUN = 1 ETH

    function setUp() public {
        token = new SUNToken();
        manager = new RedemptionManager(address(token), WEI_PER_TOKEN);

        token.mint(user, 1000e18);
        vm.prank(user);
        token.approve(address(manager), type(uint256).max);

        vm.deal(address(this), 10 ether);
        manager.fund{value: 1 ether}();
    }

    function test_Redeem() public {
        uint256 sunAmount = 100e18; // 100 SUN
        uint256 expectedEth = (sunAmount * WEI_PER_TOKEN) / 1e18;

        uint256 before = user.balance;
        vm.prank(user);
        manager.redeem(sunAmount);

        assertEq(user.balance - before, expectedEth);
        assertEq(token.balanceOf(user), 900e18);
    }

    function test_RedeemZeroReverts() public {
        vm.prank(user);
        vm.expectRevert(RedemptionManager.InvalidAmount.selector);
        manager.redeem(0);
    }

    function test_OnlyOwnerCanSetRate() public {
        vm.prank(user);
        vm.expectRevert(RedemptionManager.NotOwner.selector);
        manager.setRate(1 ether);
    }

    function test_RedeemFailsWhenUnderfunded() public {
        // Drain the contract first.
        manager.withdraw(1 ether);

        vm.prank(user);
        vm.expectRevert(RedemptionManager.InsufficientContractBalance.selector);
        manager.redeem(100e18);
    }
}