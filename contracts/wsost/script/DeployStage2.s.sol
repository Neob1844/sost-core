// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Stage 2 TESTNET deployment (Sepolia only). Deploys NEW contracts; it never reuses the
// superseded PoPC SOSTEscrow. The XAUT/PAXG addresses must be TEST tokens (Sepolia "Mock XAUT"
// 0x38Ca…44D0 / "Mock PAXG" 0x754A…dec7: public mint, no value). The script refuses chain 1.
//
// env: PRIVATE_KEY (disposable testnet deployer), OBSERVERS (3 comma-separated), GUARDIANS
// (5 comma-separated), BRIDGE_VAULT_HASH (keccak256 of the devnet/testnet Bridge Vault address),
// TEST_XAUT, TEST_PAXG
//
// GAS WARNING (docs/bridge/EVM_GAS_ESTIMATION.md): `forge script --broadcast` WITHOUT --skip-simulation
// sets every gas limit from forge's LOCAL EVM (pre-Glamsterdam pricing) x 1.3. On Sepolia since
// Glamsterdam (EIP-8037) contract creation costs ~5-7x more (WSOST 2.24M local vs 15.10M real) and those
// transactions run out of gas, burning the fee. Always either
//   (a) pass --skip-simulation (forge then asks the target node's eth_estimateGas, x1.3), or
//   (b) use tests/bridge/sepolia_stage2_deploy.py (node estimates, margin, EIP-7825 cap, --dry-run),
// and first run a dry-run gas plan: python3 ops/sostbridge/evm_gas.py --rpc ... --from ... --plan ...
import {Script, console2} from "forge-std/Script.sol";
import {WSOST} from "../src/WSOST.sol";
import {GoldReserveVault} from "../src/GoldReserveVault.sol";
import {QuarantineVault} from "../src/QuarantineVault.sol";
import {AtomicSwapHTLCv2} from "atomic-swap/AtomicSwapHTLCv2.sol";

contract DeployStage2 is Script {
    function run() external {
        require(block.chainid != 1, "STAGE2: NEVER ETHEREUM MAINNET");
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(pk);
        address[] memory obs = vm.envAddress("OBSERVERS", ",");
        address[] memory gl = vm.envAddress("GUARDIANS", ",");
        require(obs.length == 3 && gl.length == 5, "need 3 observers and 5 guardians");
        address[5] memory g; for (uint256 i = 0; i < 5; i++) g[i] = gl[i];
        address xaut = vm.envAddress("TEST_XAUT");
        address paxg = vm.envAddress("TEST_PAXG");
        address[] memory reg = new address[](2); reg[0] = xaut; reg[1] = paxg;

        vm.startBroadcast(pk);
        WSOST w = new WSOST(vm.envBytes32("BRIDGE_VAULT_HASH"), WSOST.Config({admin: deployer, observers: obs, threshold: 2,
            minConfirmations: 30, exposureCap: 100_000e8, dailyMintCap: 50_000e8}));
        QuarantineVault q = new QuarantineVault(g, reg, 1 hours);
        GoldReserveVault r = new GoldReserveVault(g, address(q), xaut, paxg, 1 hours, 10 minutes);
        AtomicSwapHTLCv2 h = new AtomicSwapHTLCv2();
        vm.stopBroadcast();

        console2.log("chainId", block.chainid);
        console2.log("WSOST", address(w));
        console2.log("QuarantineVault", address(q));
        console2.log("GoldReserveVault", address(r));
        console2.log("AtomicSwapHTLCv2", address(h));
    }
}
