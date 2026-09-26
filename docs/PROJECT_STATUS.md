# SOST — master status (DONE / TESTING / BLOCKED / NOT STARTED)

**Deadline snapshot (real mainnet height read 2026-09-26): height 28035 → ~1865 blocks to #29,900 (~13 days @600s), ~1965 to #30,000 (V16 activation).**

**Autonomous execution mandate active:** advance through dev-branch work without asking per-task; NEVER publish/deploy/merge-to-main/spend/sign/touch STRATO/miner/wallet/NODE_BIND/consensus without express authorization. Branches frozen & on GitHub: sec1 `feat/fork-store-hardening` 32cabab2 · sec2 `release/v16.3.0-sec1-rpc` (node 5b50a448, miner/cli==v16.3.0) · RPC `fix/rpc-crash-hardening` · proxy-mitigation `fix/rpc-proxy-interim-mitigation` · P2P `feat/p2p-headers-first-ibd` · gauntlet `test/security-gauntlet` · atomic-swap `feat/btc-atomic-swap-complete`. Tag v16.3.0 intact.

**Gauntlet status:** C cASERT bit-exact **DONE** (14,896 vec, 0 div) · E durability **DONE** + **IBD mining-gate fix** (branch `fix/ibd-mining-gate`: node refuses getblocktemplate while a peer advertises higher height → no mining on a stale tip after genesis fallback; bootstrap unaffected) · D mass adversarial lab **DONE** (`test/security-gauntlet`: sec2 RSS-flat/0-crash/0-unfair-ban under 200 sim-peers; P2P-fix converges under 150-peer attack) · CPU-DoS/TSan(0 races)/ASan+UBSan/reproducible+SBOM/RPC+block fuzz **DONE**. **Pending:** C V16-activation-boundary note (cASERT is continuous across #30000 — no cASERT fork there; verified via 29900/30000/40000 vectors), disk-full-during-save = BLOCKED-on-env, full multi-real-node eclipse = Phase-5 (needs real operators).

**Phase 1 (sec2) = PREPARED, BLOCKED on 3 independent prod authorizations** (A proxy mitigation, B release publish, C STRATO swap) — procedures written + lab-verified, none executed.

---

# SOST — Master status tracker

Single source of truth for every authorized workstream. Priority until block #29,900:
security + fast/reliable sync + network stability. Nothing merged/published/deployed without
explicit owner authorization. No consensus, STRATO, WSL miner, wallet or NODE_BIND changes.
Snapshot maintained by the agent; update on every task step.

Mainnet snapshot: block 27,972 (2026-09-25). #29,900 ≈ 1,928 blocks away.

---

## P1 — sec1 security revision (v16.3.0-sec1)  ·  DONE, awaiting publish authorization
- **Branch:** `feat/fork-store-hardening` · **last commit:** `32cabab2`
- **Frozen node source:** `1a675744` → node `d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213`; miner `2ef9d0a7`/cli `489f4374` byte-identical to v16.3.0.
- **Tests done:** diff vs v16.3.0 = non-consensus (only sost-node.cpp + beacon.cpp base64 UB); Debug/ASan/UBSan halt_on_error=1 **115/115, 0 findings**; Release 115/115; 300s churn+fork-storm survived; CI green on 1a675744; genesis→tip sync (enc+plain) 9/9 hashes + UTXO 66,239 + emission identical; beacon base64 UB fixed (differential 200,015/0); reproducible on canonical path.
- **Residual risks:** base64 ENCODE UB in cli/miner (local-only, deferred); path-independent reproducibility (Phase G); btc-* CI excluded (need bitcoind).
- **Next action:** on owner OK → tag `v16.3.0-sec1`, add `sost-node-sec1` + `SHA256SUMS.sec1` to the existing v16.3.0 release (keep original tag/binaries). Procedure: `docs/security/V16_3_0_SEC1_INCORPORATION.md`. **HOLD for authorization.**

## P2 — Fast initial sync (chain.json batched save)  ·  SPEED + resume PASS; hardening tests pending
- **Branch:** `feat/p2p-headers-first-ibd` · **last commit:** `9d56bf1b` · node `53101a42`
- **Tests done:** bottleneck #1 confirmed in code (full chain.json rewrite per block, O(N²)); ANTES/DESPUÉS full genesis→tip **202 min → 18.2 min (~11×)**, <60 min on WSL/HDD; crash `kill -9` between saves → resumes, hashes at 6k/8k/10k/12k MATCH, 0 rejects; 115/115 tests (no regression).
- **Pending / risks:** (a) kill DURING a chain.json write (mid-write atomicity, not only between saves); (b) adversarial reorgs with batched save; (c) fresh-install test on Windows + Linux; (d) not yet combined with sec1 into one verified binary.
- **Next action:** write-interruption test + adversarial reorg test (P2 next-steps 1).

## P3 — Bitcoin-Core-style P2P (locator / headers-first)  ·  fork convergence FIXED (branch); headers-first still pending
- **Branch:** `feat/p2p-headers-first-ibd` · **fix commit:** `73b85b1b` · **audit commit:** `496c6c10` (`docs/p2p/PHASE1_AUDIT.md`, `docs/p2p/FORK_CONVERGENCE_AB.md`)
- **DONE — A/B reproduced + fixed:** empirically reproduced with two devnet nodes; the 4-layer defect (request only above tip / no ancestor; fork never assembles from out-of-order orphans; orphan/fork fragments deduped away at BOTH the BLCK layer and process_block; progress measured by BLCK-arrived not chain-advanced — so the honest higher-work peer was BANNED as "empty DONE spam"). Fixed backward-compatibly over the existing height-based GETB (serving peer unchanged): ancestor walk-back (block locator as height requests) + orphan cascade on fork storage + dedup carve-out for pending orphan/fork + progress=chain-advanced. **Result: shallow fork (2-block reorg) AND genesis-deep fork (no shared history) both converge automatically over P2P, no manual restart (~3s).** Regression: normal linear IBD + devnet reorg/payout/mempool/rollover/jackpot_v2 E2E all PASS; compiles clean in mainnet profile; no consensus rule changed.
- **Security Gauntlet (modified node) — PASS:** dedup carve-outs validation-safe (bad-PoW still rejected; reorg_connect lifts ONLY the dedup cache) + memory-safe (RSS ~10MB under all floods; caps hold); found+fixed an orphan-pool-duplication DoS (`b5178dd0`; 300 resends 200->1). Adversarial reorg/partition-heal PASS; restart mid-reorg 5/5 clean recoveries; 400-block reception fuzz survives; full-sync byte-identical (28/28 block hashes, subsidy/UTXO match); reorg/payout/mempool/rollover/jackpot_v2 E2E all PASS. See `docs/security/P2P_GAUNTLET_RESULTS.md`.
- **Next action:** fuller headers-first (download header chain first to know fork point + target, then parallel block download); ConvergenceX header-verifiability audit; peer diversity + stale-tip guard. Branch only — no merge/publish without authorization.

## P4 — Security Gauntlet  ·  PARTIAL (P2P/persistence slice DONE; rest pending)
- **P2P/persistence slice DONE (on `feat/p2p-headers-first-ibd`):** block-reception fuzz, orphan/duplicate/out-of-order adversarial, reorg + partition-heal, restart/recovery mid-reorg (5/5), fork-store memory/CPU/storage limits, dedup-exception safety, full-sync emission/UTXO/consensus equivalence — all PASS (`docs/security/P2P_GAUNTLET_RESULTS.md`).
- **sec2 combined-node Gauntlet extended:** CPU-DoS (8 workers ~141 req/s, RSS flat 11MB, no crash), **TSan 0 data races** (RPC-concurrency AND block-production write paths, incl. culprit inputs), reproducible-build PROVEN + SBOM + signing procedure (`V16_3_0_SEC2_REPRODUCIBILITY_SBOM.md`, item G). Combined branch tip `19186bab`.
- **Gauntlet still pending (full-node program, not sec2-surface):** D mass adversarial lab (100s peers, eclipse, partition/heal), C cASERT bit-exact independent model (Python sim is behavioral only), E extended chaos (random-point SIGKILL during save, disk-full, corrupted-chain recovery).
- **Branch:** `feat/fork-store-hardening` (B/C/F/H) · latest security commit on branch.
- **Done + executed:** B monetary invariants (I1–I6, 30,245 heights); C subsidy/emission bit-exact model (0 divergences vs C++ and vs live chain); F CPU-DoS partial (network allocations size-guarded, offset reads guarded); H orchestrator `tests/security-gauntlet.sh` runs → PARTIAL-PASS.
- **Pending:** A full fuzzing (mempool/NODE_BIND/heartbeat/Jackpot/reorg/persistence); C rest (cASERT bit-exact, DTD, Jackpot, NODE_BIND, heartbeat, UTXO); D mass adversarial lab (100s peers, eclipse, partition/heal); E chaos/persistence; F full cheap→expensive audit + peer diversity; G reproducible build path-independence + SBOM + signing; TSan. **Must include the new persistence + P2P changes in the adversarial runs.**

## SEC — v16.3.0 sec2: combined security update (sec1 + 2 RPC fixes)  ·  PREPARED + VERIFIED (awaiting publish auth)
- **Branch:** `release/v16.3.0-sec1-rpc` (`30fa5a2d`; sec1 base `32cabab2` + RPC fix `ebe4f790`) · docs `V16_3_0_SEC2_COMBINED.md`, `SHA256SUMS.v16.3.0-sec2`. Also standalone `fix/rpc-crash-hardening` (`eb2dd5b9`). All pushed to GitHub.
- **What/why:** two PRE-EXISTING unauthenticated remote-DoS in RPC (reproduce on original sec1/main), both reachable anonymously via the public gateway (`getblock`/`getblockhash` are no-auth reads; nginx 10r/s does not mitigate): (1) `getblockhash ["str"]` uncaught std::stoll -> node abort; (2) `getblock [[[[1]]]]` json_get_params infinite loop -> OOM (~6GB/call). sec2 = sec1 + fixes (dispatch try/catch + tokenizer delimiter-advance + 256 cap). Diff vs sec1 = RPC I/O only; miner/cli byte-identical to v16.3.0.
- **Binary (definitive, reproducible):** `sost-node-sec2 = 5b50a448f3e319ef6137da61093750bd6d286cc508ff69fe994cf3532c4fa157`; miner `2ef9d0a7…`==v16.3.0, cli `489f4374…`==v16.3.0. Reproducible ONLY with build dir named exactly `build` inside the source tree.
- **Verified:** bugs reproduced on original sec1 & gone on sec2; ctest 119/119; ASan+UBSan 0 findings; RPC+block fuzz survive (RSS flat); reorg/payout/mempool/rollover/jackpot_v2 E2E all PASS; full sync byte-identical (consensus/emission/UTXO/SbPoW/cASERT/DTD/Jackpot/NODE_BIND/#30000 intact).
- **Publication PREPARED (task 3/4/5 done):** `V16_3_0_SEC2_RELEASE_INCORPORATION.md` (add sost-node-sec2 to the v16.3.0 release, no tag move / no overwrite + downloader verify), `V16_3_0_SEC2_STRATO_DEPLOY_PLAN.md` (controlled reversible node-only swap: backup + health checks + rollback, NOT executed). **Interim mitigation** ready + lab-verified: branch `fix/rpc-proxy-interim-mitigation` (`RPC_PROXY_INTERIM_MITIGATION.md`) — public-gateway param-shape validation returns 400 on both culprit inputs; tested in front of the UNFIXED node (stays alive) without breaking the explorer; NOT applied to prod.
- **Gauntlet (sec2 surface) DONE:** RPC DoS, parser audit, resource/CPU-DoS (8 concurrent workers ~141 req/s, RSS flat 11MB, no crash), adversarial (fuzz/reorg/orphan/recovery), ASan+UBSan 0 findings, ctest 119/119, full-sync byte-identical.
- **Next action:** await explicit authorization to (a) apply the interim proxy mitigation, (b) publish sost-node-sec2, (c) VPS swap per the deploy plan. Do NOT mix with the P2P branch. Priority before block 29,900.
## LT — Long-term direction (confirmed) · after security + pending work
- **SOST is fully independent of GeaSpirit** — no shared code/infra/assets/docs/strategy.
- **Goal 1 — full decentralization:** cross-platform node installer, reproducible clean-sync from genesis, exchange/operator integration folder, recruit >=3 independent node operators, and the "24h with founder infra OFF" independence test (discovery/sync/mine/recover without STRATO). The P2P convergence + fast-sync + sec2 work already built the technical base. Hard open problem: hashrate diversity (one miner ~90%), demand-dependent, cannot be manufactured.
- **Goal 2 — secure native atomic swaps (NEXT BIG PROJECT after the above):** NOT greenfield — `feat/btc-atomic-swap-complete` is code-complete (HTLC primitives already in consensus, 22 test files, contracts, threat model 54/0). Remaining = validate against a real bitcoind-regtest + independent security audit before any BTC activation. This is the moat for exchange listings without capital.
- Gold reference stays informational (not backing/peg); MiCA angle = legal-counsel item, not settled here.

## P5 — Coin selection  ·  audited + designed (parked, NOT cancelled)
- **Branch:** `feat/wallet-coin-selection` · **last commit:** `62b34f7b` (`docs/wallet/COIN_SELECTION_AUDIT.md`)
- **Finding:** greedy oldest-first, no BnB/effective-value/waste; the 77-input tx was NOT a bug (all rewards ~3.93 → 77 needed under any algorithm); ≥4 duplicate selectors; fee = stocks per physical byte.
- **Next action (after P1–P4):** unify the 4 selectors; implement BnB + effective-value + fallback + waste; test PSBT/CLI/web; benchmark vs current. No consensus change.

## P6 — Bretton Woods gold reference  ·  formula in branch (parked, NOT cancelled)
- **Branch:** `feat/web-bretton-woods-reference` · **last commit:** `bb3b7280` (`docs/web/BRETTON_WOODS_REFERENCE.md`)
- **Done:** single-source JS `WEIGHT_MG = 31.1034768/35 = 0.8886707657142857 mg` + disclaimers.
- **Next action (after P1–P4):** rewrite sost-reference.html (history + calc + first-listing methodology), two charts, explorer card, audit hardcoded 1.14mg text. Reference only — NOT gold backing / peg / redemption right.

## P7 — Explorer drill-down + PoPC cleanup  ·  recon done (parked, NOT cancelled)
- **Branch:** `feat/explorer-drilldown-wallet-popc` (recon only; no code committed — at `2910f0d6`)
- **Findings:** getaddressinfo gives UTXOs (client-side drill-downs doable: TOTAL/MINED/RECEIVED-held/UTXOS); getaddressflows returns only totals → GROSS/DTD-lifetime/NET-OUTFLOW need a new paginated read-only `getaddresshistory` RPC. PoPC form only validates + localStorage (no real registration); Gateway flags all OFF.
- **Next action (after P1–P4):** client-side drill-downs; `getaddresshistory` RPC (paginated, cursor/addr validation, tip cache, reorg handling, anti-DoS); retire obsolete PoPC form, keep historical page; Gateway stays OFF.

---

## Cross-cutting rules
No new projects. No branch mixing / no overwriting verified changes. No consensus or activation-height
changes. No STRATO / WSL miner / wallet / NODE_BIND. No publish/deploy without authorization. Never mark
a test PASS without executing it. If #29,900 nears: ship the fully-verified security+sync work first,
keep the rest parked with residual risks documented.
