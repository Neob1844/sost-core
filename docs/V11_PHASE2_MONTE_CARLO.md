# V11 Phase 2 — Formal Monte Carlo + Activation Readiness (C9)

Status: **C9 review complete.** `V11_PHASE2_HEIGHT` remains
`INT64_MAX` in `include/sost/params.h` (Phase 2 dormant). This
document collects the Monte Carlo evidence used to decide the C5/C6/C7
parameter set is safe to ship as-is, and to record what the lottery
does and does NOT defend against.

Tooling: `tools/lottery_montecarlo.py` (analysis tool only — not
consensus, not linked into any binary, not in the test suite).
Determinism is anchored by `--seed` (default 42).

## 1. Executive summary

- The C5/C6/C7 lottery (cap=5 cooldown window, current-block winner
  allowed iff clean in H-1..H-5, full protocol-side allocation
  redirected on triggered blocks) **passes every invariant** the C9
  verification checks: per-block accounting, cumulative emission,
  reorg-style undo, and RNG determinism.
- With **zero sybils**, the cooldown window collapses the dominant
  miner's lottery share from ~17% (no cooldown) to **~0%** at cap=5,
  even at 92% PoW dominance. That is the regime the lottery was
  designed for and it works.
- With **sybils on the order of the network's honest miner count**, the
  defense degrades sharply. At dom=70% / honest=10 / sybils=10 the
  dominant captures ~54% of the lottery; at sybils=100 they capture
  ~92%. **The lottery is NOT Sybil-proof under the assumption that the
  dominant can pre-legitimate sybil addresses.** Larger cooldown
  windows make this strictly worse, not better.
- Recommendation: **keep cap=5**. It minimizes both (a) sybil
  amplification vs. larger windows and (b) rollover/jackpot blowup vs.
  smaller windows, while still flushing same-pool repeat winners.
  Activation can proceed once the SbPoW + coinbase wiring is fully
  reviewed by another reader.

`READY_FOR_HEIGHT_DECISION = YES` — but with the caveat that the
lottery's Sybil resistance is honest-worth-of-mining, not
identity-bound. A future B+D redesign (per project memory) is the
right place to address that.

## 2. Current final rule (C5 + C6 + C7 + C7.1 + C8)

- Trigger schedule (height-anchored, mirrors `is_lottery_block` in
  `include/sost/lottery.h`):
  - First `LOTTERY_HIGH_FREQ_WINDOW = 5000` blocks after activation:
    `triggered ⟺ (height % 3) != 0` (2-of-3 high-frequency).
  - Thereafter, permanently: `triggered ⟺ (height % 3) == 0` (1-of-3).
- Cooldown window: `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = 5`
  (hard-coded, reviewed in C9).
- Eligibility (C7.1):
  1. Address has won ≥ 1 block-reward in `[0, height-1]`.
  2. Address has NOT won a block-reward in
     `[height - 5, height - 1]` (previous 5 blocks).
- Coinbase shape on triggered blocks (C8 / `phase2_coinbase_split`):
  - **MINER receives 50%** of `subsidy + fees` (PoW share, never
    touched by lottery).
  - **The full protocol-side allocation (the other 50% — Gold 25% +
    PoPC 25%, combined)** is redirected to the lottery winner if
    the eligibility set is non-empty (PAYOUT), or accumulated into
    `pending_lottery_amount` if the set is empty (UPDATE).
- Jackpot rollover invariant:
  `outputs_sum + (pending_after − pending_before) == subsidy + fees`
  per block, and cumulatively
  `cumulative_outputs + ending_pending == n_blocks × (subsidy + fees)`.

## 3. Scenario grid

Main run (lifecycle freq mode, 100,000 blocks/scenario):

| dimension       | values              |
| --------------- | ------------------- |
| dominant share  | 0.50, 0.70, 0.85, 0.92 |
| honest miners   | 5, 10, 35, 100      |
| dominant sybils | 0, 5, 10, 100       |
| cooldown window | 0, 5, 10, 30        |
| freq mode       | lifecycle (5000 hf + perm) |
| subsidy / fees  | 8 / 0               |
| seed            | 42                  |

Total: **256 scenarios × 100k blocks = 25,600,000 simulated blocks**.
Wall-clock runtime: 108.8s on the C9 host. Reorg simulation: 1000
trials over depths {1, 2, 5, 10}. Determinism: 5 Python-side checks
mirroring `select_lottery_winner_index`.

