// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../SOSTEscrow.sol";
import "../test/MockERC20.sol";

contract DeploySepolia is Script {
    function run() external {
        require(block.chainid == 11155111, "Not Sepolia -- aborting to prevent misdeployment");

        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        console.log("=== SEPOLIA TESTNET DEPLOYMENT ===");
        console.log("Chain ID: 11155111 (Sepolia)");
        console.log("");

        vm.startBroadcast(deployerKey);

        // Deploy mock tokens for testnet
        MockERC20 mockXAUT = new MockERC20("Mock Tether Gold", "mXAUT", 6);
        MockERC20 mockPAXG = new MockERC20("Mock Paxos Gold", "mPAXG", 18);

        // Deploy escrow with mock token addresses
        SOSTEscrow escrow = new SOSTEscrow(address(mockXAUT), address(mockPAXG));

        vm.stopBroadcast();

        console.log("Deployment complete.");
        console.log("  Mock XAUT: ", address(mockXAUT));
        console.log("  Mock PAXG: ", address(mockPAXG));
        console.log("  SOSTEscrow:", address(escrow));
        console.log("");
        console.log("Next steps:");
        console.log("  1. Verify contracts on Etherscan (Sepolia)");
        console.log("  2. Mint test tokens via cast send");
        console.log("  3. Test deposit/withdraw flow end-to-end");
    }
}
