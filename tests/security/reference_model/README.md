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

## cASERT / difficulty — real finding (executed, NOT passed)
Ran the project's existing parity validator `scripts/validate_simulator_parity.py`
(cASERT sim v5_simulator.py vs src/pow/casert.cpp + params.h):
- 16/18 constants PASS (2 FAIL: H_MIN/H_MAX profile-range differ), behavioural 5/5 PASS,
- but **2 HIGH logic divergences**: the Python sim uses a simplified PID (lag*0.25) vs the
  C++ 5-term PID with EWMA (K_L=0.40 etc.), and does NOT model bitsQ. Verdict: **LOW confidence**.
Conclusion: the existing Python cASERT is a *behavioural* model, not a consensus-exact replica.
A **bit-exact independent cASERT reference** (replicating the exact integer PID/EWMA/bitsQ math,
same as done for subsidy) is a real, sizeable **PENDING** Phase C item — not marked passed.
