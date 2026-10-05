# D1 — Peer Autonomy (persistent peer store + autonomous redial)
**Branch `feat/p2p-autonomy-d1` off tag `v30000`. POST-#30,000 ONLY — NOT for the V30000 fork. Node binary FROZEN at 78fefb67 until the fork.**

## What this adds (non-consensus, NO wire-protocol change → full backward compatibility)
- **Persistent peer store** `peers.txt` in the datadir (next to chain.json): the addresses of GOOD outbound peers (dialable, handshake-complete), deduped, capped at 256, atomic write (tmp+rename), mode 600. Never wiped by an empty set.
- **Redial-from-store at bootstrap:** when no `--connect` is given, the node tries stored peers FIRST (up to 3), then the default seeds to fill — so a restart reuses known-good peers and depends less on seed DNS.
- **Maintenance redial fix:** the 30s loop now, when it has ZERO peers, redials from (a) `--connect`, (b) the peer store, (c) default seeds (unless `--noseed`). Closes the old gap where a seed-only node that lost all peers never redialed (was guarded by `!connect_addrs.empty()`).

## Why it is safe
- No new wire message, no change to VERS/GETB/BLCK/TXXX/PING/BCNN → old↔new peers fully interoperate.
- No consensus/validation/serialization/fork-choice change (purely connection management + local file I/O).
- Bounded store (≤256) → no unbounded growth. Only OUTBOUND, handshake-complete peers are stored (we know those are dialable; no attacker-supplied address is persisted — that is the separate, later ADDR/GETADDR increment, which needs fuzzing).
- Redial is done OUTSIDE the g_peers lock so the blocking connect() never stalls peer writers.

## Tests
- `tests/d1_peer_store_test.cpp`: 9/9 (path derivation, round-trip, dedupe, mode 600, garbage rejection, bound ≤256, empty-no-wipe).
- Full node ctest on the branch: (see CI/ctest run) — changes are additive/non-consensus.

## NOT yet done (next increments on this branch, still POST-#30,000, require soak + adversarial)
- **ADDR / GETADDR peer gossip** (new wire verbs) — needs fuzzing of malformed peer messages, eclipse-amplification review, rate-limit reuse. Only persist gossiped addrs after validation + bound.
- **D2** multi-domain seeds + fallback IP list (DEFAULT_SEEDS change).
- Multi-node soak + adversarial lab + canary before any deploy.

## Release gate before deploying this (post-#30,000)
old/new peer compat PROVEN · malformed-peer fuzz PASS · no remote crash/OOM · no eclipse amplification · bounded peer DB · ctest green · multi-node soak PASS · canary PASS · reproducible build + fresh hashes verified.
