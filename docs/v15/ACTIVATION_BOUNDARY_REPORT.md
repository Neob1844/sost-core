# V15 activation-boundary report (P9)

**Result: PASS.** V15 activates on mainnet at height **25000** with a clean `>=` boundary and no
off-by-one. Verified by `tests/test_v15_activation_boundary.cpp` (ctest `v15-activation-boundary`),
compiled in the MAINNET profile (no `SOST_DEVNET_FORKS` / `SOST_TESTNET_FORKS`), 15/15 assertions —
evidence `artifacts/v15-final-validation/activation-boundary.log`.

## Profile selection (no DEV/testnet confusion)
`include/sost/params.h` selects `V15_HEIGHT` by preprocessor:
```
#if defined(SOST_DEVNET_FORKS)   → 18
#elif defined(SOST_TESTNET_FORKS)→ 12500
#else                            → 25000   (MAINNET)
```
The test is compiled with neither flag and asserts `V15_HEIGHT == 25000`, so a mainnet build
cannot silently inherit the DEV (18) or testnet (12500) height.

## What activates at exactly 25000 — the emission transition (T)
Gate: `height >= sost::V15_HEIGHT` (two coherent sites in `src/sost-node.cpp`):
- `1441` (coinbase construction expectation) and `5729` (coinbase validation).
- h ≤ **24999**: pre-V15 emission — NORMAL 50/25/25 (miner / Gold Vault / PoPC).
- h ≥ **25000**: V15 `UPDATE_EMPTY` shape — Gold Vault = 0, PoPC = 0; the non-miner half is
  redirected to the DTD lottery pending. Same miner-only coinbase shape (no miner-side change).
- Both sites use the identical `>= V15_HEIGHT` comparison, so template and validator agree on the
  boundary block.

## What activates at 25290 — the Historical DTD Jackpot (J)
Gate: `is_hist_jackpot_height(h)` = `h >= HIST_JACKPOT_FIRST_HEIGHT && (h - first) % cadence == 0`,
with `HIST_JACKPOT_FIRST_HEIGHT = V15_HEIGHT + 290 = 25290` (draw-aligned, `% 3 == 0`).
- The jackpot is **NOT** active at the fork block itself — no jackpot anywhere in [24998, 25289].
- First jackpot at **25290**, then every `cadence` blocks (not every block).
- This intentional 290-block offset gives the reserve/rollover machinery a clean start after the
  emission transition, and keeps the first draw DTD-aligned.

## Off-by-one surface (explicitly tested)
| height | `>= V15_HEIGHT` | emission | jackpot |
|--------|------------------|----------|---------|
| 24998  | false | pre-V15 50/25/25 | no |
| 24999  | false | pre-V15 50/25/25 (last pre-fork block) | no |
| 25000  | true  | **V15 transition** (gold=0, popc=0) | no |
| 25001  | true  | V15 | no |
| 25002  | true  | V15 | no |
| …      |       |      | first at 25290 |

## Coherence invariants (compile-time + tested)
- `static_assert(V15_HEIGHT > DTD_DOMINANCE_GATE_HEIGHT)` — V15 sits after the historical ladder.
- `HIST_JACKPOT_CAP_STOCKS >= HIST_JACKPOT_BASE_STOCKS`.
- `HIST_JACKPOT_ACTIVATION_HEIGHT == V15_HEIGHT`; first jackpot `% 3 == 0`.

**Gate status: PASS** (mainnet boundary correct; no off-by-one; DEV/testnet heights not leaked into
the mainnet build). The DEVNET_FAST harnesses additionally exercise crossing the live V15 boundary
(height 18) end-to-end.
