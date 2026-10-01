# V30000 rollback procedure (STRATO / mainnet)

## Before the swap
1. Record the CURRENT live binaries + their SHA256 and keep a copy:
   ```
   mkdir -p /opt/sost/rollback-v30000-$(date +%Y%m%d_%H%M%S)
   cp -p /opt/sost/sost-node /opt/sost/sost-miner /opt/sost/sost-cli \
         /opt/sost/rollback-v30000-*/
   sha256sum /opt/sost/rollback-v30000-*/*
   ```
2. Snapshot the chain/datadir (or confirm it is append-only and a resync is viable).

## If rollback is needed BEFORE block #30000
The new binaries are byte-identical in behavior to the old below 30000 (asset types
inert via R2/R11; admin gate only active >=30000). Rollback is safe: stop services,
restore the previous binaries from the rollback dir, restart. No chain state is
invalidated because no asset/restricted tx can have been mined below 30000.

## If rollback is needed AT/AFTER block #30000
Native-asset / admin-gated txs may now exist on-chain. Rolling back to a pre-V30000
binary that does NOT understand asset tx types would REJECT those blocks and fork the
node off the network. DO NOT roll back to a pre-V30000 binary after 30000 unless the
whole network coordinates a rollback. Instead, roll forward with a fixed V30000 build.
(This is the normal property of any hard fork.)

## Service restore commands (STRATO)
```
systemctl stop sost-node sost-miner           # or: kill -9 <pid> (never by name)
cp -p /opt/sost/rollback-v30000-*/sost-node   /opt/sost/sost-node
cp -p /opt/sost/rollback-v30000-*/sost-miner  /opt/sost/sost-miner
cp -p /opt/sost/rollback-v30000-*/sost-cli    /opt/sost/sost-cli
sha256sum /opt/sost/sost-node /opt/sost/sost-miner /opt/sost/sost-cli   # verify
systemctl start sost-node && systemctl start sost-miner
```
