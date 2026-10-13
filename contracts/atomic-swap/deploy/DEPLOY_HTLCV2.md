# Deploy AtomicSwapHTLCv2 — owner action (gas)

The v2 HTLC (weird-ERC20-safe: USDT no-return, PAXG fee-on-transfer balance-delta + slippage) is LAB
VERIFIED (14 tests; full suite 71/71) but **NOT deployed**. Deploying spends gas and is an explicit owner
action. v1 was never deployed either (corrected 2026-10-12: no EVM HTLC contract is deployed on any network; all addresses are null).

## Facts
- contract: `contracts/atomic-swap/src/AtomicSwapHTLCv2.sol`, solc 0.8.24, optimizer runs 200
- constructor: none (no owner/admin/pause/drain)
- creation bytecode keccak256: `0xbe82b2ed28271272808f25f639d66d0b308911af41fe43d50617a5d5d004deeb`
- creation gas: ~1,234,479
- ABI: `deploy/AtomicSwapHTLCv2.abi.json` · bytecode: `deploy/AtomicSwapHTLCv2.bytecode.txt`

## Cost (owner)
- **Sepolia (recommended first):** ~free with a faucet.
- **Ethereum mainnet:** 1.234M gas × gas price → ≈ **0.015 ETH @ 12 gwei**, ≈ **0.03 ETH @ 25 gwei**.
  These figures use the pre-Glamsterdam schedule. On Sepolia (EIP-8037) the same contract used **9,742,661** gas;
  if Ethereum Mainnet adopts EIP-8037 the cost is ~8x higher. Re-measure with the mainnet node before any decision.

## Deploy

> **Gas warning.** Never `forge script --broadcast` without `--skip-simulation`: forge would take the gas
> limit from its local EVM (pre-Glamsterdam pricing) and, on chains with EIP-8037 state-creation pricing
> (Sepolia since 2026-10-06), the deployment runs out of gas and the fee is lost. First run a dry-run gas
> plan against the target node (`python3 ops/sostbridge/evm_gas.py --rpc "$RPC" --from <deployer> --plan plan.json`)
> and see `docs/bridge/EVM_GAS_ESTIMATION.md`. Ethereum Mainnet deployment is not authorised by this document.
```
cd contracts/atomic-swap && forge install foundry-rs/forge-std --no-git   # if lib/ absent
export PRIVATE_KEY=0x<deployer key>          # owner-held; never in repo/CI
export RPC=<https rpc for the target network>
forge script script/DeployHTLCv2.s.sol --rpc-url "$RPC" --broadcast --skip-simulation \
  --verify --etherscan-api-key "$ETHERSCAN_API_KEY"   # --verify optional
```
Then paste the printed address into `deploy/htlc-v2-config.json` (`addresses.<network>`) and redeploy the web;
the DEX will then enable USDT/PAXG/XAUT against the active network.

## Verify (if not auto-verified)
```
forge verify-contract <ADDR> src/AtomicSwapHTLCv2.sol:AtomicSwapHTLCv2 \
  --chain <mainnet|sepolia> --watch --compiler-version 0.8.24
```

## Rollback
No on-chain rollback needed (no owner, no state migration): if a deployment is unwanted, simply do not
reference its address in `htlc-v2-config.json` — the UI treats a null address as DISABLED. v1 remains the
only referenced contract until v2's address is filled in.

## ACTION REQUIRES OWNER AUTHORIZATION
DEPLOY AtomicSwapHTLCv2 · network: Sepolia (free) and/or Ethereum mainnet · max cost ≈ 0.03 ETH mainnet /
~free Sepolia · you must provide the deployer PRIVATE_KEY + RPC and run the forge script (or approve it).

## Keyless deploy (recommended — the key never leaves your wallet)
Do NOT give anyone your PRIVATE_KEY. Two safe options:
- **A) You run forge locally.** `export PRIVATE_KEY=...` on YOUR machine only, then run the forge script
  above against your RPC. The key stays on your machine.
- **B) Wallet-signed unsigned tx.** Generate an unsigned creation tx and sign it in your own wallet:
  ```
  node contracts/atomic-swap/deploy/make_unsigned_tx.js <chainId> <nonce> <maxFeeGwei> > unsigned-tx.json
  # chainId 11155111 = Sepolia, 1 = Ethereum mainnet; nonce = your deployer account's next nonce
  ```
  Review `unsigned-tx.json` (to:null, data=bytecode, gas 1,400,000), sign it in your wallet / hardware
  device, and broadcast. The contract has no constructor args, so the deployed code == the audited bytecode
  (keccak `0xbe82b2ed…004deeb`). This assistant never asks for or handles your private key.
