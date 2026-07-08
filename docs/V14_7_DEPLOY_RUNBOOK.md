# V14.7 Deploy Runbook — Atomic Swap re-activation at block 18,000

**STATUS: DOCUMENT ONLY — DO NOT RUN NOW.** Execute in the coordinated window
**after block 17,900, before block 18,000.** As of writing the chain is ~16,520
(~1,500 blocks / several days away). The V14.7 binary is a **no-op until block
18,000** — recompiling early is harmless but restarting the node/miner now buys
nothing and risks re-introducing the mining disruption that the rollback fixed.

## What is already done (on `main`)

- V14.7 relay gate (`atomic_swap_relay_active_at`, mainnet **18,000**) — PR #63
  capsule exemption re-gated as a coordinated flag-day.
- Companion rule (commit `382f3520`): expired HTLC LOCKs are kept out of block
  templates and evicted from the mempool — closes the root cause of the earlier
  mining disruption (13× R17 block rejections). Regtest 8/8, mainnet subset 7/7.
- Announcement published (X / Telegram / BitcoinTalk); site banners updated.

## Miner address (RESOLVED)

On-chain verification (recent blocks) shows this Beelink mines with:

```
sost1c1c6d7e1fee477a5b74f6e4235329ec1475d66da
```

`~/auto_mine.sh` was corrected on 2026-07-08 from the stale
`sost1a8eae8f80fedd8d86187db628a0d81e0367f76de` (which produces no blocks) to the
address above.

> ⚠️ **VERIFY BEFORE RELAUNCH:** the currently-running miner that produces the
> `sost1c1c6d…` blocks was **not** launched by this `auto_mine.sh` (no local
> `sost-miner` process or `~/mining.log` was visible, and the script had the wrong
> address). Confirm which command/session actually launches your miner and make
> sure it uses `sost1c1c6d…` — or relaunch via the corrected `auto_mine.sh`.

## Order: NODE first, then MINER

### Step 1 — NODE (VPS `212.132.108.244`)

```bash
cd /opt/sost && git pull origin main
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
sudo systemctl restart sost-node
sudo systemctl status sost-node --no-pager | head -6
```

Mandatory flags: `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF` (never
flip TESTNET_FORKS to ON — the node would reject mainnet blocks).

### Step 2 — MINER (Beelink / WSL)

```bash
cd ~/SOST/sostcore/sost-core && git pull origin main
cmake --build build --target sost-miner sost-cli sost-signtx -j"$(nproc)"
# relaunch your miner (uses the corrected sost1c1c6d… address):
pkill -TERM -x sost-miner 2>/dev/null || true
sleep 3
bash ~/auto_mine.sh   # OR your real launch command — must use sost1c1c6d…
```

### Step 3 — Verify (both across block 18,000)

```bash
# node responsive + advancing:
curl -s -u USER:PASS -d '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:18232
```

- Confirm your miner is producing blocks and the on-chain `miner_address` is
  `sost1c1c6d…` (check the explorer / getblock).
- Confirm mining stays healthy for 30–60 blocks (no repeated stale/reject).

## After block 18,000 — swap self-test (founder, optional)

Once past 18,000 the HTLC relay is active. When testing a real self-swap:

- **Set `refund_height` comfortably in the FUTURE** (e.g. current height + 500 or
  more) and CLAIM/REFUND promptly. The earlier incident was a lock that EXPIRED
  in the mempool (refund_height 16259) and poisoned the template. The companion
  rule now protects the network (evicts expired locks), but still create
  well-formed locks with room before expiry.
- Native EVM only (ETH/BNB). Swap stays founder-testing / DO NOT USE publicly.

## Rollback (safe — policy gate, no fork risk)

V14.7 is a relay/policy gate; block validity is byte-identical, so a rollback
does not fork the chain. If coverage is unsafe near 18,000: raise `V14_7_HEIGHT`
(one line in `include/sost/params.h`), recompile, re-announce — before miners
build the activation binary.
