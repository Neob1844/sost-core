# SOST V16 — 5-Minute Miner & Node Upgrade Guide

**What:** one mandatory upgrade for every node and miner.
**When:** update **after block #29,900 and before #30,000**. V16 activates by itself at
**#30,000** — you do nothing at the height.
**Why:** from #30,000 the **DTD Jackpot** becomes an independent, node-gated,
PoW-weighted draw (first V2 draw **#30,186**). DTD-normal and the 100/500/rollover
payout are unchanged. A V15 node will fork off after #30,000.

Set these once:
```bash
SRC=/path/to/sost-core          # your source checkout
WALLET=/path/to/wallet.json     # your mining wallet (key label: default)
RPC=http://127.0.0.1:18232/      # your node RPC
```

---

## 1. Upgrade the node + miner (≈3 min)  —  do this between #29,900 and #29,999
```bash
cd "$SRC"
git fetch && git checkout <V16-release-tag>     # the tag from the release notes
# stop your running node + miner first, then back up your data dir (chain + wallet)
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
sha256sum build/sost-node build/sost-miner       # compare to the published hashes
```
Start the node, then the miner **with `--realtime`** (mandatory — without it your blocks
are rejected as "timestamp too far in future"):
```bash
build/sost-node  --wallet "$WALLET" --chain <chain.json> &          # your usual flags
build/sost-miner --realtime --rpc 127.0.0.1:18232 --wallet "$WALLET" \
                 --mining-key-label default --address <your-address> --threads <N>
```
A V16 node **before #30,000 is byte-identical to V15**, so restarting in the window
changes no rule. Confirm `getblockcount` advances and your tip matches the network.
**Done — you are upgraded.** Steps 2–3 are only if you want to play the DTD Jackpot.

---

## 2. (Optional) Join the DTD Jackpot — bind your node key ONCE (≈1 min)
Eligibility = real PoW (**≥3 SbPoW blocks per 5,000**) **and** an active, heart­beating
node. Extra nodes do **not** raise your odds — only your PoW does; the node is a gate.
```bash
NODE_PRIV=$(openssl rand -hex 32)                 # 32-byte node key — SAVE IT, keep secret
echo "NODE_PRIV=$NODE_PRIV"                        # store this somewhere safe
BIND_HEX=$(build/sost-cli --wallet "$WALLET" createnodebind 1 "$NODE_PRIV")
curl -s -H 'content-type:application/json' \
  --data "{\"method\":\"sendrawtransaction\",\"params\":[\"$BIND_HEX\"],\"id\":1}" "$RPC"
```
Bind once (`bind_seq` starts at 1). To rotate the key later, bind again with a
**strictly higher** seq. The bind is effective one block after it confirms.

---

## 3. (Optional) Turn on the automatic heartbeat (≈30 sec)
Restart your node with the **same** node key — it then publishes one heartbeat per epoch
for you, forever, with nothing else to run:
```bash
build/sost-node ... --node-key "$NODE_PRIV"       # add this flag to your usual command
```
It never heartbeats before #30,000, only while your bind is active, and it re-fills a
heartbeat automatically after a reorg. That's it — keep the node running.

*(No `--node-key`? A manual cron alternative is in `OPERATOR_GUIDE.md` §3.)*

---

## 4. Check your status any time
```bash
build/sost-cli --rpc 127.0.0.1:18232 checkhistoricaljackpoteligibility <your-address>
#   -> eligible, node_bound, pow_blocks/pow_minimum, heartbeats_valid/required, weight, reasons[]
```
`eligible:true` with `reasons:[]` means you are in the next draw. During the first two
epochs after #30,000 the heartbeat requirement ramps up gradually (bootstrap), so a
freshly bound node can already qualify.

---

### One-screen summary
| You want to… | Do this |
|---|---|
| Stay on the network | Upgrade node + miner before #30,000 (step 1). Mandatory. |
| Keep mining | Run the miner with `--realtime`. No other change. |
| Play the DTD Jackpot | `createnodebind` once (step 2) + run node with `--node-key` (step 3). |
| Check eligibility | `checkhistoricaljackpoteligibility <address>` (step 4). |

Activation **#30,000** · first DTD Jackpot V2 draw **#30,186** · DTD-normal unchanged ·
payout 100 base / 500 cap / rollover from the existing reserve (supply-neutral).
