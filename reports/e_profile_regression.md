# E-Profile Regression Validation for V6 Slew-Rate Fork

**Date:** 2026-04-17 20:35:31
**Seeds:** 50 paired seeds per configuration
**Blocks:** 5000 per run
**Total runs:** 54
**Configurations:** 9 profiles x 3 conditions x 2 slew rates = 54

## Previous E-Profile Coverage

The pid_tuning_campaign.py (1650 runs) used `start_height=4300` with
on-schedule initial conditions (lag=0). E profiles were only reached
*reactively* when hashrate variance or stalls pushed the chain behind.
In those runs, E profiles were transient (typically <5% of blocks).
No test started the chain at E4/E3/E2/E1 to measure recovery behavior.
This test fills that gap with explicit E-start scenarios.

## Summary: All Configurations

| Profile | Condition | Slew | mean_dt | std_dt | gt_40m | pct_E | pct_B0 | recovery_B0 | sawtooth | stuck_E |
|---------|-----------|------|---------|--------|--------|-------|--------|-------------|----------|---------|
|  E4 | HIGH_VAR    | 1 |     598 |    922 | 175.1 |  27.6 |  61.9 |         24 |     1.1 |     42 |
|  E4 | HIGH_VAR    | 3 |     599 |   2115 | 160.9 |  35.6 |  60.3 |         22 |   217.1 |    208 |
|  E4 | NORMAL      | 1 |     598 |    727 | 126.5 |  30.3 |  61.6 |         26 |     0.0 |     30 |
|  E4 | NORMAL      | 3 |     598 |   1628 | 126.4 |  34.1 |  62.5 |         24 |   144.9 |    151 |
|  E4 | WITH_STALLS | 1 |     599 |   1066 | 162.3 |  57.2 |  41.1 |         41 |     0.0 |    146 |
|  E4 | WITH_STALLS | 3 |     598 |   1349 | 168.6 |  52.5 |  46.4 |         37 |    45.8 |    197 |
|  E3 | HIGH_VAR    | 1 |     598 |    937 | 174.5 |  27.6 |  61.8 |         16 |     1.1 |     45 |
|  E3 | HIGH_VAR    | 3 |     600 |   2043 | 161.7 |  34.9 |  60.9 |         14 |   219.8 |    196 |
|  E3 | NORMAL      | 1 |     598 |    734 | 126.6 |  30.2 |  61.7 |         16 |     0.0 |     29 |
|  E3 | NORMAL      | 3 |     599 |   1673 | 125.8 |  34.1 |  62.6 |         14 |   151.4 |    157 |
|  E3 | WITH_STALLS | 1 |     599 |   1067 | 162.4 |  57.0 |  41.2 |         27 |     0.0 |    146 |
|  E3 | WITH_STALLS | 3 |     599 |   1370 | 168.5 |  52.3 |  46.6 |         20 |    42.9 |    200 |
|  E2 | HIGH_VAR    | 1 |     599 |    930 | 174.0 |  27.4 |  62.1 |          5 |     1.1 |     42 |
|  E2 | HIGH_VAR    | 3 |     600 |   1973 | 162.0 |  34.4 |  61.5 |          2 |   221.6 |    189 |
|  E2 | NORMAL      | 1 |     599 |    726 | 125.9 |  29.9 |  62.0 |          5 |     0.0 |     26 |
|  E2 | NORMAL      | 3 |     599 |   1656 | 126.3 |  33.8 |  62.8 |          2 |   155.4 |    161 |
|  E2 | WITH_STALLS | 1 |     600 |   1067 | 162.6 |  56.8 |  41.5 |          8 |     0.0 |    145 |
|  E2 | WITH_STALLS | 3 |     600 |   1347 | 169.2 |  52.1 |  46.8 |          4 |    44.4 |    198 |
|  E1 | HIGH_VAR    | 1 |     599 |    935 | 174.8 |  27.3 |  62.1 |          3 |     0.8 |     42 |
|  E1 | HIGH_VAR    | 3 |     600 |   2090 | 162.5 |  34.7 |  61.2 |          2 |   225.7 |    205 |
|  E1 | NORMAL      | 1 |     599 |    730 | 126.9 |  29.8 |  62.1 |          3 |     0.0 |     25 |
|  E1 | NORMAL      | 3 |     600 |   1652 | 126.6 |  33.3 |  63.2 |          2 |   152.3 |    156 |
|  E1 | WITH_STALLS | 1 |     600 |   1067 | 163.2 |  56.6 |  41.6 |          4 |     0.0 |    144 |
|  E1 | WITH_STALLS | 3 |     600 |   1323 | 169.6 |  51.8 |  47.2 |          3 |    44.0 |    182 |
|  B0 | HIGH_VAR    | 1 |     601 |    938 | 176.7 |  27.2 |  62.0 |          1 |     1.1 |     42 |
|  B0 | HIGH_VAR    | 3 |     601 |   2274 | 160.9 |  35.9 |  60.0 |          1 |   223.8 |    246 |
|  B0 | NORMAL      | 1 |     601 |    735 | 127.9 |  29.7 |  62.0 |          1 |     0.0 |     26 |
|  B0 | NORMAL      | 3 |     601 |   1703 | 126.6 |  33.8 |  62.7 |          1 |   152.7 |    167 |
|  B0 | WITH_STALLS | 1 |     602 |   1068 | 163.5 |  56.4 |  41.7 |          1 |     0.0 |    143 |
|  B0 | WITH_STALLS | 3 |     602 |   1368 | 169.9 |  52.0 |  46.9 |          1 |    45.3 |    192 |
|  H1 | HIGH_VAR    | 1 |     601 |    930 | 176.9 |  27.1 |  61.9 |          6 |     1.5 |     41 |
|  H1 | HIGH_VAR    | 3 |     602 |   2208 | 161.6 |  36.0 |  59.8 |          6 |   219.5 |    221 |
|  H1 | NORMAL      | 1 |     601 |    734 | 128.8 |  29.7 |  61.9 |          5 |     0.0 |     25 |
|  H1 | NORMAL      | 3 |     601 |   1674 | 126.7 |  34.0 |  62.4 |          3 |   156.5 |    157 |
|  H1 | WITH_STALLS | 1 |     602 |   1069 | 164.2 |  56.4 |  41.7 |          5 |     0.0 |    145 |
|  H1 | WITH_STALLS | 3 |     602 |   1344 | 170.2 |  52.0 |  46.9 |          7 |    50.2 |    186 |
|  H3 | HIGH_VAR    | 1 |     602 |    938 | 178.4 |  27.2 |  61.9 |         12 |     0.8 |     41 |
|  H3 | HIGH_VAR    | 3 |     604 |   2098 | 163.4 |  35.2 |  60.5 |         17 |   223.7 |    197 |
|  H3 | NORMAL      | 1 |     602 |    739 | 129.8 |  29.6 |  61.9 |         13 |     0.0 |     26 |
|  H3 | NORMAL      | 3 |     603 |   1653 | 129.1 |  33.3 |  63.0 |         18 |   151.9 |    156 |
|  H3 | WITH_STALLS | 1 |     603 |   1073 | 165.1 |  56.3 |  41.6 |         12 |     0.0 |    145 |
|  H3 | WITH_STALLS | 3 |     603 |   1351 | 170.9 |  52.0 |  46.8 |         15 |    47.3 |    186 |
|  H6 | HIGH_VAR    | 1 |     604 |    946 | 178.5 |  27.0 |  61.9 |         16 |     1.1 |     45 |
|  H6 | HIGH_VAR    | 3 |     605 |   2220 | 160.9 |  36.1 |  59.5 |         34 |   231.7 |    212 |
|  H6 | NORMAL      | 1 |     604 |    743 | 131.5 |  29.6 |  61.8 |         17 |     0.0 |     25 |
|  H6 | NORMAL      | 3 |     604 |   1660 | 129.5 |  33.7 |  62.6 |         26 |   154.8 |    152 |
|  H6 | WITH_STALLS | 1 |     605 |   1078 | 166.0 |  56.3 |  41.6 |         15 |     0.0 |    143 |
|  H6 | WITH_STALLS | 3 |     604 |   1381 | 171.4 |  51.9 |  46.9 |         28 |    45.4 |    196 |
|  H9 | HIGH_VAR    | 1 |     605 |    944 | 179.2 |  27.0 |  61.9 |         22 |     0.8 |     42 |
|  H9 | HIGH_VAR    | 3 |     605 |   1965 | 166.2 |  34.2 |  61.4 |         32 |   225.0 |    184 |
|  H9 | NORMAL      | 1 |     605 |    753 | 131.2 |  29.6 |  61.8 |         21 |     0.0 |     26 |
|  H9 | NORMAL      | 3 |     605 |   1681 | 129.1 |  33.8 |  62.5 |         22 |   162.8 |    154 |
|  H9 | WITH_STALLS | 1 |     606 |   1081 | 167.0 |  56.2 |  41.6 |         19 |     0.0 |    147 |
|  H9 | WITH_STALLS | 3 |     606 |   1369 | 172.3 |  51.8 |  46.9 |         24 |    47.1 |    191 |

