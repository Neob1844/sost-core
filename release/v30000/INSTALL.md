# V30000 install / migration (STRATO mainnet) — commands prepared, NOT executed

> Pre-requisite: bake the operator admin address into ADMIN_AUTHORITY_PKH and rebuild
> (docs/v30000/ADMIN_CONSENSUS_GATE.md); regenerate SHA256SUMS; set the web auth
> credential (deploy/TOKENIZATION_AUTH_SETUP.md). Only then run the swap below.

## 1. Backup + rollback snapshot (see ROLLBACK.md)
```
TS=$(date +%Y%m%d_%H%M%S); mkdir -p /opt/sost/rollback-v30000-$TS
cp -p /opt/sost/sost-node /opt/sost/sost-miner /opt/sost/sost-cli /opt/sost/rollback-v30000-$TS/
sha256sum /opt/sost/rollback-v30000-$TS/*
```
## 2. Stage new binaries + verify hashes BEFORE swap
```
# upload node/miner/cli to /opt/sost/stage/ then:
sha256sum -c /opt/sost/stage/SHA256SUMS.txt   # must match the release SHA256SUMS
```
## 3. Swap (REQUIRES operator YES — this is the irreversible step held for pre-flight)
```
systemctl stop sost-miner                      # stop miner first
systemctl stop sost-node
install -m755 /opt/sost/stage/sost-node  /opt/sost/sost-node
install -m755 /opt/sost/stage/sost-miner /opt/sost/sost-miner
install -m755 /opt/sost/stage/sost-cli   /opt/sost/sost-cli
sha256sum /opt/sost/sost-node /opt/sost/sost-miner /opt/sost/sost-cli   # re-verify in place
systemctl start sost-node
# wait for sync to tip, confirm getblockcount advances, THEN:
systemctl start sost-miner --realtime          # miner MUST run with --realtime (timestamp rule)
```
## 4. Peer coordination
```
# All mining/validating peers must run a V30000 binary BEFORE height 30000, or they
# fork off when the asset/admin-gate rules activate. Notify peers; confirm each reports
# the V30000 node version and reaches 30000 on the same chain. Keep >1 peer on standby.
```
