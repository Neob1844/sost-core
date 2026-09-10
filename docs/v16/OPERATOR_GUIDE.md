# SOST V16 — Operator Guide (DRAFT)

Mandatory upgrade for **all validating nodes and miners**.
**Update after block #29,900 and before #30,000.** Activation auto-fires at **#30,000**
(no restart/command/config change is needed at the height).

---

## 1. Node upgrade checklist

```
1. Have the source + these instructions ready BEFORE #29,900.
2. When the chain is between #29,900 and #29,999:
   - stop sost-node
   - back up the data dir (chain.json + wallet)
   - build V16:
       cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
       cmake --build build --target sost-node sost-miner sost-cli -j$(nproc)
   - verify the binary (version string + SHA256 published with the release)
   - start sost-node
   - confirm: getblockcount advances, peers connected, tip matches the network
3. Do NOTHING at #30,000 — V2 activates automatically.
```

A V16 node **before #30,000 behaves exactly like V15** (byte-identical replay), so it is
safe to restart in the window. Restarting at, say, #29,930 does NOT change any rule.

## 2. Miner

- Rebuild the miner from the V16 release and **run it with `--realtime`** (mandatory —
  without it the miner stamps future timestamps and blocks are rejected
  "timestamp too far in future"). Keep the machine clock NTP-synced.
- The miner needs no other change for V16; it keeps signing SbPoW blocks as today.

## 3. Participating in the Historical Jackpot V2 (optional, from #30,000)

To be eligible you must (a) mine real PoW (≥3 SbPoW blocks / 5,000) **and** (b) bind a
node key and keep it heartbeating. Extra nodes do **not** increase your odds — only PoW
does; the node requirement is a gate.

**Step A — generate a node key** (any 32-byte secp256k1 private key; keep it secret):
```
NODE_PRIV=$(openssl rand -hex 32)
```

**Step B — bind it to your mining wallet** (signed by your mining key, label `default`):
```
BIND_HEX=$(sost-cli --wallet <your-mining-wallet.json> createnodebind 1 "$NODE_PRIV")
sost-cli --rpc <node-host:port> sendrawtransaction "$BIND_HEX"      # or via the node RPC
```
Do this once (bind_seq starts at 1). To rotate the node key later, bind again with a
**strictly higher bind_seq**.

**Step C — emit one heartbeat per epoch** (epoch = 288 blocks, aligned to #30,000).
The heartbeat must land inside its own epoch and reference that epoch's `tip_ref`
(= hash of the block at `epoch_start − 1`). A ready-to-cron snippet (bash + a node RPC
at `$RPC`):
```bash
A=30000; L=288                                   # activation, epoch length (mainnet)
rpc(){ curl -s -H 'content-type:application/json' --data "{\"method\":\"$1\",\"params\":$2,\"id\":1}" "$RPC"; }
TIP=$(rpc getblockcount '[]' | grep -oE '[0-9]+' | head -1)
[ "$TIP" -lt "$A" ] && exit 0                     # not active yet
EPOCH=$(( (TIP - A) / L ))
REF=$(( A + EPOCH*L - 1 ))                        # epoch_start - 1
TIPREF=$(rpc getblockhash "[$REF]" | grep -oE '[a-f0-9]{64}')
HB=$(sost-cli --wallet <any-wallet.json> nodeheartbeat "$NODE_PRIV" "$EPOCH" "$TIPREF")
rpc sendrawtransaction "[\"$HB\"]" >/dev/null
```
Run it a few times per epoch (e.g. cron every ~30–60 min). The mempool accepts **one**
heartbeat per (node, epoch); duplicates are ignored, so re-running is safe.

> A native `--auto-heartbeat` mode may ship in a follow-up; the cron above is the
> supported path today and is fully robust (idempotent, restart/reorg safe).

**Step D — check your status any time:**
```
sost-cli --rpc <node> checkhistoricaljackpoteligibility <your-mining-address>
# -> eligible, node_bound, pow_blocks/pow_minimum, heartbeats_valid/required, weight, reasons[]
sost-cli --rpc <node> getjackpotv2audit <jackpot-height>
# -> full eligible set, weights, total_weight, winner
```

## 4. If you do NOT upgrade

A node still on V15 after #30,000 will **reject V2 blocks and fork off** the network.
The upgrade is **mandatory for validating nodes**. Non-mining wallets that only query a
public V16 node are unaffected.

## 5. Key facts

- Activation: **#30,000**. First V2 jackpot draw: **#30,186**.
- DTD-normal is unchanged; the jackpot is now a separate, node-gated, PoW-weighted draw.
- Payout unchanged (100 base / 500 cap / rollover, from the existing reserve).
- Honest wording for any public messaging: **"Verified node participation"** — not a
  claim of an independent/unique/24-7 physical node.
