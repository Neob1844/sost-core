# V15 Release — OPTION A (V15 + EVM Atomic Swap, BTC OFF)

**This is the immediate, deployable release and the permanent fallback.** Build with the default
flags (`SOST_BTC_HTLC_SIGNING=OFF`). BTC HTLC is absent/fail-closed; no bitcoind dependency.

## What is ON
- V15 consensus @ **25000** (DTD 50/50, emission transition, Historical Jackpot first @ **25290**).
- EVM Atomic Swap HTLC — live @ **16000** (relay 17000); Foundry 57/57; policy/dashboard corrected.

## What is OFF
- **BTC Atomic Swap = DISABLED.** The production binary contains **no libwally / no BTC signing symbols**
  (verified: 0 in build/sost-node). BTC cannot be activated in this build. Dashboard shows BTC as
  disabled/coming-soon. Release notes must state: **BTC Atomic Swap: NOT ENABLED IN THIS RELEASE.**

## Build
```
cmake -S . -B build-rc -DCMAKE_BUILD_TYPE=Release          # SOST_BTC_HTLC_SIGNING defaults OFF
cmake --build build-rc --target sost-node sost-cli sost-miner sost-signtx
```
No bitcoind, no BTC credentials, no external Bitcoin infra required. Node builds + runs + serves V15
with zero Bitcoin dependency.

## Validation status (owner-waived heavy tests)
V15 consensus: attack matrix / rollover / reserve / payout / boundary / reorg-restart-reindex / mainnet
+ testnet ctest — GREEN. Heavy suites (pre-V15 compat, ASan/UBSan full, long SbPoW) = WAIVED_BY_OWNER.
EVM external audit = WAITING_EXTERNAL_AUDIT (does not block Option A shipping with BTC OFF).

**OPTION A: READY for deployment preparation.**
