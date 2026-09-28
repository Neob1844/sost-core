# SACS P1 — Lab Isolation Flag (`--noseed` / `--disable-dns-seeds`)

**Status:** IMPLEMENTED + TESTED (research branch `research/sost-autonomous-chain-safety`).
**Consensus impact:** NONE. This is a pure P2P-bootstrap runtime flag. It does not
touch difficulty, mining, PoPC, block validation, heights, or any consensus rule.
Flag OFF (the default) preserves current behaviour byte-for-byte.

## Why
The SACS reorg experiments need a node that advances an *isolated* local devnet
chain. Without isolation, a fresh node resolves and dials `seed*.sostcore.com`,
connects to the production seed, and is pulled into IBD/fast-sync against mainnet —
so the local experiment chain never advances. `--noseed` removes that coupling.

## What it does
When `--noseed` (or its alias `--disable-dns-seeds`) is set:
- The default-seed bootstrap block (`DEFAULT_SEEDS[]`) is skipped entirely, so the
  node makes **zero `getaddrinfo()` / DNS queries** for the seed hostnames.
- The node makes **no external auto-connections**. It dials only peers given
  explicitly via `--connect host:port`.
- Inbound listening and explicit `--connect` are unchanged (so a 2-node lab still
  forms by pointing one node at the other).

There is no ADDR/gossip-based auto-dial path in the node (`connect_peer()` is called
only from the seed block, the explicit `--connect` loop, and the explicit-peer
auto-reconnect loop), so gating the seed block alone yields full isolation.

Implementation: `src/sost-node.cpp` — global `g_noseed`, arg parse for
`--noseed`/`--disable-dns-seeds`, and `if(g_noseed){…} else if(connect_addrs.empty()){…}`
around the `DEFAULT_SEEDS` bootstrap. Commit `2245d355`.

## Test — `tests/sacs_p1_isolation.sh`
Runs the node under `strace -f -e trace=connect` twice and classifies every
outbound `connect()` (loopback `127.*` vs external). Environment: WSL, DNS resolver
`nameserver 10.255.255.254` (a non-loopback address), so any DNS lookup shows up as
an external connect to `10.255.255.254:53`.

### RUN A — FLAG ON (`--noseed --connect 127.0.0.1:9`)
```
[P2P] --noseed: DNS seeds and external auto-connect DISABLED. Using only 1 explicit --connect peer(s).
[P2P] Cannot connect to 127.0.0.1:9
[P2P] Listening on port 0
```
`connect()` targets (strace): **only** `127.0.0.1:9` (the explicit peer).
External (non-127.*) connects: **0**. DNS queries to seed hostnames: **0**.

### RUN B — FLAG OFF (default)
```
[P2P] No --connect specified; trying 4 default seeds (want up to 3)...
[P2P] Cannot resolve seed-eu.sostcore.com   (regional records not yet published)
[P2P] Cannot resolve seed-apac.sostcore.com
[P2P] Cannot resolve seed-us.sostcore.com
[P2P]   seed connected: seed.sostcore.com
[P2P] bootstrapped from 1 default seed(s).
```
External connects: **5** — `10.255.255.254` ×4 (DNS resolver, port 53) and
`212.132.108.244` ×1 (the resolved production seed IP, port 19333).

### Verdict
| Assertion | ON | OFF |
|---|---|---|
| external (non-loopback) connects | 0 ✓ | 5 ✓ |
| DNS to seed hostnames | 0 ✓ | yes ✓ |
| "isolation DISABLED" log line | 1 ✓ | — |
| "trying N default seeds" log line | 0 ✓ | 1 ✓ |

**RESULT: PASS.** `--noseed` gives zero external connections and zero seed DNS while
still honouring explicit `--connect`; the default path still reaches the seed, proving
the flag is what changes the behaviour.
