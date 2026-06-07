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
| signaling channel | **DECISION PENDING** | see below — NOT the header version field |

## ✅ Signaling channel — DECIDED: coinbase approval marker (2026-06-07)
The initial sketch used a **block-header `version` bit**. That is **invalid**: SbPoW pins
`header.version` to exactly **1** (pre-7100) or **2** (post-7100) and rejects anything else
(`VERSION_MISMATCH`, `include/sost/sbpow.h`). `proposals.h`'s BIP9-style "bits 8-28 of version"
is a placeholder and is **not consensus-wired** for the same reason. So the per-block G4 approval
signal needs a different, deterministic channel. Candidates:

1. **Coinbase approval marker (recommended)** — each block's coinbase carries a recognized
   0-value marker output (a tag) when its miner approves the pending vault-spend proposal. The
   validator counts, over the previous 67 blocks, how many coinbases carry the marker. Pros:
   per-block (matches "61 of 67"), deterministic from chain state, no header/SbPoW change.
   Cost: the CB5/CB6 coinbase-shape validation must allow the extra recognized marker output
   **only when G4 is active** (gated; pre-activation replay stays bit-identical).
2. **Approval-marker transaction** — a dedicated tx-type a miner includes to approve; a block
   "approves" if it contains a valid marker for the active proposal. Pros: doesn't touch the
   coinbase. Cost: a new tx-type + "which proposal is active" definition.
3. **Defer per-block signaling** — instead, require the vault-spend tx to reference a proposal
   that has been on-chain ≥67 blocks with developer non-veto (silence=accept), dropping the
   miner-percentage and relying on G5's veto. Simplest, but drops the "90% miner" property.

**Recommendation:** option 1 (coinbase marker), gated at `GV_G4_ACTIVATION_HEIGHT`. The pure
tally below is channel-agnostic, so this decision only affects how `miner_yes` is sourced.

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
