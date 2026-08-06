# Failures log

No unresolved failures. Notes on handled issues:
- soak runner arg-passing bug (harness args folded into path) — FIXED b242d4ea, soak rerun 18/18 PASS.
- rollover phase-2 winner-forcing infeasible in DEV (single dominant miner >80% excluded + late miner in exclusion window) — REFRAMED to reserve-preservation proof; winner-spend covered by run_v15_devnet_payout.sh.
