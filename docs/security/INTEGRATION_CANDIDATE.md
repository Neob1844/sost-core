# Integrated candidate — sec2 + P2P + IBD gate (Phase 3)

Branch `integration/sec2-p2p-ibd`. **Dev branch only — NOT merged to main, NOT released, NOT
deployed.** Changes BOTH node AND miner (unlike sec2, which is node-only). Frozen source
branches (`feat/fork-store-hardening`, `release/v16.3.0-sec1-rpc`, `feat/p2p-headers-first-ibd`,
`fix/ibd-mining-gate`) were NOT modified.

## Integration log (commits, conflicts, resolutions)
- **Base:** `release/v16.3.0-sec1-rpc` @ `19186bab` (sec2 = sec1 fork-store hardening + beacon UB
  fix + RPC dispatch/param-parser fixes).
- **Merge `feat/p2p-headers-first-ibd` @ `796b0094`** (P2P convergence: ancestor walk-back, orphan
  cascade on fork storage, dedup carve-outs, progress=chain-advanced; sync-perf batched save):
  **1 conflict** in `src/sost-node.cpp` orphan-store path — sec1's per-origin quota
  (`fork_store_admit`) vs P2P's duplicate-orphan guard (`g_block_index.count(bid)`). **Resolution:
  combined both** (dedup guard first → then quota-gated insertion; both defenses are complementary
  and both retained). Incidental website files from the older merge-base were reset to sec2 state.
- **Merge `fix/ibd-mining-gate` @ `7ad9aba0`** (checkpoint-height mining gate + miner honors it):
  **0 conflicts** (getblocktemplate/miner untouched by the other branches).

## Binary hashes (mainnet, reproducible build)
```
sost-node   c0c21da0e5358f42ca67ca797a9396651c96195f4d400133443b8aafce833833   (integrated)
sost-miner  5a29cad4d97b4ac1be4a546abd493131865a68f688b217648d2197025de7a2eb   (== ibd-gate miner)
sost-cli    489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07   (== v16.3.0, unchanged)
```

## Validation ON THE INTEGRATED BINARY (not reused from individual branches)
- **ctest 119/119** (consensus/unit) — no regression from the 3-way integration.
- **cASERT bit-exact:** 14,896 vectors, 0 divergences (recompiled against the integrated `casert.cpp`).
- **Consensus/DTD/Jackpot E2E:** `run_v15_devnet_reorg` 9/0, `run_v16_devnet_jackpot_v2` 9/0.
- **P2P convergence:** shallow fork + genesis-deep fork both auto-converge; converges to an honest
  higher-work peer **under a 120-peer adversarial attack** (RSS 11 MB, RPC 14/14, orphans max 3,
  0 crashes, 0 unfair bans on the honest peer).
- **IBD mining gate 5/5:** liar@999999 → mines (DoS defeated); 5 colluding liars → mines;
  genesis+honest → recovers+mines; genesis+only-liars → refused, no genesis chain; solo → mines.
- **RPC DoS (sec2) intact:** `getblockhash ["str"]` → error (no abort); `getblock [[[[1]]]]` →
  error, RSS flat 9 MB (no OOM).

## Honest threat bounding (eclipse / Sybil)
- The IBD gate is **attacker-independent** (gates on our OWN checkpoint-validated tip height, never
  on peer-announced height) → immune to the announced-height Sybil DoS. Verified (T1/T2).
- It does **NOT** claim to solve eclipse in general: a node whose peer set is FULLY controlled by an
  attacker still cannot obtain honest blocks — the gate then correctly REFUSES to mine on the stale
  tip (T4), which is the safe failure, but the node is still eclipsed. General eclipse resistance
  (anchor/persistent peers, address-bucket diversity, outbound-only preference) is **network
  hardening for Phase 5**, out of scope here. This candidate does NOT add it.
- Remaining possible: a partially-synced node ABOVE the checkpoint but below the real tip will mine
  soon-orphaned blocks (non-catastrophic; deep-reorg protection). A tighter floor (most-recent
  checkpoint / minimum-chainwork) would narrow this — documented option.

## NOT included (deliberately)
- **headers-first / parallel download:** excluded pending the ConvergenceX header-verifiability
  audit (must prove exactly what a header attests before trusting header-announced work). Kept OUT
  of the candidate until that audit passes.
- No new trust anchors, mandatory checkpoints, or remote/snapshot dependencies were added.

## Residual / BLOCKED
- **Real mainnet genesis-sync + benchmark on this binary:** needs the mainnet chain in the lab
  (connect a lab node to mainnet seeds — a read-only sync, ~18 min). Devnet full-sync is
  byte-identical; the sync-perf fix is included unchanged, so the ~11× improvement is expected to
  carry over. NOT yet run on this exact binary → marked TESTING, not PASS.
- **66 historic exceptions:** code-assessed (bounded ≤5038, exact-hash-anchored, no PoW bypass — see
  `HISTORIC_EXCEPTIONS_ASSESSMENT.md`); a block-by-block independent re-validation needs the real
  historical block data → documented as a lab follow-up.
- TSan on the integrated binary: the code union equals branches already TSan-clean (0 races); a
  dedicated integrated TSan run is a recommended confirmation, not yet executed → TESTING.
