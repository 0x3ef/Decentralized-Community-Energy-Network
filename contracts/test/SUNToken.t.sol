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
        vm.prank(minter);
        token.mint(user, 10 ether, creditId);
        vm.prank(admin);
        token.pause();

        vm.prank(user);
        vm.expectRevert();
        token.transfer(address(0x1234), 1 ether);
    }

    function testAdminCanGrantMinterRole() public {
        address newMinter = address(0x123);

        bytes32 role = token.MINTER_ROLE();
        vm.prank(admin);
        token.grantRole(role, newMinter);

        vm.prank(newMinter);
        token.mint(user, 5 ether, creditId);

        assertEq(token.balanceOf(user), 5 ether);
    }
    function testAccountingAnchorCannotBeOverwritten() public {
        vm.startPrank(minter);
        token.mint(user, 5 ether, creditId);
        bytes32 evidence = keccak256("verified interval and source measurements");
        token.anchorAccounting(creditId, evidence);
        assertEq(token.accountingAnchors(creditId), evidence);
        vm.expectRevert(); token.anchorAccounting(creditId, keccak256("replacement"));
        vm.stopPrank();
    }
}