# V15 PoPC — P5 Soak & Replay Report

Status: **deterministic soak + replay-equivalence: DONE (in CI).** Live multi-node
testnet soak across the gate heights: **operational step, run on the testnet by the
operator** (checklist below). No coordinated flip until this report's live section
is signed off.

## What P5 proves and how

P5 does **not** add features. It demonstrates that the staged PoPC/DTD activation
behaves exactly as designed, deterministically, and that mainnet replay is
byte-identical while the final gates stay deferred/false.

### Constants under test (params.h)
- `V15_HEIGHT` — PoPC automation + Gold Vault governance go live. Mainnet **20000**, testnet **300**.
- `DTD_POPC_GRACE_BLOCKS = 1000` — ~7 days.
- `DTD_POPC_ELIGIBILITY_HEIGHT = V15_HEIGHT + DTD_POPC_GRACE_BLOCKS` — DTD starts *requiring* PoPC. Mainnet **21000**, testnet **1300**.
- `DTD_POPC_GATE_CONSENSUS_ACTIVE = false` — even past eligibility, the lottery does **not** require PoPC until this flag is flipped in a future coordinated release.

### Deterministic soak — `test-popc-v15-soak` (24/24 on mainnet AND testnet builds)
Pure, reproducible simulation of the full staged flow:
- **PoPC live at V15_HEIGHT**; DTD-PoPC eligibility only bites at `DTD_POPC_ELIGIBILITY_HEIGHT`
  **and** only when the flag is on (`lottery::popc_eligibility_enforced` is now a pure,
  testable gate used by the real call site in `lottery.cpp`).
- **Grace window** `V15_HEIGHT → eligibility` lets a miner create + activate a contract
  (active inside the window and still active at the eligibility height; the first audit
  falls at activation+1440 > the 1000-block window, so an early activator is safe).
- **Register-only / unactivated owners do NOT count** → excluded once the flag is on.
- **Reorg around the gates**: an activated chain vs a not-activated chain yield different
  eligibility, recomputed purely (no stale state).
- **Mainnet replay byte-identical**: with the shipped flag (`false`), a chain *with* PoPC
  carriers excludes nobody — identical to a chain with no PoPC. On the mainnet build PoPC
  automation is also deferred (`popc_v15_active_at(20000/21000) == false`).

### Supporting coverage already in CI (full ctest 75/75, both builds)
- `test-popc-v15` (P1), `test-popc-v15-set` (P2, Register=Pending), `test-popc-v15-carrier` (P3),
  `test-popc-v15-eligibility` (P4a hook), `test-popc-v15-lifecycle` (P4b auto-slash/settle),
  `test-popc-v15-authz` (P4c owner authorization; Slash/Settle not carriable),
  `test-v14-fork-gates` (static_assert pins V15_HEIGHT, the grace window and the eligibility
  height, and that the flag ships false).

## Live testnet soak — operator checklist (NOT yet done)

**Full step-by-step operator package: `docs/V15_POPC_TESTNET_SOAK_GUIDE.md`** (build flags, node/miner
startup, the `popc15-carrier` payload generator + `sost-cli send --popc-carrier`, and go/no-go criteria).

Run on a testnet built with `-DSOST_TESTNET_FORKS=ON` (V15_HEIGHT=300, eligibility=1300),
ideally ≥2 nodes to confirm cross-node agreement:

1. Sync past **block 300**: confirm PoPC carriers are accepted and Gold Vault governance is live.
2. In **[300, 1300)**: post a Register carrier, then an owner-signed Activate; confirm the
   commitment shows Active and the owner is eligible.
3. Post an **unauthorized** Renew/Suspend (wrong key) and a **register-only** owner; confirm
   neither counts (no active commitment).
4. Cross **block 1300** with the flag still false: confirm the lottery does **not** drop
   anyone (eligibility unchanged).
5. Force a **reorg** spanning 300 and 1300; confirm every node recomputes the identical
   active set with no stale state.
6. **Replay** the full mainnet chain with this binary: confirm byte-identical tip/state hash
   to the pre-V15 binary (gates deferred ⇒ no divergence).
7. Record block heights, node IDs and the resulting state hashes here and sign off.

Only after 1–7 pass on the live testnet should `DTD_POPC_GATE_CONSENSUS_ACTIVE` be
considered for a flip — under a fresh, announced fork height, in its own coordinated
release. Until then mainnet is unchanged.
