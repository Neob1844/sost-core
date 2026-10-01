# V30000 peer coordination (mainnet) — inventory, order, verification

## Observed network (from the live STRATO node, getnetworksummary + getpeerinfo)
- **STRATO** (local, the node/miner we will swap): mainnet, height ~28,825, label "STRATO".
- **2 external connected peers** (the P2P exposes neither a version string nor address
  exchange, so remote version detection is NOT possible — per getnetworksummary
  "no address exchange in the P2P protocol"):
  - peer A: 167.86.x.x  (conntime earlier — long-lived)
  - peer B: 175.158.x.x
- `connected_external: 2`, `discovered_active: null`. No other reachable nodes are visible.

## Who these are (operator to confirm — from project memory)
- The admin/laptop miner `sost1ad01a…` (now the ADMIN_AUTHORITY), the Beelink `sost1c1c6d…`,
  and the dominant producer `sost1993a8…` (~90% of recent blocks). Map the two external
  IPs to these machines — **only you can confirm which IP is which and which you control.**

## Fork-safety analysis (why this matters)
V30000 activates TWO classes of consensus change at #30000:
1. **V16 (already enforced by the current prod binary)** — any node at #30000 must run a
   V16-aware binary or it forks. The CURRENT production node already enforces V16@30000, so
   peers that stayed in sync past earlier V16 prep are already V16-aware.
2. **NEW in V30000: native-asset tx/out types + admin gate.** A pre-V30000 node will REJECT
   a block that contains an ASSET_* tx (unknown type) and fork off. BUT asset txs are
   admin-only (gate S14) and developer-gated, so **no asset tx exists until YOU create one.**
   => A pre-V30000 peer stays in consensus on normal blocks and only forks if/when an asset
   block is mined. You control the first asset tx, so you can guarantee every peer is on
   V30000 BEFORE any asset block.

## Required before PEERS READY: YES
Each machine that mines or validates at #30000 must run the V30000 release:
1. Confirm which of the 2 external peers you control; identify any you do NOT control.
2. Distribute the V30000 binaries (verified SHA256 = release/v30000/SHA256SUMS.txt) to each.
3. **Update order (lowest risk):**
   a. Non-producing / validating-only peers first (no block production risk).
   b. The dominant producer (`sost1993a8…`) next — the highest-impact node; schedule a
      brief coordinated stop/swap/restart with --realtime.
   c. STRATO last (or jointly), so a known-good peer is always up.
4. Keep ≥1 peer on the known-good current binary until the new ones are confirmed in sync.

## How to verify each peer actually runs V30000
On each machine:
- `sost-node --version` → must print the V30000 build banner (v0.4.0 MAINNET).
- `sha256sum /opt/sost/sost-node` → must equal the release NODE hash
  `a1dde8086b821945e2d91a820b3294c519a66078dcb1767f3bb7af828fb0c411`.
- After restart, confirm it reaches the same tip hash as STRATO at a common height
  (`getblockhash <h>` matches) — proves it is on the same chain, not forked.
- A pre-V30000 node can also be detected the moment it rejects the first asset block:
  before going public, mine ONE admin asset tx on a staging height and confirm every peer
  accepts the block (same tip). Only then is the network truly V30000-ready.

## Current status
PEERS READY: **NO** — remote version detection is impossible via the P2P protocol, and the
2 external peers' binaries are not yet confirmed as V30000 by the operator. Flips to YES
once you confirm/upgrade each per the steps above.
