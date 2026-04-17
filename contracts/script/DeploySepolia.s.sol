// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../SOSTEscrow.sol";
import "../test/MockERC20.sol";

contract DeploySepolia is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        vm.startBroadcast(deployerKey);

        // Deploy mock tokens for testnet
        MockERC20 mockXAUT = new MockERC20("Mock Tether Gold", "mXAUT", 6);
        MockERC20 mockPAXG = new MockERC20("Mock Paxos Gold", "mPAXG", 18);

        // Deploy escrow with mock token addresses
        SOSTEscrow escrow = new SOSTEscrow(address(mockXAUT), address(mockPAXG));

        vm.stopBroadcast();

        console.log("Mock XAUT deployed at:", address(mockXAUT));
        console.log("Mock PAXG deployed at:", address(mockPAXG));
        console.log("SOSTEscrow deployed at:", address(escrow));
        console.log("");
        console.log("Next steps:");
        console.log("1. Verify: forge verify-contract", address(escrow), "SOSTEscrow --chain sepolia");
        console.log("2. Mint test tokens: cast send", address(mockXAUT), "'mint(address,uint256)' YOUR_ADDRESS 1000000 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $SEPOLIA_RPC_URL");
    }
}
