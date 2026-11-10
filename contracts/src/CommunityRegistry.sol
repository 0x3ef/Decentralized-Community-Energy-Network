// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @notice Governance of physical boundaries, membership and metering authority.
/// @dev Admin is a multisig or timelock contract; proposals confer no authority.
contract CommunityRegistry is AccessControl, Pausable {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant METER_REGISTRAR_ROLE = keccak256("METER_REGISTRAR_ROLE");
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");
    bytes32 public constant SETTLEMENT_ROLE = keccak256("SETTLEMENT_ROLE");
    mapping(bytes32 => uint256) public priceWeiPerKwh;

    struct Protocol {
        address settlement;
        address vault;
        address sun;
    }
    mapping(bytes32 => Protocol) public protocols;
    event ProtocolBound(bytes32 indexed community, address settlement, address vault, address sun);

    function bindProtocol(bytes32 id, address settlement, address vault, address sun)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        require(
            communities[id].proposer != address(0) && protocols[id].vault == address(0), "unknown or bound protocol"
        );
        require(
            settlement.code.length > 0 && vault.code.length > 0 && sun.code.length > 0, "contract deployment required"
        );
        protocols[id] = Protocol(settlement, vault, sun);
        emit ProtocolBound(id, settlement, vault, sun);
    }
    event PricePolicyConfigured(bytes32 indexed community, uint256 weiPerKwh, bytes32 policy);
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    enum Status {
        DRAFT,
        PROPOSED,
        UNDER_REVIEW,
        APPROVED,
        ACTIVE,
        SUSPENDED,
        REJECTED,
        ARCHIVED
    }
    enum Membership {
        NONE,
        PENDING,
        APPROVED,
        ACTIVE,
        SUSPENDED,
        REVOKED
    }

    struct Community {
        address proposer;
        address operator;
        Status status;
        bytes32 boundary;
        bytes32 policy;
        uint32 intervalSeconds;
    }
    mapping(bytes32 => Community) public communities;
    mapping(bytes32 => mapping(address => Membership)) public memberships;
    mapping(bytes32 => mapping(bytes32 => address)) public nodes;
    mapping(bytes32 => mapping(bytes32 => bytes32)) public meters;
    event CommunityTransition(
        bytes32 indexed communityId,
        Status status,
        address indexed operator,
        bytes32 boundary,
        bytes32 policy,
        uint32 intervalSeconds
    );
    event MembershipChanged(bytes32 indexed communityId, address indexed member, Membership status);
    event NodeRegistered(bytes32 indexed communityId, bytes32 indexed nodeId, address indexed owner);
    event MeterAuthorized(bytes32 indexed communityId, bytes32 indexed nodeId, bytes32 indexed meterId, bool active);

    constructor(address governor) {
        require(governor.code.length > 0, "contract governance required");
        _grantRole(DEFAULT_ADMIN_ROLE, governor);
        _grantRole(REGISTRAR_ROLE, governor);
        _grantRole(METER_REGISTRAR_ROLE, governor);
        _grantRole(PAUSER_ROLE, governor);
    }

    function propose(bytes32 id, bytes32 boundary, bytes32 policy, uint32 intervalSeconds) external whenNotPaused {
        require(id != 0 && boundary != 0 && policy != 0 && intervalSeconds > 0, "invalid proposal");
        require(communities[id].proposer == address(0), "duplicate community");
        communities[id] = Community(msg.sender, address(0), Status.PROPOSED, boundary, policy, intervalSeconds);
        _emit(id);
    }

    function transition(bytes32 id, Status next, address operator) external onlyRole(REGISTRAR_ROLE) {
        Community storage c = communities[id];
        require(c.proposer != address(0), "unknown community");
        bool valid = (c.status == Status.PROPOSED && next == Status.UNDER_REVIEW)
            || (c.status == Status.UNDER_REVIEW && (next == Status.APPROVED || next == Status.REJECTED))
            || (c.status == Status.APPROVED && next == Status.ACTIVE)
            || (c.status == Status.ACTIVE && next == Status.SUSPENDED)
            || (c.status == Status.SUSPENDED && (next == Status.ACTIVE || next == Status.ARCHIVED))
            || (c.status == Status.REJECTED && next == Status.ARCHIVED);
        require(valid, "invalid transition");
        if (next == Status.ACTIVE) {
            require(!paused() && operator != address(0) && priceWeiPerKwh[id] > 0, "invalid activation");
            c.operator = operator;
        }
        c.status = next;
        _emit(id);
    }

    function _emit(bytes32 id) private {
        Community memory c = communities[id];
        emit CommunityTransition(id, c.status, c.operator, c.boundary, c.policy, c.intervalSeconds);
    }

    function isActive(bytes32 id) public view returns (bool) {
        return !paused() && communities[id].status == Status.ACTIVE;
    }

    function isMember(bytes32 id, address member) external view returns (bool) {
        return isActive(id) && memberships[id][member] == Membership.ACTIVE;
    }

    function applyMembership(bytes32 id) external {
        require(communities[id].proposer != address(0), "unknown community");
        require(memberships[id][msg.sender] == Membership.NONE, "already applied");
        memberships[id][msg.sender] = Membership.PENDING;
        emit MembershipChanged(id, msg.sender, Membership.PENDING);
    }

    function setMembership(bytes32 id, address member, Membership next) external onlyRole(REGISTRAR_ROLE) {
        require(member != address(0), "zero member");
        Membership previous = memberships[id][member];
        require(
            (previous == Membership.PENDING && next == Membership.APPROVED)
                || (previous == Membership.APPROVED && next == Membership.ACTIVE)
                || (previous == Membership.ACTIVE && (next == Membership.SUSPENDED || next == Membership.REVOKED))
                || (previous == Membership.SUSPENDED && (next == Membership.ACTIVE || next == Membership.REVOKED)),
            "invalid membership transition"
        );
        memberships[id][member] = next;
        emit MembershipChanged(id, member, next);
    }

    function registerNode(bytes32 id, bytes32 node, address owner) external onlyRole(METER_REGISTRAR_ROLE) {
        require(isActive(id) && memberships[id][owner] == Membership.ACTIVE, "inactive owner");
        require(node != 0 && nodes[id][node] == address(0), "duplicate node");
        nodes[id][node] = owner;
        emit NodeRegistered(id, node, owner);
    }

    function authorizeMeter(bytes32 id, bytes32 node, bytes32 meter, bool active)
        external
        onlyRole(METER_REGISTRAR_ROLE)
    {
        require(isActive(id) && nodes[id][node] != address(0) && meter != 0, "invalid meter");
        require(meters[id][meter] == 0 || meters[id][meter] == node, "meter bound elsewhere");
        meters[id][meter] = active ? node : bytes32(0);
        emit MeterAuthorized(id, node, meter, active);
    }

    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    function configurePrice(bytes32 id, uint256 price) external onlyRole(REGISTRAR_ROLE) {
        require(communities[id].status == Status.APPROVED && price > 0, "approved policy required");
        priceWeiPerKwh[id] = price;
        emit PricePolicyConfigured(id, price, communities[id].policy);
    }
}
