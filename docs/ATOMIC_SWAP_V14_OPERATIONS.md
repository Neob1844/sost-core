# Atomic Swap V14 — Operations runbook (founder-only, GO mainnet at block 15,000)

CTO decision: **GO** at block 15,000, EVM-only, gate stays `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT =
V14_HEIGHT`. Founder-only, public DO-NOT-USE, risks accepted (no external audit, no reorg tests,
non-standard-ERC20 untested, split risk). This runbook = how to do it with maximum containment.

## THE ONE RULE that controls all risk
Reaching block 15,000 is **benign**: with the new binary everywhere, nothing changes until an HTLC
tx is mined. **The point of no return is the FIRST HTLC transaction.** So:
> **Do NOT create any HTLC until you have confirmed the majority of hashrate is on the new binary.**
Before that first HTLC, a rollback is trivial; after it, a rollback is a hard fork. Control the timing.

## A. Pre-fork — update YOUR infra (do now; safe — gate inert until 15,000)
Build flags are MANDATORY (or the node rejects all blocks): `-DSOST_ENABLE_PHASE2_SBPOW=ON
-DSOST_TESTNET_FORKS=OFF`. Verify the cache before restart.

**VPS (node — critical):**
```
ssh -i ~/.ssh/sost_vps root@212.132.108.244        # use the key; plain ssh root@ fails
cd /opt/sost && git pull origin main               # must include 517213cd (the V14 gate flip)
git log -1 --format='%h %s' && grep -n ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT include/sost/atomic_swap.h  # = V14_HEIGHT
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF
grep -E "SOST_ENABLE_PHASE2_SBPOW|SOST_TESTNET_FORKS" build/CMakeCache.txt   # ON / OFF or STOP
cmake --build build --target sost-node -j$(nproc)
sudo systemctl restart sost-node && sudo systemctl status sost-node --no-pager | head -6
curl -s -u USER:PASS -X POST http://127.0.0.1:18232 -d '{"method":"getblockcount","id":1}'  # height advancing
```
**Beelink (miner):** same git pull + cmake (same flags + grep) + `cmake --build build --target
sost-miner` + relaunch the miner (your usual block). SbPoW ON is required (miner computes the proof).

## B. Coordinate external miners (BEFORE the first HTLC)
Post the announcements (BitcoinTalk + Telegram + X — drafts in `docs/ATOMIC_SWAP_V14_MINER_DISCLOSURE.md`).
Reach the known high-hashrate miners directly. Goal: as much hashrate as possible on the new binary
**before** you create any HTLC. With few miners, every one matters.

## C. Monitoring window (block 14,800 → 15,050)
- Watch height advancing on the VPS node (`getblockcount`) and that your miner keeps finding blocks.
- At 15,000: nothing should visibly change (no HTLCs yet). If the chain keeps advancing normally,
  the upgrade landed cleanly.
