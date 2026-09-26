# Assessment of the 66 historical height+hash exceptions (Step 6)

Two hardcoded tables in `src/sost-node.cpp` used for correct resync-from-genesis:
- **(1) cASERT exceptions — 19 blocks** (13–22 Apr 2026, early heights).
- **(2) Param-table exceptions — 47 blocks** (heights **4715–5038**, `HISTORIC_PARAM_MAX_HEIGHT=5038`).

## Findings — NO unintended trust/validation problem
1. **Strictly historical / cannot apply forward.** Max height 5038; the chain is at ~28,035 and
   the #30,000 fork is future. Neither table can match any height > 5038 → **zero forward attack
   surface** (irrelevant to the #29,900/#30,000 window).
2. **Exact height + full recomputed block-id anchored.** An exception applies only if the block's
   recomputed `block_id` equals the recorded hash (`historic_param_id_matches`). A different block
   at the same height does NOT match → normal validation rejects it. **No substitution attack.**
3. **Does NOT bypass PoW / ConvergenceX.** It only restores the miner's ORIGINAL stability params
   (scale/steps/k/margin) so the CX transcript verifies bit-identically for a block mined before a
   later param-table correction. PoW is still fully checked. It is a deterministic replay of the
   historically-correct verification params, equivalent in trust model to hard checkpoints.
4. **Fixed size, cannot grow** (hardcoded 19+47 entries).
5. **Required for correctness:** without them, a fresh genesis resync would reject those historical
   blocks (param mismatch) and fail to sync.

## Residual note
These are trust anchors comparable to the hard-checkpoint table; they add no NEW trust surface
beyond checkpoints/assumevalid, and are validated by the live chain that was built with them.
