// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ERC20Pausable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

contract SUNToken is ERC20, ERC20Pausable, ERC20Burnable, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    mapping(bytes32 => bool) public issuedCredits;

    error ZeroAddress();
    error ZeroAmount();
    error CreditAlreadyIssued(bytes32 creditId);
    error InvalidCreditId();

    event CreditIssued(
        bytes32 indexed creditId,
        address indexed recipient,
        uint256 amount
    );

    constructor(address admin, address minter)
        ERC20("Solar Energy Unit", "SUN")
    {
        if (admin == address(0) || minter == address(0)) {
            revert ZeroAddress();
        }

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(MINTER_ROLE, minter);
    }

    function mint(
        address recipient,
        uint256 amount,
        bytes32 creditId
    ) external onlyRole(MINTER_ROLE) {
        if (recipient == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (creditId == bytes32(0)) revert InvalidCreditId();

        if (issuedCredits[creditId]) {
            revert CreditAlreadyIssued(creditId);
        }

        // La escritura y el mint ocurren en la misma transacción.
        // Si _mint falla, issuedCredits también se revierte.
        issuedCredits[creditId] = true;

        _mint(recipient, amount);

        emit CreditIssued(creditId, recipient, amount);
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(AccessControl)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }

    function _update(
        address from,
        address to,
        uint256 value
    ) internal override(ERC20, ERC20Pausable) {
        super._update(from, to, value);
    }
}