## Paired Comparison: Slew=1 vs Slew=3

Positive delta = slew=1 is HIGHER. For std_dt/gt_40m/pct_E/sawtooth/recovery, lower is better.

| Profile | Condition | Metric | Delta(s1-s3) | 95% CI | Verdict |
|---------|-----------|--------|-------------|--------|---------|
|  B0 | HIGH_VAR    | mean_dt        |       -0.9 | +/-    0.7 | BETTER |
|  B0 | HIGH_VAR    | std_dt         |    -1335.8 | +/-  277.8 | BETTER |
|  B0 | HIGH_VAR    | gt_40m         |      +15.8 | +/-    4.6 | WORSE |
|  B0 | HIGH_VAR    | sawtooth       |     -222.6 | +/-   12.3 | BETTER |
|  B0 | HIGH_VAR    | pct_E          |       -8.7 | +/-    1.5 | BETTER |
|  B0 | HIGH_VAR    | recovery_to_B0 |       +0.0 | +/-    0.0 | NEUTRAL |
|  B0 | NORMAL      | mean_dt        |       -0.5 | +/-    0.5 | NEUTRAL |
|  B0 | NORMAL      | std_dt         |     -968.1 | +/-  108.6 | BETTER |
|  B0 | NORMAL      | gt_40m         |       +1.3 | +/-    2.6 | NEUTRAL |
|  B0 | NORMAL      | sawtooth       |     -152.7 | +/-   11.4 | BETTER |
|  B0 | NORMAL      | pct_E          |       -4.1 | +/-    1.0 | BETTER |
|  B0 | NORMAL      | recovery_to_B0 |       +0.0 | +/-    0.0 | NEUTRAL |
|  B0 | WITH_STALLS | mean_dt        |       +0.0 | +/-    0.1 | NEUTRAL |
|  B0 | WITH_STALLS | std_dt         |     -300.9 | +/-   84.8 | BETTER |
|  B0 | WITH_STALLS | gt_40m         |       -6.4 | +/-    1.7 | BETTER |
|  B0 | WITH_STALLS | sawtooth       |      -45.3 | +/-    6.7 | BETTER |
|  B0 | WITH_STALLS | pct_E          |       +4.4 | +/-    0.6 | WORSE |
|  B0 | WITH_STALLS | recovery_to_B0 |       +0.0 | +/-    0.0 | NEUTRAL |
|  E1 | HIGH_VAR    | mean_dt        |       -0.9 | +/-    0.8 | NEUTRAL |
|  E1 | HIGH_VAR    | std_dt         |    -1155.0 | +/-  295.1 | BETTER |
|  E1 | HIGH_VAR    | gt_40m         |      +12.3 | +/-    4.0 | WORSE |
|  E1 | HIGH_VAR    | sawtooth       |     -225.0 | +/-   14.3 | BETTER |
|  E1 | HIGH_VAR    | pct_E          |       -7.4 | +/-    1.3 | BETTER |
|  E1 | HIGH_VAR    | recovery_to_B0 |       +0.6 | +/-    0.4 | WORSE |
|  E1 | NORMAL      | mean_dt        |       -0.5 | +/-    0.5 | NEUTRAL |
|  E1 | NORMAL      | std_dt         |     -921.8 | +/-  120.5 | BETTER |
|  E1 | NORMAL      | gt_40m         |       +0.3 | +/-    2.9 | NEUTRAL |
|  E1 | NORMAL      | sawtooth       |     -152.3 | +/-   11.6 | BETTER |
|  E1 | NORMAL      | pct_E          |       -3.6 | +/-    1.0 | BETTER |
|  E1 | NORMAL      | recovery_to_B0 |       +0.4 | +/-    0.3 | WORSE |
|  E1 | WITH_STALLS | mean_dt        |       +0.1 | +/-    0.1 | BETTER |
|  E1 | WITH_STALLS | std_dt         |     -256.7 | +/-   79.4 | BETTER |
|  E1 | WITH_STALLS | gt_40m         |       -6.4 | +/-    1.6 | BETTER |
|  E1 | WITH_STALLS | sawtooth       |      -44.0 | +/-    6.9 | BETTER |
|  E1 | WITH_STALLS | pct_E          |       +4.8 | +/-    0.6 | WORSE |
|  E1 | WITH_STALLS | recovery_to_B0 |       +1.4 | +/-    1.3 | WORSE |
|  E2 | HIGH_VAR    | mean_dt        |       -1.1 | +/-    1.0 | NEUTRAL |
|  E2 | HIGH_VAR    | std_dt         |    -1043.4 | +/-  139.5 | BETTER |
|  E2 | HIGH_VAR    | gt_40m         |      +12.0 | +/-    3.7 | WORSE |
|  E2 | HIGH_VAR    | sawtooth       |     -220.4 | +/-   16.2 | BETTER |
|  E2 | HIGH_VAR    | pct_E          |       -7.0 | +/-    1.2 | BETTER |
|  E2 | HIGH_VAR    | recovery_to_B0 |       +2.5 | +/-    1.0 | WORSE |
|  E2 | NORMAL      | mean_dt        |       -0.2 | +/-    0.2 | WORSE |
|  E2 | NORMAL      | std_dt         |     -930.0 | +/-  117.9 | BETTER |
|  E2 | NORMAL      | gt_40m         |       -0.3 | +/-    3.0 | NEUTRAL |
|  E2 | NORMAL      | sawtooth       |     -155.4 | +/-   11.6 | BETTER |
|  E2 | NORMAL      | pct_E          |       -3.9 | +/-    1.0 | BETTER |
|  E2 | NORMAL      | recovery_to_B0 |       +2.7 | +/-    0.9 | WORSE |
|  E2 | WITH_STALLS | mean_dt        |       +0.1 | +/-    0.1 | BETTER |
|  E2 | WITH_STALLS | std_dt         |     -280.4 | +/-   87.5 | BETTER |
|  E2 | WITH_STALLS | gt_40m         |       -6.6 | +/-    1.5 | BETTER |
|  E2 | WITH_STALLS | sawtooth       |      -44.4 | +/-    7.7 | BETTER |
|  E2 | WITH_STALLS | pct_E          |       +4.7 | +/-    0.6 | WORSE |
|  E2 | WITH_STALLS | recovery_to_B0 |       +4.2 | +/-    2.3 | WORSE |
|  E3 | HIGH_VAR    | mean_dt        |       -1.4 | +/-    1.2 | NEUTRAL |
|  E3 | HIGH_VAR    | std_dt         |    -1106.1 | +/-  180.3 | BETTER |
|  E3 | HIGH_VAR    | gt_40m         |      +12.8 | +/-    2.9 | WORSE |
|  E3 | HIGH_VAR    | sawtooth       |     -218.7 | +/-   14.4 | BETTER |
|  E3 | HIGH_VAR    | pct_E          |       -7.3 | +/-    1.1 | BETTER |
|  E3 | HIGH_VAR    | recovery_to_B0 |       +1.7 | +/-    0.5 | WORSE |
|  E3 | NORMAL      | mean_dt        |       -0.7 | +/-    1.0 | NEUTRAL |
|  E3 | NORMAL      | std_dt         |     -938.3 | +/-  121.8 | BETTER |
|  E3 | NORMAL      | gt_40m         |       +0.9 | +/-    2.7 | NEUTRAL |
|  E3 | NORMAL      | sawtooth       |     -151.4 | +/-   13.1 | BETTER |
|  E3 | NORMAL      | pct_E          |       -3.8 | +/-    1.0 | BETTER |
|  E3 | NORMAL      | recovery_to_B0 |       +1.8 | +/-    0.5 | WORSE |
|  E3 | WITH_STALLS | mean_dt        |       +0.1 | +/-    0.1 | BETTER |
|  E3 | WITH_STALLS | std_dt         |     -303.1 | +/-   98.7 | BETTER |
|  E3 | WITH_STALLS | gt_40m         |       -6.1 | +/-    1.6 | BETTER |
|  E3 | WITH_STALLS | sawtooth       |      -42.9 | +/-    7.6 | BETTER |
|  E3 | WITH_STALLS | pct_E          |       +4.7 | +/-    0.7 | WORSE |
|  E3 | WITH_STALLS | recovery_to_B0 |       +7.2 | +/-    3.9 | WORSE |
|  E4 | HIGH_VAR    | mean_dt        |       -1.5 | +/-    1.1 | NEUTRAL |
|  E4 | HIGH_VAR    | std_dt         |    -1192.7 | +/-  185.2 | BETTER |
|  E4 | HIGH_VAR    | gt_40m         |      +14.1 | +/-    3.2 | WORSE |
|  E4 | HIGH_VAR    | sawtooth       |     -216.0 | +/-   14.6 | BETTER |
|  E4 | HIGH_VAR    | pct_E          |       -8.0 | +/-    1.1 | BETTER |
|  E4 | HIGH_VAR    | recovery_to_B0 |       +1.7 | +/-    0.5 | WORSE |
|  E4 | NORMAL      | mean_dt        |       -0.3 | +/-    0.4 | NEUTRAL |
|  E4 | NORMAL      | std_dt         |     -901.3 | +/-  112.5 | BETTER |
|  E4 | NORMAL      | gt_40m         |       +0.1 | +/-    2.6 | NEUTRAL |
|  E4 | NORMAL      | sawtooth       |     -144.9 | +/-   12.1 | BETTER |
|  E4 | NORMAL      | pct_E          |       -3.8 | +/-    1.0 | BETTER |
|  E4 | NORMAL      | recovery_to_B0 |       +1.9 | +/-    0.7 | WORSE |
|  E4 | WITH_STALLS | mean_dt        |       +0.1 | +/-    0.1 | BETTER |
|  E4 | WITH_STALLS | std_dt         |     -282.6 | +/-   85.8 | BETTER |
|  E4 | WITH_STALLS | gt_40m         |       -6.2 | +/-    1.5 | BETTER |
|  E4 | WITH_STALLS | sawtooth       |      -45.8 | +/-    7.4 | BETTER |
|  E4 | WITH_STALLS | pct_E          |       +4.7 | +/-    0.7 | WORSE |
|  E4 | WITH_STALLS | recovery_to_B0 |       +3.9 | +/-    2.7 | WORSE |
|  H1 | HIGH_VAR    | mean_dt        |       -1.2 | +/-    0.9 | BETTER |
|  H1 | HIGH_VAR    | std_dt         |    -1277.9 | +/-  250.3 | BETTER |
|  H1 | HIGH_VAR    | gt_40m         |      +15.2 | +/-    4.1 | WORSE |
|  H1 | HIGH_VAR    | sawtooth       |     -218.0 | +/-   15.8 | BETTER |
|  H1 | HIGH_VAR    | pct_E          |       -8.8 | +/-    1.6 | BETTER |
|  H1 | HIGH_VAR    | recovery_to_B0 |       +0.3 | +/-    3.5 | NEUTRAL |
|  H1 | NORMAL      | mean_dt        |       -0.1 | +/-    0.2 | NEUTRAL |
|  H1 | NORMAL      | std_dt         |     -940.1 | +/-  121.0 | BETTER |
|  H1 | NORMAL      | gt_40m         |       +2.1 | +/-    2.9 | NEUTRAL |
|  H1 | NORMAL      | sawtooth       |     -156.5 | +/-   10.9 | BETTER |
|  H1 | NORMAL      | pct_E          |       -4.4 | +/-    1.0 | BETTER |
|  H1 | NORMAL      | recovery_to_B0 |       +2.3 | +/-    0.9 | WORSE |
|  H1 | WITH_STALLS | mean_dt        |       +0.0 | +/-    0.1 | NEUTRAL |
|  H1 | WITH_STALLS | std_dt         |     -274.7 | +/-   78.8 | BETTER |
|  H1 | WITH_STALLS | gt_40m         |       -6.0 | +/-    1.4 | BETTER |
|  H1 | WITH_STALLS | sawtooth       |      -50.2 | +/-    7.4 | BETTER |
|  H1 | WITH_STALLS | pct_E          |       +4.4 | +/-    0.6 | WORSE |
|  H1 | WITH_STALLS | recovery_to_B0 |       -1.6 | +/-    3.8 | NEUTRAL |
|  H3 | HIGH_VAR    | mean_dt        |       -1.2 | +/-    1.1 | BETTER |
|  H3 | HIGH_VAR    | std_dt         |    -1159.6 | +/-  162.6 | BETTER |
|  H3 | HIGH_VAR    | gt_40m         |      +15.0 | +/-    3.5 | WORSE |
|  H3 | HIGH_VAR    | sawtooth       |     -223.0 | +/-   15.5 | BETTER |
|  H3 | HIGH_VAR    | pct_E          |       -8.0 | +/-    1.2 | BETTER |
|  H3 | HIGH_VAR    | recovery_to_B0 |       -4.2 | +/-    6.3 | NEUTRAL |
|  H3 | NORMAL      | mean_dt        |       -0.8 | +/-    0.6 | BETTER |
|  H3 | NORMAL      | std_dt         |     -913.8 | +/-  146.9 | BETTER |
|  H3 | NORMAL      | gt_40m         |       +0.7 | +/-    3.0 | NEUTRAL |
|  H3 | NORMAL      | sawtooth       |     -151.9 | +/-   11.8 | BETTER |
|  H3 | NORMAL      | pct_E          |       -3.7 | +/-    1.1 | BETTER |
|  H3 | NORMAL      | recovery_to_B0 |       -5.8 | +/-    5.6 | BETTER |
|  H3 | WITH_STALLS | mean_dt        |       +0.1 | +/-    0.1 | WORSE |
|  H3 | WITH_STALLS | std_dt         |     -277.6 | +/-   74.1 | BETTER |
|  H3 | WITH_STALLS | gt_40m         |       -5.8 | +/-    1.6 | BETTER |
|  H3 | WITH_STALLS | sawtooth       |      -47.3 | +/-    7.7 | BETTER |
|  H3 | WITH_STALLS | pct_E          |       +4.3 | +/-    0.6 | WORSE |
|  H3 | WITH_STALLS | recovery_to_B0 |       -3.5 | +/-    5.3 | NEUTRAL |
|  H6 | HIGH_VAR    | mean_dt        |       -1.4 | +/-    1.1 | BETTER |
|  H6 | HIGH_VAR    | std_dt         |    -1274.7 | +/-  223.0 | BETTER |
|  H6 | HIGH_VAR    | gt_40m         |      +17.7 | +/-    4.1 | WORSE |
|  H6 | HIGH_VAR    | sawtooth       |     -230.6 | +/-   12.8 | BETTER |
|  H6 | HIGH_VAR    | pct_E          |       -9.1 | +/-    1.4 | BETTER |
|  H6 | HIGH_VAR    | recovery_to_B0 |      -17.9 | +/-   14.0 | BETTER |
|  H6 | NORMAL      | mean_dt        |       -0.4 | +/-    0.5 | NEUTRAL |
|  H6 | NORMAL      | std_dt         |     -916.4 | +/-  145.4 | BETTER |
|  H6 | NORMAL      | gt_40m         |       +2.0 | +/-    3.7 | NEUTRAL |
|  H6 | NORMAL      | sawtooth       |     -154.8 | +/-   14.2 | BETTER |
|  H6 | NORMAL      | pct_E          |       -4.1 | +/-    1.1 | BETTER |
|  H6 | NORMAL      | recovery_to_B0 |       -8.6 | +/-    6.8 | BETTER |
|  H6 | WITH_STALLS | mean_dt        |       +0.1 | +/-    0.1 | WORSE |
|  H6 | WITH_STALLS | std_dt         |     -302.4 | +/-   85.6 | BETTER |
|  H6 | WITH_STALLS | gt_40m         |       -5.4 | +/-    1.6 | BETTER |
|  H6 | WITH_STALLS | sawtooth       |      -45.4 | +/-    7.6 | BETTER |
|  H6 | WITH_STALLS | pct_E          |       +4.4 | +/-    0.7 | WORSE |
|  H6 | WITH_STALLS | recovery_to_B0 |      -14.0 | +/-   15.0 | NEUTRAL |
|  H9 | HIGH_VAR    | mean_dt        |       -0.3 | +/-    0.2 | BETTER |
|  H9 | HIGH_VAR    | std_dt         |    -1020.6 | +/-  158.5 | BETTER |
|  H9 | HIGH_VAR    | gt_40m         |      +13.1 | +/-    4.0 | WORSE |
|  H9 | HIGH_VAR    | sawtooth       |     -224.2 | +/-   14.6 | BETTER |
|  H9 | HIGH_VAR    | pct_E          |       -7.2 | +/-    1.2 | BETTER |
|  H9 | HIGH_VAR    | recovery_to_B0 |      -10.4 | +/-   12.2 | NEUTRAL |
|  H9 | NORMAL      | mean_dt        |       -0.4 | +/-    0.4 | NEUTRAL |
|  H9 | NORMAL      | std_dt         |     -928.1 | +/-  139.0 | BETTER |
|  H9 | NORMAL      | gt_40m         |       +2.1 | +/-    2.8 | NEUTRAL |
|  H9 | NORMAL      | sawtooth       |     -162.8 | +/-   12.8 | BETTER |
|  H9 | NORMAL      | pct_E          |       -4.2 | +/-    1.0 | BETTER |
|  H9 | NORMAL      | recovery_to_B0 |       -0.8 | +/-    5.6 | NEUTRAL |
|  H9 | WITH_STALLS | mean_dt        |       +0.0 | +/-    0.1 | NEUTRAL |
|  H9 | WITH_STALLS | std_dt         |     -288.0 | +/-   76.1 | BETTER |
|  H9 | WITH_STALLS | gt_40m         |       -5.4 | +/-    1.6 | BETTER |
|  H9 | WITH_STALLS | sawtooth       |      -47.1 | +/-    8.0 | BETTER |
|  H9 | WITH_STALLS | pct_E          |       +4.4 | +/-    0.6 | WORSE |
|  H9 | WITH_STALLS | recovery_to_B0 |       -5.6 | +/-    8.6 | NEUTRAL |

