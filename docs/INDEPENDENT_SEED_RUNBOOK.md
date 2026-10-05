# Independent Bootstrap Seed — Runbook
Goal: provide a bootstrap source that does NOT depend on the sostcore.com DNS zone, so a
BRAND-NEW node can join the network even if sostcore.com is unreachable.

## Today (v30000 release) — manual independent seed
Run an independent full node (see INDEPENDENT_NODE_RUNBOOK.md) with a stable, publicly
reachable address, and publish it. New operators add it via `--connect <yourhost>:19333`.

## With the D1/D2 release (post-#30,000, after full gates) — zero-config independent seeds
The node reads `<datadir>/seeds.txt` (see seeds.txt.example) and dials those BEFORE the
built-in sostcore.com seeds, at startup and on auto-reconnect. So the community can add
independent seeds by editing a text file — no recompile, no central DNS:
    echo "seed.youroperator.example"      >> ~/.sost/seeds.txt   # host (default :19333)
    echo "203.0.113.42:19333"             >> ~/.sost/seeds.txt   # or host:port
Best practice for true independence:
- run ≥2 seed nodes on DIFFERENT providers / ASNs / regions
- if you publish a seed HOSTNAME, host its DNS on a different registrar/zone than sostcore.com
- keep inbound 19333 open; keep the node synced.

## Verify (lab-proven, Phase 6)
A fresh node with ONLY seeds.txt (no --connect) and sostcore.com unreachable still bootstraps
and syncs. That is the definition of "sostcore.com is not a technical requirement."
