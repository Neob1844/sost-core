# SOST V15 — Final consensus deployment procedure (operator)
Release commit **1a88c5ec** · activation **#25,000** · update deadline **before #24,900** (deploy ASAP — the
binary is height-gated / identical before #25,000, so earlier = more safety margin). Flags MANDATORY:
`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release`.

## GO / NO-GO
| Item | Value |
|---|---|
| RELEASE COMMIT | 1a88c5ec (HEAD == origin/main) |
| NODE SHA256 | 20c9e74f03df8f5ae380d7c41b8aaea45614b00bebea21ea310bf471195b8c01 |
| MINER SHA256 | 850469d0af5c81a5a4a950aaac1e44f340cf247f1ed75486aac1d06340cbc370 |
| TESTS | dtd-recency 13 · lottery-eligibility 77 · jackpot 108 · coinbase-phase2 76 · frequency 79 · rollover 53 — ALL PASS |
| RPC ROTATION | REQUIRED before/with deploy (operator) |
| NODE BACKUP | in the block below |
| MINER BACKUP | in the block below |
| PRE-FORK COMPATIBILITY | YES — height-gated, identical behaviour < #25,000 |
| ACTIVATION HEIGHT | #25,000 |
| UPDATE DEADLINE | before #24,900 |
| **DECISION** | **GO** |
Hashes are per-toolchain; other operators who rebuild will get their own hash — publish the reference toolchain in the manifest.

## 1) NODE — VPS (root@212.132.108.244, /opt/sost)
```bash
ssh -i ~/.ssh/sost_vps root@212.132.108.244
cd /opt/sost
# backup current binary + record its hash
cp -a build/sost-node "build/sost-node.bak.$(date -u +%Y%m%d_%H%M%S)" 2>/dev/null || true
sha256sum build/sost-node 2>/dev/null | tee /root/sost-node.prev.sha256
# fetch + freeze to the exact release commit
git fetch origin && git checkout 1a88c5ec
# clean build with mandatory flags
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)" --target sost-node
sha256sum build/sost-node                      # compare to release hash (per-toolchain)
# restart via systemd (runs as user 'sost' — NEVER start the DB manually as root)
sudo systemctl restart sost-node
sleep 5
systemctl is-active sost-node && journalctl -u sost-node -n 20 --no-pager
# RPC health (use the ROTATED creds):
sost-cli getblockcount ; sost-cli getbestblockhash ; sost-cli getpeerinfo | head
```
Verify: block count climbing, peers connected, no DB-permission errors, no reorg/fork errors, tip as expected.

## 2) MINER — WSL laptop
```bash
cd /home/sost/SOST/sostcore/sost-core
git fetch origin && git checkout 1a88c5ec
cmake -S . -B build-v15-release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build-v15-release -j4 --target sost-miner
sha256sum build-v15-release/sost-miner          # == 850469d0af5c81a5a4a950aaac1e44f340cf247f1ed75486aac1d06340cbc370
# stop ONLY the old miner (by its path), then relaunch the new one:
pkill -f 'build-final/sost-miner'
nohup build-v15-release/sost-miner --profile mainnet --realtime \
  --wallet /home/sost/sost-keys/cex-wallet.json --mining-key-label 'SOST CEX LIQUIDITY RESERVE' \
  --rpc 127.0.0.1:18232 --rpc-user <NEW_USER> --rpc-pass <NEW_PASS> \
  --threads 13 --blocks 999999 --max-nonce 500000 >/tmp/sost-miner.log 2>&1 &
pgrep -af sost-miner        # must show EXACTLY one, the new binary
tail -f /tmp/sost-miner.log # templates received, realtime timestamps, no "timestamp too far in future"
```
`--realtime` is MANDATORY (without it blocks are stamped prev+600s and rejected). Never run two miners at once.

## 3) RPC credential rotation (do before/with deploy)
- Pick a NEW rpc user+pass; set it on BOTH node and miner. Store in a config file with `chmod 600`, owned by the
  service user; avoid passing the secret on the command line where `ps` would expose it, if the build supports a
  config/env form. Do NOT commit or print the secret. The old pass appeared in `ps` — treat it as burned.

## 4) End-to-end mining check
Miner connects to RPC · receives templates · realtime timestamps · normal attempts · correct wallet/key · a
mined block appears on the canonical chain (getbestblockhash matches node).

## 5) Rollback (ONLY valid BEFORE #25,000)
```bash
# node:
sudo systemctl stop sost-node
cp -a build/sost-node.bak.<ts> build/sost-node
sudo systemctl start sost-node ; sost-cli getblockcount ; sost-cli getpeerinfo | head
# miner: pkill -f build-v15-release/sost-miner ; relaunch the previous build-final/sost-miner (with --realtime)
```
**After #25,000, reverting to the old (pre-recency, pre-V15) binary is NOT a normal rollback — it would place the
node on an incompatible chain.** Past activation, fix forward, not back.
