# V1 — fork/orphan store poisoning: regression

Reproduces the vulnerability and proves the fix.

- `v1_fork_poison_attacker.py` — floods a victim node with UNIQUE cheap forks
  from 40 source IPs of one /24 (127.0.0.0/24), evading the per-IP ban.
- `v1_fork_honest_peer.py` — one honest peer from a DIFFERENT /24 (127.0.1.0/24)
  sends a single fork afterwards.

PASS criterion: after the flood, the honest fork must still be stored.

Result on this codebase:
  v16.3.0 (before): attacker fills all 1000 entries; honest fork stored = NO (poisoned).
  fork-store-hardening (after): attacker capped at 150 by the /24 quota; honest fork stored = YES.

Run: launch a node with a ~500-block chain, then
  python3 v1_fork_poison_attacker.py 127.0.0.1 <p2p> <genesis_hex> <base_block.json>
  python3 v1_fork_honest_peer.py    127.0.0.1 <p2p> <genesis_hex> <base_block.json>
Inspect with RPC getforkstats.
