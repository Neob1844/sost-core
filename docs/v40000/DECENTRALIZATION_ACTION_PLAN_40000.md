# DECENTRALIZATION ACTION PLAN — before #40,000

Status: **PLAN + READ-ONLY ANALYSIS.** Nothing here changes consensus, and nothing
here was deployed. Written 2026-10-13 against `release/v40000-prep` @ `11dc2fcc`.
It turns the gates in `DECENTRALIZATION_GATES_40000.md` (G1–G9) into a minimum
plan: who does what, how it is measured, and whether a miss blocks the release.

**DECENTRALIZATION_GATES_MET = NO.**
* Independent seeds: 0.
* Hosting providers: 1. Regions: 1.
* Producers: 2 in the V16 window.
* No mainnet run of G1/G2/G3/G5/G8/G9 is recorded.

This plan does **not** claim decentralization from software capability. Being able
to persist, gossip and use `seeds.txt` says nothing about who runs the nodes.

## 0. What the code actually does (verified at `11dc2fcc`)

All references are to `src/sost-node.cpp` unless noted.

| Mechanism | Code | Fact |
|---|---|---|
| Compiled-in seeds | `:461-466` | 4 names, all under `sostcore.com`: `seed-eu`, `seed-apac`, `seed-us`, `seed` (alias). No fallback IP literals. |
| Operator seeds file | `:478-497` | `<dir of --chain>/seeds.txt`, one `host` or `host:port` per line, `#` comments, at most 64 entries. A bare host gets port 19333 (hardcoded literal `:493`, equal to `P2P_PORT_DEFAULT` `:301`). |
| Peer store | `:498-555` | `<dir of --chain>/peers.txt`, mode 600, atomic tmp+fsync+rename. Saved every 30 s (`:11003`). Never wiped by an empty set (`:522`). |
| What the store holds | `:515`, `:10409` | **Only the currently connected, handshake-complete outbound peers, written as the dialed string.** For a seed peer that string is the hostname (`seed-eu.sostcore.com:19333`), not the IP. |
| Boot order (no `--connect`) | `:10932-10971` | store → `seeds.txt` → `DEFAULT_SEEDS`; stops at `WANT = 3` (`:10934`). |
| `--connect` | `:10565`, `:10973-10983` | If any `--connect` is given, the store, `seeds.txt` and the defaults are **skipped at boot**. They are still used by the zero-peer redial. There is no `--addnode` (add without excluding). |
| Zero-peer redial | `:10996-11043` | Fires only when `g_peers.empty()` (`:11000`): `--connect` → store → gossip candidates → `seeds.txt` → defaults, `want = 3` (`:11009`). |
| ADDR gossip | `:559-628`, `:9334-9346`, `:9744-9765` | VERS capability byte (`:5469`), one GADR per peer. Serves ≤ 100 addresses at most once per 60 s. Receives ≤ 1000. |
| What is gossiped | `:617-628` | **Outbound peers and store entries only.** Inbound peers are never shared, and a node never advertises its own listen address (VERS is 41 bytes: height, genesis, capability, `:5464-5470`). |
| Gossip filter | `:598-601`, `include/sost/p2p_addr_filter.h` | On mainnet a gossiped address must be a public IPv4 **literal**, so hostnames are dropped. |
| Gossip candidates | `:564`, `:605-616` | Held in memory (cap 256, FIFO). **Dialed only by the zero-peer redial** (`:11025`). They are never persisted. |
| Peer view over RPC | `:2940-2970` | `getpeerinfo` masks the last two octets, so `/16` is the finest resolution. |
| Inbound limits | `:716-717` | 32 inbound, 2 per IP. |

**Three consequences the gate doc does not state.**

1. **G1 in practice.** A node that bootstrapped from the default seeds has a
   `peers.txt` holding `seed-*.sostcore.com:19333`. If sostcore.com DNS is gone,
   that store is useless. The lab G1/PHASE6 PASS used IP-literal peers. A
   default-configured mainnet node does not get that result.
