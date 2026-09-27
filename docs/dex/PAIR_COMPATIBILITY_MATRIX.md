# SOST Atomic-Swap Pair Compatibility Matrix

Status of every asset advertised in Atomic Swap / SOST DEX V2. Honest per-asset; adding an
asset to a dropdown does NOT make it tradable. All pairs are SOST ↔ X (both directions) and
are **non-custodial atomic swaps that require a real counterparty with inventory** — there is
no AMM and no house liquidity, so no executable quote exists until a counterparty posts one.
Everything is **PREVIEW / TESTNET · NOT ACTIVE**; no mainnet trading is enabled.

Legend: **IMPLEMENTED** (code path exists) · **TESTED-LAB** (end-to-end lab settlement+refund
proven) · **READY-FOR-AUDIT** · **READY-FOR-MAINNET** · **BLOCKED** (with exact reason).

| Pair | Chain / kind | Decimals | Transfer behaviour | HTLC / escrow | Refund | Status | Exact blocker |
|---|---|---|---|---|---|---|---|
| **SOST↔BTC** | SOST native ↔ Bitcoin native | 8 / 8 | native | SOST `OUT_HTLC_LOCK` ↔ BIP-199 P2WSH (BIP-143 sighash) | timelock both legs | **TESTED-LAB** (regtest); BTC leg OFF on mainnet | mainnet: real bitcoind validation + operator enable + external audit |
| **SOST↔ETH** | SOST native ↔ EVM native | 8 / 18 | native | SOST HTLC ↔ `AtomicSwapHTLC.lockNative` | `refund()` after timeout | **TESTED-LAB** | mainnet: HTLC contract audit + deployment |
| **SOST↔USDC** | SOST native ↔ EVM ERC-20 | 8 / 6 | standard (returns bool) | SOST HTLC ↔ `lockERC20` (approve+transferFrom) | `refund()` | **TESTED-LAB** (mock USDC) · **caveat shown** | real-USDC fork test; Circle blacklist/pause mid-swap handling; audit |
| **SOST↔USDT** | SOST native ↔ EVM ERC-20 | 8 / 6 | **no boolean return** | current HTLC uses strict `require(ok)` → USDT reverts | n/a | **BLOCKED** | HTLC needs SafeERC20-style handling (contract change + audit) before enable |
| **SOST↔PAXG** | SOST native ↔ EVM ERC-20 | 8 / 18 | **fee-on-transfer** | fixed-amount escrow receives less than sent → funds can stick | n/a | **BLOCKED** | balance-delta (received-amount) escrow adapter + pinned-fork test with the real PAXG contract + audit |
| **SOST↔XAUT** | SOST native ↔ EVM ERC-20 | 8 / 6 | **unverified** (possible admin/transfer restrictions) | untested against real contract | n/a | **BLOCKED** | pinned-fork test of the real Tether-Gold contract (approve/transferFrom/restrictions) + adapter if required + audit. A mock-token pass is NOT sufficient |

## Notes
- **USDT / PAXG / XAUT are correctly kept disabled** with the exact outstanding requirement
  shown in the UI (not a generic "disabled"). They are NOT presented as operational.
- **XAUT ≠ PAXG.** Both are tokenized gold but have different contracts, decimals (XAUT 6 vs
  PAXG 18), networks and possible restrictions — each must be tested individually against its
  real contract; neither may inherit the other's result.
- **No fabricated quotes/liquidity/balances/executions.** A quote is shown as executable only
  when a real counterparty and inventory exist (none do yet → PREVIEW).

## What is BLOCKED-ENVIRONMENT here (not faked, not marked done)
The remaining real end-to-end work — per-pair browser E2E with real wallet extensions
(MetaMask/Xverse/etc.), the PAXG balance-delta escrow adapter, and the XAUT/USDC/PAXG
**real-contract** tests on a pinned EVM mainnet fork (anvil `--fork-url` + archive RPC) — cannot
run in this sandbox (no browser extensions; forking mainnet needs an external archive RPC;
persistent processes are killed by RLIMIT_FSIZE). Per the owner's directive this work proceeds
on a **separate branch** and must never delay or risk the V16 hard fork at block #30,000.

## Production / mainnet requirements (for any pair to leave PREVIEW)
Real counterparty liquidity · external audit of the HTLC + any ERC-20 adapter · real-contract
fork tests green · owner authorization. Until all hold, the pair stays disabled or PREVIEW.
