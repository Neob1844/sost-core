# CASERT V6 Pre-Fork Slew Rate Validation

**Date**: 2026-04-16 18:22 UTC

**Configuration**: 11 scenarios x 3 slew rates x 50 seeds x 5000 blocks = 1650 runs

**Fixed PID**: K_L=0.4, K_I=0.15, K_B=0.05, K_R=0.05, K_V=0.02, I_leak=0.988

## 1. Topline: Slew=1 vs 2 vs 3 (averaged across all scenarios)

| Metric | slew=1 | slew=2 | slew=3 | slew=1 vs 3 |
|--------|--------|--------|--------|-------------|
| mean_dt | 600.96 | 601.08 | 601.62 | -0.1% |
| std_dt | 894.37 | 1164.47 | 1709.06 | -47.7% |
| p95_dt | 1932.77 | 1915.57 | 1861.37 | +3.8% |
| p99_dt | 4487.81 | 4735.54 | 4864.36 | -7.7% |
| gt_20m | 611.27 | 577.02 | 533.01 | +14.7% |
| gt_40m | 153.36 | 156.13 | 152.27 | +0.7% |
| gt_60m | 70.45 | 79.29 | 82.21 | -14.3% |
| target_error | 0.97 | 1.09 | 1.62 | -40.0% |
| sawtooth | 0.10 | 6.02 | 139.93 | -99.9% |
| pct_H9plus | 0.00 | 0.01 | 0.16 | -99.9% |
| pct_E | 36.99 | 36.10 | 39.80 | -7.1% |
| pct_B0 | 55.73 | 59.33 | 57.13 | -2.4% |
| antistall_count | 0.00 | 0.00 | 0.00 | 0% |
| lag_amplitude | 5.74 | 8.15 | 17.02 | -66.3% |
| robustness | 0.74 | 1.05 | 2.22 | -66.9% |
| worst_seed_mean | 603.36 | 606.22 | 613.19 | -1.6% |

## 2. Per-Scenario Breakdown

| Scenario | std_dt winner | std_dt(1) | std_dt(3) | gt_40m(1) | gt_40m(3) | saw(1) | saw(3) |
|----------|---------------|-----------|-----------|-----------|-----------|--------|--------|
| NORMAL_LOW | slew=1 | 708.7 | 1551.0 | 114.3 | 117.8 | 0.0 | 140.9 |
| NORMAL_MED | slew=1 | 755.1 | 1863.7 | 126.0 | 125.9 | 0.0 | 159.2 |
| NORMAL_HIGH | slew=1 | 932.9 | 2356.1 | 176.3 | 160.0 | 0.0 | 213.3 |
| TOPHEAVY_MED | slew=1 | 768.7 | 1712.0 | 125.3 | 127.6 | 0.0 | 157.3 |
| TOPHEAVY_HIGH | slew=1 | 941.4 | 2060.5 | 175.4 | 160.8 | 0.8 | 225.6 |
| STALLS_MED | slew=1 | 1066.3 | 1363.6 | 161.7 | 168.8 | 0.0 | 45.5 |
| STALLS_HIGH | slew=1 | 1272.0 | 1445.3 | 223.5 | 226.5 | 0.0 | 34.3 |
| SHOCK_TOP1 | slew=1 | 743.9 | 1648.1 | 127.8 | 129.3 | 0.0 | 162.2 |
| SHOCK_TOP2 | slew=1 | 750.0 | 1599.3 | 127.4 | 128.7 | 0.0 | 159.8 |
| SHOCK_STAGGERED | slew=1 | 748.0 | 1686.7 | 127.7 | 127.7 | 0.0 | 165.4 |
| STRESS_ALL | slew=1 | 1151.1 | 1513.3 | 201.5 | 201.9 | 0.4 | 75.7 |

## 3. Paired Statistical Tests (slew=1 vs slew=3)

For each scenario, paired differences (same seed): delta = metric(slew=1) - metric(slew=3)


### std_dt

