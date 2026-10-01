# SOST V30000 — operator upgrade guide (hard fork at block #30,000)

## TL;DR for every node/miner operator
**All THREE binaries changed. Update node + miner + cli.** This is NOT a v16.2.x-style
CLI-only release — the old "only sost-cli changed; node & miner byte-identical" notice does
NOT apply to V30000.

| binary | v16.2.3 public | V30000 (RC_FINAL) | action |
|---|---|---|---|
| sost-node  | b253e4a9… | **78fefb67a15615f3df1b0a4f498239ccba07ba47ce6e333d13d5d2afdcecbb56** | **UPDATE** |
| sost-miner | 2ef9d0a7… | **eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951** | **UPDATE** |
| sost-cli   | 489f4374… | **c8ae00b9a6745f7c84cc8791b9994d32052a07d1fed12aa82c4e283fba2f691b** | update (needed for admin/dev asset ops; harmless for miners) |

## Timeline
- **Now → well before #29,900:** official binaries + SHA256 + GitHub release + this guide published.
- **~#29,900 → #30,000:** operators replace node + miner (and cli) with V30000 and restart; the
  miner MUST run with `--realtime`.
- **#30,000:** activation is AUTOMATIC by height. No manual command, no second deploy.
  `#29,999` old rules · `#30,000` V30000 active · `#30,001+` new rules fully in force.

## What activates at #30,000 (why node + miner changed)
- **V16 Historical Jackpot V2** (JACKPOT_V2_HEIGHT=30000): new jackpot/coinbase construction →
  the MINER must be V30000 to build valid jackpot blocks; the NODE to validate them.
- **SACS V2**: deep-reorg recovery (MAX_REORG_DEPTH cap → alarm; bounded fork-store).
- **SEC2**: node-internal RPC hardening (malformed RPC can no longer crash/OOM the node).
- **Native asset layer + the 4 tokenization modalities + SOST-layer DEX** (consensus-active,
  developer-gated): asset tx/out types become valid — a non-V30000 node will REJECT an asset
  block, so every operator must be on V30000 before the asset layer is first exercised.

## Public access to DEX / Tokenization
DEX + Tokenization (Tokenize/Auction/Draw/Project Funding) are **live at protocol level from
#30,000 but PUBLIC ACCESS IS BLOCKED** — restricted to the admin authority by BOTH a consensus
gate (S14; only the admin address may execute asset ops) and server-side web auth. Miners do
NOT need to do anything about these features; they are developer/admin-only and experimental.
*Technical availability does not constitute regulatory authorization.*

## Upgrade steps (operator)
```
# 1. download the V30000 binaries + SHA256SUMS from the official release
sha256sum -c SHA256SUMS            # MUST verify before installing
# 2. stop, replace, restart
systemctl stop sost-miner sost-node     # (or kill by PID)
install -m755 sost-node  /opt/sost/build/sost-node
install -m755 sost-miner /opt/sost/build/sost-miner
install -m755 sost-cli   /opt/sost/sost-cli
sha256sum /opt/sost/build/sost-node /opt/sost/build/sost-miner   # re-verify in place
systemctl start sost-node               # wait until synced to tip
systemctl start sost-miner              # must include --realtime
# 3. confirm: sost-node --version shows V30000; getblockhash <h> matches the network at a common height
```
All validating nodes/operators must update before #30,000 or they fork off when the new rules
activate.
