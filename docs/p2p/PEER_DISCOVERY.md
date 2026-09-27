# SOST Peer Discovery Without STRATO — Design (no insecure fast-path)

**Status: DESIGN + reference algorithm.** Today a fresh node only learns peers from
manual `--connect host:port` (verified in `src/sost-node.cpp` arg parsing); the project VPS
("STRATO") is the de-facto single seed. That is a **centralization + liveness risk**: if it is
down or censored, new nodes cannot join. This document designs decentralized discovery and a
reference for the one genuinely security-critical part — the anti-poisoning address manager —
**without** shipping insecure gossip quickly. Live 24h multi-operator validation is
**BLOCKED-EXTERNAL** (needs independent operators).

## Threat model
An attacker who can feed a new node addresses wants to **eclipse** it — fill its peer table
with attacker-controlled nodes so it sees a false chain / withheld blocks. Defenses must ensure
that (a) no single source can dominate the table, (b) unsolicited addresses can't flush good
ones, (c) discovery has redundant, independent roots so no one operator is a chokepoint.

## Discovery roots (defense in depth, independent failure domains)
1. **DNS seeds** — a handful of `seed.sost*.` hostnames run by different operators, each
   returning A/AAAA records of long-lived reachable nodes. Cheap, standard (Bitcoin/Zcash use
   this). A node queries several and unions the results; **no single seed's answer may fill more
   than a capped fraction of the initial set** (see reference §"per-source cap").
2. **Static anchor set** — a small, signed, versioned list shipped in the release
   (`anchors.json`, replaces the implicit STRATO default). Used only if DNS fails. Must be
   multi-operator so it is not a re-centralization. Anchors are *hints*, never trusted for
   chain data (PoW still decides).
3. **Community seeds** — operator-supplied `--seed host:port` / config entries, and the
   existing `--connect` (kept). Lets anyone bootstrap from peers they already trust.
4. **Persisted peers** — on restart, reuse the previously-learned "tried" table (peers we
   have successfully connected to), so a returning node needs no external root at all.
5. **ADDR gossip (LAST, and rate-limited)** — once connected, peers exchange address records.
   This is the poisoning surface, so it is gated by the address manager below and is **off the
   critical path**: a node is fully functional from roots 1–4 without ever trusting gossip.

## Address manager (the anti-poisoning core) — reference in `peer-addrman.js`
Modeled on Bitcoin Core's `addrman` new/tried tables, minimized:
- **Two tables:** `new` (addresses heard but never connected) and `tried` (addresses we have
  successfully connected to). Only `tried` peers are preferred for outbound.
- **Source bucketing / per-source cap:** each address remembers the *source* that gave it.
  A single source can occupy at most `MAX_SHARE_PER_SOURCE` of `new` (reference: 10%). This is
  the key eclipse defense — a flood from one peer cannot evict the whole table.
- **Group-diversity for outbound:** outbound connections are spread across distinct network
  groups (e.g. /16 IPv4 buckets), so an attacker owning one subnet can't own all our outbound.
- **Bounded, deterministic eviction:** tables have fixed capacity; insertion into a full bucket
  evicts the *worst* existing entry (oldest-unattempted / most-failed), never a random good
  `tried` peer. `tried` entries are only demoted after repeated connection failure.
- **ADDR rate-limit:** unsolicited ADDR messages are capped per-peer per-interval; addresses
  over the cap are dropped (the existing beacon gossip already has per-peer rate-limits and a
  dedup LRU — reuse that discipline).
- **No consensus role:** the address manager only decides *who to dial*; it never affects block
  validity. PoW + validation remain the sole arbiters of the chain.

## Why not "just gossip fast"
Naive ADDR gossip with no source accounting is the classic eclipse vector. Shipping it before
the bucketing/eviction/rate-limit rules are implemented **and adversarially tested** would make
new nodes *less* safe than the current manual-connect model. Hence: design first, reference
algorithm + tests now, C++ port with adversarial tests + multi-operator 24h test before it is
enabled by default.

## Rollout plan (each step gated)
1. **[DESIGN, this doc]** roots + address-manager rules.
2. **[reference + tests]** `peer-addrman.js` — selection/eviction/anti-poisoning proven on a
   simulated hostile feed (this commit).
3. **[C++ port]** into the node's peer layer behind a flag, default OFF; DNS-seed + anchor
   loader; adversarial unit tests (flood, subnet-monopoly, ADDR-spam, restart-persistence).
4. **[BLOCKED-EXTERNAL]** clean-node bring-up from DNS/anchors only, then a 24h multi-operator
   test with independent nodes (not the author's machines) before default-ON.

## Explicit boundaries
- **NODE_BIND / listen configuration is not touched.**
- No change to consensus, block relay format, or the beacon gossip already active at V13.
- Anchors/DNS results are dialing hints only — never trusted for chain state.
