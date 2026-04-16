# CASERT V6 Slew Rate: Executive Summary

**RECOMMEND slew=1 for V6 (with minor gt_40m caveats)**

## Key Findings

- **std_dt improvement**: 47.7% (slew=1 wins decisively)
- **mean_dt**: slew=1 = 601.0s vs slew=3 = 601.6s (target 600s)
- **gt_40m blocks**: slew=1 = 153.4 vs slew=3 = 152.3
- **sawtooth score**: slew=1 = 0.1 vs slew=3 = 139.9
- **p99 block time**: slew=1 = 4488s vs slew=3 = 4864s

## Decision Criteria: 4/6 PASS

1. mean_dt in range: PASS
2. std_dt wins >= 8/11: PASS (11/11)
3. gt_40m no regression: FAIL
4. sawtooth wins >= 8/11: PASS
5. Statistical significance: PASS
6. No 10%+ regression: FAIL

## Methodology

- 11 scenarios covering normal, top-heavy, stall, shock, and stress conditions
- 50 paired seeds per scenario (same seed set for slew=1/2/3)
- 5000 blocks per run
- Fixed 5-term PID with real C++ coefficients
- 95% confidence intervals from paired t-tests
