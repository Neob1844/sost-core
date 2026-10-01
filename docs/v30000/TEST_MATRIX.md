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

## V30000 PRODUCTION RELEASE — additional verification (2026-10-01)
| # | Criterion | Kind | Result |
|---|---|---|---|
| 16 | Admin consensus gate (S14) — admin-authorised passes, non-admin rejected, fail-closed, non-asset not gated | consensus unit (devnet+mainnet libs) | **8/8 PASS** (test_admin_gate) |
| 17 | Activation boundary 29999 -> 30000 -> 30001 on the MAINNET build (activation=30000) | consensus | **11/11 PASS** (test_native_assets_activation vs build-v30000-prod) |
| 18 | Web public-access gate + 4-state notice | puppeteer | **8/8 PASS** (earlier) + copy updated to the 4-state wording |
| 19 | Server-side admin auth (nginx bcrypt, rate-limit, deny-by-default) | config prepared | READY (operator sets credentials; not deployed) |
| 20 | Clean MAINNET build node/miner/cli + SHA256 | build | **OK** (v0.4.0 MAINNET; SHA256SUMS.txt) |
| 21 | SACS V2 regression | prior-validated | resource_v2 500/501/550 PASS + GATE A/B/C (earlier this session); heavy sacs_p* node harness NOT re-run this turn |

## Honest gaps for the FINAL build
- The RC binaries use the **all-zero ADMIN_AUTHORITY_PKH placeholder** (fail-closed). The
  FINAL mainnet binaries must bake the operator's real admin address pkh — this changes
  the hashes; SHA256SUMS must be regenerated. (The admin pubkey/address is public; the
  private key is never needed by the build.)
- Live-node reorg (two competing chains) not scripted; reorg-safety proven at index level.
- Full sacs_p* node harness not re-run this turn (prior-validated).

## FINAL BUILD re-run (2026-10-01, baked admin sost1ad01a...a2, build-v30000-final / build-v30000-devadmin)
| Test | Result |
|---|---|
| Full consensus/unit suite (9 suites) vs final MAINNET lib | **9/9 PASS** |
| Activation boundary 29999→30000→30001 (mainnet lib) | **11/11 PASS** |
| Admin protocol gate S14 — LIVE node: admin create OK + non-admin create REJECTED (`-25 consensus: S14`) + not in index | **PASS** (e2e_gate_live) |
| LIVE TWO-CHAIN REORG — converge_d8 converges; reject_d9 rejected (depth 9 > REORG_LIMIT 8), restart-stable | **PASS** (sacs_p2_reorg) |
| SACS V2 heavy resource harness depth 200 — converged + UTXO root A==B + restart-stable + RSS 16 MB bounded | **PASS** (sacs_v2_resource_final) |
| RESTART — asset index rebuilt identically (issued 3000/burned 500/circ 2500) under gate | **PASS** (e2e_restart_final) |
| MEMPOOL — admin asset tx accepted to mempool+mined; non-admin rejected at sendrawtransaction | **PASS** (within e2e_gate_live) |
| Web admin auth (nginx bcrypt) LIVE | **PASS** deny-side (401 no-creds / 401 wrong / 301 http→https / 429 rate-limit / 200 public); owner verifies successful login |
| Sanitizers (ASAN/UBSAN) on new pure logic | **CLEAN** |

FINAL COMMIT f0537f3893aaca29653a98819aa68bdf07be8dd9
NODE  a1dde8086b821945e2d91a820b3294c519a66078dcb1767f3bb7af828fb0c411
MINER eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951
CLI   c8ae00b9a6745f7c84cc8791b9994d32052a07d1fed12aa82c4e283fba2f691b
PEERS READY: NO (operator confirmation/upgrade of the 2 external peers required — PEER_COORDINATION.md)

## RC_FINAL certification (2026-10-01, node 78fefb67, SEC2 included)
- **SEC2 full battery** (final node): malformed-crash (`getblockhash["str"]`/`[null]`) → clean error, ALIVE · deep-nesting (7-level) → ALIVE RSS bounded · 5000-param resource → cap-256, ALIVE · **fuzz 300 malformed → ALIVE, RSS flat 9.1 MB** · post-attack getblockcount OK · 0 crash markers → **SEC2_NODE_SURVIVES: PASS**
- **ASAN/UBSAN** (sanitizer node build): SEC2 battery + 120 malformed calls → **0 sanitizer reports, node ALIVE = CLEAN**
- **Joint regression ctest: 119/119 PASS, 0 failed** (incl. convergencex-v11/SBPOW, transcript-v2, escrow, gold-vault, popc-single-model, dynamic-rewards, profile-magic — covers V16 / SACS / SBPOW / core consensus)
- **Asset/modality/gate suite: 9/9 PASS** vs final lib
- **Live on final build:** gate-live (admin OK + non-admin `-25 S14`), auction (atomic swap), draw (entropy+settlement), restart (index rebuild) — all PASS
- **SACS V2:** two-chain reorg (reject depth 9 > limit 8) + resource depth-200 (converged, UTXO A==B, RSS 16 MB) — PASS
