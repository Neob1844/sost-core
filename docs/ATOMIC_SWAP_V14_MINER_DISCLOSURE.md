# Atomic Swap — miner/user disclosure (DRAFT for review — NOT published)

Status: **DRAFT on branch `feature/v14-atomic-swap-evm-disclosure`. Nothing merged, deployed
or communicated.** The activation height is **NOT set** in code (see the open decision below).

## 1. Explorer banner (already added to `website/sost-explorer.html`)
Bilingual red top banner: the Atomic Swap is founder-only testing, not externally audited, **DO
NOT USE — funds can be lost**, wait for the founder's official "safe to use" announcement.
Height-agnostic on purpose (no activation block baked in until the dev sets it).

## 2. BitcoinTalk announcement (DRAFT — publish only after you approve + the gate is finalised)

```
[CRITICAL] SOST Atomic Swap — FOUNDER TESTING PHASE — DO NOT USE

Why "technically present" does NOT mean "ready to use".

The SOST-side HTLC consensus, the EVM HTLC contract, the BTC signing primitives,
and the wallet/CLI/RPC builders for atomic swaps are code-complete and pass the
internal test suites (SOST consensus 12/12; EVM contract 52/52; BTC crypto vectors
green). The BTC funding path (UTXO selection + fee estimation) is still a stub, so
only SOST <-> EVM (ETH/BNB/USDT/USDC/PAXG/XAUT) is in scope; SOST <-> BTC is not.

DO NOT USE THE ATOMIC SWAP.

- No external cryptographic audit has been performed.
- No third-party end-to-end mainnet validation has been performed.
- Only the founder is testing, under controlled conditions.
- A bug in un-audited cross-chain code can cause PERMANENT loss of funds.

Any use of the atomic-swap functionality before the official "safe to use"
announcement is ENTIRELY AT THE USER'S OWN RISK. SOST Protocol / the founder
assume no responsibility for funds lost during this testing phase.

The founder will announce — on this thread, the SOST website news section, and the
official Telegram (t.me/SOSTProtocolOfficial) — WHEN the system has been validated
as safe for public use. Until that announcement: do not use it. Use OTC P2P methods.
```

## 3. OPEN DECISION — activation height (needs the dev's informed call before any flip)
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` is still `INT64_MAX` (OFF). It was **not** changed.

**Why not 15,000 (V14):** `params.h` states `V14_HEIGHT = 15000 // MAINNET (UNCHANGED —
already in deployed binaries, no node re-update needed)`. V14 was designed to require **no new
binary**. Injecting a brand-new consensus rule (atomic-swap activation) at 15,000 means the
binaries miners are already running do **not** contain that rule → **a chain split is
near-certain** unless every miner recompiles and redeploys a new binary in the few days before
block 15,000. The disclosure banner does not mitigate a split — a split breaks the whole network.

**Safer options to choose from (dev decides):**
- A dedicated activation height comfortably ahead of "now" that gives miners a real
  recompile/redeploy window (e.g. a round block a few weeks out), shipped as an explicit
  network upgrade with SHA-256-published binaries and a coordinated miner announcement.
- Or keep the documented `V15_HEIGHT = 20000` (atomic swap was always slated for V15).

**To flip, once a height is chosen:** set `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` to that height
(keep `SOST_BTC_HTLC_SIGNING=OFF` — EVM-only), run unit tests + full `ctest`, publish the new
binary's SHA-256, and confirm every miner has upgraded before that block. EVM-only (BTC to V15).

## 4. What is NOT done (by design, awaiting your review)
- Gate NOT flipped. No release build. No deploy. No miner communication. OTC page left in its
  current safe "disabled / preview" state. BTC stays OFF (funding path is a stub).
