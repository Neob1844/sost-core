# V14 (block 15,000) — deployment checklist

Phase A / A7 of `docs/V14_EXECUTION_PLAN.md`. Operator runbook to ship the V14
binary safely. **Golden rule: never edit `chain.json` by hand; never flip a
deferred gate at deploy time.** What ships enforced in V14: H3/H4 hardening +
relay fee floor (+ any component whose gate has been proven and announced).

## A. Pre-deploy (≥ 1 week before block 15,000)
- [ ] V14 branch merged to `main`; CI `v14-fork-safety` green.
- [ ] `ctest` all green locally, including `v14-fork-gates` and `v14-h3-h4`.
- [ ] Release binary built `-DCMAKE_BUILD_TYPE=Release`; record `sha256sum sost-node`.
- [ ] Keep a **baseline** (pre-V14) `sost-node` binary for replay comparison.

## B. Replay validation (CRITICAL — bit-identical pre-fork)
- [ ] `scripts/validate-v14-replay.sh <candidate> <baseline> /opt/sost/chain.json` → **PASS**
      (same final height + same UTXO-set root, replaying 0..14,999). [needs A2/A3]
- [ ] Save the replay log under `deploy/validation_logs/`.

## C. Testnet dry-run (recommended)
- [ ] Private testnet with V14 activated at a low height (e.g. 200) mines across the
      boundary with no consensus error; RPC `getblocktemplate`/`submitblock` OK. [needs A4]

## D. Beacon advisory
- [ ] Sign + publish the V14 notice (`docs/V14_BEACON_NOTICE_TEMPLATE.md`).
- [ ] Announce on BitcoinTalk + official Telegram (t.me/SOSTProtocolOfficial).

## E. Deploy (VPS, before ~block 14,900)
```
# VPS (server /opt/sost, sost-node only)
cd /opt/sost && git pull origin main
cd build && make -j$(nproc)
sudo cp /opt/sost/chain.json /opt/sost/backups/chain_pre_v14.json   # backup
sudo systemctl restart sost-node
sudo systemctl status sost-node --no-pager | head -6
```
- [ ] WSL miner: `git pull && make`, scp fresh `chain.json` from VPS, relaunch miner
      (see memory: SOST deploy workflow — 12 threads, mainnet, RPC auth).

## F. Post-fork verification (first hours after 15,000)
- [ ] Tip ≥ 15,010; no REJECT/reorg in `journalctl -u sost-node`.
- [ ] Node and miner on the **same tip** (no divergence).
- [ ] Explorer shows post-15,000 blocks; beacon banner visible.
- [ ] New blocks honor the 10 stocks/byte relay floor.

## G. Rollback (only if divergence)
- [ ] Stop node; restore `chain_pre_v14.json`; revert to baseline binary; restart
      (replays from 14,999 under old rules). Do NOT hand-edit chain.json. File an incident note.
