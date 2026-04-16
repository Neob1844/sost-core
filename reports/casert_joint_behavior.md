# CASERT Joint Behavior Test Results

**Date:** 2026-04-16 20:37:05
**Configurations:** 14

## Results Summary

| Config | mean_dt | std_dt | gt_40m | sawtooth | pct_H9+ | bitsQ-profile corr |
|--------|---------|--------|--------|----------|---------|-------------------|
| M1_current_slew1_cap8 | 602 | 808 | 52.1 | 0.0 | 0.0% | 0.790 |
| M1_reference_slew3_cap8 | 604 | 1684 | 50.2 | 67.7 | 0.2% | 0.664 |
| M2_slew1_cap8 | 602 | 808 | 52.1 | 0.0 | 0.0% | 0.790 |
| M2_slew1_nobitsq | 602 | 778 | 50.7 | 0.0 | 0.0% | 0.000 |
| M2_slew3_cap8 | 604 | 1684 | 50.2 | 67.7 | 0.2% | 0.664 |
| M2_slew3_nobitsq | 604 | 1653 | 50.1 | 61.2 | 0.2% | 0.000 |
| M3_slew1_capcurrent_12pct | 602 | 808 | 52.1 | 0.0 | 0.0% | 0.790 |
| M3_slew1_caploose_25pct | 602 | 808 | 52.1 | 0.0 | 0.0% | 0.777 |
| M3_slew1_captight_6pct | 602 | 805 | 52.2 | 0.0 | 0.0% | 0.795 |
| M3_slew1_capuncapped | 602 | 808 | 52.1 | 0.0 | 0.0% | 0.776 |
| M3_slew3_capcurrent_12pct | 604 | 1684 | 50.2 | 67.7 | 0.2% | 0.664 |
| M3_slew3_caploose_25pct | 602 | 1532 | 51.0 | 69.5 | 0.2% | 0.601 |
| M3_slew3_captight_6pct | 603 | 1713 | 49.9 | 68.9 | 0.2% | 0.725 |
| M3_slew3_capuncapped | 602 | 1527 | 50.9 | 69.5 | 0.2% | 0.575 |

## MODE 1: Full Current System

**M1_current_slew1_cap8**: mean_dt=602s, std=808s, gt_40m=52.1, sawtooth=0.0, H9+=0.0%, corr=0.790
**M1_reference_slew3_cap8**: mean_dt=604s, std=1684s, gt_40m=50.2, sawtooth=67.7, H9+=0.2%, corr=0.664

## MODE 2: Equalizer Variations

**M2_slew1_cap8**: mean_dt=602s, std=808s, gt_40m=52.1, sawtooth=0.0, H9+=0.0%, corr=0.790
**M2_slew1_nobitsq**: mean_dt=602s, std=778s, gt_40m=50.7, sawtooth=0.0, H9+=0.0%, corr=0.000
**M2_slew3_cap8**: mean_dt=604s, std=1684s, gt_40m=50.2, sawtooth=67.7, H9+=0.2%, corr=0.664
**M2_slew3_nobitsq**: mean_dt=604s, std=1653s, gt_40m=50.1, sawtooth=61.2, H9+=0.2%, corr=0.000

## MODE 3: bitsQ Cap Variations

**M3_slew1_capcurrent_12pct**: mean_dt=602s, std=808s, gt_40m=52.1, sawtooth=0.0, H9+=0.0%, corr=0.790
**M3_slew1_caploose_25pct**: mean_dt=602s, std=808s, gt_40m=52.1, sawtooth=0.0, H9+=0.0%, corr=0.777
**M3_slew1_captight_6pct**: mean_dt=602s, std=805s, gt_40m=52.2, sawtooth=0.0, H9+=0.0%, corr=0.795
**M3_slew1_capuncapped**: mean_dt=602s, std=808s, gt_40m=52.1, sawtooth=0.0, H9+=0.0%, corr=0.776
**M3_slew3_capcurrent_12pct**: mean_dt=604s, std=1684s, gt_40m=50.2, sawtooth=67.7, H9+=0.2%, corr=0.664
**M3_slew3_caploose_25pct**: mean_dt=602s, std=1532s, gt_40m=51.0, sawtooth=69.5, H9+=0.2%, corr=0.601
**M3_slew3_captight_6pct**: mean_dt=603s, std=1713s, gt_40m=49.9, sawtooth=68.9, H9+=0.2%, corr=0.725
**M3_slew3_capuncapped**: mean_dt=602s, std=1527s, gt_40m=50.9, sawtooth=69.5, H9+=0.2%, corr=0.575

## Key Findings

- **Lowest std_dt:** M2_slew1_nobitsq (778s)
- **Highest std_dt:** M3_slew3_captight_6pct (1713s)
- **Lowest sawtooth:** M1_current_slew1_cap8 (0.0)
- **Highest sawtooth:** M3_slew3_capuncapped (69.5)

### bitsQ Impact Analysis

- With bitsQ (slew=1): std_dt=808s, sawtooth=0.0
- Without bitsQ (slew=1): std_dt=778s, sawtooth=0.0
- bitsQ effect on std_dt: +31s (harmful)
- bitsQ effect on sawtooth: +0.0 (beneficial)

## V6 Fork Recommendation

Based on the joint behavior analysis:

1. Slew=1 vs slew=3: std_dt improvement = 876s, sawtooth reduction = 67.7
2. bitsQ cap variations have secondary impact compared to slew rate
3. The two subsystems are coherent (positive correlation) and do not interfere destructively
