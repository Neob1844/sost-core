# SOST — Always-On Miner Runbook (systemd)

Purpose: run a SOST miner that survives reboots and never depends on a desktop
session (no WSL2 that suspends). This is the structural fix for the repeated
"machine slept → tunnel/clock died → chain stalled for hours" incidents: a
dedicated box that is always up removes the single-point dependency on the
Beelink.

## 0. Golden rule — THE NODE ALWAYS WINS
If the miner and a node share the same box, the node is the priority. The miner
runs niced/limited so it can never starve the node. If the miner degrades the
node, cut the miner's threads or stop it — never the node.

## 1. Hardware requirements (read first)
- **RAM: ≥ 8 GB.** The ConvergenceX PoW is memory-hard — it builds a ~4 GB
  dataset (shared across threads). A 3–4 GB box will swap-thrash, hash at
  near-zero, and can drag a co-located node down. **Do not run the miner on a
  box with < 6 GB free RAM.** (This is why we did NOT put it on the 3.8 GB
  production VPS.)
- **CPU: 2+ cores.** 1 core for the node if co-located, ≥1 for the miner.
- **Always-on:** a cheap dedicated VPS (~8 GB, ~8–12 €/mo) or a home machine that
  never suspends. NOT a laptop/WSL2 that sleeps.
- **Disk:** a few GB for the chain.

## 2. Two deployment shapes
- **A) Dedicated miner box that also runs its own node** (recommended, fully
  independent): run `sost-node` + `sost-miner` on the same 8 GB box, miner talks
  to the local node over `127.0.0.1` (no SSH tunnel — that removes one of the two
  historical failure modes outright).
- **B) Miner-only box pointing at a remote node's RPC.** Needs the node's RPC
  reachable + credentials (or, in the future, the public mining endpoint — see
  docs/design/PUBLIC_MINING_ENDPOINT_DESIGN.md). Until that endpoint exists,
  prefer shape A.

## 3. Build (mandatory flags)
```bash
cd /opt/sost && git checkout main && git pull origin main
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-cli sost-miner sost-signtx -j$(nproc)
```
⚠ `-DSOST_TESTNET_FORKS=OFF` and `-DSOST_ENABLE_PHASE2_SBPOW=ON` are REQUIRED or
the node rejects mainnet blocks.

## 4. Wallet / signing key (once)
The miner needs a wallet holding the SbPoW signing key whose address receives the
rewards:
```bash
# create or reuse a mining wallet + key label
/opt/sost/build/sost-cli wallet-create /opt/sost/build/miner-wallet.json
/opt/sost/build/sost-cli wallet-newkey  /opt/sost/build/miner-wallet.json --label mainnet-miner
# note the derived sost1... address; that is where block rewards land.
```
Keep `miner-wallet.json` backed up and OFF any public path (chmod 600).

## 5. systemd service — the miner
`/etc/systemd/system/sost-miner.service`:
```ini
[Unit]
Description=SOST always-on miner
After=network-online.target sost-node.service
Wants=network-online.target

[Service]
Type=simple
User=sost
WorkingDirectory=/opt/sost/build
# THE NODE WINS: lowest CPU/IO priority so the miner never starves a co-located node.
Nice=15
IOSchedulingClass=idle
CPUWeight=20
# Memory ceiling so a runaway miner can never OOM-kill the node (tune to box):
MemoryMax=5G
ExecStart=/opt/sost/build/sost-miner \
  --wallet /opt/sost/build/miner-wallet.json \
  --mining-key-label mainnet-miner \
  --rpc 127.0.0.1:18232 \
  --rpc-user sost --rpc-pass sost \
  --profile mainnet \
  --threads 1 \
  --blocks 1000000 --realtime
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Notes:
- `--threads 1` on a shared box; raise only if the node has spare cores.
- `--rpc 127.0.0.1:18232` = the local node (shape A). No tunnel.
- `Nice=15` + `CPUWeight=20` + `IOSchedulingClass=idle` = the node always preempts
  the miner. `MemoryMax` is the hard OOM guard.

## 6. Start + verify (node priority check)
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sost-miner
# 1) miner alive + producing:
journalctl -u sost-miner -n 20 --no-pager    # look for "submitted to node OK"
# 2) NODE still healthy under miner load (THE check that matters):
for i in 1 2 3; do curl -s -u sost:sost -d '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' http://127.0.0.1:18232/ ; echo; sleep 20; done
```
Node height must keep rising and getblockcount must stay fast (<1 s). If the node
slows or swaps: lower `--threads`, lower `MemoryMax`, or `systemctl stop
sost-miner`. **Never degrade the node to keep the miner up.**

## 7. Health monitoring (cheap)
- Chain advancing: watch the explorer height or `getblockcount` on the node's
  `:18232`. If it rises, the network is producing.
- Do NOT judge health by the miner's local `REJECTED` lines — a multi-threaded
  miner races itself; `submitted to node OK` + rising height = healthy.

## 8. Why this ends the stalls
- No desktop/WSL2 session to suspend → no dropped tunnel, no clock drift.
- systemd `Restart=always` → a crashed miner relaunches in seconds.
- `enable` → survives reboots.
- The node stays prioritized, so the miner can never take down the piece that has
  been solid the whole time.

This is the cure the incident post-mortems pointed to; the Beelink + guard is the
stopgap until this box exists.
