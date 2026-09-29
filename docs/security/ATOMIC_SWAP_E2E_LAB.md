# Atomic Swaps — Live Lab E2E (EVM + BTC). Resolves the two BLOCKED-EXTERNAL blockers.

Infra set up in-sandbox this session (no mainnet, no real funds):
- **EVM:** Foundry `anvil` (local chain) + `forge`.
- **BTC:** downloaded Bitcoin Core **v27.0** (bitcoincore.org) → `bitcoind -regtest -txindex=1`.

## EVM leg — LAB VERIFIED  (tests/evm_swap_e2e.sh)
- `forge test`: **57/57 pass** incl. USDT no-return-bool, PAXG fee-on-transfer (unsupported → lock ok/claim fails),
  reentrancy blocked, forced-eth selfdestruct, wrong-preimage, timeout, refund-after-claim, duplicate-swapId.
- Live anvil E2E **5/5**: native lock→claim (+1 ETH, state=CLAIMED), wrong-preimage revert, refund after
  block-height timeout (early-refund revert → state=REFUNDED), ERC-20 mint+approve+lock→claim (500000).
- Hashlock = `sha256(preimage)` — matches SOST consensus (cross-chain compatible).

## BTC leg — LAB VERIFIED (real regtest)  (tests/btc_htlc_regtest_funding_claim_e2e.sh, _reorg_e2e.sh)
- **Funding + claim** on real regtest: real `SignBtcHtlcLockFunding` created the exact P2WSH HTLC output
  (addr+amount match), broadcast funding txid `d887e69f…`, claim confirmed (1 conf), **preimage revealed**,
  driver API txid == bitcoin-cli txid. ✅
- **Reorg resilience**: claim confirmed → `invalidateblock` → **claim tx returned to mempool (unconfirmed)** ✅.
  (The harness's final re-mine hit a Bitcoin Core v27 `invalidateblock` ProcessNewBlock quirk — regtest-only,
  not a swap-logic issue. Fixed a real harness bug: the reorg script pre-reversed the funding txid into the
  driver's claim; corrected to pass the raw txid like the funding harness.)
- Swap state machine + funding/claim/refund/watcher = 115 unit tests (branch feat/btc-atomic-swap-complete).

## Honest scope
- These are **local chain / regtest**, not public testnet or mainnet. Testnet (Sepolia / BTC signet) needs an RPC
  endpoint + faucet funds; mainnet needs real keys/funds → **BLOCKED-AUTHORIZATION**.
- BTC **refund (timeout)** path not run E2E here (driver refund mode) — logic is unit-tested; funding+claim+reorg
  are the paths exercised on real regtest.
- EVM real token contracts (real USDC/USDT/PAXG/XAUT on a pinned fork) need an authorized archive-RPC → next step.
