# Phase 13 — GO / NO-GO: D1/D2 peer autonomy inclusion in V30000

**Candidate:** branch `feat/p2p-autonomy-d1` @ `79c84702` (off tag `v30000`).
**Synthesis height:** mainnet #29,345 (freeze target ~#29,750, activation #30,000).

## What the candidate changes vs the frozen v30000
```
 src/sost-node.cpp   | 310 ++++--   (P2P peer store + ADDR/GETADDR gossip + seeds.txt + --p2p-bind)
 docs/*, tests/*      | new          (runbooks, examples, 2 test suites)
 13 files, +588/-36
```
**ZERO consensus files touched** — `params.h`, `sbpow.*`, validation, cASERT, emission are
byte-for-byte identical to v30000. D1/D2 is purely peer discovery/connection + docs.

## Candidate binary hashes (mainnet Release, reproducible back-to-back)
| Binary | Candidate (D1/D2) | Deployed v30000 |
|--------|-------------------|-----------------|
| sost-node  | `7d50611b09f7f9c89a653233e5aa1b03a7786a0b14087a654ea29cbea29e5123` | `78fefb67…` |
| sost-miner | `37e9b064cbc4e197e61ed5787b82f62d0d6b1374400140c8c176aa2a5febbb33` | `eec96efb…` |
| sost-cli   | `7c65f8b06333224b5e3543f66fc8615c43620563d8f4c36424260a7756e02870` | `c8ae00b9…` |

## Gate matrix

| Gate | D1a peer-store | D1b ADDR-gossip | D2 seeds.txt | Evidence |
|------|:---:|:---:|:---:|----------|
| BUILD (mainnet flags) | PASS | PASS | PASS | Release, PHASE2_SBPOW=ON, TESTNET_FORKS=OFF |
| UNIT + CTEST | PASS | PASS | PASS | **119/119** ctest, 0 fail |
| FUZZ | — | PASS | — | 200k iters ASan/UBSan on parse_addr_payload, 0 crash |
| MULTI-NODE (Phase 1) | PASS | PASS | PASS | 5/5 OLD↔NEW compat matrix |
| OLD-NEW COMPAT | PASS | PASS | PASS | OLD not penalized, no split, identical tip/chainwork |
| RESTART/PERSIST (Phase 2) | PASS | — | — | 10/10 peer-store torture (restart×100, corrupt/huge/dup/empty) |
| CORRUPTION | PASS | — | PASS | malformed peers.txt/seeds.txt → no crash, bounded, never wiped |
| ADVERSARIAL WIRE (Phase 3) | — | PASS | — | 500k junk addrs over real socket → +264KB RSS, FD flat, alive |
| ECLIPSE/POISONING (Phase 4) | PASS | PASS | PASS | ≤2 conns/IP; raw gossip never persisted; candidates bounded 256 |
| PARTITION/CONVERGE (Phase 5) | PASS | PASS | PASS | 9/9 — G1(h15) vs G2(h5) diverge → heal via store → heavier wins, SACS untouched |
| LOSS-OF-SEEDS (Phase 6) | PASS | — | PASS | bootstrap with sostcore.com down; no-source fails closed cleanly |
| RESOURCE LIMITS | PASS | PASS | PASS | RSS/FD/candidates/store all bounded under flood |
| SOAK/CANARY (Phase 7/8) | PASS* | PASS* | PASS* | isolated 4-node OLD+NEW mesh, 0 errors, RSS decelerating |
| REPRODUCIBLE BUILD (Phase 11) | PASS | PASS | PASS | byte-identical double build |

\* soak is ongoing; final GO requires it staying clean through the freeze window.

## SAFE TO INCLUDE BEFORE #30,000: **YES (technical)** — conditioned on 2 operator gates

Every technical gate is green. D1/D2 adds no consensus change, is backward-compatible with
the all-OLD mainnet (a NEW node joins without splitting — Phase 1), survives adversarial
input, and is reproducible. The only thing it changes is that a node no longer *depends* on
sostcore.com to find peers — strictly more decentralized, strictly more resilient.

Two non-technical gates remain, both the OWNER's call:
1. **Replace the frozen known-good binary.** Shipping D1/D2 means a new release binary
   (`7d50611b…`) replaces `78fefb67…`. The war-room froze v30000 as fallback; swapping it
   needs explicit owner authorization.
2. **Soak duration.** Let the isolated soak run clean through to the freeze window
   (#29,750) before committing. If any leak/crash/error appears, NO-GO and keep v30000.

## Recommendation
Present this package to the owner. If the owner authorizes replacing the frozen binary AND
the soak stays clean to #29,750: **GO** (ship D1/D2 in V30000). Otherwise: **NO-GO**, keep
v30000 (`78fefb67…`) as the deployed release and ship D1/D2 as the first post-#30,000 point
release — it is height-independent and loses nothing by shipping later.
