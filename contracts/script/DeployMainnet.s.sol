// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../SOSTEscrow.sol";

contract DeployMainnet is Script {
    // Real mainnet token addresses
    address constant XAUT = 0x68749665FF8D2d112Fa859AA293F07A622782F38;
    address constant PAXG = 0x45804880De22913dAFE09f4980848ECE6EcbAf78;

    function run() external {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        console.log("=== MAINNET DEPLOYMENT ===");
        console.log("XAUT:", XAUT);
        console.log("PAXG:", PAXG);
        console.log("THIS IS REAL MONEY. Press Ctrl+C to abort.");
        console.log("");

        vm.startBroadcast(deployerKey);
        SOSTEscrow escrow = new SOSTEscrow(XAUT, PAXG);
        vm.stopBroadcast();

        console.log("SOSTEscrow deployed at:", address(escrow));
        console.log("Verify: forge verify-contract", address(escrow), "SOSTEscrow --chain mainnet --constructor-args $(cast abi-encode 'constructor(address,address)' 0x68749665FF8D2d112Fa859AA293F07a622782F38 0x45804880De22913dAFE09f4980848ECE6EcbAf78)");
    }
}
