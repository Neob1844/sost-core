# SOST V15 — release notes (candidate)

**Activation: mainnet block 25000** (testnet 12500, DEVNET_FAST 18). The currently deployed binary
is **v0.3.2**, which ships the V15 gates DEFERRED — reaching 25000 with it activates nothing. The
network must run the V15 binary (this candidate) BEFORE 25000; see V15_ROLLOUT.md.

## What activates at 25000
1. **Emission transition (T).** From height ≥ 25000, non-lottery-triggered blocks stop funding the
   Gold Vault and PoPC pool; the former non-miner half is redirected to the DTD lottery pending
   (miner-only `UPDATE` coinbase shape — no miner-side change). Total subsidy is unchanged; nothing
   new is minted. Pre-25000 blocks keep the NORMAL 50/25/25 split, byte-identical to pre-V15.
2. **Historical DTD Jackpot (J).** Starting at height **25290** (V15 + 290, DTD-draw-aligned), on a
   cadence, one canonical `TX_TYPE_JACKPOT` may spend the keyless Gold/PoPC reserve to pay a DTD
   winner (base 100 SOST, rollover-capped at 500 SOST). It is a supply-neutral REDISTRIBUTION of the
   existing reserve — authorized ONLY by byte-exact canonical reconstruction from the pre-block
   state, no signature, current miner excluded (no self-payout). Once the reserve drains to 0 the
   jackpot is retired (one-way latch).

## Safety properties (validated)
- Every V15 rule is strictly height-gated at 25000 (boundary test 15/15, no off-by-one).
- The jackpot cannot mint value: canonical reconstruction + an independent value-conservation
  backstop (`sum(inputs) >= sum(outputs)`), both before any state mutation, on every ConnectBlock path.
- Reserve is keyless — only the canonical jackpot can spend it.
- Reorg/restart/reindex crossing activation preserve state atomically.
- No DEV RPCs / test flags / failpoints in production binaries (count=0 in mainnet/testnet).

## NOT changed / not in this fork
- No change to any ancient fork or to V14 (block 15000, EVM HTLC stays active).
- PoPC automation + Gold Vault governance gates remain consensus-DEFERRED (INT64_MAX) until a
  future soaked release.
- Atomic Swap BTC HTLC stays gated OFF (decoupled from V15; never activated without external review).

## Consensus notes
- V15 being "the last fork" is a project decision, not a code assumption — nothing hard-codes away
  a future emergency fork.
- One post-fork hardening item is tracked (audit B-2: make the failed-reorg restore fatal instead of
  a silent truncated break) for a later tested, height-gated release.
