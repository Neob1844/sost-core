# Remaining V15 gates — exact commands (run on a NON-miner-saturated box)

Everything here is engineering that this session could not finish ONLY because this box runs the
13-thread mainnet miner (CPU-saturated) or lacks a tool. Each block is copy-paste runnable on a
clean checkout of `feat/v15-jackpot-explorer-card` at HEAD. Pipe each to a log under
`artifacts/v15-final-validation/`. `main` stays untouched until GATE_STATUS.md is all GREEN.

## Gate #6/#7 — ASan + UBSan (full)
Consensus-arithmetic subset is scripted (fast, bounded):
```
bash artifacts/v15-final-validation/run_sanitizer_consensus_tests.sh   # test-jackpot/rollover/dtd/eligibility/frequency under ASan+UBSan
```
Full node/harness under sanitizers (heavy — clean box):
```
cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address,undefined"
cmake --build build-asan -j"$(nproc)"
ctest --test-dir build-asan --output-on-failure --timeout 1200      # all unit/integration under ASan/UBSan
```

## Gate #8 — static analysis (needs the tool; not installed on this box)
```
sudo apt-get install -y cppcheck            # or clang-tidy
cppcheck --enable=warning,performance,portability --error-exitcode=2 \
  --suppress=missingIncludeSystem -I include src/sost-node.cpp src/sost-miner.cpp 2>cppcheck.log
# clang-tidy path: build with -DCMAKE_EXPORT_COMPILE_COMMANDS=ON then run clang-tidy over changed files.
```
Requirement: no critical/high findings on the V15 consensus + miner changes.

## Gate #9 — pre-V15 compatibility (cross-build old vs new)
Prove the new binary agrees with the deployed binary on ALL state strictly below the fork.
```
git worktree add ../sost-old <DEPLOYED_TAG_OR_COMMIT>     # e.g. the v0.3.2 tag actually deployed
cmake -S ../sost-old -B ../sost-old/build && cmake --build ../sost-old/build --target sost-node -j"$(nproc)"
# Mine a chain BELOW the mainnet fork height with the OLD node; then point the NEW node at that
# chain dir and confirm it validates/reindexes with an identical tip hash and zero rejected blocks.
# (In DEVNET_FAST the fork is height 18 — the DEV harnesses already cross it; this gate is the
#  MAINNET-height cross-binary check that can only be done with the real deployed binary.)
```

## Gate #5 (finish) — testnet-profile ctest
```
cmake -S . -B build-testnet -DSOST_TESTNET_FORKS=... && cmake --build build-testnet -j"$(nproc)"
ctest --test-dir build-testnet --output-on-failure
```

## Gate #12 — testnet long SbPoW run (~8.5 h, real not declared)
Bring up a testnet node+miner with V15 at a near height (e.g. 12500) and let it run through the
activation for several hours; assert: crosses V15, jackpot cadence fires, no stall/reject/fork,
memory flat. This is the ~8.5 h external-machine run — must be REAL.

## Gate #13/#17 — RC packaging (only AFTER every gate above is GREEN)
```
# from clean main after: git merge --no-ff feat/v15-jackpot-explorer-card
git tag -a <v0.4.0-v15> -m "V15 activation release"
cmake -S . -B build-rc -DCMAKE_BUILD_TYPE=Release && cmake --build build-rc -j"$(nproc)"
sha256sum build-rc/sost-node build-rc/sost-miner build-rc/sost-cli build-rc/sost-signtx > MANIFEST.sha256
# verify NO dev symbols in production binaries:
for b in sost-node sost-miner sost-cli; do
  strings build-rc/$b | grep -E 'devjackpotstate|devsetreorgfailpoint|devchainstate|inject-tx-at1|attack-jackpot|dump-block' \
    && echo "LEAK in $b" || echo "$b clean"
done
# then re-run: bash tests/run_v15_devnet_quick.sh  (GO)  ← from main
```
Then follow `RUNBOOK_CUTOVER.md` for the supervised window (24,900–25,000).

## Not a blocker (honest)
Attack-map #14 (accumulation↔winner reorg transition) needs a DEV miner that can mine as N
addresses (multi-address winner control). Nice-to-have coverage; the winner-binding itself is
already proven by `coinbase-mutate` + the reorg harness. Track as a future add.
