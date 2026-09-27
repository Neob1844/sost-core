# SACS — MAX_REORG_DEPTH = 500: behaviour, boundary, and test status

Reference height at analysis: **28263** (→#29900: 1637 · →#30000: 1737). No consensus/mainnet change.

## Real-node literal-depth test (499/500/501/550/600): BLOCKED-ENVIRONMENT
Measured devnet mining rate in this sandbox: **~151 s/block** (SbPoW is memory-hard AND the local
mainnet miner runs `--threads 10`, saturating CPU; I cannot touch that miner). Mining 600 blocks per
partition ≈ **~25 hours**, ×2 partitions — infeasible in a bounded run. So the literal-depth real-node
experiment is **BLOCKED-ENVIRONMENT** (rate measured, not assumed). Reproducible alternative below.

## Definitive behaviour, traced through the actual enforcement code
Chain selection is already **most-cumulative-valid-work** (not longest): `src/sost-node.cpp:231,5793`,
`include/sost/sostcompact.h::compare_chainwork`. A peer cannot impose a chain by announcing work/height.

`MAX_REORG_DEPTH = 500` (`src/sost-node.cpp:446`) is enforced at THREE points:
1. **:7199** block-accept — rejects any incoming block whose `height < local_tip − 500`.
2. **:7388** fork-storage cutoff.
3. **:7479** reorg — aborts if adopting the fork requires `disconnect_count > 500` of the node's own blocks.

**Boundary (two partitions that share ancestor #A, each mines `d` blocks, then reconnect):**
the less-work side must disconnect its own `d` blocks and connect the winner's `d` blocks starting at #A+1.
- `d ≤ 500`: disconnect count = d ≤ 500 (:7479 passes, check is `> 500`) AND the winner's block #A+1 is
  within 500 of the loser's tip #A+d (:7199 passes) → **CONVERGES to the most-work chain.**
- `d ≥ 501`: disconnect count = d > 500 → **:7479 aborts the reorg**; also #A+1 is now >500 below the
  loser's tip → **:7199 rejects the winner's fork blocks** → **PERSISTENT SPLIT, despite valid more work.**

Therefore, precisely: **499 → converge · 500 → converge (boundary) · 501 → split · 550 → split · 600 → split.**
This confirms the mission's hypothesis: MAX_REORG_DEPTH=500 converts a >500-block partition into a
**persistent split even when a valid chain has more work**. It also does NOT stop a <500-block 51% reorg.

- **UTXO/balances:** within the limit, `try_reorganize()` replays via the FULL validation path + BlockUndo,
  so the UTXO set stays consistent through the reorg. Beyond the limit no reorg is attempted, so each side
  keeps its own internally-consistent (but divergent) UTXO set.
- **Restart:** the limit is relative to the loaded tip; a restarted node still refuses a >500 reorg → the
  split persists across restarts. Nothing self-heals it without operator action or a rule change.

## Reproducible alternative (ready to run; the tractable equivalent)
The rejection is a single comparison against the constant, so the boundary behaviour is identical at any
scale. Compile a **devnet-only** node with `MAX_REORG_DEPTH` scaled (e.g. 8) under `#if defined(SOST_DEVNET_FORKS)`
(mainnet path byte-identical), then run two real `sost-node` processes from a common ancestor, mine fork
depths 6/7/8/9/10 (≡ 499/500/501/550/600 vs the limit), reconnect, and observe converge (≤limit) vs split
(>limit) + UTXO integrity + restart. At ~151 s/block this is ~20–40 min/partition — runnable in background,
just slow under the mainnet miner's CPU load. Node recompile + orchestration is the executable next step.

## Consequence for Delivery B (future fork, devnet only)
Options to study on devnet: keep hard 500; pure most-work (no hard cap) like Bitcoin; **500 as an operational
ALARM (SACS deep-reorg alert) rather than a hard accept-rule** — separating operational policy from consensus.
NOT to be changed in V16 / mainnet without a coordinated future fork.
