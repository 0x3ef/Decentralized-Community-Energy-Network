// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {CommunityRegistry} from "./CommunityRegistry.sol";

interface IApprovedSettlement {
    function communityId() external view returns (bytes32);
    function allocationRoot(bytes32 batch)
        external
        view
        returns (bytes32 root, uint256 allocatedWh, uint256 priceWeiPerKwh, uint64 start, uint64 end);
}

/// @notice Native ETH liabilities, SUN escrow and atomic approved allocation delivery.
/// @dev No operator sweep, ETH pull from EOAs, fiat rate, or payment on retirement.
contract NativeSettlementVault is ReentrancyGuard {
    using SafeERC20 for IERC20;
    enum State {
        NONE,
        RESERVED,
        SETTLED,
        CANCELLED
    }

    struct Allocation {
        bytes32 batch;
        address producer;
        address consumer;
        uint256 wh;
        uint256 cost;
        uint64 reservedAt;
        State state;
        bytes32 consumptionKey;
        bytes32 consumerNode;
    }
    CommunityRegistry public immutable registry;
    IApprovedSettlement public immutable settlement;
    IERC20 public immutable sun;
    bytes32 public immutable communityId;
    mapping(address => uint256) public available;
    mapping(address => uint256) public reserved;
    mapping(address => uint256) public earnings;
    mapping(address => uint256) public sunAvailable;
    mapping(address => uint256) public sunReserved;
    mapping(address => uint256) public priceLimit;
    mapping(bytes32 => Allocation) public allocations;
    mapping(bytes32 => uint256) public allocatedEnergy;
    mapping(bytes32 => uint256) public consumptionUsed;
    mapping(bytes32 => uint256) public consumptionCap;
    mapping(bytes32 => mapping(address => uint256)) public deliveredEnergy;
    mapping(bytes32 => mapping(bytes32 => uint256)) public deliveredEnergyByNode;
    mapping(bytes32 => mapping(bytes32 => uint256)) public retirementCap;
    uint256 public totalLiabilities;
    uint256 public sunLiabilities;
    event Deposited(address indexed member, uint256 amount, uint256 maxPriceWeiPerKwh);
    event Withdrawn(address indexed member, address indexed recipient, uint256 amount, bool producerEarnings);
    event SunEscrowed(address indexed producer, uint256 amount);
    event AllocationReserved(
        bytes32 indexed id,
        bytes32 indexed batch,
        address indexed consumer,
        address producer,
        uint256 energyWh,
        uint256 weiAmount
    );
    event AllocationSettled(
        bytes32 indexed id,
        bytes32 indexed batch,
        address producer,
        address consumer,
        uint256 energyWh,
        uint256 weiAmount
    );
    event AllocationCancelled(bytes32 indexed id);

    constructor(CommunityRegistry registry_, IApprovedSettlement settlement_, IERC20 sun_) {
        require(
            address(registry_) != address(0) && address(settlement_) != address(0) && address(sun_) != address(0),
            "invalid deployment"
        );
        registry = registry_;
        settlement = settlement_;
        sun = sun_;
        communityId = settlement_.communityId();
    }
    modifier activeMember() {
        require(registry.isMember(communityId, msg.sender), "active member required");
        _;
    }

    function deposit(uint256 maxPriceWeiPerKwh) external payable activeMember {
        require(msg.value > 0 && maxPriceWeiPerKwh > 0, "invalid deposit");
        available[msg.sender] += msg.value;
        priceLimit[msg.sender] = maxPriceWeiPerKwh;
        totalLiabilities += msg.value;
        emit Deposited(msg.sender, msg.value, maxPriceWeiPerKwh);
    }

    function depositSUN(uint256 amount) external activeMember nonReentrant {
        require(amount > 0, "zero escrow");
        sunAvailable[msg.sender] += amount;
        sunLiabilities += amount;
        sun.safeTransferFrom(msg.sender, address(this), amount);
        emit SunEscrowed(msg.sender, amount);
    }

    function withdraw(uint256 amount, address payable recipient) external nonReentrant {
        require(
            amount > 0 && recipient != address(0) && amount <= available[msg.sender], "funds reserved or unavailable"
        );
        available[msg.sender] -= amount;
        totalLiabilities -= amount;
        _pay(recipient, amount);
        emit Withdrawn(msg.sender, recipient, amount, false);
    }

    function withdrawEarnings(uint256 amount, address payable recipient) external nonReentrant {
        require(amount > 0 && recipient != address(0) && amount <= earnings[msg.sender], "earnings unavailable");
        earnings[msg.sender] -= amount;
        totalLiabilities -= amount;
        _pay(recipient, amount);
        emit Withdrawn(msg.sender, recipient, amount, true);
    }

    function withdrawSUN(uint256 amount) external nonReentrant {
        require(amount > 0 && amount <= sunAvailable[msg.sender], "SUN reserved or unavailable");
        sunAvailable[msg.sender] -= amount;
        sunLiabilities -= amount;
        sun.safeTransfer(msg.sender, amount);
    }

    function _pay(address payable recipient, uint256 amount) private {
        (bool ok,) = recipient.call{value: amount}("");
        require(ok, "ETH withdrawal failed");
    }

    function leaf(
        bytes32 batch,
        bytes32 id,
        address producer,
        address consumer,
        bytes32 consumerNode,
        uint256 wh,
        uint256 consumerWhCap,
        uint256 price
    ) public pure returns (bytes32) {
        return keccak256(
            bytes.concat(
                keccak256(abi.encode(uint8(2), batch, id, producer, consumer, consumerNode, wh, consumerWhCap, price))
            )
        );
    }

    function reserve(
        bytes32 batch,
        bytes32 id,
        address producer,
        address consumer,
        bytes32 consumerNode,
        uint256 wh,
        uint256 consumerWhCap,
        bytes32[] calldata proof
    ) external nonReentrant {
        require(
            registry.hasRole(registry.SETTLEMENT_ROLE(), msg.sender) && registry.isActive(communityId),
            "settlement authority required"
        );
        require(
            registry.isMember(communityId, producer) && registry.isMember(communityId, consumer)
                && producer != consumer,
            "invalid participants"
        );
        require(registry.nodes(communityId, consumerNode) == consumer, "unapproved consumer node");
        require(
            id != 0 && allocations[id].state == State.NONE && wh > 0 && consumerWhCap >= wh,
            "duplicate or invalid allocation"
        );
        (bytes32 root, uint256 cap, uint256 price, uint64 start, uint64 end) = settlement.allocationRoot(batch);
        require(
            MerkleProof.verify(
                proof, root, leaf(batch, id, producer, consumer, consumerNode, wh, consumerWhCap, price)
            ),
            "invalid allocation proof"
        );
        uint256 cost = Math.mulDiv(wh, price, 1000, Math.Rounding.Ceil);
        require(
            price > 0 && price <= priceLimit[consumer] && available[consumer] >= cost,
            "underfunded or price not authorized"
        );
        require(
            sunAvailable[producer] >= wh * 1e15 && allocatedEnergy[batch] + wh <= cap,
            "SUN or allocated energy unavailable"
        );
        bytes32 key = keccak256(abi.encode(communityId, consumerNode, start, end));
        require(
            (consumptionCap[key] == 0 || consumptionCap[key] == consumerWhCap)
                && consumptionUsed[key] + wh <= consumerWhCap,
            "consumer allocation exceeded"
        );
        consumptionCap[key] = consumerWhCap;
        retirementCap[batch][consumerNode] = consumerWhCap;
        consumptionUsed[key] += wh;
        allocatedEnergy[batch] += wh;
        available[consumer] -= cost;
        reserved[consumer] += cost;
        sunAvailable[producer] -= wh * 1e15;
        sunReserved[producer] += wh * 1e15;
        allocations[id] =
            Allocation(batch, producer, consumer, wh, cost, uint64(block.timestamp), State.RESERVED, key, consumerNode);
        emit AllocationReserved(id, batch, consumer, producer, wh, cost);
    }

    function execute(bytes32 id) external nonReentrant {
        Allocation storage a = allocations[id];
        require(a.state == State.RESERVED && registry.isActive(communityId), "not executable");
        require(
            registry.isMember(communityId, a.consumer) && registry.isMember(communityId, a.producer),
            "membership suspended"
        );
        settlement.allocationRoot(a.batch); // Still-finalized, active settlement.
        a.state = State.SETTLED;
        reserved[a.consumer] -= a.cost;
        earnings[a.producer] += a.cost;
        sunReserved[a.producer] -= a.wh * 1e15;
        sunLiabilities -= a.wh * 1e15;
        deliveredEnergy[a.batch][a.consumer] += a.wh;
        deliveredEnergyByNode[a.batch][a.consumerNode] += a.wh;
        sun.safeTransfer(a.consumer, a.wh * 1e15);
        emit AllocationSettled(id, a.batch, a.producer, a.consumer, a.wh, a.cost);
    }

    function cancel(bytes32 id) external nonReentrant {
        Allocation storage a = allocations[id];
        require(msg.sender == a.consumer && a.state == State.RESERVED, "not consumer reservation");
        require(
            !registry.isActive(communityId) || block.timestamp >= a.reservedAt + 7 days, "reservation still binding"
        );
        a.state = State.CANCELLED;
        reserved[a.consumer] -= a.cost;
        available[a.consumer] += a.cost;
        sunReserved[a.producer] -= a.wh * 1e15;
        sunAvailable[a.producer] += a.wh * 1e15;
        allocatedEnergy[a.batch] -= a.wh;
        consumptionUsed[a.consumptionKey] -= a.wh;
        emit AllocationCancelled(id);
    }
}
