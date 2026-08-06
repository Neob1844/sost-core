# V15 validation — commit index (feat/v15-jackpot-explorer-card)

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
