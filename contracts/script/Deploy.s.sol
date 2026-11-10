// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Script, console2} from "forge-std/Script.sol";
import {SUNToken} from "../src/SUNToken.sol";
import {MockUSD} from "../src/MockUSD.sol";
import {EnergyMarketplace} from "../src/EnergyMarketplace.sol";
import {EnergyCompensation} from "../src/EnergyCompensation.sol";

contract Deploy is Script {
    function run() external {
        require(block.chainid == 31337 || block.chainid == 1337, "local development only");
        uint256 key = vm.envUint("BACKEND_PRIVATE_KEY");
        address authority = vm.addr(key);
        bytes32 community = vm.envBytes32("COMMUNITY_ID");
        vm.startBroadcast(key);
        SUNToken sun = new SUNToken(authority, authority);
        MockUSD payment = new MockUSD(authority);
        EnergyMarketplace market = new EnergyMarketplace(address(sun), address(payment), community, authority);
        EnergyCompensation compensation = new EnergyCompensation(address(sun), community, authority);
        vm.stopBroadcast();
        console2.log("SUN", address(sun));
        console2.log("USDx (simulated)", address(payment));
        console2.log("Marketplace", address(market));
        console2.log("Compensation", address(compensation));
    }
}
