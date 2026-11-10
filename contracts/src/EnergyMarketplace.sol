// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title EnergyMarketplace
/// @notice Escrow-based sell orders for SUN with atomic native-token settlement.
/// @dev Buyers call fillOrder themselves. The backend must not pay on behalf of
///      a buyer unless a separate signed-authorization design is implemented.
contract EnergyMarketplace is ReentrancyGuard {
    using SafeERC20 for IERC20;

    enum OrderType { Sell, Buy }

    struct Order {
        uint256 id;
        address maker;
        OrderType orderType;
        uint256 amount;
        uint256 pricePerToken;
        uint256 remaining;
        bool active;
        uint256 createdAt;
    }

    IERC20 public immutable sunToken;
    address public owner;
    uint256 public nextOrderId;
    mapping(uint256 => Order) public orders;

    event OrderPlaced(
        uint256 indexed orderId,
        address indexed maker,
        OrderType orderType,
        uint256 amount,
        uint256 pricePerToken
    );
    event OrderFilled(
        uint256 indexed orderId,
        address indexed buyer,
        uint256 amount,
        uint256 totalPaid
    );
    event OrderCancelled(uint256 indexed orderId);

    error NotOwner();
    error NotMaker();
    error InvalidAddress();
    error InvalidAmount();
    error InvalidPrice();
    error OrderNotActive();
    error InsufficientPayment();
    error TransferFailed();
    error BuyerMustBeCaller();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address tokenAddress) {
        if (tokenAddress == address(0)) revert InvalidAddress();
        sunToken = IERC20(tokenAddress);
        owner = msg.sender;
    }

    function placeSellOrder(
        uint256 amount,
        uint256 pricePerToken
    ) external nonReentrant returns (uint256) {
        if (amount == 0) revert InvalidAmount();
        if (pricePerToken == 0) revert InvalidPrice();

        uint256 orderId = nextOrderId++;
        orders[orderId] = Order({
            id: orderId,
            maker: msg.sender,
            orderType: OrderType.Sell,
            amount: amount,
            pricePerToken: pricePerToken,
            remaining: amount,
            active: true,
            createdAt: block.timestamp
        });

        sunToken.safeTransferFrom(msg.sender, address(this), amount);
        emit OrderPlaced(
            orderId, msg.sender, OrderType.Sell, amount, pricePerToken
        );
        return orderId;
    }

    function cancelOrder(uint256 orderId) external nonReentrant {
        Order storage order = orders[orderId];
        if (order.maker != msg.sender) revert NotMaker();
        if (!order.active) revert OrderNotActive();

        order.active = false;
        uint256 refund = order.remaining;
        order.remaining = 0;
        if (refund > 0) sunToken.safeTransfer(msg.sender, refund);
        emit OrderCancelled(orderId);
    }

    /// @notice Buy part or all of an escrowed sell order.
    /// @dev pricePerToken is wei per whole SUN token (18 decimals).
    function fillOrder(
        uint256 orderId,
        uint256 fillAmount,
        address buyer
    ) external payable nonReentrant {
        if (buyer != msg.sender) revert BuyerMustBeCaller();

        Order storage order = orders[orderId];
        if (!order.active) revert OrderNotActive();
        if (fillAmount == 0 || fillAmount > order.remaining) {
            revert InvalidAmount();
        }

        uint256 totalCost = (fillAmount * order.pricePerToken) / 1e18;
        if (totalCost == 0 || msg.value < totalCost) {
            revert InsufficientPayment();
        }

        order.remaining -= fillAmount;
        if (order.remaining == 0) order.active = false;

        sunToken.safeTransfer(buyer, fillAmount);

        (bool paid,) = payable(order.maker).call{value: totalCost}("");
        if (!paid) revert TransferFailed();

        if (msg.value > totalCost) {
            (bool refunded,) = payable(msg.sender).call{
                value: msg.value - totalCost
            }("");
            if (!refunded) revert TransferFailed();
        }

        emit OrderFilled(orderId, buyer, fillAmount, totalCost);
    }

    function getOrder(uint256 orderId) external view returns (Order memory) {
        return orders[orderId];
    }

    function isActive(uint256 orderId) external view returns (bool) {
        return orders[orderId].active;
    }
}
