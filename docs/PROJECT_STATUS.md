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
- **Branch:** `feat/fork-store-hardening` (B/C/F/H) · latest security commit on branch.
- **Done + executed:** B monetary invariants (I1–I6, 30,245 heights); C subsidy/emission bit-exact model (0 divergences vs C++ and vs live chain); F CPU-DoS partial (network allocations size-guarded, offset reads guarded); H orchestrator `tests/security-gauntlet.sh` runs → PARTIAL-PASS.
- **Pending:** A full fuzzing (mempool/NODE_BIND/heartbeat/Jackpot/reorg/persistence); C rest (cASERT bit-exact, DTD, Jackpot, NODE_BIND, heartbeat, UTXO); D mass adversarial lab (100s peers, eclipse, partition/heal); E chaos/persistence; F full cheap→expensive audit + peer diversity; G reproducible build path-independence + SBOM + signing; TSan. **Must include the new persistence + P2P changes in the adversarial runs.**

## SEC — RPC crash hardening (found by fuzzing)  ·  FIXED on branch (pre-existing on main)
- **Branch:** `fix/rpc-crash-hardening` (off `main`, NOT merged) · `docs/security/RPC_CRASH_HARDENING.md`
- **Two pre-existing remote-DoS defects, one unauthenticated RPC call each (reproduce on unmodified main):** (1) `getblockhash` non-numeric height -> uncaught `std::stoll` -> `std::terminate` -> node aborts; (2) `getblock` nested-array param -> `json_get_params` infinite loop -> **OOM (~6 GB/call -> kernel OOM-kill)**. Fixed: dispatch try/catch -> JSON-RPC error; tokenizer advances past a delimiter at the cursor + 256-param cap. Verified: 300-call fuzz responsive (RSS flat 9MB), valid RPC unaffected, mainnet compiles, reorg/payout E2E PASS.
- **Next action:** owner authorization to land before block 29,900 (stability priority). Kept separate from the P2P branch and sec1.

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