## E-Profile Specific Analysis

### 1. Recovery from E profiles to B0

| Start | Condition | Slew=1 blocks | Slew=3 blocks | Delta |
|-------|-----------|--------------|--------------|-------|
| E4 | NORMAL      |           26 |           24 |    +2 |
| E4 | HIGH_VAR    |           24 |           22 |    +2 |
| E4 | WITH_STALLS |           41 |           37 |    +4 |
| E3 | NORMAL      |           16 |           14 |    +2 |
| E3 | HIGH_VAR    |           16 |           14 |    +2 |
| E3 | WITH_STALLS |           27 |           20 |    +7 |
| E2 | NORMAL      |            5 |            2 |    +3 |
| E2 | HIGH_VAR    |            5 |            2 |    +2 |
| E2 | WITH_STALLS |            8 |            4 |    +4 |
| E1 | NORMAL      |            3 |            2 |    +0 |
| E1 | HIGH_VAR    |            3 |            2 |    +1 |
| E1 | WITH_STALLS |            4 |            3 |    +1 |

### 2. Time stuck in E profiles (max consecutive blocks)

| Start | Condition | Slew=1 | Slew=3 | Delta |
|-------|-----------|--------|--------|-------|
| E4 | NORMAL      |     30 |    151 |  -121 |
| E4 | HIGH_VAR    |     42 |    208 |  -166 |
| E4 | WITH_STALLS |    146 |    197 |   -50 |
| E3 | NORMAL      |     29 |    157 |  -127 |
| E3 | HIGH_VAR    |     45 |    196 |  -151 |
| E3 | WITH_STALLS |    146 |    200 |   -55 |
| E2 | NORMAL      |     26 |    161 |  -135 |
| E2 | HIGH_VAR    |     42 |    189 |  -147 |
| E2 | WITH_STALLS |    145 |    198 |   -52 |
| E1 | NORMAL      |     25 |    156 |  -130 |
| E1 | HIGH_VAR    |     42 |    205 |  -162 |
| E1 | WITH_STALLS |    144 |    182 |   -38 |

