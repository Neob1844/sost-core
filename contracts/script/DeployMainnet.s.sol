// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../SOSTEscrow.sol";

contract DeployMainnet is Script {
    // Real mainnet token addresses
    address constant XAUT = 0x68749665FF8D2d112Fa859AA293F07A622782F38;
    address constant PAXG = 0x45804880De22913dAFE09f4980848ECE6EcbAf78;

    function run() external {
        require(block.chainid == 1, "Not mainnet -- aborting to prevent misdeployment");

        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        console.log("=== ETHEREUM MAINNET DEPLOYMENT ===");
        console.log("Chain ID: 1 (Mainnet)");
        console.log("XAUT:", XAUT);
        console.log("PAXG:", PAXG);
        console.log("THIS IS REAL MONEY. Press Ctrl+C to abort.");
        console.log("");

        vm.startBroadcast(deployerKey);
        SOSTEscrow escrow = new SOSTEscrow(XAUT, PAXG);
        vm.stopBroadcast();

        console.log("Deployment complete.");
        console.log("  SOSTEscrow:", address(escrow));
        console.log("");
        console.log("Post-deploy checklist:");
        console.log("  1. Verify source on Etherscan with constructor args");
        console.log("  2. Confirm no proxy/admin/selfdestruct in deployed bytecode");
        console.log("  3. Test small deposit before announcing publicly");
        console.log("  4. Publish contract address on sostcore.com");
    }
}
