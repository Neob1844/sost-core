# Atomic Swap — V14 activation + miner/user disclosure (branch `feature/v14-atomic-swap-evm-disclosure`)

**CTO decision (executed on branch, NOT merged/deployed/announced):** activate the Atomic Swap
HTLC consensus rules at **V14 / block 15,000**, **EVM-only** (SOST ↔ ETH/BNB/USDT/USDC/PAXG/XAUT);
SOST ↔ BTC deferred to V15 (BTC funding path is a stub). The dev accepts that V14 was a no-update
fork and that this makes V14 a **mandatory binary-upgrade** fork; mitigated by the urgent
recompile banner + announcement below.

## What changed on the branch
- `include/sost/atomic_swap.h`: `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_HEIGHT` (was INT64_MAX);
  includes `sost/params.h`. `SOST_BTC_HTLC_SIGNING` stays OFF (EVM-only).
- Gate tripwire tests updated to the active value (coordinator T14 static_assert + btc_signing T2
  now assert `== V14_HEIGHT`; htlc-lock T23 updated to the real `R24_HTLC_REFUND_BEFORE_TIMEOUT`).
- **Verified: all 12 C++ atomic-swap suites pass with the gate ACTIVE (44/44 htlc-lock).**
  EVM contract unaffected (52/52). sost-core compiles.
- Explorer banner (`website/sost-explorer.html`): urgent mandatory-miner-upgrade + DO-NOT-USE.

## NOT done (awaiting dev review + coordinated go-live)
Branch NOT merged to main. No release binary built. No deploy. No miner announcement sent.
A full `ctest` and a clean **EVM-only release build** (default `SOST_BTC_HTLC_SIGNING=OFF`) must be
run + the binary SHA-256 published before any miner upgrades.

## BitcoinTalk announcement (DRAFT — publish only after dev approves + release binary + SHA-256)

```
[URGENT][V14] MANDATORY node/miner upgrade before block 15,000 — Atomic Swap activates

ALL NODES AND MINERS MUST UPGRADE BEFORE BLOCK 15,000. THIS IS EXTREMELY URGENT.

The V14 fork activates at block 15,000 and enables the Atomic Swap HTLC consensus
rules (SOST <-> ETH/BNB/USDT/USDC/PAXG/XAUT; BTC deferred to V15). This is a
MANDATORY binary upgrade — unlike earlier V14 hardening, this changes consensus.

WHAT YOU MUST DO:
  1. git pull the latest sost-core.
  2. Recompile the new binary (verify SHA-256 below).
  3. Restart your NODE and your MINER.
  4. Do this AFTER block 14,800 and BEFORE block 15,000.

IF YOU DO NOT UPGRADE IN THAT WINDOW:
  From height 15,000 your node will REJECT EVERY BLOCK and you will be split off
  onto a dead forked chain. There is no recovery except upgrading and resyncing.

Binary SHA-256: <PUBLISH HERE>
Build instructions: <link>

--- ATOMIC SWAP: DO NOT USE (founder testing) ---
The atomic swap is enabled in consensus but is in FOUNDER-ONLY TESTING. It has had
NO external cryptographic audit and NO third-party validation. DO NOT USE IT — a bug
can cause PERMANENT loss of funds. Use is entirely at your own risk. The founder will
announce on this thread, the SOST website and Telegram (t.me/SOSTProtocolOfficial)
WHEN it is validated as safe. Until then: do not use it.
```

## Miner coordination (operate before block 15,000; chain is ~1,900 blocks away at posting)
- T-now: publish binary + SHA-256; post the announcement on BitcoinTalk + Telegram + the banner.
- Reach the known high-hashrate miners directly (they MUST upgrade) — with few miners, every one
  matters: a single un-upgraded miner with hashrate produces a competing (old-rules) chain.
- Recompile/restart window: after block 14,800, before 15,000.
- Rollback: if coverage is unsafe near 15,000, revert the gate to INT64_MAX (single constexpr) and
  re-publish — before any miner builds the activation binary.
