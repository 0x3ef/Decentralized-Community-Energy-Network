// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SUNToken} from "../src/SUNToken.sol";

contract SUNTokenTest is Test {
    SUNToken private token;

    address private admin = address(0xA11CE);
    address private minter = address(0xB0B);
    address private user = address(0xCAFE);

    bytes32 private creditId = keccak256("credit-001");

    function setUp() public {
        token = new SUNToken(admin, minter);
    }

    function testMinterCanIssueCredit() public {
        uint256 amount = 10 ether;

        vm.prank(minter);
        token.mint(user, amount, creditId);

        assertEq(token.balanceOf(user), amount);
        assertEq(token.totalSupply(), amount);
        assertTrue(token.issuedCredits(creditId));
    }

    function testCannotIssueSameCreditTwice() public {
        vm.startPrank(minter);

        token.mint(user, 10 ether, creditId);

        vm.expectRevert(
            abi.encodeWithSelector(
                SUNToken.CreditAlreadyIssued.selector,
                creditId
            )
        );

        token.mint(user, 10 ether, creditId);

        vm.stopPrank();

        assertEq(token.balanceOf(user), 10 ether);
    }

    function testNonMinterCannotMint() public {
        vm.prank(user);

        vm.expectRevert();
        token.mint(user, 10 ether, creditId);
    }

    function testAdminCanPauseTransfers() public {
        vm.prank(admin);
        token.pause();

        vm.prank(minter);
        token.mint(user, 10 ether, creditId);

        vm.prank(user);
        vm.expectRevert();
        token.transfer(address(0x1234), 1 ether);
    }

    function testAdminCanGrantMinterRole() public {
        address newMinter = address(0x123);

        vm.prank(admin);
        token.grantRole(token.MINTER_ROLE(), newMinter);

        vm.prank(newMinter);
        token.mint(user, 5 ether, creditId);

        assertEq(token.balanceOf(user), 5 ether);
    }
}