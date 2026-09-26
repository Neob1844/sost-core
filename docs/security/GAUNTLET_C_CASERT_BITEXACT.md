# Gauntlet C — cASERT bit-exact independent differential (ACTIVE regime)

Closes the gap the earlier Phase-C note flagged: the previous Python cASERT sim was
*behavioral* (LOW-confidence parity). This is an **independent bit-exact reimplementation**
of the difficulty controller, diffed against the REAL `sost::casert_next_bitsq`.

## Scope
The **active consensus regime** that governs every current and future block through the
#30,000 fork: `next_height >= 5270` avg288 proportional controller + V11 slingshot
(5270 ≤ h < 7350) + V12 slingshot (h ≥ 7350). cASERT is integer-deterministic (fixed-point
`log2_q16`/`horner_2exp`; the active path is pure integer arithmetic), so bit-exact
reproduction is well-defined.

Out of scope (historical, already validated by the live chain — every real block below 5270
was accepted by mainnet): pre-V6PP anchor-based exponential, the V2/V4/V5 ahead-guard and
burst-guard, and the 5175–5269 median era. Noted, not independently re-modeled.

## Method
- `dump.cpp` builds 289-block synthetic chains and calls the real `casert_next_bitsq` over a
  systematic grid: prev_bitsq ∈ {MIN, MIN+50, 200k, GENESIS, 3M, MAX-100, MAX}; heights
  {5270, 6000, 7349, 7350, 20000, 29900, 30000, 40000}; constant intervals ∈ {1,300,570,585,
  600,615,630,660,720,840,1000,2000,90000} and two-value interval pairs (avg-truncation);
  slingshot elapsed bands straddling every threshold (1200/1800/3600/7200/10800, strict >).
- `model.py` recomputes the result independently (same window→287 intervals, dt clamp
  [1,86400], avg truncation, tiered caps, proportional correction, MIN/MAX clamp, V11/V12
  slingshot) and diffs against the C++ output.

## Result
**14,896 vectors, 0 divergences — BIT-EXACT PASS.** Covers all deviation tiers, dt clamps,
cap tiers (dead-band/0.5/1/2/3%), proportional-vs-cap interplay, MIN/MAX saturation, avg
truncation, and every slingshot tier.

## Reorg-safety
The active cASERT path is a **pure function** of the last-288 block metas (time, powDiffQ,
profile) — it holds **no static/hidden state** (unlike the historical V4 ahead-guard, which
used a `static bool` and was made stateless at V5/height≥4500). Therefore a reorg is simply a
recompute over the new active chain and yields a deterministic result; there is no cross-sync
divergence surface in the active regime.

## Reproduce
`tests/security/casert_differential/run.sh <repo-root>` → prints `divergencias: 0`.
