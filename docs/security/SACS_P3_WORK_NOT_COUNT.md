# SACS P3 — Chain Selection is by WORK, not Block COUNT

**Status:** PROVEN by code + P2 evidence + monitor labels. The *specific* empirical
"fewer-blocks-but-more-work chain wins" mining construction is **INCONCLUSIVE** in the
devnet regime (documented below, NOT marked PASS).

## Proof that selection is by cumulative work (not height/count)
1. **Code** (`try_reorganize`, `src/sost-node.cpp`): the reorg is gated on
   `compare_chainwork(fork_tip_work, active_tip_work) <= 0 → no reorg` (Step 4), and the
   fork-acceptance path only sets `needs_reorg` when `compare_chainwork(fork, active) > 0`.
   Height/count never enters the selection.
2. **P2 reject_d9** (executed): chain A had **more blocks (10 vs 9) AND more work** yet B
   REFUSED to adopt it — because the reorg depth exceeded the cap. This directly shows a
   higher block count does NOT force adoption.
3. **P4 monitor** (executed): every `FORK_DETECTED` event is labelled
   `fork_has_more_work` / `fork_has_less_or_equal_work`, and only a `more_work` fork ever
   produced a `REORG_STARTED`. The competing-work comparison is visible per fork block.

## The empirical construction that did NOT reproduce
Goal: build chain A with FEWER blocks but MORE cumulative work than a longer chain B,
then show B adopts A (abandoning its longer chain). Method: mine A fast (hoping cASERT
raises per-block difficulty) and B slowly with 14–28 s gaps (hoping difficulty drops).

Observed (devnet, `tests/sacs_p3_work.sh`):
| run | A (fast) | B (slow) |
|---|---|---|
| A5/B7 | 5 blk, work 11108 (avg 2221) | 7 blk, work 11704 (avg 1672) |
| A6/B8 | 6 blk, work 11460 (avg 1910) | 8 blk, work 11877 (avg 1485) |
| A6/B7 | 6 blk, work 11460 | 7 blk, work 11704 |

B's per-block work IS lower than A's (difficulty divergence exists), but never enough
for A's fewer blocks to out-total B's. Crucially, **B=7 produced identical work (11704)
at both 14 s and 28 s gaps** — devnet cASERT is essentially insensitive to solvetime in
this range (short target and/or a difficulty floor), so cumulative work ≈ block-count ×
~constant. A "more-blocks-but-less-work" chain is therefore not constructible by
timestamp manipulation in this devnet, so this particular demonstration is INCONCLUSIVE.
It is **not** marked PASS. The work-not-count property itself is established by the three
proofs above.
