# V30000 Tokenization + DEX — test matrix (devnet activation 42)

All results reproduced from the committed tests/E2E scripts on branch
`feat/v30000-native-assets`. "E2E" = real devnet node + miner + CLI
(build→sign→broadcast→mempool→block→apply→query). "consensus" = the real
validation and/or block-connect path (ValidateTransactionConsensus /
UtxoSet::ConnectBlock). Nothing is a mock.

| # | Criterion | Kind | Result |
|---|---|---|---|
| 1 | NATIVE ASSETS validator (conservation / supply / cap / authority / overflow / separation / duplicate-genesis) | consensus unit | **18/18 PASS** (test_native_assets_consensus) |
| 2 | Asset serialization round-trips | unit | **PASS** (test_native_assets_serial) |
| 3 | Asset index apply + **REORG undo** (reverse-order, byte-for-byte restore) | unit | **PASS** (test_native_assets_index) |
| 4 | TOKENIZE — create / issue / transfer / burn | E2E | **PASS** (GOLD 1,000,000; SILVER issue +500k within cap; burn 200k supply-accounted; transfer 700k/300k) |
| 5 | DRAW — 4 real entries + block-hash entropy + verifiable winner + settlement | E2E | **PASS** (winner_index deterministic & recomputable; prize→winner, losers 0) |
| 6 | DRAW selection library (determinism / range / entropy-sensitivity / domain-sep / uniformity / canonical order) | unit | **8/8 PASS** (test_draw_selection) |
| 7 | AUCTION — atomic asset↔SOST swap (single tx) | E2E | **PASS** (seller asset 500→0, buyer 0→500; buyer SOST 10→7.00; one txid) |
| 8 | PROJECT FUNDING — HTLC crowdfund (goal-met claim / goal-unmet refund / R21 / R22 / R24) | consensus + block-path | **8/8 PASS** (test_project_funding) |
| 9 | ACTIVATION @30000 — pre-fork rejection (R2/R11), post-fork acceptance, exact boundary | consensus | **11/11 PASS** (test_native_assets_activation) |
| 10 | ADVERSARIAL rejects | consensus | covered by #1 (18/18) |
| 11 | MEMPOOL acceptance (broadcast→mempool→block) | E2E | **PASS** (exercised by every E2E) |
| 12 | DEX orderbook / offer validation (timeouts, margin, hashlock, issuer-freeze) | unit | **PASS** (test_atomic_swap_orderbook) |
| 13 | DEX settlement — HTLC atomic swap | consensus | **PASS** (live since block 16000; test_htlc_block_path_v14_5) |
| 14 | NODE RESTART — asset index rebuilt from chain replay | E2E | **PASS** — see RESTART below |
| 15 | Public-access GATE + regulatory notice (real block, dev bypass, truthful copy, 4 modalities) | DOM/puppeteer | **8/8 PASS** (tokenization-gate.js) |

## RESTART (e2e_restart.sh)
**PASS.** Created CAPPED asset (mint 2000) + issue +1000 + burn 500 -> issued 3000 / burned 500 / circulating 2500, balance 2500 at height 64. Node killed by PID and relaunched on the same chain file: height, asset balance and supply index all rebuilt **identically** from chain replay (derived state, no separate asset DB).

## Known gaps (honest)
- **Live-node reorg** (two competing chains triggering a real DisconnectBlock on
  a running node) is NOT scripted; reorg-safety is proven at the index level
  (#3) and the node wiring mirrors the already-proven node-participation
  apply/undo at all six Connect/DisconnectBlock sites.
- All results are **devnet (activation 42)**. Mainnet activates at 30000 and is
  not yet crossed; nothing is claimed as mainnet-live.

## Confirmations
- 4 MODALITIES OPERATIONAL ON-CHAIN: **YES** (Tokenize, Auction, Draw, Project Funding)
- NO MOCKS / NO PLACEHOLDERS: **YES**
- ACTIVATION GATED AT #30000: **YES**
- PUBLIC ACCESS GATED (real barrier) + DEVELOPER ACCESS: **YES**
- REGULATORY NOTICES REFLECT REAL STATE (not "LIVE AT PROTOCOL LEVEL"): **YES**
- DEPLOYED TO PRODUCTION: **NO** (branch only, by design)
