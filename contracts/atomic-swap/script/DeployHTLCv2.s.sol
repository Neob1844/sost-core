// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Script.sol";
import "../src/AtomicSwapHTLCv2.sol";

// Deploys AtomicSwapHTLCv2 (no constructor args, no owner/admin). Broadcasting
// requires PRIVATE_KEY in the environment and an --rpc-url; that spends gas and
// is an explicit OWNER action (never run from CI or this repo's sandbox).
//   forge script script/DeployHTLCv2.s.sol --rpc-url $RPC --broadcast --verify
contract DeployHTLCv2 is Script {
    function run() external returns (address addr) {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        vm.startBroadcast(pk);
        AtomicSwapHTLCv2 h = new AtomicSwapHTLCv2();
        vm.stopBroadcast();
        addr = address(h);
        console2.log("AtomicSwapHTLCv2 deployed at", addr);
    }
}