Contrast runs (10k blocks each, hf-only and perm-only) confirmed
qualitatively identical Sybil sensitivity — the freq mode controls
*how often* the lottery fires but not *who* it advantages.

## 4. Main result tables

### 4.1 Selected rows from the FULL MATRIX

Format:
`hash hon syb win | blk_dom lot_dom tot_dom med_hon wst_hon roll pool jp_avg jp_max dbl`

```
 hash  hon  syb  win |  blk_dom  lot_dom  tot_dom  med_hon  wst_hon   roll    pool  jp_avg  jp_max    dbl
------------------------------------------------------------------------------------------------------------------------
   50    5    0    0 |    50.2%    16.7%    28.0%   16.70%   16.42%   0.0%     6.0    0.00       0  16.4%
   50    5    0    5 |    50.2%     1.4%    25.3%   19.84%   19.21%   0.0%     3.0    0.00       8  10.4%
   50    5    0   10 |    49.9%     0.1%    25.0%   19.95%   19.34%   2.8%     1.7    0.48      24  10.0%
   50    5    0   30 |    50.0%     0.0%    25.0%   20.01%   18.65%  27.9%     0.2   51.52     668   9.6%
   70   10    0    0 |    70.1%     9.1%    36.7%    9.11%    8.84%   0.0%    11.0    0.00       0   9.1%
   70   10    0    5 |    70.1%     0.0%    35.1%    9.96%    9.70%   0.0%     8.6    0.00      12   3.1%
   70   10   10    5 |    70.0%    58.4%    46.1%    4.16%    3.91%   0.0%    13.7    0.00       0   1.6%
   70   10  100    5 |    70.0%    92.0%    50.6%    0.81%    0.65%   0.0%   107.7    0.00       0   0.4%
   85    5    0    5 |    85.0%     0.0%    42.5%   19.99%   19.74%   0.0%     4.0    0.00      12   0.6%
   85    5  100    5 |    85.0%    95.8%    55.2%    0.84%    0.78%   0.0%   103.7    0.00       0   0.0%
   92    5    0    5 |    92.0%     0.0%    46.0%   19.99%   19.65%   0.0%     4.1    0.00      12   0.0%
   92    5  100    5 |    92.0%    95.3%    56.6%    0.93%    0.85%   0.0%   103.7    0.00       0   0.0%
```

The sybil=0 rows show the cooldown working as designed: at cap=5 the
dominant's lottery share drops to ~0% across all dom levels. The
sybil=100 rows show the failure mode: dominant captures ~92-96% of
the lottery regardless of cap or dom share.

### 4.2 Decision table — realistic shape (dom 70-85%, honest 5-10)

```
 window | dom_lot_no_syb dom_lot_syb_10 dom_lot_syb_100 | med_hon_no_syb rollover
------------------------------------------------------------------------------------------------------------------------
      0 |          12.8%          60.6%           93.2% |         12.84%     0.0%
      5 |           0.0%          62.5%           94.0% |         15.03%     0.0%
     10 |           0.0%          66.3%           94.7% |         14.97%     0.1%
     30 |           0.0%          77.7%           96.8% |         14.91%     4.2%
```

cap=5 is strictly the best non-zero window: it eliminates the
no-sybil dominant share, gives the highest honest median in the
no-sybil column, has near-zero rollover, and grows the slowest with
sybil count.

### 4.3 Stress case

`dom=0.92, honest=5, sybils=100, window=5, freq=lifecycle, 100k blocks`:

| metric                   | value     |
| ------------------------ | --------- |
| dom_block_share          | 91.99%    |
| dom_lottery_share        | 95.30%    |
| dom_total_share          | 62.67%    |
| honest_median_total      | 0.96%     |
| honest_worst_total       | 0.94%     |
| empty_eligibility_rate   | 0.00%     |
| double_win_rate          | 0.06%     |
| cooldown_exclusion_rate  | 1.31%     |
| accounting_ok            | True      |

The lottery shifts the dominant's *total emission share* from 91.99%
(PoW-only) to 62.67% (PoW + lottery). That is real redistribution, but
it does NOT come from honest miners — it comes from the dominant's own
sybil pool returning the lottery share back to the dominant.

## 5. Sybil sensitivity analysis