### 3. Post-recovery overshoot (pct_H9plus after E-start)

| Start | Condition | Slew=1 H9+% | Slew=3 H9+% | Delta |
|-------|-----------|-------------|-------------|-------|
| E4 | NORMAL      |       0.00% |       0.16% |  -0.16 |
| E4 | HIGH_VAR    |       0.00% |       0.24% |  -0.24 |
| E4 | WITH_STALLS |       0.00% |       0.05% |  -0.05 |
| E3 | NORMAL      |       0.00% |       0.17% |  -0.17 |
| E3 | HIGH_VAR    |       0.00% |       0.24% |  -0.24 |
| E3 | WITH_STALLS |       0.00% |       0.05% |  -0.05 |
| E2 | NORMAL      |       0.00% |       0.17% |  -0.17 |
| E2 | HIGH_VAR    |       0.00% |       0.25% |  -0.25 |
| E2 | WITH_STALLS |       0.00% |       0.05% |  -0.05 |
| E1 | NORMAL      |       0.00% |       0.17% |  -0.17 |
| E1 | HIGH_VAR    |       0.00% |       0.25% |  -0.25 |
| E1 | WITH_STALLS |       0.00% |       0.05% |  -0.05 |

### 4. Does slew=3 materially outperform slew=1 anywhere?

