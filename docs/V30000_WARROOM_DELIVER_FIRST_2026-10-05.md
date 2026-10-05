# V30000 WAR ROOM — DELIVER FIRST (verified, read-only, no changes made)
**2026-10-05 · chain tip #29,321 · activation #30,000**

## Two verified corrections to the prior audit (both change the plan)
1. **SEC2 is ALREADY in V30000 and deployed.** `619d5d65` (RPC hardening) + `fc903ec6` (RC_FINAL CERTIFIED, SEC2) are ancestors of tag `v30000`; published release node = `78fefb67` = the running VPS node. SEC2 = +18 lines in `src/sost-node.cpp` (RPC dispatch try/catch over `std::stoll` + `json_get_params` nested/delimiter cap) — RPC-only, NON-CONSENSUS ("valid calls unaffected, no consensus"). The prior audit compared against the obsolete standalone SEC2 node `5b50a448` (v16.3.0 base) and wrongly concluded "not deployed."
2. **SACS is in V30000 too — and SACS V2 is a CONSENSUS change at #30,000.** `SACS_V2_ACTIVATION_HEIGHT = 30000` (mainnet). From #30,000, deep fork blocks beyond MAX_REORG_DEPTH=500 that are post-activation are STORED (not hard-rejected) so `try_reorganize` evaluates them by strict valid cumulative work; pre-activation (V16) history keeps the hard 500-cap. The devnet `--sacs-recovery-mode` (Delivery B) is correctly hard-disabled on TESTNET/MAINNET. SACS observability RPC (`getsacsstatus/getsacsevents`, `DEEP_REORG_ALERT`) also present. Certified in RC_FINAL ("SEC2 full battery + ASAN + ctest 119/119 + reorg 9/0 under attack"). The prior audit audited the SACS research branch + main, missing the v30000-tag SACS V2.

## Block budget (live #29,321, observed 608 s/block)
to #29,750 = 429 blk ~72.5h · #29,800 = 479 blk ~81h · #29,900 = 579 blk ~98h · #30,000 = 679 blk ~115h · #29,900→#30,000 = 100 blk ~17h.

## GO / NO-GO
| Change | Consensus | Binary | Net-compat risk | Security benefit | Complete | Tests | Soak | SAFE FOR V30000 |
|---|---|---|---|---|---|---|---|---|
| SEC2 fold into V30000 | NO | — | — | CRITICAL | **ALREADY DONE** | PASS (RC_FINAL) | PASS | **GO — already in; no action** |
| Build a NEW SEC2 binary | NO | YES | MED | none (already in) | — | — | — | **NO-GO** (unnecessary; breaks freeze) |
| SACS V2 consensus @30000 | **YES** | already in | LOW (uniform, all run 78fefb67) | MED | ALREADY IN release | PASS (RC_FINAL reorg 9/0) | PASS | **OWNER DECISION (A keep / B rebuild-remove)** |
| SACS observability | NO | already in | — | LOW | ALREADY IN | PASS | PASS | **GO — already in** |
| Remove SACS V2 (rebuild) | YES | YES | **HIGH** | — | NO | NOT RUN | NOT RUN | **NO-GO unless owner orders** |
| peer-store / ADDR / GETADDR | NO | YES | MED/HIGH | HIGH | NO | NOT RUN | NOT RUN | **NO-GO now → D1 post-#30,000** |
| independent nodes / multi-seed / fallback / mirrors | NO | NO | LOW | MED | owner infra | n/a | n/a | **GO (non-binary; needs owner hosting/domains)** |
| release signing (sign existing SHA256SUMS) | NO | NO | LOW | MED | preparable | n/a | n/a | **GO to prepare (offline key = owner step)** |

## Internal freeze
- **BINARY: already frozen (de-facto now).** 78fefb67 (SEC2 + SACS V2 + native assets) is the certified release. **Recommendation: ZERO binary change before #30,000** — the strongest safely-producible V30000 is the one already deployed. Any rebuild in the ~4-day window is pure fork risk.
- **Non-binary (decentralization infra / web / docs): continue to ~#29,800, then verify/monitor only.**

## Final release gate (evidence)
CONSENSUS TESTS: PASS (ctest 119/119) · SEC2 ADVERSARIAL: PASS (RC_FINAL battery) · REORG: PASS (9/0) · SYNC genesis→tip: PASS (25m06s, 66/66 hashes) · MINER→NODE / RPC / EXPLORER: live · REPRODUCIBLE BUILD: path-dependent PARTIAL · HASHES: VERIFIED (deployed==published) · WEBSITE HASHES: MATCH · NO STALE RELEASE LINKS: PASS (swept; 6517916b = genesis block hash, not a binary).

## The one decision needed from the owner
SACS V2 is a consensus change ALREADY in the frozen V30000, activating at #30,000 — which contradicts the written NO-GO "no SACS consensus in this fork". `SACS_V2_ACTIVATION_HEIGHT` is a compile-time constexpr → it cannot be disabled at runtime; removing it REQUIRES a rebuild.
- **(A) KEEP** the certified release (recommended): conservative, tested, deployed, stable; only affects >500-deep post-activation reorgs (extremely rare); adds no split risk (all mainnet nodes run 78fefb67; uniform activation). Lower risk.
- **(B) REBUILD V30000 without SACS V2**: honors the strict NO-GO but creates a new, less-tested binary + new hashes + coordinated redeploy in a 4-day window. Higher risk — the exact fork-destabilization the war-room forbids.
No binary action taken; awaiting the owner's A/B.
