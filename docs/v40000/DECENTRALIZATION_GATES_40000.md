# DECENTRALIZATION GATES — #40,000

Status: these are acceptance tests, not marketing. None of them needs a consensus
change; they are NODE_HARDENING and operational work.

Baseline: code at `release/v40000-prep` `bc8a45d9`.

Verdict: **DECENTRALIZATION_40000_GATES_READY = YES (defined and testable) / NO (met).**
Every gate below has a procedure and a threshold, and the P2P gates (G1–G3, G5a)
have passing lab evidence. The operational gates G4, G5b, G6 and G7 are **not met**:
there are 0 independent seeds, 1 hosting provider and 1 region, and 2 active
producers.

## Current measured facts (code + docs)

**Bootstrap path** (`src/sost-node.cpp`):

* `DEFAULT_SEEDS` (`:460-465`) has 4 DNS names, all under `sostcore.com`
  (seed-eu, seed-apac, seed-us, seed). They resolve to effectively one VPS in
  Germany. APAC and US are planned (`docs/SEED_NODES.md`).
* There are no compiled-in fallback IPs.
* Peer sources, in order: the `peers.txt` peer store (`:497-540`; cap 256,
  atomic write, mode 600, saved every 30 s, never wiped by an empty set), then
  `<datadir>/seeds.txt` (`:476-496`; up to 64 entries), then `DEFAULT_SEEDS`.
  `--connect` peers are always dialed; `--noseed` disables DNS.
* With zero peers the node redials, in order: `--connect`, the store, gossip
  candidates, then the seeds (`:10868-10903`).
* Address gossip is GADR/ADDR with a capability byte (`CAP_ADDR`):
  * served at most once per 60 s per peer, ≤ 100 addresses
  * received ≤ 1000 entries, each ≤ 64 bytes; malformed input costs +10
    misbehaviour
  * candidates are held in memory only (cap 256)
  * the SSRF filter `include/sost/p2p_addr_filter.h` accepts only public IPv4
    literals on mainnet

**Consensus dependency on SOSTcore infrastructure: none.**

* The node makes no HTTP calls.
* Checkpoints are compiled in (`include/sost/checkpoints.h`; a `checkpoint.json`
  override is local only and never fetched).
* `sostcore` appears in node and miner code only as seed hostnames and banner text.

**Code merge state:**

* The D1/D2 code (peer store `48b0f480`, ADDR/GETADDR `cdb4d745`, Gate-6 hardening
  `eca62d7d`, SIGPIPE fix `7b9ac273`) is **already an ancestor of
  release/v40000-prep**.
* `feat/p2p-autonomy-d1` is ahead by only two war-room harness/doc commits
  (`f801fe24`, `cd21cc36`).

**Test targets** (CMakeLists):

* `d1-peer-store`: 9 checks
* `d1-addr-fuzz`: 8 unit checks + 200k random inputs, clean under ASan/UBSan
* `d1-gossip-filter`: public/private/CGNAT/hostname/IPv6 boundaries

**Recorded evidence:**

* `docs/D1_PEER_AUTONOMY.md`
* `docs/warroom/GATE9_FINAL_BATTERY.md`: ctest 122/122; P2P adversarial 7/7;
  peer-store torture 10/10; partition/heal 9/9; bootstrap without sostcore PASS
* `docs/warroom/PHASE6_LOSS_OF_SEEDS_EVIDENCE.md`: devnet, seed unreachable;
  bootstrap from `peers.txt` only, `seeds.txt` only, or both PASS; no source at
  all fails closed

**Operations:**

* Independent seeds: **0**.
* Operators: "observed 2; independent UNKNOWN"
  (`docs/SOST_DECENTRALIZATION_SECURITY_AUDIT_2026-10-05.md`).
* Hosting providers: **1**. Regions: **1** (EU).
* Producers: **2** in the last 429 blocks (V16 window; see ECONOMICS_80_15_5.md);
  174 distinct in 25,000..30,428; one producer historically holds 50–90 % of
  blocks (honest hardware).
* `docs/decentralization/INFRA_INDEPENDENCE_TEST_PLAN.md` is PLANNED, NOT
  EXECUTED. No 24 h independence result exists.

**Stale docs (fix, non-consensus):**

* These still say the peer store and gossip are "not found / missing":
  * `docs/decentralization/BOOTSTRAP_AUDIT.md`
  * `website/decentralization-status.json` (`persistent_peer_recovery`)
  * the 2026-10-05 audit
* `docs/AUTONOMY_STATUS_CHECK.md` (March) is obsolete.

## Gates

Notation: N = number, PASS(lab) = passed on devnet/lab, not on mainnet.

### G1 — Peer persistence across restart
*Procedure.*
1. Mainnet node A runs ≥ 1 h with no `--connect` and ≥ 3 outbound peers.
2. Record `peers.txt` (count, mode).
3. Stop A and block DNS for `*.sostcore.com` (`/etc/hosts` → 0.0.0.0, or a netns
   resolver).
4. Restart and measure the time to the first handshake and to 3 peers.

*Pass:* `peers.txt` holds ≥ 3 entries and mode is 600. ≥ 1 peer within 60 s and
≥ 3 within 10 min, with zero DNS lookups to sostcore.com (verified with tcpdump on
port 53).

*Status:* PASS(lab). Covered by `d1-peer-store` 9/9, peer-store torture 10/10 and
PHASE6 evidence. **Not yet run on mainnet.**

*Gap:* one recorded mainnet run.

### G2 — Autonomous discovery with sostcore.com DNS/seeds down
*Procedure.*
1. Start a fresh node with an empty datadir, `seeds.txt` holding 1 non-sostcore
   peer, and sostcore.com blackholed.
