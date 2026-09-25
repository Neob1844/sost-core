# Phase C — Independent reference model (differential testing)

Goal: a small, independent implementation that recomputes SOST's rules, and
differential tests C++ SOST == reference model. A divergence must stop the release.

## Done (real, executed)
- **subsidy(height) + cumulative_emission(height)** — `subsidy_model.py`, reimplemented
  from spec. Differential vs the real `src/subsidy.cpp` (`subsidy_dump.cpp`) over 30,307
  heights (dense 0..30000, epoch boundaries ±2 to ~7.9M, samples to 50M, supply-cap
  region): **0 divergences**. Also validated against the LIVE chain: model
  cumulative_emission(26973) == node getsupplyinfo total_supply_stocks (21177310678562).
  Runner: `run_subsidy_diff.sh` (exits non-zero on any divergence).

## Pending (to model + differential-test next)
- cASERT / difficulty (bits_q) transition
- DTD eligibility (window, cooldown, anti-dominance)
- Jackpot V2 eligibility (NODE_BIND + PoW weight + heartbeat ramp)
- NODE_BIND state machine; heartbeat epoch state
- simplified UTXO transition