`Δ_10 = dom_lottery_share(sybils=10) − dom_lottery_share(sybils=0)`,
`Δ_100 = dom_lottery_share(sybils=100) − dom_lottery_share(sybils=0)`.

Selected rows (full table in stdout):

```
 hash  hon  win |   no_syb   syb=10   syb=100 |    Δ_10    Δ_100
------------------------------------------------------------------------------------------------------------------------
   50    5    5 |     1.4%    77.5%     97.1% |  +76.1%   +95.7%
   70   10    5 |     0.0%    54.4%     92.0% |  +54.4%   +92.0%
   85   10    5 |     0.0%    52.0%     91.7% |  +52.0%   +91.7%
   92  100    5 |     0.0%     9.4%     50.4% |   +9.4%   +50.4%
```

Conclusion (one sentence): **the lottery is fragile to sybilation
proportional to the network's honest miner count** — when the
dominant's sybil count exceeds the honest count the dominant
recaptures most of the lottery share, and no choice of cooldown
window inside `{0, 5, 10, 30}` prevents this.

## 6. Jackpot / rollover analysis

Selected rows from the JACKPOT ANALYSIS table:

```
 hash  hon  syb  win | roll_rate empty_elig     jp_avg     jp_max   dbl_win
------------------------------------------------------------------------------------------------------------------------
   50    5    0   30 |    27.92%     79.78%      51.52        668     9.64%
   50    5    0   10 |     2.77%      7.91%       0.48         24     9.98%
   50    5    0    5 |     0.00%      0.01%       0.00          8    10.39%
   50    5    0    0 |     0.00%      0.00%       0.00          0    16.43%
   70   10    0    5 |     0.00%      0.05%       0.00         12     3.06%
```

Cap=30 produces a 28% rollover rate and a max jackpot of 668 stocks
(vs. an 8-stock subsidy) — that is a long-tail concentration risk
the protocol probably should NOT inherit by default. Cap=5 keeps
rollover rate ≤ 0.05% in all realistic scenarios. Cap=0 has
zero rollover but highest dominant lottery share (~17% at honest=5).

double_win_rate (lottery winner == PoW winner of the same block) sits
at 0-10% under cap=5, which is acceptable: it's an artifact of
self-rotation, not a design flaw.

## 7. Reorg simulation results

```
trials:          1000
depths:          [1, 2, 5, 10]
failures:        0
max divergence:  0
verdict:         PASS
```

Each trial picks a random `depth ∈ {1, 2, 5, 10}` and a random
`base_height` and verifies that:
- a chain rebuilt from genesis with the alt seed up to base_height
  produces the same `pending` and `cumulative_outputs` as a chain
  truncated at base_height (deterministic replay invariance), and
- snapshotted `pending` at `base_height − depth` matches the
  `pending_history[base_height − depth − 1]` carried inside the full
  rebuild (undo-snapshot invariance).

Both invariants pass for all 1000 trials.

## 8. Accounting invariant results

Run scope: 25,600,000 blocks (256 scenarios × 100,000 blocks each).

```
=== ACCOUNTING INVARIANT ===
Total blocks simulated:           25600000
Total subsidy emitted:            204800000  (subsidy=8 fees=0)
Sum of all coinbase outputs:      204799968
Ending pending_lottery (sum):     32
X + Y == total emission?          PASS
Per-block invariant violations:   0
```

`outputs(204,799,968) + ending_pending(32) == 204,800,000 == n_blocks × subsidy`.
Per-block invariant
`outputs_sum + (pending_after − pending_before) == subsidy + fees`
holds across every one of 25.6M simulated blocks.

## 9. Determinism results

Mirrors the contract documented in
`include/sost/lottery.h::select_lottery_winner_index` and exercised
by `tests/test_lottery_eligibility.cpp` and
`tests/test_lottery_rollover.cpp`. The C++ tests are authoritative;
these Python checks are a sanity layer for this analysis script.

```
[PASS] lex_sort              raw bytes sort identical x86/ARM
[PASS] stable                10 calls all returned 1
[PASS] seed_sensitive        4 distinct seeds → 2 distinct winners
[PASS] endian_safe           manual=289077008422317534 vs from_bytes=289077008422317534
[PASS] dict_order            3 insertion orders → winners [1, 1, 1]
```