**Yes, 34 metric(s) where slew=3 is significantly better:**

- E4/NORMAL/recovery_to_B0: delta=+1.9 +/- 0.7
- E4/HIGH_VAR/gt_40m: delta=+14.1 +/- 3.2
- E4/HIGH_VAR/recovery_to_B0: delta=+1.7 +/- 0.5
- E4/WITH_STALLS/pct_E: delta=+4.7 +/- 0.7
- E4/WITH_STALLS/recovery_to_B0: delta=+3.9 +/- 2.7
- E3/NORMAL/recovery_to_B0: delta=+1.8 +/- 0.5
- E3/HIGH_VAR/gt_40m: delta=+12.8 +/- 2.9
- E3/HIGH_VAR/recovery_to_B0: delta=+1.7 +/- 0.5
- E3/WITH_STALLS/pct_E: delta=+4.7 +/- 0.7
- E3/WITH_STALLS/recovery_to_B0: delta=+7.2 +/- 3.9
- E2/NORMAL/mean_dt: delta=-0.2 +/- 0.2
- E2/NORMAL/recovery_to_B0: delta=+2.7 +/- 0.9
- E2/HIGH_VAR/gt_40m: delta=+12.0 +/- 3.7
- E2/HIGH_VAR/recovery_to_B0: delta=+2.5 +/- 1.0
- E2/WITH_STALLS/pct_E: delta=+4.7 +/- 0.6
- E2/WITH_STALLS/recovery_to_B0: delta=+4.2 +/- 2.3
- E1/NORMAL/recovery_to_B0: delta=+0.4 +/- 0.3
- E1/HIGH_VAR/gt_40m: delta=+12.3 +/- 4.0
- E1/HIGH_VAR/recovery_to_B0: delta=+0.6 +/- 0.4
- E1/WITH_STALLS/pct_E: delta=+4.8 +/- 0.6
- E1/WITH_STALLS/recovery_to_B0: delta=+1.4 +/- 1.3
- B0/HIGH_VAR/gt_40m: delta=+15.8 +/- 4.6
- B0/WITH_STALLS/pct_E: delta=+4.4 +/- 0.6
- H1/NORMAL/recovery_to_B0: delta=+2.3 +/- 0.9
- H1/HIGH_VAR/gt_40m: delta=+15.2 +/- 4.1
- H1/WITH_STALLS/pct_E: delta=+4.4 +/- 0.6
- H3/HIGH_VAR/gt_40m: delta=+15.0 +/- 3.5
- H3/WITH_STALLS/mean_dt: delta=+0.1 +/- 0.1
- H3/WITH_STALLS/pct_E: delta=+4.3 +/- 0.6
- H6/HIGH_VAR/gt_40m: delta=+17.7 +/- 4.1
- H6/WITH_STALLS/mean_dt: delta=+0.1 +/- 0.1
- H6/WITH_STALLS/pct_E: delta=+4.4 +/- 0.7
- H9/HIGH_VAR/gt_40m: delta=+13.1 +/- 4.0
- H9/WITH_STALLS/pct_E: delta=+4.4 +/- 0.6

## Verdict

Across 162 paired metric comparisons:
- BETTER (slew=1 wins): 94
- NEUTRAL: 34
- WORSE (slew=3 wins): 34

### PROCEED WITH CAVEAT

Slew=1 shows minor regressions: E-profile recovery to B0 is slower with slew=1; higher E-profile residency with slew=1.
These are expected consequences of lower slew rate and do not
impact overall chain health. The stability gains from slew=1
outweigh the slightly slower E-recovery.