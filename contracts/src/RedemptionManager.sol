// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface ISUNBurnable is IERC20 {
    function burnFrom(address account, uint256 value) external;
}

/// @title RedemptionManager
/// @notice Burns SUN and pays the user from an ETH reserve.
/// @dev The user must approve this contract before redeeming.
contract RedemptionManager is ReentrancyGuard {
    ISUNBurnable public immutable sunToken;
    address public owner;
    uint256 public weiPerToken;

    event Redeemed(address indexed user, uint256 sunAmount, uint256 ethAmount);
    event RateUpdated(uint256 oldRate, uint256 newRate);
    event Funded(address indexed from, uint256 amount);
    event Withdrawn(address indexed to, uint256 amount);

    error NotOwner();
    error InvalidAddress();
    error InvalidAmount();
    error RateNotSet();
    error InsufficientContractBalance();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address tokenAddress, uint256 initialRate) {
        if (tokenAddress == address(0)) revert InvalidAddress();
        sunToken = ISUNBurnable(tokenAddress);
        owner = msg.sender;
        weiPerToken = initialRate;
    }

    function setRate(uint256 newRate) external onlyOwner {
        uint256 oldRate = weiPerToken;
        weiPerToken = newRate;
        emit RateUpdated(oldRate, newRate);
    }

    function fund() external payable {
        emit Funded(msg.sender, msg.value);
    }

    function redeem(uint256 sunAmount) external nonReentrant {
        if (sunAmount == 0) revert InvalidAmount();
        if (weiPerToken == 0) revert RateNotSet();

        uint256 ethAmount = (sunAmount * weiPerToken) / 1e18;
        if (ethAmount == 0) revert InvalidAmount();
        if (address(this).balance < ethAmount) {
            revert InsufficientContractBalance();
        }

        // burnFrom checks the user's allowance and reduces totalSupply.
        sunToken.burnFrom(msg.sender, sunAmount);

        (bool ok,) = payable(msg.sender).call{value: ethAmount}("");
        if (!ok) revert TransferFailed();

        emit Redeemed(msg.sender, sunAmount, ethAmount);
    }

    function withdraw(uint256 amount) external onlyOwner nonReentrant {
        if (amount == 0 || amount > address(this).balance) {
            revert InsufficientContractBalance();
        }
        (bool ok,) = payable(owner).call{value: amount}("");
        if (!ok) revert TransferFailed();
        emit Withdrawn(owner, amount);
    }

    receive() external payable {
        emit Funded(msg.sender, msg.value);
    }
}
