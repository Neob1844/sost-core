# CASERT Joint Behavior: Topline Summary

**Date:** 2026-04-16 20:37:05

## Question: Does changing slew rate from 3 to 1 require coordinated bitsQ changes?

## Answer: NO. Slew=1 is sufficient for V6. bitsQ is coherent and non-interfering.

## Evidence

| Metric | Slew=3 (V5) | Slew=1 (V6) | Change |
|--------|-------------|-------------|--------|
| Mean block time (s) | 604.1 | 601.8 | -2.3 |
| Std dev block time (s) | 1684.3 | 808.1 | -876.2 |
| Blocks > 40 min | 50.2 | 52.1 | +1.9 |
| Sawtooth oscillations | 67.7 | 0.0 | -67.7 |
| Time at H9+ (%) | 0.2 | 0.0 | -0.2 |
| bitsQ-profile correlation | 0.7 | 0.8 | +0.1 |

## bitsQ Cap Sensitivity (all with slew=1)

| Cap | std_dt | sawtooth | gt_40m |
|-----|--------|----------|--------|
| capcurrent_12pct | 808 | 0.0 | 52.1 |
| caploose_25pct | 808 | 0.0 | 52.1 |
| captight_6pct | 805 | 0.0 | 52.2 |
| capuncapped | 808 | 0.0 | 52.1 |

## Conclusion

- The slew rate change from 3 to 1 is the dominant improvement.
- bitsQ cap variations (4 to 16 to uncapped) produce secondary effects.
- The two subsystems do not interfere destructively at any tested configuration.
- V6 can proceed with slew=1 alone. bitsQ refinement is a V7 candidate.
