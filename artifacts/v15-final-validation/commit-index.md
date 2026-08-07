# V15 validation — commit index

28a2c82c docs(v15): T-24900 engineering-freeze timeline + rigorous per-assertion multi-block coverage audit (5 FULL / 4 PARTIAL / 5 NONE)
ea44a761 docs(v15): register changed end-goal (merge to main + coordinated deploy before 25000) + GO gates + multi-block scenario coverage mapping
531cb46f chore(v15): update handoff after V15-A partial (attack matrix 17-case) → next step recorded
f23afb4b test(v15): extend valid-PoW attack matrix with 4 new single-mutations
e4da908b chore(v15): set up autonomous-validation tracking + attack-matrix inventory (phase 0)
039dbbb3 docs: DEV functional soak complete (18/18 PASS, 3 rounds, no leak)
165a8b2c docs: record reindex/load_chain + rollover proofs and soak status in V15 readiness
afb3f29d V15: add Historical-Jackpot rollover coverage (no-winner events preserve the reserve)
b6410ff0 V15: add Historical-Jackpot reindex/load_chain equivalence + tamper rejection
b242d4ea tests: fix soak runner arg-passing (harness args were folded into the script path)
bb1cf8f8 tests: add V15 DEV functional soak harness (loops proven harnesses, tracks metrics/leaks)
09676b9b docs: record proven V15 reorg lifecycle (failed-reorg atomicity, restart, failpoint isolation)
cecaa8b0 V15: add Historical-Jackpot process-restart coverage (DEVNET_FAST)
ecccd704 V15: prove failed-reorg rollback atomicity (DEV failpoint + zero-drift harness)
960afb6d node: fix V15 jackpot-reorg deadlock + undo-vector misalignment (3 root causes)
92991f57 feat(devnet): add isolated raw jackpot injection support (--inject-tx-at1, count=0 mainnet/testnet)
fec1acbb feat(devnet): add devjackpotstate RPC for numeric rollover introspection (DEV-only, isolated)
06fe4219 test(v15): reject jackpot at non-event height (M02) + stale replay (M03) + rollover-cap 100->500->500