2. After 6 h, count the distinct peers learned via ADDR (store entries not in
   `seeds.txt`).

*Pass:* ≥ 3 additional peers learned through gossip, and the node syncs to the tip
(hash equals two external observers).

*Status:* PASS(lab) for the bootstrap mechanics. With an **empty** `peers.txt`, an
empty `seeds.txt` and sostcore.com down, the node **cannot** bootstrap; this fails
closed by design. **Not met on mainnet:** there is no independent seed to put in
`seeds.txt`.

*Gap:* ≥ 1 independent seed (G4).

### G3 — Address gossip propagation
*Procedure.* Run a 5-node lab in a line topology (A–B–C–D–E), each node knowing
only its neighbour. Measure the time until every node's candidate set contains
every other node's public address.

*Pass:* full propagation in ≤ 30 min. A malformed ADDR flood (1000 × 64 B junk,
10/s) causes ≤ +1 MB RSS, the peer is banned at score 100, and the node keeps
syncing.

*Status:* PASS(lab) for robustness (`d1-addr-fuzz` 200k; P2P adversarial 7/7,
500k junk addresses → +204 KB RSS). **The line-topology propagation timing is not
recorded.**

*Gap:* record the propagation run.

### G4 — ≥ N independent seeds
*Definition.* A seed is independent if it has a distinct operator, a distinct
domain (not `*.sostcore.com`) and a distinct ASN from the project VPS.

*Pass:* N ≥ 3 independent seeds, each reachable ≥ 99 % over 14 days (probe every
5 min from two external vantage points). Shipped in `DEFAULT_SEEDS` and/or as
documented fallback IPs in a signed release.

*Status:* **0. NOT MET.** A paid independent seed proposal exists
(`docs/warroom/INFRA_PROPOSAL_PAID.md`, about 3–6 USD/month) and is awaiting an
owner decision.

### G5 — Recovery when sostcore.com is unavailable
*G5a (node).* Block every `*.sostcore.com` name and IP for 24 h on 3 nodes with
populated stores.

*Pass:* all 3 stay at the network tip (observer hashes equal), reconnect after a
forced restart, and never stall more than 3 × 600 s.

*Status:* PASS(lab), "bootstrap without sostcore". Mainnet run not done.

*G5b (users).* With sostcore.com down, a new user must be able to:
1. download a signed release from a mirror not on sostcore.com or the sole GitHub
   account;
2. verify the signature;
3. bootstrap from documented seeds;
4. broadcast a transaction via their own node.

*Pass:* all 4 steps succeed.

*Status:* **NOT MET.** There is a single release source, and RPC and explorer are
single instances (audit SPOF list).

### G6 — ≥ N independent operators / hosting providers / regions
*Procedure.* Publish an operator registry (operator, ASN, country, node pubkey from
NODE_BIND where available). Verify each operator by a signed challenge plus
reachability from two vantage points.

*Pass:* ≥ 5 operators, ≥ 3 ASNs/hosting providers and ≥ 3 regions (continents),
with no single operator holding more than 40 % of reachable nodes.

*Status:* 1 provider, 1 region, independent operators UNKNOWN. **NOT MET.**

*Measurement aid:* NODE_BIND/HEARTBEAT (live since 30,194) gives an on-chain count
of node identities, but not of independence.

### G7 — Additional miners
*Pass:* ≥ 5 distinct producers in every 2,016-block window over 30 days. The top
producer stays below 50 % of blocks in that window, and the DTD anti-dominance gate
is armed (≥ 11 distinct miners in 288) at ≥ 50 % of heights.

*Status:* 2 producers in the V16 window, top-1 68.8 %; gate unarmed. **NOT MET.**
This is outside protocol control; track it, don't fake it.

### G8 — No consensus dependency on SOSTcore infrastructure
*Procedure.*
1. Static check: grep node and consensus sources for network fetches (HTTP/DNS
   other than P2P seeds).
2. Dynamic check: run a node in a netns whose only egress is P2P to non-sostcore
   peers; sync from genesis and validate to the tip.

*Pass:* there are no HTTP clients in node code, the full sync matches the tip
hash, and `getblockchaininfo` is identical to an external observer's.

*Status:* static PASS (no HTTP calls; checkpoints are compiled in). The dynamic
full-sync run is not recorded.

### G9 — 24 h independence test
This runs `INFRA_INDEPENDENCE_TEST_PLAN.md` Variant A (N ≥ 3 independent nodes,
M ≥ 2 independent miners, sostcore infrastructure off).

*Pass:* blocks keep arriving (no gap > 3 × target), no observer divergence, no reorg
deeper than 2.

*Status:* **NOT EXECUTED.**

## Summary

| Gate | Testable | Lab | Mainnet met |
|---|---|---|---|
| G1 persistence | yes | PASS | not run |
| G2 discovery w/o sostcore | yes | PASS (with a non-empty source) | NO (no independent seed) |
| G3 gossip | yes | PASS (robustness) | timing not recorded |
| G4 independent seeds ≥ 3 | yes | n/a | **NO (0)** |
| G5a node recovery | yes | PASS | not run |
| G5b user recovery | yes | n/a | **NO** |
| G6 operators/providers/regions | yes | n/a | **NO (1/1/1)** |
| G7 miners | yes | n/a | **NO (2)** |
| G8 no consensus dependency | yes | static PASS | dynamic not run |
| G9 24 h independence | yes | n/a | **NOT EXECUTED** |

None of these is a consensus fork. They are not blockers *for activating the
#40,000 consensus code*. They **are** blockers for any public claim of
decentralization, and G4 + G6 are blockers for a bridge that relies on independent
observers and signers.
