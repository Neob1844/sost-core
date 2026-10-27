# Deploy AtomicSwapHTLCv2 — owner action (gas)

The v2 HTLC (weird-ERC20-safe: USDT no-return, PAXG fee-on-transfer balance-delta + slippage) is LAB
VERIFIED (F-1 fixed, see below; not externally audited) but **NOT deployed**. Deploying spends gas and is an explicit owner
action. v1 was never deployed either. Correction (C713, 2026-10-27): no EVM HTLC deployment is recorded for any mainnet (read-only check: the stage-2 deployer has nonce 0 and the Sepolia
address has no code on Ethereum, Arbitrum, BNB and Base), but a Sepolia
test instance of the PRE-FIX v2 exists (see below); the canonical addresses in `htlc-v2-config.json` stay null.

> **F-1 (C713, CRITICAL) — the earlier v2 bytecode is vulnerable and must never be deployed or used.**
> Before the fix, `claimNative` did not check that the swap is a native one, so the claimer of any ERC-20
> swap (even a worthless self-made token) was paid `lockedAmount` wei out of other swaps' native ETH escrow.
> The Sepolia test instance `0x395295622fDE4702BA199e4898F85B9d85175794` (deployed 2026-10-13) runs that
> vulnerable bytecode (creation keccak `0xbe82b2ed…deeb`); treat it as deprecated and never paste it into
> `htlc-v2-config.json`. The fixed source enforces the asset kind on all four claim/refund paths and has
> adversarial, fuzz and invariant tests (`test/AtomicSwapHTLCv2Isolation.t.sol`). It is NOT externally
> audited; the creation gas below has to be re-measured for the new bytecode.

## Facts
- contract: `contracts/atomic-swap/src/AtomicSwapHTLCv2.sol`, solc 0.8.24, optimizer runs 200
- constructor: none (no owner/admin/pause/drain)
- creation bytecode keccak256: `0x63b368e607ed34bca071b3bad9162d1ac5d6d4842d6f527550442732d2bbd98e` (F-1 fixed; was `0xbe82b2ed…deeb`)
- creation gas: ~1,234,479
- ABI: `deploy/AtomicSwapHTLCv2.abi.json` · bytecode: `deploy/AtomicSwapHTLCv2.bytecode.txt`

## Cost (owner)
- **Sepolia (recommended first):** ~free with a faucet.
- **Ethereum mainnet:** 1.234M gas × gas price → ≈ **0.015 ETH @ 12 gwei**, ≈ **0.03 ETH @ 25 gwei**.

## Deploy
```
cd contracts/atomic-swap && forge install foundry-rs/forge-std --no-git   # if lib/ absent
export PRIVATE_KEY=0x<deployer key>          # owner-held; never in repo/CI
export RPC=<https rpc for the target network>
forge script script/DeployHTLCv2.s.sol --rpc-url "$RPC" --broadcast \
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
