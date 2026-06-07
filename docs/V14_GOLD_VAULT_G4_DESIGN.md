# V14 Gold Vault — G4: 67-block miner signaling window

> Phase B / G4 of `docs/V14_EXECUTION_PLAN.md`. This is the **affirmative miner
> approval** layer on top of Slice 1 (G1/G2/G3a). A Gold Vault spend that passes
> Slice 1 (whitelisted destination + per-spend cap) ALSO requires **≥90% miner
> approval over a 67-block window**, with a **+10% foundation quality boost** and
> **silence=accept** for the developer/genesis veto (the veto itself is G5).
>
> Built first as a **pure, unit-tested module** (`include/sost/gv_g4.h`), gate
> **deferred on mainnet** (`INT64_MAX`) and **active on the testnet build**
> (`-DSOST_TESTNET_FORKS`, V14_HEIGHT). No block-validation wiring yet — that is
> the next sub-step, once the tally logic is locked and tested.

## Parameters
| Constant | Value | Meaning |
|---|---|---|
| `GV_G4_SIGNAL_WINDOW` | 67 | blocks in the signaling window |
| `GV_G4_THRESHOLD_PCT` | 90 | required affirmative percentage |
| approval floor | **61** | `ceil(67 × 90 / 100)` — min YES blocks |
| `GV_G4_FOUNDATION_PCT` | 10 | foundation "quality boost" weight |
| foundation weight | **7** | `ceil(67 × 10 / 100)` blocks added when the foundation signals |
| `GV_G4_SIGNAL_BIT` | 8 | block-header version bit miners set to approve (proposals.h bits 8-28) |

## Tally rule (pure)
```
effective_yes = min(window, miner_yes + (foundation_signaled ? foundation_weight : 0))
approved      = effective_yes >= approval_floor          // 61 of 67
```
- A miner approves a pending vault-spend proposal by setting `GV_G4_SIGNAL_BIT` in its
  block version during the 67-block window that follows the proposal.
- The foundation/developer "quality boost" adds 7 effective YES blocks (≈+10%) when it
  endorses — it cannot exceed the window.
- **silence = accept** applies to the developer/genesis **veto** (G5): if no veto lands in
  the grace window, the miner-approved spend stands. The veto/grace machinery is G5.

## Determinism & safety
- Pure integer arithmetic (no floats) — identical on every node/compiler.
- `gv_g4_active_at(height)` is the only gate; below it, behaviour is unchanged (the wiring,
  once added, is a no-op pre-activation → historical replay stays bit-identical).
- Mainnet ships **deferred** (`GV_G4_ACTIVATION_HEIGHT = INT64_MAX`); the final pre-fork
  commit flips it to `V14_HEIGHT` together with Slice 1 and G5, after testnet soak + replay.

## Next sub-steps (after this pure module)
1. Wire the tally into block validation: track the pending proposal + count `GV_G4_SIGNAL_BIT`
   over the window; reject a vault spend that lacks 61/67 approval.
2. G5: developer/genesis veto tx-type + 10-block grace + silence=accept + auto-disconnect @100,000.
3. Cross-validator agreement test + testnet soak across the activation height.
