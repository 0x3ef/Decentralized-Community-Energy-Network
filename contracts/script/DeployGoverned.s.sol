// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Script, console2} from "forge-std/Script.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {CommunityRegistry} from "../src/CommunityRegistry.sol";
import {CommunitySettlement} from "../src/CommunitySettlement.sol";
import {NativeSettlementVault, IApprovedSettlement} from "../src/NativeSettlementVault.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SUNToken} from "../src/SUNToken.sol";

/// @notice Explicit native deployment. Review and execute the separate governance setup plan.
contract DeployGoverned is Script {
    function run() external {
        require(
            block.chainid == 31337 || block.chainid == 1337 || block.chainid == 11155111, "development deployment only"
        );
        uint256 key = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address proposer = vm.envAddress("GOVERNANCE_PROPOSER_ADDRESS");
        address executor = vm.envAddress("GOVERNANCE_EXECUTOR_ADDRESS");
        require(proposer != address(0) && executor != address(0), "explicit governance required");
        uint256 delay = vm.envOr("GOVERNANCE_DELAY", uint256(block.chainid == 11155111 ? 1 days : 0));
        uint256 challenge = vm.envOr("CHALLENGE_PERIOD", uint256(1 days));
        require(challenge <= type(uint64).max, "challenge overflow");
        require(block.chainid != 11155111 || (delay >= 1 days && challenge >= 1 days), "unsafe public delay");
        bytes32 community = vm.envBytes32("COMMUNITY_ID");
        require(community != 0, "community required");
        address[] memory proposers = new address[](1);
        proposers[0] = proposer;
        address[] memory executors = new address[](1);
        executors[0] = executor;
        vm.startBroadcast(key);
        TimelockController governor = new TimelockController(delay, proposers, executors, address(0));
        CommunityRegistry registry = new CommunityRegistry(address(governor));
        SUNToken sun = new SUNToken(address(governor), address(governor));
        CommunitySettlement settlement = new CommunitySettlement(registry, sun, address(governor), uint64(challenge), community);
        NativeSettlementVault vault =
            new NativeSettlementVault(registry, IApprovedSettlement(address(settlement)), IERC20(address(sun)));
        // Activation, oracle assignment and mint authority changes must be
        // scheduled and executed through the timelock, never the deployer EOA.
        vm.stopBroadcast();
        console2.log("Timelock", address(governor));
        console2.log("Registry", address(registry));
        console2.log("SUN", address(sun));
        console2.log("Settlement", address(settlement));
        console2.log("ETH vault", address(vault));
    }
}
