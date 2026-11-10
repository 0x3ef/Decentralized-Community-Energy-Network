// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {EnumerableSet} from "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

/// @notice Community-scoped SUN escrow with atomic simulated USDx payment.
/// @dev Each deployment serves one community. Generic ERC20 transfers do not
/// enforce community provenance; compensation additionally requires an attestation.
contract EnergyMarketplace is ReentrancyGuard, AccessControl {
    using SafeERC20 for IERC20;
    using EnumerableSet for EnumerableSet.UintSet;
    EnumerableSet.UintSet private activeOrders;
    uint256 public constant MAX_ACTIVE_ORDERS = 128;
    struct Order {
        uint256 id; address maker; uint256 amount; uint256 pricePerToken;
        uint256 remaining; bool active; uint256 createdAt; uint256 expiresAt;
    }
    IERC20 public immutable sunToken;
    IERC20 public immutable paymentToken;
    uint256 public immutable sunUnit;
    bytes32 public immutable communityId;
    uint256 public nextOrderId;
    mapping(address => bool) public members;
    mapping(uint256 => Order) public orders;
    event MembershipUpdated(address indexed member, bool authorized);
    event OrderPlaced(uint256 indexed orderId, address indexed maker, uint256 amount, uint256 pricePerToken, uint256 expiresAt);
    event OrderFilled(uint256 indexed orderId, address indexed buyer, address indexed seller, uint256 amount, uint256 totalPaid);
    event OrderCancelled(uint256 indexed orderId);
    constructor(address sun, address payment, bytes32 community, address admin) {
        require(sun != address(0) && payment != address(0) && sun != payment && admin != address(0), "invalid address");
        require(community != bytes32(0), "invalid community");
        sunToken = IERC20(sun); paymentToken = IERC20(payment);
        uint8 precision = IERC20Metadata(sun).decimals();
        require(precision <= 36, "unsupported decimals");
        sunUnit = 10 ** precision; communityId = community;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }
    function setMember(address member, bool authorized) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(member != address(0), "zero member");
        members[member] = authorized; emit MembershipUpdated(member, authorized);
    }
    /// @param pricePerToken USDx base units per whole SUN; no ETH conversion.
    function placeSellOrder(uint256 amount, uint256 pricePerToken, uint256 expiresAt) external nonReentrant returns (uint256 id) {
        require(members[msg.sender], "unauthorized member");
        require(amount > 0 && pricePerToken > 0 && expiresAt > block.timestamp, "invalid order");
        require(activeOrders.length() < MAX_ACTIVE_ORDERS, "community order capacity reached");
        id = nextOrderId++;
        activeOrders.add(id);
        orders[id] = Order(id, msg.sender, amount, pricePerToken, amount, true, block.timestamp, expiresAt);
        sunToken.safeTransferFrom(msg.sender, address(this), amount);
        emit OrderPlaced(id, msg.sender, amount, pricePerToken, expiresAt);
    }
    function cancelOrder(uint256 id) external nonReentrant {
        Order storage order = orders[id];
        require(order.maker == msg.sender, "not maker");
        _cancel(order);
    }
    function expireOrder(uint256 id) external nonReentrant {
        Order storage order = orders[id];
        require(block.timestamp >= order.expiresAt, "not expired");
        _cancel(order);
    }
    function _cancel(Order storage order) private {
        require(order.active, "inactive");
        order.active = false;
        activeOrders.remove(order.id);
        uint256 refund = order.remaining; order.remaining = 0;
        sunToken.safeTransfer(order.maker, refund);
        emit OrderCancelled(order.id);
    }
    function quote(uint256 id, uint256 amount) public view returns (uint256) {
        // Round up so fractional fills never receive unpaid SUN dust.
        return Math.mulDiv(amount, orders[id].pricePerToken, sunUnit, Math.Rounding.Ceil);
    }
    function fillOrder(uint256 id, uint256 amount) external nonReentrant {
        _fillOrder(id, amount);
    }
    /// @notice Match the lowest-price eligible SELL order, then earliest order ID.
    /// @dev The bounded active book prevents an unbounded historical-order scan.
    function bestOrder(address buyer) public view returns (uint256 id, bool found) {
        uint256 bestPrice = type(uint256).max;
        for (uint256 i; i < activeOrders.length(); ++i) {
            uint256 candidate = activeOrders.at(i);
            Order storage item = orders[candidate];
            if (item.maker == buyer || !members[item.maker] || block.timestamp >= item.expiresAt) continue;
            if (!found || item.pricePerToken < bestPrice || (item.pricePerToken == bestPrice && candidate < id)) {
                id = candidate; bestPrice = item.pricePerToken; found = true;
            }
        }
    }
    function fillBestOrder(uint256 amount, uint256 maxPricePerToken) external nonReentrant {
        (uint256 id, bool found) = bestOrder(msg.sender);
        require(found && orders[id].pricePerToken <= maxPricePerToken, "no acceptable order");
        _fillOrder(id, amount);
    }
    function activeOrderIds() external view returns (uint256[] memory) { return activeOrders.values(); }
    function _fillOrder(uint256 id, uint256 amount) private {
        Order storage order = orders[id];
        require(members[msg.sender] && members[order.maker], "unauthorized member");
        require(order.active && block.timestamp < order.expiresAt, "inactive or expired");
        require(msg.sender != order.maker && amount > 0 && amount <= order.remaining, "invalid fill");
        uint256 cost = quote(id, amount);
        order.remaining -= amount;
        if (order.remaining == 0) { order.active = false; activeOrders.remove(id); }
        paymentToken.safeTransferFrom(msg.sender, order.maker, cost);
        sunToken.safeTransfer(msg.sender, amount);
        emit OrderFilled(id, msg.sender, order.maker, amount, cost);
    }
    function getOrder(uint256 id) external view returns (Order memory) { return orders[id]; }
    function isActive(uint256 id) external view returns (bool) { return orders[id].active && block.timestamp < orders[id].expiresAt; }
}
