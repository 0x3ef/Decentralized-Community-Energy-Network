// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @notice Retire SUN against an operator-approved, hashed allocation record.
/// User must call retire and approve this contract; operators cannot burn alone.
contract EnergyCompensation is AccessControl, ReentrancyGuard {
    bytes32 public constant APPROVER_ROLE = keccak256("APPROVER_ROLE");
    struct Authorization { address consumer; uint256 amount; bytes32 evidence; bool retired; }
    ERC20Burnable public immutable sunToken;
    bytes32 public immutable communityId;
    mapping(bytes32 => Authorization) public authorizations;
    event RetirementAuthorized(bytes32 indexed retirementId, address indexed consumer, uint256 amount, bytes32 evidence);
    event CreditRetired(bytes32 indexed retirementId, address indexed consumer, bytes32 indexed communityId, uint256 amount, bytes32 evidence);
    constructor(address sun, bytes32 community, address admin) {
        require(sun != address(0) && community != bytes32(0) && admin != address(0), "invalid configuration");
        sunToken = ERC20Burnable(sun); communityId = community;
        _grantRole(DEFAULT_ADMIN_ROLE, admin); _grantRole(APPROVER_ROLE, admin);
    }
    function authorize(bytes32 id, address consumer, uint256 amount, bytes32 evidence) external onlyRole(APPROVER_ROLE) {
        require(id != bytes32(0) && consumer != address(0) && amount > 0 && evidence != bytes32(0), "invalid authorization");
        require(authorizations[id].consumer == address(0), "duplicate retirement");
        authorizations[id] = Authorization(consumer, amount, evidence, false);
        emit RetirementAuthorized(id, consumer, amount, evidence);
    }
    function retire(bytes32 id) external nonReentrant {
        Authorization storage item = authorizations[id];
        require(item.consumer == msg.sender && !item.retired, "unauthorized or retired");
        item.retired = true;
        sunToken.burnFrom(msg.sender, item.amount);
        emit CreditRetired(id, msg.sender, communityId, item.amount, item.evidence);
    }
}
