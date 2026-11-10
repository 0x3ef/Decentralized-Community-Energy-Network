// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {SUNToken} from "../src/SUNToken.sol";

contract Deploy is Script {
    function run() external returns (SUNToken token) {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        address admin = vm.envAddress("SUN_ADMIN_ADDRESS");
        address minter = vm.envAddress("SUN_MINTER_ADDRESS");

        vm.startBroadcast(deployerPrivateKey);

        token = new SUNToken(admin, minter);

        vm.stopBroadcast();

        console2.log("SUNToken deployed at:", address(token));
        console2.log("Admin:", admin);
        console2.log("Minter:", minter);
    }
}