2. **G3 in practice.** In the current topology ADDR delivers almost no dialable
   addresses:
   * A typical node's outbound peers are the seeds. They are gossiped as
     hostnames, and receivers drop hostnames.
   * The seed's own peers are mostly inbound, and inbound peers are never shared.
   * Nobody advertises a listen address.

   Gossip works only between operators who used `--connect` with IP literals.
3. **No growth past 3.** A node with 1–3 peers never dials gossip candidates. It
   stays at that peer count until it loses **every** peer. There is no outbound
   target and no address book, so "autonomous discovery" today means "recovery
   from total isolation", not "growing a diverse peer set".

None of these is a consensus issue. All three are small P2P changes, listed as
**P1–P5** below.

## 1. Non-consensus code gaps (core dev)

All of these are P2P/CLI only. No wire-incompatible change: old peers ignore the
extra VERS bytes, as they already ignore the capability byte.

| ID | Change | Where | Why |
|---|---|---|---|
| **P1** | Persist the **resolved IPv4:port** of each outbound peer, from `getpeername`, in addition to or instead of the dialed hostname | `connect_peer` `:10388-10411`, `save_peer_store` `:510` | G1/G5a must survive sostcore.com DNS loss |
| **P2** | Make the store a bounded **address book**, not a snapshot. Keep the last N (≤ 256) peers that completed a handshake, with a last-success time. Expire after 14 days of failures. Persist gossip-learned addresses only after a successful handshake. | `:510-555` | Today a restart can only redial the ≤ 3 peers that were connected at the last save |
| **P3** | **Outbound target maintenance.** Each 30 s cycle, if outbound < 8, dial up to 2 candidates from the book and gossip set. Prefer distinct /16s, with at most 2 outbound per /16. | main loop `:10990-11043` | Grow past 3 peers; resist eclipse; make G3 propagation real |
| **P4** | **Self-advertisement.** Append the listen port as a u16 to VERS. Share inbound peers as `ip:listen_port` only after a successful outbound probe ("feeler"). Add `--externalip <ipv4>` for operators. | `p2p_send_version` `:5464`, VERS parse `:9333`, `addrs_to_share` `:617` | Without it, gossip cannot spread nodes that accept connections |
| **P5** | **`--addnode <host:port>`**: dialed in addition to store, `seeds.txt` and defaults, unlike `--connect`, which suppresses them at boot. Document both in `--help` and `docs/decentralization/RUN_A_NODE.md`. | arg parse `:10565`, boot `:10932` | Operators currently have to choose between "only my peers" and "only defaults" |
| **P6** | `DEFAULT_SEEDS` gains vetted **independent** hostnames, plus a compiled-in list of ≥ 3 **fallback IP literals**, only after G4 evidence exists. | `:461-466` | Fresh-node bootstrap without sostcore.com and without a hand-made `seeds.txt` |
| **P7** | `getpeerinfo` gains `"subnet16"` and `"source"` (connect / store / seedsfile / dns / gossip / inbound), still masked. Optional `getpeerstore` gives the count only. | `:2955` | Lets `check_decentralization_gates.py` measure bootstrap provenance |
| **P8** | Fix the stale docs: `docs/decentralization/BOOTSTRAP_AUDIT.md`, `website/decentralization-status.json` (`persistent_peer_recovery` still says "no persistent peer store") and `docs/AUTONOMY_STATUS_CHECK.md`. They must also state consequences 1–3 above. | docs/web | Honest public status |

P1, P3 and P5 are each well under 100 lines. P2 and P4 are larger and need the
existing `d1-peer-store`, `d1-addr-fuzz` and `d1-gossip-filter` tests extended.
They also need a 5-node line-topology lab run (G3). None of P1–P8 touches block
or transaction validity.

## 2. Per-gate plan

