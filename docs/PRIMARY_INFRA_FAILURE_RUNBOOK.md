# Primary Infrastructure Failure — Recovery Runbook
What still works, and what to do, if sostcore.com / the primary VPS / explorer / public RPC
go down. (Scope: operational autonomy. Consensus is unaffected by any of this.)

## What KEEPS WORKING automatically (no action)
- Every already-connected full node keeps validating, relaying blocks + txs, and mining.
- Consensus, difficulty (cASERT), SACS V2 reorg handling — all local to each node.
- A node with ≥1 live peer continues indefinitely.

## What is AFFECTED
- A BRAND-NEW node that only knows the sostcore.com DNS seeds cannot bootstrap (until it has
  an alternative source). The explorer/public-RPC convenience endpoints are unavailable.

## Recovery actions (operator)
1. **Bootstrap new nodes from alternatives:** `--connect <independent-node>:19333`, or (D1/D2
   release) a `seeds.txt` / `peers.txt` pointing at independent nodes. (Phase 6 proves this works.)
2. **Software:** fetch binaries from a mirror (RELEASE_MIRROR_RUNBOOK.md) and verify against
   SHA256SUMS.txt.
3. **Status:** query any independent node's RPC (`getinfo`, `getblockcount`) instead of the
   public explorer; or run a local explorer against your own node.
4. **Do NOT** rush consensus/binary changes during an outage. The frozen v30000 (78fefb67) is
   the known-good release; keep it.

## Readiness checklist (do BEFORE an outage)
- [ ] ≥2 independent full nodes on different providers/ASNs, inbound 19333 open
- [ ] published independent node addresses (for --connect / seeds.txt)
- [ ] ≥1 release mirror with SHA256SUMS.txt
- [ ] seeds.txt / peers.txt documented for operators
- [ ] (target) the 24h primary-OFF independence test executed + evidence published