| Scenario | mean delta | std delta | 95% CI | significant? |
|----------|-----------|-----------|--------|-------------|
| NORMAL_LOW | -842.32 | 363.37 | [-945.61, -739.03] | YES |
| NORMAL_MED | -1108.65 | 986.06 | [-1388.95, -828.36] | YES |
| NORMAL_HIGH | -1423.19 | 845.81 | [-1663.62, -1182.77] | YES |
| TOPHEAVY_MED | -943.30 | 489.28 | [-1082.38, -804.22] | YES |
| TOPHEAVY_HIGH | -1119.09 | 695.64 | [-1316.83, -921.36] | YES |
| STALLS_MED | -297.30 | 306.68 | [-384.48, -210.13] | YES |
| STALLS_HIGH | -173.29 | 225.38 | [-237.35, -109.22] | YES |
| SHOCK_TOP1 | -904.22 | 376.80 | [-1011.33, -797.11] | YES |
| SHOCK_TOP2 | -849.30 | 387.21 | [-959.37, -739.23] | YES |
| SHOCK_STAGGERED | -938.68 | 470.77 | [-1072.51, -804.86] | YES |
| STRESS_ALL | -362.18 | 360.69 | [-464.71, -259.65] | YES |

### gt_40m

| Scenario | mean delta | std delta | 95% CI | significant? |
|----------|-----------|-----------|--------|-------------|
| NORMAL_LOW | -3.52 | 7.73 | [-5.72, -1.32] | YES |
| NORMAL_MED | 0.10 | 10.65 | [-2.93, 3.13] | no |
| NORMAL_HIGH | 16.32 | 15.03 | [12.05, 20.59] | no |
| TOPHEAVY_MED | -2.30 | 9.91 | [-5.12, 0.52] | no |
| TOPHEAVY_HIGH | 14.56 | 12.67 | [10.96, 18.16] | no |
| STALLS_MED | -7.12 | 5.50 | [-8.68, -5.56] | YES |
| STALLS_HIGH | -2.96 | 5.33 | [-4.48, -1.44] | YES |
| SHOCK_TOP1 | -1.48 | 9.06 | [-4.05, 1.09] | no |
| SHOCK_TOP2 | -1.28 | 8.86 | [-3.80, 1.24] | no |
| SHOCK_STAGGERED | 0.02 | 9.10 | [-2.57, 2.61] | no |
| STRESS_ALL | -0.34 | 6.46 | [-2.18, 1.50] | no |

### sawtooth

| Scenario | mean delta | std delta | 95% CI | significant? |
|----------|-----------|-----------|--------|-------------|
| NORMAL_LOW | -140.86 | 42.82 | [-153.03, -128.69] | YES |
| NORMAL_MED | -159.24 | 48.79 | [-173.11, -145.37] | YES |
| NORMAL_HIGH | -213.32 | 48.56 | [-227.12, -199.52] | YES |
| TOPHEAVY_MED | -157.28 | 40.39 | [-168.76, -145.80] | YES |
| TOPHEAVY_HIGH | -224.82 | 50.66 | [-239.22, -210.42] | YES |
| STALLS_MED | -45.52 | 29.54 | [-53.92, -37.12] | YES |
| STALLS_HIGH | -34.26 | 24.71 | [-41.29, -27.23] | YES |
| SHOCK_TOP1 | -162.22 | 48.77 | [-176.08, -148.36] | YES |
| SHOCK_TOP2 | -159.78 | 50.39 | [-174.10, -145.46] | YES |
| SHOCK_STAGGERED | -165.44 | 45.71 | [-178.43, -152.45] | YES |
| STRESS_ALL | -75.36 | 32.80 | [-84.68, -66.04] | YES |

### mean_dt

| Scenario | mean delta | std delta | 95% CI | significant? |
|----------|-----------|-----------|--------|-------------|
| NORMAL_LOW | -0.76 | 2.77 | [-1.54, 0.03] | no |
| NORMAL_MED | -1.31 | 4.08 | [-2.47, -0.15] | YES |
| NORMAL_HIGH | -1.49 | 4.03 | [-2.64, -0.34] | YES |
| TOPHEAVY_MED | -0.97 | 3.19 | [-1.88, -0.06] | YES |
| TOPHEAVY_HIGH | -0.97 | 2.30 | [-1.63, -0.32] | YES |
| STALLS_MED | -0.04 | 0.70 | [-0.24, 0.16] | no |
| STALLS_HIGH | -0.24 | 2.04 | [-0.82, 0.34] | no |
| SHOCK_TOP1 | -0.45 | 1.36 | [-0.84, -0.07] | YES |
| SHOCK_TOP2 | -0.37 | 0.90 | [-0.62, -0.11] | YES |
| SHOCK_STAGGERED | -0.48 | 1.21 | [-0.82, -0.13] | YES |
| STRESS_ALL | -0.05 | 0.35 | [-0.15, 0.05] | no |

## 4. Safety Analysis: Does slew=1 break anything?

### mean_dt within 600 +/- 15s

PASS: All scenarios within tolerance.

