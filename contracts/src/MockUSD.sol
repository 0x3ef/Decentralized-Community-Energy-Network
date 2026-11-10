// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @notice Unbacked development points: one USDx denotes one simulated peso.
/// @dev Deployment and faucet are restricted to local EVM chain IDs.
contract MockUSD is ERC20, AccessControl {
    bytes32 public constant FAUCET_ROLE = keccak256("FAUCET_ROLE");
    constructor(address admin) ERC20("Simulated Peso (no monetary backing)", "USDx") {
        require(block.chainid == 31337 || block.chainid == 1337, "local development only");
        require(admin != address(0), "zero admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(FAUCET_ROLE, admin);
    }
    function decimals() public pure override returns (uint8) { return 6; }
    function faucet(address recipient, uint256 amount) external onlyRole(FAUCET_ROLE) {
        require(block.chainid == 31337 || block.chainid == 1337, "local development only");
        require(amount > 0 && amount <= 1_000_000 * 1e6, "invalid faucet amount");
        _mint(recipient, amount);
    }
}
