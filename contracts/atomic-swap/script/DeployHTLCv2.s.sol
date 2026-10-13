// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Script.sol";
import "../src/AtomicSwapHTLCv2.sol";

// Deploys AtomicSwapHTLCv2 (no constructor args, no owner/admin). Broadcasting
// requires PRIVATE_KEY in the environment and an --rpc-url; that spends gas and
// is an explicit OWNER action (never run from CI or this repo's sandbox).
//   forge script script/DeployHTLCv2.s.sol --rpc-url $RPC --broadcast --skip-simulation --verify
//
// GAS WARNING (docs/bridge/EVM_GAS_ESTIMATION.md): `forge script --broadcast` WITHOUT --skip-simulation
// sets every gas limit from forge's LOCAL EVM (pre-Glamsterdam pricing) x 1.3. On Sepolia since
// Glamsterdam (EIP-8037) contract creation costs ~5-7x more (WSOST 2.24M local vs 15.10M real) and those
// transactions run out of gas, burning the fee. Always either
//   (a) pass --skip-simulation (forge then asks the target node's eth_estimateGas, x1.3), or
//   (b) use tests/bridge/sepolia_stage2_deploy.py (node estimates, margin, EIP-7825 cap, --dry-run),
// and first run a dry-run gas plan: python3 ops/sostbridge/evm_gas.py --rpc ... --from ... --plan ...
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