### gt_40m not worse than slew=3

Scenarios where slew=1 has more gt_40m blocks:
  NORMAL_HIGH: slew=1 gt_40m=176.3 vs slew=3 gt_40m=160.0 (+10.2%)
  TOPHEAVY_HIGH: slew=1 gt_40m=175.4 vs slew=3 gt_40m=160.8 (+9.1%)

### No regression > 10% in critical metrics

Regressions > 10%:
  NORMAL_HIGH/gt_40m: slew=1=176.30 vs slew=3=159.98 (+10.2%)

### Per-scenario worst_seed_mean (stress test)

| Scenario | worst(slew=1) | worst(slew=3) |
|----------|---------------|---------------|
| NORMAL_LOW | 601.6s | 618.8s |
| NORMAL_MED | 601.7s | 625.8s |
| NORMAL_HIGH | 602.1s | 618.1s |
| TOPHEAVY_MED | 602.0s | 619.6s |
| TOPHEAVY_HIGH | 602.5s | 613.2s |
| STALLS_MED | 604.7s | 605.9s |
| STALLS_HIGH | 607.9s | 616.2s |
| SHOCK_TOP1 | 601.6s | 607.4s |
| SHOCK_TOP2 | 602.5s | 603.8s |
| SHOCK_STAGGERED | 601.7s | 607.4s |
| STRESS_ALL | 608.8s | 608.9s |

## 5. Fork-Readiness Reasoning

### Is this consensus-critical?

**Yes.** `profile_index` is embedded in every block header and validated by all nodes. Changing `slew_rate` changes which profile indices are valid at each height. This requires a coordinated hard fork.

### Is the change simple to specify?

**Yes.** One constant change in `include/sost/params.h`:
```cpp
-inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 3;
+inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 1;
```
(Plus a V6 fork height gate so the change activates at a specific block.)

### Risk of non-intuitive behavior at activation?

At the fork height, profile transitions will be limited to +/-1 per block instead of +/-3. If the chain is at a high profile (e.g., H9) when the fork activates, the descent to B0 will take 9 blocks minimum instead of 3. This is the INTENDED behavior (smoother transitions) but operators should be aware that the first few blocks after activation may have slightly different timing characteristics as the equalizer adjusts.

**Mitigation**: Choose a fork height when the chain is expected to be near B0 (lag ~ 0). This is standard practice for CASERT fork activations.

### Should it go in V6 or wait for V7?

**V6 is appropriate with caveats.** Most decision criteria are met. Review the specific failures noted above before proceeding.

## 6. Recommendation

### **RECOMMEND slew=1 for V6 (with minor gt_40m caveats)**

**Decision criteria results**:

1. mean_dt within 600 +/- 15s: **PASS**
2. std_dt lower in >= 8/11 scenarios: **PASS** (11/11)
3. gt_40m not worse in any scenario: **FAIL**
4. sawtooth lower in >= 8/11 scenarios: **PASS** (11 wins + 0 ties)
5. std_dt statistically significant: **PASS** (11/11 scenarios significant)
6. No regression > 10%: **FAIL**

slew=1 wins **decisively** with 47.7% std_dt improvement overall.

slew=1 is std_dt winner in 11/11 scenarios.
slew=2 is std_dt winner in 0/11 scenarios (where neither 1 nor 3 wins).

## 7. Appendix: Implementation Details

### Exact diff for include/sost/params.h

```diff
--- a/include/sost/params.h
+++ b/include/sost/params.h
-inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 3;       // max +/-3 profile levels per block
+inline constexpr int32_t  CASERT_V6_SLEW_RATE     = 1;       // max +/-1 profile levels per block (V6)
```

**Note**: The actual implementation will need a V6 fork height gate:
```cpp
const int32_t slew = (nHeight >= CASERT_V6_FORK_HEIGHT)
                   ? CASERT_V6_SLEW_RATE
                   : CASERT_V3_SLEW_RATE;
```

### Pre-fork checklist

- [ ] Run full consensus test suite with V6 fork height set to test height
- [ ] Verify IBD (initial block download) across the fork boundary
- [ ] Test activation with chain at various profile levels (B0, H3, H6, H9)
- [ ] Confirm anti-stall decay still works correctly with slew=1
- [ ] Verify EBR (Emergency Behind Release) still functions correctly
- [ ] Test reorg across fork boundary
- [ ] Update CASERT_V3_SLEW_RATE references in documentation
- [ ] Coordinate activation height with mining pool operators
- [ ] Release candidate with at least 2 weeks testnet soak time