- Watch for **chain split signals**: peers stuck, your node's tip diverging from the explorer,
  `REJECTED block` in logs. (A lone REJECTED right after a reorg/tunnel hiccup has been transient
  before — don't panic-fix; instrument `submitblock` first.)

## D. First swap — founder safety protocol (only after C looks clean)
1. **Native first** — SOST ↔ **ETH or BNB native** only. Do NOT touch USDT/PAXG/XAUT first
   (non-standard ERC20, untested → highest bug risk).
2. **Ridiculous amount** (cents), one single swap.
3. Test the **REFUND path** first (lock + let it time out + refund) before trusting CLAIM.
4. Then a full **CLAIM** cycle, waiting many confirmations on both chains.
5. Several successful cycles before any real capital. Never promote it; banner stays DO-NOT-USE.
CLI steps: `docs/ATOMIC_SWAP_CLI_GUIDE.md`.

## E. Emergency plan
- **Before the first HTLC (benign window):** if miner coverage is unsafe or you get cold feet →
  the safe lever is simply **do not create an HTLC**. Optionally revert the gate to `INT64_MAX`
  (one-line in `include/sost/atomic_swap.h`), rebuild, redeploy, re-announce — clean, no fork,
  because no HTLC ever existed.
- **Split detected (chain diverges):** the canonical chain is the majority-hashrate (your) chain.
  Un-upgraded miners must rebuild with the new binary + resync to rejoin. Do NOT create more HTLCs
  until rejoined.
- **Invalid-HTLC / consensus bug found AFTER an HTLC is mined (worst case):** this is a hard fork
  to fix — coordinated emergency point-release + everyone rebuilds. Avoid reaching here by keeping
  D step 2 tiny and not scaling until many clean cycles.
- Rollback commit is a single constexpr flip; keep it ready but unused unless needed.

## Using the Web Console (`website/atomic-swap-console.html`)
A founder-only guided console + operative EVM layer. Linked from the OTC and DEX nav (⚛ Atomic
Swap). Reachable at `https://sostcore.com/atomic-swap-console.html` once the website is deployed.
It never asks for a seed/private key, never holds keys; the SOST side is command-generation + RPC
reads, the EVM side signs through the user's MetaMask. Tabs:
- **Overview / education** — HTLC concept + glossary.
- **Readiness** — LIVE height via `/rpc` + SELF-attested node/miner checks (commit, flags, restart,
  explorer match, no REJECTED, hashrate). Self items are NOT verified by the page — verify them on
  your machines.
- **1 · Refund test** — generates secret+hashlock (Web Crypto, in-tab only) and the exact
  `createhtlclock`/`refundhtlc` commands; guarded to preview-only below height 15,010.
- **EVM operate (Phase II)** — real `AtomicSwapHTLC` calls via MetaMask: connect, network detect,
  gas/token balance, ERC-20 decimals/allowance (read live, never assumed), `lockNative`/`lockERC20`/
  `claim`/`refund`/`getSwap`. Calldata is shown before every signature; encoder is byte-verified
  against the contract ABI (`website/js/atomic-swap-evm.js`, tests in `*.test.js`, cross-checked
  with `cast`).
- **2 · Claim flow (SOST CLI)** — generates the SOST-side `claimhtlc` command.
- **Swap status** — `gethtlcstatus`/`listhtlclocks` command + read-only RPC query + local swap-log
  download + emergency bundle (never includes keys/secret).
- **Emergency** — the 3 scenarios above.

## Founder-only mainnet procedure (web)
1. Update VPS node + Beelink miner to the V14 build (commit `b57c41ed`+; SBPOW=ON, TESTNET=OFF).
2. Wait to height ≥ 15,010. Tick the Readiness self-checks honestly.
3. **SOST side:** generate S/H in the console, run the generated `createhtlclock` on your node, sign,
   `sendrawtransaction`; verify with `gethtlcstatus`. First do a REFUND-only test (tiny amount).
4. **EVM side (only after the contract is DEPLOYED — see limitations):** connect MetaMask, set the
   contract address, pick native ETH/BNB, tiny amount, set `refundTime` EARLIER (wall-clock) than the
   SOST `refund_height`; LOCK; counterparty confirms; CLAIM reveals S; the other side claims with S.

## Known limitations (current)
- **The EVM `AtomicSwapHTLC` contract is NOT deployed and NOT audited.** Until the founder deploys it
  to Ethereum / BNB Chain and pastes the address in the console, EVM operations are disabled by
  design (the console refuses to call a non-existent contract). Deploying an unaudited contract to
  mainnet is an explicit founder decision and a separate step.
- No external audit, no reorg tests, no live cross-chain e2e; non-standard ERC-20 (USDT/PAXG/XAUT)
  untested — native ETH/BNB first.
- `refundTime` (EVM block.number) vs SOST `refund_height` ordering is wallet/operator-enforced, not
  contract-enforced.
- **SOST ↔ BTC is deferred to V15** (BTC HTLC signing is a stub; the console excludes BTC entirely).

## Status snapshot
Gate = V14_HEIGHT (15,000), EVM-only, `SOST_BTC_HTLC_SIGNING=OFF` (BTC = V15). ctest 92/92,
EVM 52/52 (internal). EVM contract NOT deployed/audited. Unverified: reorg, live e2e, external
audit, non-standard ERC20. Founder-only. Web console: Phase I + Phase II (EVM operative once a
contract address is configured).