OWNER_TYPE values: core dev, foundation ops, independent operator, community miner.
BLOCKS_RELEASE_IF_UNMET refers to the #40,000 **software release**. Separately,
every unmet gate blocks any public "decentralized" claim, and G4 + G6 block any
bridge that depends on independent observers or signers
(`ECOSYSTEM_PACKAGE_40000.md`).

### D-1 — ≥ 3 independent seed operators (G4)
* **CURRENT:** 0. `DEFAULT_SEEDS` `:461-466` are all `*.sostcore.com` and resolve
  to one VPS (`docs/SEED_NODES.md`; `website/decentralization-status.json` "all
  default seeds are under one domain"). The paid proposal
  (`docs/warroom/INFRA_PROPOSAL_PAID.md` §1) still awaits owner GO.
* **TARGET:** ≥ 3 seeds that each have:
  * a distinct operator (not the foundation, and distinct from each other);
  * a domain other than `sostcore.com`;
  * an ASN distinct from the project VPS and from each other;
  * a signed challenge on file;
  * ≥ 99 % reachability over 14 days from 2 vantage points.
* **ACTION:**
  1. Publish a seed-operator call with requirements: public IPv4, TCP 19333,
     systemd, release binary hash check, 2–4 GB RAM.
  2. Each operator signs a challenge (`seed:<host>:<date>`) with their
     NODE_BIND node key, or with a sost1 address key if no node key.
  3. Record the operator in `docs/v40000/seed_registry.json`, in the format of
     `scripts/v40000/fixtures/seed_registry.json`, including the evidence.
  4. Publish a signed `seeds.txt` (IP literals) for operators to drop next to
     `--chain`.
  5. After 14 days at ≥ 99 %, add the seeds to `DEFAULT_SEEDS` and as fallback
     IPs (P6). This takes effect only in a new binary.
* **OWNER_TYPE:** independent operator (runs the seed); foundation ops (registry,
  probes); core dev (P6).
* **TEST:**
  * Run
    `check_decentralization_gates.py --source src/sost-node.cpp --seed-registry docs/v40000/seed_registry.json`.
    Expect `G4_INDEPENDENT_SEEDS MET`.
  * A 5-minute TCP-connect probe to each seed from 2 vantage points on
    different ASNs, with the log kept 14 days.
* **BLOCKS_RELEASE_IF_UNMET: NO.** The release's correctness does not depend on
  who runs seeds, and recruiting operators is outside the developers' control.
  It does block the bridge/observer launch and any decentralization claim.

### D-2 — ≥ 3 hosting providers (G6, infrastructure part)
* **CURRENT:** 1 (the project VPS; GATES doc "Hosting providers: 1"). No provider
  mapping exists for the peer view.
* **TARGET:** ≥ 3 distinct ASNs among reachable public nodes, with no single
  operator above 40 % of reachable nodes.
* **ACTION:**
  1. The fastest partial step is foundation ops buying 2 small VPSs (about 3–6 USD
     a month each, per the paid proposal) at 2 other providers. That gives
     **provider diversity, not operator independence**, and the registry must
     say so.
  2. Independent seeds (D-1) count here only if they are on other ASNs.
  3. Keep a local `asn_map.json` (prefix → ASN, provider, region) from a public
     registry dump. It stays local, and nothing is fetched in tests.
* **OWNER_TYPE:** foundation ops (2 VPSs, map); independent operator.
* **TEST:** run
  `check_decentralization_gates.py --asn-map asn_map.json` against nodes in ≥ 2
  regions. `G6_PEER_VIEW_ASN_REGION` reports distinct ASNs. Only /16 is visible,
  so the result is a lower bound, and ambiguous /16s are reported, not counted.
* **BLOCKS_RELEASE_IF_UNMET: NO.** Operational. It blocks claims and the bridge.

### D-3 — ≥ 3 geographic regions (G6, geography part)
* **CURRENT:** 1 (EU, Germany). `seed-apac` and `seed-us` are planned names
  with no confirmed nodes (`docs/SEED_NODES.md` DNS checklist unchecked).
* **TARGET:** ≥ 3 continents among reachable public nodes, and ≥ 1 seed outside
  EU in each of NA and APAC.
* **ACTION:**
  * Place the 2 D-2 VPSs in NA and APAC.
  * Point `seed-us` and `seed-apac` at them (still the project domain, so they
    do not count for G4).
  * Prefer independent operators in other regions for D-1.
* **OWNER_TYPE:** foundation ops; independent operator.
* **TEST:**
  * `getent hosts seed-us.sostcore.com seed-apac.sostcore.com` resolve to
    distinct ASNs.
  * `nc -vz <ip> 19333` succeeds.
  * The script's region count with the map reaches ≥ 3.
* **BLOCKS_RELEASE_IF_UNMET: NO.** Operational.

### D-4 — Autonomous peer recovery without sostcore.com (G1 + G5a)
* **CURRENT:**
  * Lab PASS (`docs/warroom/PHASE6_LOSS_OF_SEEDS_EVIDENCE.md`,
    `GATE9_FINAL_BATTERY.md`).
  * Mainnet not run.
  * Code gap: the store keeps hostnames (`:10409` → `:515`), so a
    default-bootstrapped node's store is useless without sostcore.com DNS.
  * Redial fires only at zero peers (`:11000`).
* **TARGET:**
  * A node with ≥ 1 h uptime and populated store, restarted with `*.sostcore.com`
    blackholed, reaches 1 peer in ≤ 60 s and 3 in ≤ 10 min.
  * It makes zero DNS queries for sostcore.com.
  * It stays at the tip for 24 h (G5a, 3 nodes).
* **ACTION:**
  1. Land P1 and P2.
  2. Then run the G1/G5a procedure on 3 mainnet nodes (one per region once D-3
     exists):
     * `/etc/hosts` entries `0.0.0.0 seed.sostcore.com seed-eu.sostcore.com seed-us.sostcore.com seed-apac.sostcore.com`;
     * `tcpdump -n port 53` running;
     * restart;
     * log time to peers;
     * compare tip hash with 2 observers every 10 min for 24 h.
* **OWNER_TYPE:** core dev (P1/P2); foundation ops (runs); independent operator
  (one of the 3 nodes).
* **TEST:**
  * The `peers.txt` line count is ≥ 3 and contains IP literals:
    `grep -cE '^[0-9.]+:[0-9]+$' peers.txt`.
  * `stat -c %a` gives 600.
  * Node log lines `stored peer connected` appear with timestamps.
  * Zero port-53 queries for `sostcore` appear in the capture.
  * The 24 h tip-hash comparison log has no divergence and no gap > 1800 s.
* **BLOCKS_RELEASE_IF_UNMET: YES** for P1 plus one recorded mainnet G1 run. The
  release ships and documents "peer persistence", the fix is small and fully in
  core-dev control, and today that claim fails in the default configuration.
  The 24 h 3-node G5a part is NO, because it needs D-3.

### D-5 — Address gossip persistence and propagation (G3)
* **CURRENT:**
  * Candidates are memory-only (`:564`) and dialed only at zero peers
    (`:11025`).
  * Only outbound peers are shared (`:620`).
  * There is no self-advertisement (`:5464-5470`).
  * Robustness is lab-PASS (`d1-addr-fuzz` 200k, adversarial 7/7). The
    propagation timing is not recorded.
* **TARGET:**
  * In a 5-node line lab (A–B–C–D–E, each knowing one neighbour), every node
    learns every other node's address within 30 min and reaches ≥ 3 outbound
    without a seed.
  * The learned addresses survive a restart (they are in the address book).
* **ACTION:**
  * Land P2, P3 and P4.
  * Extend `d1-peer-store` and `d1-gossip-filter`.
  * Add a devnet line-topology harness that asserts the propagation time and
    the restart survival.
* **OWNER_TYPE:** core dev.
* **TEST:**
  * Harness output gives per-node `t_full_propagation` ≤ 1800 s.
  * After a kill of every node and a restart, every node reconnects with all
    seeds and `--connect` removed.
  * A malformed-ADDR flood adds ≤ 1 MB RSS (existing case).
* **BLOCKS_RELEASE_IF_UNMET: YES** for P2 + P3 with the lab propagation run.
  Without them the "address gossip" feature in the release cannot discover peers
  in the real topology (consequence 2). P4 can slip to a point release if P3
  lands. Rationale: in-control code, and the public release notes would
  otherwise overstate it.

### D-6 — Independent bootstrap path (G2 + G5b)
* **CURRENT:**
  * A fresh node with empty store and `seeds.txt` and sostcore.com down cannot
    bootstrap. It fails closed by design.
  * There is no non-sostcore seed to put in `seeds.txt` (G2).
  * There is one release source, and RPC and explorer are single instances
    (G5b NOT MET).
  * Reproducible build exists (`docs/decentralization/REPRODUCIBLE_BUILD.md`).
* **TARGET:** with sostcore.com down, a new user can:
  1. get a signed release from a mirror that is neither sostcore.com nor the
     single GitHub account;
  2. verify the signature;
  3. bootstrap from a documented, non-sostcore seed list (`seeds.txt` or
     fallback IPs);
  4. broadcast a transaction through their own node.
* **ACTION:**
  * Sign the #40,000 release `SHA256SUMS` with a published release key.
  * Mirror it per `RELEASE_MIRROR_RUNBOOK.md`: IPFS CID plus 1 independent
    mirror operator.
  * Publish the D-1 `seeds.txt` in the release tarball and in the mirror.
  * Document `--addnode` (P5).
* **OWNER_TYPE:** core dev (signing, P5, tarball); foundation ops (mirror);
  independent operator (second mirror, seeds).
* **TEST:** in a network namespace whose resolver returns NXDOMAIN for
  `sostcore.com` and whose firewall drops the project VPS IP, run the 4 steps
  from scratch with an empty datadir:
  * steps 1–2 by `sha256sum -c` plus signature verify on a mirror download;
  * step 3 shown by `getblockcount` reaching the observer tip;
  * step 4 by `sendrawtransaction` with the txid seen by an external observer.
* **BLOCKS_RELEASE_IF_UNMET:**
  * **YES** for the signed `SHA256SUMS` plus ≥ 1 mirror outside sostcore.com.
    These are cheap and in-control, and a hard-fork binary must be verifiable if
    the primary host is down.
  * **NO** for the bootstrap step 3, which depends on D-1.

### D-7 — Additional independent miners (G7)
* **CURRENT:**
  * 2 producers in the last 429 blocks, top-1 68.8 % (GATES doc, ECONOMICS doc).
  * 174 distinct addresses in 25,000..30,428.
  * The DTD anti-dominance gate is not armed (it needs ≥ 11 distinct miners in
    288).
* **TARGET:**
  * ≥ 5 distinct producers in every 2,016-block window over 30 days;
  * top-1 < 50 %;
  * the DTD gate armed at ≥ 50 % of heights.
* **ACTION:**
  * Publish the miner guide (`docs/decentralization/MINE_SOST.md`) with the
    mandatory flags (`--realtime`, Phase-2 build flags).
  * Publish `getblocktemplate` access via the public RPC gateway.
  * Run the script weekly and publish the numbers.

  No protocol incentive change for #40,000: 80/15/5 stays WATCH.
* **OWNER_TYPE:** community miner; foundation ops (guide, measurement).
* **TEST:** `check_decentralization_gates.py --last 2016` weekly, for 5 weeks,
  using `--merge` for addresses known to share an operator.
  `G7_PRODUCERS MET` in every run.
* **BLOCKS_RELEASE_IF_UNMET: NO.** It is outside protocol control and must not
  be faked. One caveat: if #40,000 carries the multisig hard fork, the operators
  of ≥ 90 % of recent blocks must confirm the upgrade before activation, or the
  fork must slip. With 2 producers this is a 2-party check, and it is a
  scope-doc gate (§F item 6), not this one.

### D-8 — No consensus dependency on sostcore infrastructure (G8)
* **CURRENT:**
  * Static PASS: no HTTP client in node code, and checkpoints compiled in
    (`include/sost/checkpoints.h`).
  * Dynamic full sync not recorded.
* **TARGET:** a node in a network namespace whose only egress is P2P to
  non-sostcore peers syncs from genesis and matches the tip hash of 2 external
  observers.
* **ACTION:** run once on the release candidate, from 2 independent peers
  (`--connect` IP literals). Record the duration and the tip hash.
* **OWNER_TYPE:** core dev / foundation ops.
* **TEST:**
  * The `getblockchaininfo` tip hash equals both observers.
  * `grep -rn "curl\|http" src/sost-node.cpp`-style static check output is
    archived.
* **BLOCKS_RELEASE_IF_UNMET: YES.** It is cheap and in-control, and it is the
  direct evidence that a release binary has no hidden infrastructure dependency.

### D-9 — 24 h independence test (G9)
* **CURRENT:** NOT EXECUTED (`docs/decentralization/INFRA_INDEPENDENCE_TEST_PLAN.md`
  is PLANNED).
* **TARGET:** Variant A (N ≥ 3 independent nodes, M ≥ 2 independent miners,
  sostcore infrastructure off) for 24 h, with:
  * no block gap > 3 × target;
  * no observer divergence;
  * no reorg deeper than 2.
* **ACTION:** schedule after D-1 and D-7 provide the participants.
* **OWNER_TYPE:** foundation ops; independent operator; community miner.
* **TEST:** the plan's own measurement log.
* **BLOCKS_RELEASE_IF_UNMET: NO.** It depends on D-1 and D-7. It blocks any
  "runs without the project" claim.

## 3. Per-gate summary

| Gate | CURRENT | TARGET | OWNER | BLOCKS RELEASE |
|---|---|---|---|---|
| D-1 independent seeds (G4) | 0 | ≥ 3 with evidence, 14 d ≥ 99 % | indep. operator + foundation ops + core dev (P6) | NO (blocks claims/bridge) |
| D-2 hosting providers (G6) | 1 | ≥ 3 ASNs | foundation ops + indep. operator | NO |
| D-3 regions (G6) | 1 (EU) | ≥ 3 continents | foundation ops + indep. operator | NO |
| D-4 recovery w/o sostcore (G1/G5a) | lab PASS; store keeps hostnames; mainnet not run | ≤ 60 s / ≤ 10 min, 0 DNS, 24 h tip | core dev (P1/P2) + ops | **YES** (P1 + 1 mainnet G1 run) / NO (24 h 3-node) |
| D-5 gossip persistence/propagation (G3) | memory-only, zero-peer only, outbound-only, no self-advert | 5-node line ≤ 30 min, survives restart | core dev (P2/P3/P4) | **YES** (P2 + P3 + lab run) |
| D-6 independent bootstrap path (G2/G5b) | single source, no non-sostcore seed | 4-step drill passes | core dev + ops + indep. operator | **YES** (signed sums + 1 mirror) / NO (seeds part) |
| D-7 miners (G7) | 2 producers, top 68.8 % | ≥ 5 per 2,016, top < 50 % | community miner | NO |
| D-8 no infra dependency (G8) | static PASS | dynamic full-sync match | core dev / ops | **YES** |
| D-9 24 h independence (G9) | not executed | Variant A passes | ops + operators + miners | NO |

## 4. Checklist by block height

The chain pace is about 144 blocks/day. Re-anchor the dates with `getblockcount`;
the plan is keyed to heights. The multisig hard-fork notice needs 4 weeks (about
4,032 blocks), so its latest publication height is about **#35,968**. The
decentralization go/no-go is aligned with it at **#36,000**.

| By height | Item | Owner |
|---|---|---|
| #31,000 | Owner GO/NO-GO on the paid VPS proposal (2 VPSs, NA + APAC) | foundation |
| #31,000 | P1 + P5 + P8 merged to `release/v40000-prep`, with tests | core dev |
| #31,500 | Seed-operator call published; registry format fixed (`seed_registry.json`) | foundation ops |
| #32,000 | P2 + P3 merged; 5-node line-topology harness passes (D-5) | core dev |
| #32,000 | 2 foundation VPSs live in NA and APAC; `seed-us` / `seed-apac` DNS set (D-2/D-3 partial) | foundation ops |
| #32,500 | Weekly `check_decentralization_gates.py` report starts (peers, /16, ASN map, producers 2,016) | foundation ops |
| #33,000 | ≥ 3 independent seed candidates running with evidence; 14-day probes start (D-1) | indep. operators |
| #33,500 | Mainnet G1 run recorded on the P1 build (D-4); G8 dynamic full sync recorded (D-8) | core dev / ops |
| #34,000 | P4 (self-advertisement) merged or explicitly deferred to a point release | core dev |
| #35,000 | 24 h G5a on 3 nodes in 3 regions; G5b 4-step drill (D-6) with signed sums + mirror | ops |
| **#36,000** | **GO/NO-GO.** Release blockers D-4(P1 + G1 run), D-5(P2 + P3 + lab), D-6(signed sums + mirror), D-8 must be green. Freeze the decentralization status page from the measured report. | owner |
| #36,000–#38,000 | If D-1 has 14 days ≥ 99 %, add the independent seeds and fallback IPs to `DEFAULT_SEEDS` (P6) in the release binary | core dev |
| #38,000 | G9 24 h independence test if D-1 and D-7 provide participants; otherwise recorded as NOT EXECUTED | ops |
| #40,000 | Publish the measured gate table. No decentralization claim unless G4, G6 and G7 are MET. | foundation |

## 5. Measurement tool

`scripts/v40000/check_decentralization_gates.py` (stdlib, read-only RPC).

**What it calls.** Only `getpeerinfo`, `getblockcount`, `getblockhash` and
`getblock`. The password comes from a mode-600 file (`--rpc-pass-file`, which
refuses group- or world-readable files) or from `SOST_RPC_PASS`, and is never
printed.

**What it measures.**
* Peer count by direction and handshake state.
* Distinct /16 and the largest /16 share.
* With `--asn-map`: distinct ASNs, providers and regions (at /16 granularity;
  ambiguous /16s are not counted).
* Distinct producers and top-1 share over `--last N` blocks, with `--merge` for
  known address groups.
* The compiled-in seeds parsed from `--source src/sost-node.cpp`.
* With `--seed-registry`: independent seeds under strict rules (non-project
  domain, distinct non-project operator, distinct non-project ASN, non-empty
  evidence).

**Output.** Each gate is reported as MET / NOT_MET / NOT_MEASURED. `--strict`
exits 1 on any NOT_MET.

**What it cannot measure.** Operator independence from IPs, and G1–G3, G5, G8 and
G9, which are procedures. The output says so.

**Tests.**
* `python3 -I scripts/v40000/test_check_decentralization_gates.py`: 31 tests on
  fixtures in `scripts/v40000/fixtures/`, with no network.
* One test parses the real `src/sost-node.cpp` and asserts the current state:
  4 seeds, all under `sostcore.com`, G4 NOT_MET.

Example (offline, fixtures):

```
python3 -I scripts/v40000/check_decentralization_gates.py \
  --fixture-dir scripts/v40000/fixtures \
  --asn-map scripts/v40000/fixtures/asn_map.json \
  --source src/sost-node.cpp
```

Live, against your own node:

```
python3 -I scripts/v40000/check_decentralization_gates.py \
  --rpc-url http://127.0.0.1:18232 --rpc-user <user> --rpc-pass-file <mode-600 file> \
  --last 2016 --asn-map <local asn_map.json> --source src/sost-node.cpp \
  --json-out decentralization-report.json
```

## 6. Implementation status (branch `feat/v40k-p2p`, 2026-10-14)

Code only — not released, not deployed, no mainnet run. It changes none of the measured
gates (independent seeds 0, providers 1, regions 1, producers 2).

| ID | Status | Where | Evidence |
|---|---|---|---|
| P1 | DONE | `connect_peer` (getpeername), `save_peer_store`, `include/sost/p2p_addrbook.h` | lab: every `peers.txt` holds only IPv4 literals, mode 600; a node whose store had `seed-eu.sostcore.com` + one IPv4 recovered through the IPv4 entry and dropped the hostname |
| P2 | DONE | `AddrBook` (256 cap, last-success, back-off, 14-day expiry, gossip persisted only after a handshake) | `d1-peer-store` 54 checks; `d1-addr-fuzz` +50k `peers.txt` fuzz; restart lab below |
| P3 | DONE | main loop: outbound target 8, 2 dials/cycle, ≤ 2 per /16 (devnet loopback exempt), 5 s connect timeout | lab: every node ≥ 3 outbound without a seed |
| P4 | DONE | VERS 41 → 51 bytes (listen port + self nonce, cap bit 0x02), feeler verification, GADR refresh 120 s, `--externalip` | old `4d8f9899` ↔ new in both directions, no penalties; old node bootstraps from a v2 `peers.txt` |
| P5 | DONE | `--addnode` (discovery stays on), `--connect` exclusive, `bootstrap_plan` | unit tests + lab (line topology built only with `--addnode`) |
| P6 | MECHANISM DONE, LIST EMPTY | `FALLBACK_SEED_IPS` in boot plan and zero-peer redial | unit test with a test list; no operator invented — entries need D-1 evidence |
| P7 | DONE | `getpeerinfo` `source`/`subnet16`/`listen_port`/`feeler`; `getaddrbookinfo` (counts only); gates script reads them | lab, `test_check_decentralization_gates.py` 32 tests |
| P8 | DONE | `BOOTSTRAP_AUDIT.md`, `AUTONOMY_STATUS_CHECK.md`, `website/decentralization-status.json`, `RUN_A_NODE.md` | — |
| D-6 tooling | DONE (no key, no mirror deployed) | `scripts/release/`, `scripts/{sign,verify}-release.sh`, `release/MIRRORS.txt` | ctest `release-integrity` 28 checks with throwaway keys |

**Five-node lab** (`tests/p2p/run_p2p_lab.py`, devnet build, inside `unshare -rn` with only
loopback: `seed.sostcore.com` unresolvable, default seeds tried and failing):

* L1 line A←B←C←D←E, each node only `--addnode` its left neighbour:
  `t_full_propagation` A 124 s, B 93 s, C 93 s, D 93 s, E 93 s (target ≤ 1800 s);
  ≥ 3 outbound: A 63 s, B 63 s, C 33 s, D 33 s, E 63 s.
* L2 a block mined on A reached all five nodes.
* L3 all nodes stopped and restarted with no `--addnode`/`--connect`: every node had ≥ 1
  outbound peer after 59 s (the first cycle hits the 60 s back-off of the dials that failed
  while the other nodes were still starting) and ≥ 3 outbound 30 s later; reconnection came
  from `peers.txt`; a block mined on E reached every node.
* L4 a clean node with only `--addnode` to one node synced and learned all five addresses
  (≥ 3 outbound); a clean node with only a `peers.txt` (hostname + one IPv4) synced.
* L5 old/new interoperability as above. Result: 27/27 checks.
