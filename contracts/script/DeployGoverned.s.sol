// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Script, console2} from "forge-std/Script.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {CommunityRegistry} from "../src/CommunityRegistry.sol";
import {CommunitySettlement} from "../src/CommunitySettlement.sol";
import {NativeSettlementVault, IApprovedSettlement} from "../src/NativeSettlementVault.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SUNToken} from "../src/SUNToken.sol";

/// @notice Explicit local-development bootstrap. No community is auto-activated.
contract DeployGoverned is Script {
    function run() external {
        require(
            block.chainid == 31337 || block.chainid == 1337 || block.chainid == 11155111, "development deployment only"
        );
        uint256 key = vm.envUint("BACKEND_PRIVATE_KEY");
        address authority = vm.addr(key);
        bytes32 community = vm.envBytes32("COMMUNITY_ID");
        require(community != 0, "community required");
        address[] memory proposers = new address[](1);
        proposers[0] = authority;
        address[] memory executors = new address[](1);
        executors[0] = authority;
        vm.startBroadcast(key);
        TimelockController governor = new TimelockController(1 days, proposers, executors, address(0));
        CommunityRegistry registry = new CommunityRegistry(address(governor));
        SUNToken sun = new SUNToken(address(governor), address(governor));
        CommunitySettlement settlement = new CommunitySettlement(registry, sun, address(governor), 1 days, community);
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
