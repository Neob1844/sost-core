# SOST V16 — miner & node upgrade

**What:** one mandatory upgrade for every node and miner.
**Which release:** install **v16.2.0** — the current one, on your node **and**
your miner, inside the update window below. V16.1.0 carries the same consensus
rules, so it crosses the fork correctly too; V16.2.0 adds the operator-side
fixes and is what `docs/v16/SHA256SUMS` verifies. Already on V16.1.0? Update in
the same window anyway — see `docs/v16/UPGRADE_V16_2.md` for what changed.
**When:** update **after block #29,900 and before #30,000**.
**Why:** from #30,000 the DTD Jackpot becomes an independent, node-gated,
PoW-weighted draw (first V2 draw #30,186), AND DTD-normal eligibility is re-pointed
at current miners (recency 288, conditional cooldown/anti-dominance). The 100/500/
rollover payout and the 50/50 split are unchanged. A V15 node diverges after #30,000.

```text
BEFORE #29,900     read this, download, prepare — do NOT switch yet
#29,900 → #29,999  the update window (~16–17 h): stop, build, verify, restart
AT #30,000         V16 activates automatically — you do nothing
AFTER #30,000      optional: NODE_BIND + --node-key, to play the DTD Jackpot
BEFORE #30,186     confirm eligibility for the first V2 draw
```

Verify every binary against `docs/v16/SHA256SUMS` before running it. If a hash
does not match, **do not restart the node** — see the manifest on what a
mismatch does and does not mean.

---

## 1 · VPS — the node

`/opt/sost` stays on `main`: it is the operational tree and its hooks publish the
website. The release is built in a **worktree from the tag**, so that tree never
moves.

```bash
cd /opt/sost
git fetch --all --tags --prune
git worktree add /opt/sost-v16 v16.2.0
cd /opt/sost-v16
git describe --tags --exact-match          # must print v16.2.0
git rev-parse HEAD

cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-cli -j"$(nproc)"

sha256sum build/sost-node build/sost-cli
```

**Stop here** and compare against `docs/v16/SHA256SUMS` (the V16.2.0 list;
`docs/v16/SHA256SUMS_V16_1` is kept for verifying a rollback binary). Only continue if they
match. The miner is not built on the VPS — there is no `sost-miner` service there.

```bash
cd /opt/sost
cp build/sost-node "build/sost-node.v15.backup.$(date -u +%Y%m%d-%H%M%S)"
cp build/sost-cli  "build/sost-cli.v15.backup.$(date -u +%Y%m%d-%H%M%S)"
cp /etc/systemd/system/sost-node.service \
   "/etc/systemd/system/sost-node.service.pre-v16.$(date -u +%Y%m%d-%H%M%S)"

systemctl stop sost-node
install -m 0755 /opt/sost-v16/build/sost-node build/sost-node
install -m 0755 /opt/sost-v16/build/sost-cli  build/sost-cli
systemctl start sost-node
sleep 15
```

Verify — the binary that is **running**, not the one on disk:

```bash
systemctl status sost-node --no-pager -l | head -12
PID=$(systemctl show sost-node -p MainPID --value)
readlink -f "/proc/$PID/exe"
sha256sum "$(readlink -f /proc/$PID/exe)"        # == the published sost-node hash

ss -ltnp | grep -E '18232|19333'                 # RPC + P2P listening

RPC_USER=AdminNeoB
read -rsp "RPC password: " RPC_PASS; echo
curl -s -u "$RPC_USER:$RPC_PASS" -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"1.0","id":"check","method":"getblockcount","params":[]}' \
  http://127.0.0.1:18232/
unset RPC_PASS
```

The height must advance and match the network. Done.

---

## 2 · WSL — the miner

No hooks in this tree, so a detached checkout of the tag is fine.

Build it in a **worktree from the tag**, with the build directory named
`build` — the published hashes only reproduce from a directory with that name
(see the note below).

```bash
cd /home/sost/SOST/sostcore/sost-core
git status --short
git fetch --all --tags --prune
git worktree add /home/sost/sost-v162 v16.2.0
cd /home/sost/sost-v162
git describe --tags --exact-match          # must print v16.2.0

cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-miner sost-cli -j"$(nproc)"

sha256sum build/sost-miner build/sost-cli
```

> **The build directory must be called `build`.** The source path does not
> matter — `-ffile-prefix-map` normalises it, and that is measured. The build
> directory name is not normalised, so `-B build-v16` produces different bytes
> from the same commit and will not match the published hashes.

**Stop here** and compare against `docs/v16/SHA256SUMS`. Then stop the miner
(Ctrl+C in its window), install, and restart it with **exactly** the same command
as before — no flag changes:

```bash
cd /home/sost/SOST/sostcore/sost-core
cp build/sost-miner "build/sost-miner.v15.backup.$(date -u +%Y%m%d-%H%M%S)"
cp build/sost-cli   "build/sost-cli.v15.backup.$(date -u +%Y%m%d-%H%M%S)"
install -m 0755 /home/sost/sost-v162/build/sost-miner build/sost-miner
install -m 0755 /home/sost/sost-v162/build/sost-cli   build/sost-cli

/home/sost/SOST/sostcore/sost-core/build/sost-miner \
  --wallet /home/sost/sost-keys/cex-wallet.json \
  --mining-key-label "SOST CEX LIQUIDITY RESERVE" \
  --genesis /home/sost/SOST/sostcore/sost-core/genesis_block.json \
  --rpc 127.0.0.1:18232 --rpc-user AdminNeoB --rpc-pass "<your rpc password>" \
  --blocks 999999 --max-nonce 500000 --profile mainnet --realtime --threads 13
```

`--wallet` + `--mining-key-label` select the key that **signs** your blocks. Do
not replace them with `--address`: V16 jackpot eligibility and NODE_BIND both
depend on that signed mining identity. `--realtime` stays.

Nothing else is needed. At #30,000 V16 activates by itself.

---

## 3 · POST-ACTIVATION PROCEDURE — only after #30,000

Separate from the upgrade above. Do **not** run any of this before #30,000; node
transactions are not valid until the activation height.

Eligibility = real PoW (**≥3 SbPoW blocks per 2,016**) **and** an active,
heartbeating node. Extra nodes do not raise your odds — only your PoW does.

**Bind your node key once** (in WSL, with the wallet that signs your blocks):

```bash
NODE_PRIV=$(openssl rand -hex 32)      # 32-byte node key — SAVE IT, keep it secret
echo "NODE_PRIV=$NODE_PRIV"            # store it somewhere safe, offline

BIND_HEX=$(build/sost-cli --wallet /home/sost/sost-keys/cex-wallet.json \
             --mining-key-label "SOST CEX LIQUIDITY RESERVE" \
             createnodebind 1 "$NODE_PRIV")
curl -s -H 'content-type:application/json' \
  --data "{\"method\":\"sendrawtransaction\",\"params\":[\"$BIND_HEX\"],\"id\":1}" \
  http://127.0.0.1:18232/
```

`bind_seq` starts at 1; to rotate later, bind again with a strictly higher
sequence. The bind is effective one block after it confirms.

**Turn on the automatic heartbeat** — on the VPS, where the node runs. Add the
flag to the node's systemd unit and restart it once:

```bash
# /etc/systemd/system/sost-node.service  ->  append to ExecStart:
#     --node-key <the NODE_PRIV you saved>
systemctl daemon-reload && systemctl restart sost-node
```

The node then publishes one heartbeat per epoch by itself, never before #30,000,
only while the bind is active, and it re-fills a heartbeat after a reorg.

**Check eligibility before #30,186:**

```bash
curl -s -u "$RPC_USER:$RPC_PASS" -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"1.0","id":1,"method":"checkhistoricaljackpoteligibility","params":["<your sost1 address>"]}' \
  http://127.0.0.1:18232/
```

Want `eligible: true` with an empty `reasons` list. `getjackpotv2audit` at a
jackpot height shows the canonical eligible set and the winner.