All 5 checks PASS. The lottery RNG contract is portable, stable, and
order-independent. Determinism for the lottery winner is anchored on
`sha256(LOTTERY_RNG_DOMAIN || prev_block_hash || height_le)` reduced
via little-endian `read_u64_le` — identical between miner and
validator and between x86 and ARM.

## 10. Recommendation

**Keep `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = 5`.** Justification:

- Cap=5 is the smallest non-zero window that drives `dom_lot_no_syb`
  to 0.0% — i.e. it fully fixes the no-sybil case which is the case
  the lottery exists to fix.
- Larger caps (10, 30) buy nothing in the no-sybil case (already 0%)
  and make the sybil case strictly worse: at cap=30 / dom=70 / hon=10
  / syb=10 the dominant lottery share rises to 72.2% (vs 54.4% at
  cap=5), because larger cooldown windows penalize honest single-
  address miners more than they penalize a dominant with many addresses.
- Cap=5 has rollover rate ≤ 0.05% in every realistic scenario; cap=10
  introduces 0.1-2.8% rollover for sparse honest pools; cap=30
  produces 4-28% rollover and jackpot peaks of hundreds of subsidies,
  which is a separate concentration risk we'd rather not inherit by
  default.
- Cap=0 (no cooldown) leaves a non-zero dominant lottery share even
  with no sybils (~13% in the realistic table) and it does NOT do
  what the lottery was designed to do — flush same-pool repeat
  winners.

There is no value in `{10, 30}` over `5` on either axis. Cap=5 stays.

## 11. Activation readiness verdict

**`READY_FOR_HEIGHT_DECISION = YES`**, with the following honest
caveats recorded in this doc and visible to any reviewer:

1. The lottery improves miner retention against trivial concentration
   (no-sybil regime: 17% → 0% dom lottery share) and adds a real
   carrot for low-share participants (honest median lottery share
   ~10-20% at cap=5).
2. The lottery is **NOT Sybil-proof.** Pre-legitimated sybil sets on
   the order of the honest miner count return ≥ 50% of the lottery
   to the dominant; pre-legitimated sets ≫ honest count return
   ≥ 90%.
3. The accounting invariant
   `outputs + Δpending == subsidy + fees` holds bit-exactly across
   25.6M simulated blocks. The reorg-style undo invariance also
   holds across 1000 trials. The RNG determinism contract holds in
   all 5 Python sanity checks.
4. The C9 review does NOT validate B+D — the project memory record
   `project_useful_compute_trial.md` already notes that any rewarded
   B+D phase requires a future redesign. The lottery as shipped is
   the C-side mechanism only.
5. Activation height itself is NOT being set in this commit. C10 is
   the parameter-decision commit.

## Appendix A — How to reproduce

```sh
# Full 100k-block grid + accounting + reorg + determinism (≈110s):
python3 tools/lottery_montecarlo.py \
    --blocks 100000 --freq-mode lifecycle \
    --reorgs 1000 --reorg-blocks 2000 --quiet

# Stress case alone:
python3 tools/lottery_montecarlo.py \
    --single 0.92 5 100 5 --blocks 100000 --freq-mode lifecycle

# Determinism only:
python3 tools/lottery_montecarlo.py --determinism
```

Seed defaults to 42. Two runs with the same flags produce
bit-identical output.

## Appendix B — Test matrix (final pre-activation)

ON-mode build (`cmake -DSOST_ENABLE_PHASE2_SBPOW=ON`):

```
9/9 lottery-frequency      PASS
    lottery-eligibility    PASS
    lottery-rollover       PASS
    coinbase-phase2        PASS
    casert-v11             PASS
    convergencex-v11       PASS
    transcript-v2          PASS
    sbpow-header-v2        PASS
    miner-key-selection    PASS
ctest total: 37/42 (5 pre-existing failures — see KNOWN_TEST_FAILURES.md)
```

OFF-mode build (`cmake -DSOST_ENABLE_PHASE2_SBPOW=OFF`):

```
9/9 targeted Phase 2 tests PASS
    sbpow-signing / sbpow-validation / sbpow-adversarial: NOT BUILT (expected)
ctest total: 34/39 (same 5 pre-existing failures)
```

Pre-existing failures (not introduced by C9, not introduced by V11
Phase 2): `bond-lock`, `popc`, `escrow`, `dynamic-rewards`,
`checkpoints` — see `docs/KNOWN_TEST_FAILURES.md`.
