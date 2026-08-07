# V15 Release — OPTION B (V15 + EVM + real BTC Atomic Swap)

**Same code as Option A, plus the real libwally BTC signing backend compiled in.** Build with
`SOST_BTC_HTLC_SIGNING=ON` AND enable at runtime with `SOST_BTC_ATOMIC_SWAP_ENABLED=1`.

## State (honest)
- BTC signing (funding / claim / refund / serialization / witness / txid / preimage extraction) is a
  **real libwally-core implementation** — **compiles clean** and its unit suite is **121/0** (structure/
  logic). See BTC_HTLC_COMPLETION_PLAN.md.
- Broadcast is **operator-side** (the tooling emits signed raw hex; the operator broadcasts via their own
  Bitcoin node) — consistent with the SOST-side CLI design. No bitcoind is embedded in the SOST node.
- Runtime gate: `IsBtcHtlcSigningEnabled()` = OFF by default even in an ON build; requires the explicit
  `SOST_BTC_ATOMIC_SWAP_ENABLED=1` opt-in.

## THE BLOCKER (why Option B is NOT ready)
The BTC signing has **never been validated against a real Bitcoin node** (no bitcoind-regtest round-trip;
the owner waived heavy validation / no second machine). A subtle sighash/serialization error is a silent
fund-loss. **Do NOT enable Option B for real funds until:** fund → lock → confirm → redeem-with-preimage,
and timeout → refund, plus adversarial cases, all PASS on bitcoind regtest.

## Build (do NOT deploy yet)
```
cmake -S . -B build-btc-on -DCMAKE_BUILD_TYPE=Release -DSOST_BTC_HTLC_SIGNING=ON
cmake --build build-btc-on --target sost-node sost-cli sost-miner sost-signtx
# runtime (only after regtest validation): export SOST_BTC_ATOMIC_SWAP_ENABLED=1
```
External requirements (Option B only): a Bitcoin node the operator broadcasts through, network choice,
confirmations/fees/timeout parameters, credentials via the operator's secret store (NEVER in Git).

**OPTION B: NOT READY — BTC code buildable + unit-green but UNVALIDATED (needs bitcoind regtest).**
