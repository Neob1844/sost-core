# SOST — Decentralization + Security + BTC/ETH Benchmark + Roadmap (READ-ONLY AUDIT)
**2026-10-05 · chain tip ~29,071 (V30000 fork @30,000 NOT yet active) · no code/consensus/binary/process changed**

Audited: `main` repo + `v30000` tag (P2P cross-check) + served web (sostcore.com) + VPS read-only + docs. The repo's own `decentralization-status.json`, `BOOTSTRAP_AUDIT.md`, `S14_ROADMAP.md`, `PROJECT_STATUS.md` are accurate and match the code — no marketing overclaim found in the status files.

Framing (per owner): the goal is **maximum practical autonomy**, not "100% decentralized" — the network must keep discovering peers, propagating blocks/txs, validating, mining, syncing new nodes, obtaining verifiable software and recovering even if the primary VPS, sostcore.com, the explorer, the public RPC, the bootstrap seeds, main GitHub and the operators all disappear. And the BTC/ETH gap separates **engineering gaps** (buildable) from **network-maturity gaps** (only time/operators/external review provide).

---

## ENTREGA 1 — DECENTRALIZATION

### Current state (summary)
- **Consensus / mining / validation decentralization = real & permissionless (design STRONG):** PoW ConvergenceX/SbPoW + cASERT; no masternodes/voting/ChainLocks/central chain selection. Anyone can run a node and mine. No admin key over base consensus (transfers/mining/DTD).
- **Operational autonomy = the gap (EARLY):** peer discovery, bootstrap, distribution and public services are centralized on **one domain (sostcore.com)** and **one GitHub org**.

### Critical centralization dependencies (7 SPOFs, all traceable to 2 roots)
| # | Dependency | Status | SPOF | Blocks NEW-node survival if lost |
|---|---|---|---|---|
| Seeds (DNS) | 4 seeds all `*.sostcore.com` (one zone/registrar) | NOT INDEPENDENT | YES | YES |
| Bootstrap | no hardcoded fallback IPs; seeds only when `--connect` empty | PARTIAL | YES | YES |
| Website/DNS | one domain hosts site+seeds+RPC+explorer+status json | EXTERNAL DEP | YES | YES (shares seed zone) |
| Persistent peer store | none (no peers.dat/addrman) | NOT IMPLEMENTED | contributes | NO (if seeds up) |
| ADDR/GETADDR gossip | **not in code** (verb set has EKEY/VERS/GETB/BLCK/TXXX/PING/BCNN, no ADDR) | NOT IMPLEMENTED | YES (no mesh growth) | NO |
| Software distribution | single source `github.com/Neob1844/sost-core/releases` | EXTERNAL DEP | YES | NO (existing nodes run) |
| Release signing | no signature over v30000 SHA256SUMS; trust = GitHub account | NOT IMPLEMENTED | YES | NO |
| Explorer / Public RPC | 1 project explorer + 1 public RPC | EXTERNAL DEP | YES (services) | NO |

Non-blocking / OK: node decentralization (PARTIAL, permissionless), chain-data availability (full copy per node), S14 admin (scoped to tokenization/DEX only — base network survives), DTD/NODE_BIND (opt-in, non-central), build reproducibility (path-independent; cross-machine PARTIAL), release verification (SHA256SUMS present).

### Network-survival dependencies
- **Existing connected nodes:** survive sostcore.com loss — keep validating/relaying/mining (no SPOF for the connected set).
- **NEW nodes:** CANNOT bootstrap if sostcore.com DNS is down (seeds share the zone, no fallback IPs, no gossip). A seed-only node that loses all peers never redials (`reconnect` guarded by `!connect_addrs.empty()`, `src/sost-node.cpp:9584-9596`).
- **24H INFRASTRUCTURE-INDEPENDENCE TEST READY: NO** — PLANNED, not executed (`INFRA_INDEPENDENCE_TEST_PLAN.md`; `decentralization-status.json` infrastructure_independence_test_24h=planned). The three load-bearing pieces (persistent store, ADDR gossip, independent/fallback bootstrap) must land first, or a fresh node fails the test.

### Roadmap to maximum practical autonomy (phases, no dates; all P2P/operational, NO consensus change, all deferrable AFTER #30,000)
- **D1 Peer autonomy** — persistent addr store + rate-limited ADDR/GETADDR + redial-from-store. Removes: seed-only redial gap, no-mesh-growth, restart re-bootstrap. HardFork NO · Binary YES · After#30k YES.
- **D2 Bootstrap independence** — seeds on 2-3 distinct domains/registrars/DNS + DNSSEC + curated fallback-IP list + community seed operators. Removes: single-DNS-zone + no-fallback SPOF. HardFork NO · Binary YES.
- **D3 Distribution/release independence** — GPG/minisign-sign SHA256SUMS + pubkey off-GitHub + mirrors (IPFS/torrent/2nd host) + pinned toolchain for cross-machine determinism. Removes: single-source + unsigned-release SPOF. HardFork NO · process/next-release.
- **D4 Infrastructure independence** — run the 24h primary-OFF test; stand up ≥1 independent node (Singapore planned) + community nodes. Removes: unproven-recovery. Ops only.
- **D5 Governance/admin minimization (S14)** — lift the tokenization/DEX admin gate only after `S14_ROADMAP.md §3` prereqs incl. **external audit** → future height-gated release. HardFork YES (future, strictly after #30,000).
- **D6 Adversarial independence test** — eclipse/partition/deep-reorg drills; reconcile the SACS 500-cap boundary at scale. Mostly binary/monitoring; the cap→advisory change is a future consensus upgrade.

---

## SACS — SOST Autonomous Chain Safety
**STATUS: PARTIAL / RESEARCH — NOT on main, NOT in the v30000 tag, NOT running on mainnet.** Branch `research/sost-autonomous-chain-safety` (rebased 2026-09-29); ctest 119/119; **consensus diff vs main = ZERO** (observability-only additions; `MAX_REORG_DEPTH=8` + `--sacs-recovery-mode` are `#if SOST_DEVNET_FORKS` only). Web labels it **LAB VERIFIED · RESEARCH**, never mainnet-live. `build-sacs/` dirs are BUILD OUTPUT, not SACS source.
- **What it does:** each node independently follows the highest cumulative **verified-work** chain; recovers from splits; detects reorg attempts (DEEP_REORG_ALERT); protects exposed txs via a state machine (CONFIRMED→REORGED→REENTERED_MEMPOOL→CONFLICTED); read-only RPC `getchainsafety/getsacsstatus/getsacsevents`. No masternodes/votes/authority/manual dev action.
- **Honest limit (repo's own words):** NOT absolute finality — "a valid higher-work chain cannot be excluded by software alone". `MAX_REORG_DEPTH=500` cap: ≤500 converge to most-work; ≥501 persistent split even with more valid work. It detects/alerts; it does NOT stop a <500-deep 51% reorg. Correct framing: automate safety & recovery, not promise PoW finality.

---

## ENTREGA 2 — SECURITY (SEC2)

### SEC2 IDENTIFIED AS
A **narrow node-RPC crash-hardening release** (`v16.3.0-sec2`), NOT a broad security program. = sec1 (fork-store hardening) + fixes for two pre-existing **unauthenticated remote RPC-DoS** bugs reachable via the public gateway: (1) `getblockhash ["str"]` → uncaught `std::stoll` → abort; (2) `getblock [[[[1]]]]` → parser infinite loop → ~6GB OOM. Fix = dispatch try/catch + JSON delimiter-advance + nested-array cap (256). Source of truth: `protocol-status.json security_mode:"SEC2"`, `sost-security.html:603`, `docs/PROJECT_STATUS.md:57-64`.
**Scope caveat:** SEC2 is **PREPARED + lab-verified but the fixed node binary is NOT deployed** (live node `78fefb67` ≠ SEC2 `5b50a448`). Prod is protected only by an **interim gateway param-shape filter that IS live** (`/opt/sost/sost-rpc-proxy.py`), a single layer in front of the still-raw binary.

### Before → After (deployed around SEC2; most are operational web hardening, not the SEC2 binary itself)
**WEB/OPERATIONAL (live & GOOD):** node RPC bound 127.0.0.1 only (public via gateway :18299, method-gated, injects creds only for sendrawtransaction); secrets `/etc/sost/*` mode 600; **admin 2FA TOTP ACTIVE** (enrolled+enabled) + 10 one-time hashed backup codes + progressive lockout (60/300/900s) + 0.4s timing delay + 8/5min RL; signed HMAC session cookie HttpOnly+Secure+SameSite=Strict + 75s idle timeout; append-only audit log (no secrets); TLS + HSTS (max-age 1y, includeSubDomains) + X-Content-Type-Options + X-Frame-Options + Referrer/Permissions-Policy. Gateway rejects both SEC2 culprit shapes with HTTP 400.
**BLOCKCHAIN/CONSENSUS (independent of SEC2):** P2P ban scoring (100/24h, 64 inbound, 4/IP) + X25519/ChaCha20 encryption default-on; reorg cap 500 + checkpoints + coinbase maturity 1000; Beacon single-sig key offline (3-of-5 placeholders OFF); S14 gate fail-closed; DEX/EVM NOT deployed (admin-gated @30000); human-readable tx signing + new-address cooldown.

### Critical security gaps
1. **SEC2 node binary not deployed** — live node still carries both RPC-DoS bugs at the binary level; only the single live gateway filter protects prod.
2. **Docs↔prod divergence** — `PROJECT_STATUS.md` says the proxy mitigation is "NOT applied to prod," but the live proxy DOES enforce it; the mitigation lives on a branch, not tracked `main`. Prod and source diverged.
3. **CSP allows `unsafe-inline`/`unsafe-eval`** on script-src → weakens XSS protection.
4. **Release signing = tooling only** (no key, no signature, no published pubkey) — integrity yes, authenticity no.
5. **Key-material hygiene nits** — regenesis `*.enc`/`miner.json` reported mode 644; `.devnet/rpc.pass` not in .gitignore; key lines in bash_history.
6. **chain.json mid-write atomicity** — audited fail-safe; mining-halt-after-save-failure proposed, not coded.

### Engineering gaps (buildable) vs Maturity/ecosystem gaps (only time/operators/external parties)
- **Engineering:** deploy SEC2 binary; fold interim proxy fix into main; tighten CSP (nonces/hashes); generate+publish release signing key + sign SHA256SUMS; fix key-perm/gitignore/bash_history hygiene; code the mining-halt policy; path-independent reproducible build; finish the full-node adversarial gauntlet; cross-platform installer + peer persistence + working independent seed DNS.
- **Maturity/ecosystem:** independent 3rd-party security audit (code + EVM swap contract); hashrate diversity (one miner ~90% — demand-dependent, cannot be manufactured); ≥3 independent node operators + 24h founder-OFF proof; real-world DEX/atomic-swap hardening via usage + bitcoind-regtest + external audit before BTC; incident-response maturity; multi-admin/threshold custody (POST-#30000).
**Web-security ≠ blockchain-security:** the 2FA/headers/gateway harden the operator's web/admin surface; they do nothing for hashrate concentration or the node-binary DoS, and the ~90%-one-miner risk cannot be closed by any web control.

---

## ENTREGA 3 — BTC | ETH | SOST (architecture, not market cap)
Labels: MATURE / STRONG / PARTIAL / EARLY / MISSING / UNKNOWN. SOST column from code+config+VPS+docs; BTC/ETH from primary sources (Bitcoin Core/BIPs, ethereum.org/EIPs/client docs).

### Security
| Dimension | Bitcoin | Ethereum | SOST today | SOST target | Gap type |
|---|---|---|---|---|---|
| Consensus | PoW SHA-256d (MATURE) | PoS Gasper+Casper FFG (MATURE) | PoW ConvergenceX/SbPoW+cASERT (design STRONG) | same, reviewed | — |
| Economic attack resistance | STRONG (>50% hashrate, sunk ASIC) | STRONG (slash ≥1/3 stake) | **EARLY** (one miner ~90% ⇒ cheap 51%) | hashrate diversity | MATURITY |
| Hash/stake distribution | top-3 pools ≈61.6% | Lido ≈23-25% | **EARLY/MISSING** (~90% one addr) | many miners | MATURITY |
| Client implementations | PARTIAL (Core dominant) | STRONG (6 EL + 6 CL) | **MISSING** (1 impl) | ≥2 impls | ENG+MATURITY |
| Node diversity | ~25,108 nodes | ~8,203 EL nodes | **EARLY** (observed 2; independent UNKNOWN) | ≥3 independent | MATURITY |
| Consensus maturity | since 2009 | since 2022 (PoS) | **EARLY** (<1y, pre-#30k) | years live | MATURITY |
| Years in production | ~17 | ~11 (PoS ~3) | **<1** | time | MATURITY (unbuyable) |
| External audits/review | STRONG (BIP + 1000+ contrib) | STRONG (EF + Immunefi, $1M bounty) | **MISSING** (none) | ≥1 external audit | ENG→then MATURITY |
| Public bug bounty | PARTIAL (disclosure, no bounty) | STRONG ($1M) | **MISSING** | bounty/disclosure | ENG |
| Cryptography | MATURE (secp256k1/Schnorr) | MATURE (secp256k1+BLS+KZG) | STRONG reuse (secp256k1/SHA256) **but SOST-specific review MISSING** | reviewed | ENG+MATURITY |
| Release signing | MATURE (GPG guix.sigs) | STRONG (per-client) | **MISSING** (tooling only) | sign+publish key | ENG |
| Reproducible builds | MATURE (Guix bit-for-bit) | PARTIAL | **PARTIAL** (path-dependent) | cross-machine det. | ENG |
| P2P DoS hardening | STRONG | STRONG | **PARTIAL** (ban scoring yes; RPC-DoS binary undeployed; gateway interim) | deploy SEC2+gauntlet | ENG |
| Partition resistance | STRONG (reconverge) | STRONG (inactivity leak) | **PARTIAL** (SACS research, not live) | SACS/tests | ENG+MATURITY |
| Eclipse resistance | PARTIAL/STRONG (addrman) | PARTIAL (discv5) | **EARLY/MISSING** (no gossip/store, single DNS zone) | D1/D2 | ENG |
| Sybil resistance | PoW cost | staked capital | PoW cost (design OK) but low hashrate | more hashrate | MATURITY |
| Reorg resistance | probabilistic (6 conf) | finality ~12.8min | **PARTIAL** (500-cap+checkpoints; SACS research) | SACS live | ENG+MATURITY |
| Finality | probabilistic | economic finality | **probabilistic** (honest; PoW) | — (PoW) | — |
| Supply-chain | MATURE (guix.sigs) | PARTIAL | **PARTIAL** (single GH, unsigned) | mirrors+signing | ENG |

### Decentralization
| Dimension | Bitcoin | Ethereum | SOST today | SOST target | Gap type |
|---|---|---|---|---|---|
| Permissionless validation | STRONG | STRONG | **STRONG** (design) | — | — |
| Permissionless block production | STRONG | STRONG | **STRONG** (design) | — | — |
| Independent miners/validators | pools of many | ~881-922k validators | **EARLY** (~2 recent, ~90% one) | many | MATURITY |
| Concentration | top-3 ≈61.6% | Lido ≈24% | **HIGH** (one ~90%) | spread | MATURITY |
| Independent nodes | ~25k | ~8k | **EARLY** (observed 2) | ≥3 | MATURITY |
| Geo / ASN diversity | STRONG/PARTIAL | STRONG/PARTIAL | **UNKNOWN/MISSING** | measure+grow | MATURITY |
| Peer discovery | DNS seeds + addr gossip | discv5 DHT + DNS | **PARTIAL** (DNS seeds + --connect only, no gossip) | D1 | ENG |
| DNS seed diversity | 8 seeds, ~8 operators | per-client lists | **MISSING** (4 seeds, 1 domain/zone) | D2 | ENG |
| Bootstrap independence | STRONG | STRONG | **MISSING** (no fallback IPs) | D2 | ENG |
| Software repo independence | PARTIAL (1 canonical) | STRONG (many clients) | **MISSING** (1 GH) | D3 mirrors | ENG |
| Explorer independence | STRONG (many) | STRONG (many) | **MISSING** (1 project) | 3rd-party | ENG+MATURITY |
| RPC independence | STRONG | STRONG | **MISSING** (1 public) | community RPC | ENG+MATURITY |
| Governance/admin authority | none (BIP) | none (EIP) | **PARTIAL** (base: none; S14 gate on tokenization/DEX) | D5 minimize | ENG+MATURITY |
| Survive dev disappearance | PROVEN (Satoshi) | STRONG (multi-team) | **NOT PROVEN** (new-node bootstrap fails if sostcore.com down) | D1-D4 + test | ENG→then proof |
| Protocol change process | BIP | EIP | **EARLY** (owner-driven) | documented open process | MATURITY |

### TOP SECURITY GAPS
1. **Deploy the SEC2 node binary** (live binary still has both RPC-DoS bugs; only a single interim gateway layer protects prod) + fold the proxy fix into `main`.
2. **Independent third-party security audit** (code + EVM atomic-swap contract) — none exists; prerequisite to lifting S14.
3. **Release signing** (sign SHA256SUMS + publish key off-GitHub) + tighten CSP (remove unsafe-inline/eval).

### TOP DECENTRALIZATION GAPS
1. **Peer autonomy (D1):** persistent peer store + ADDR/GETADDR gossip — without it the mesh can't grow or self-heal.
2. **Bootstrap independence (D2):** seeds on independent domains/registrars + fallback IPs — today all 4 seeds share one sostcore.com zone (single DNS SPOF).
3. **Hashrate + operator diversity:** one miner ~90%, ~1 independent node, 1 explorer/RPC — MATURITY gap, demand-driven, not buildable by code.

---

## ENTREGA 4 — SECURITY + DECENTRALIZATION ROADMAP (P0-P3, measurable exits, no dates)
| Task | Prio | Risk addressed | Current→Target | Hard fork | Binary | Web only | Complexity | Exit criterion |
|---|---|---|---|---|---|---|---|---|
| Deploy SEC2 node + fold proxy fix to main | **P0** | unauthed RPC-DoS at binary; docs/prod divergence | gateway-only → fixed binary + tracked | NO | YES (node swap) | no | MED | live node sha = SEC2; both culprits 400 at node; main == prod proxy |
| Release signing + published pubkey + CSP tighten | **P0** | release authenticity; XSS | tooling-only→signed; unsafe-inline→nonce | NO | release process | yes (CSP) | MED | 3rd party verifies signed release off-GitHub; CSP has no unsafe-* |
| Key-material hygiene (perms/gitignore/history) | **P0** | secret exposure | 644/untracked → 600/ignored | NO | NO | no | LOW | perms 600; .gitignore covers; history scrubbed |
| D1 Peer autonomy (store+ADDR/GETADDR+redial) | **P1** | seed SPOF, no mesh growth, restart re-bootstrap | not impl → impl | NO | YES | no | MED/HIGH | node reconnects after full peer loss+restart with seeds blocked; learns un-told peers |
| D2 Bootstrap independence (multi-domain seeds+fallback IPs) | **P1** | single DNS-zone SPOF | 1 zone → ≥2 + fallback | NO | YES | no | MED | fresh node bootstraps with sostcore.com DNS unresolvable |
| D3 Distribution independence (mirrors) | **P1** | single-source SPOF | 1 GH → mirrors | NO | process | partial | LOW/MED | verifiable signed release from a mirror with GH+site down |
| Independent external security audit | **P2** | unreviewed consensus/EVM | none → ≥1 audit | NO | NO | no | HIGH (external) | published audit report; findings triaged |
| D4 24h infra-independence test | **P2** | unproven recovery | planned → executed | NO | NO | no | MED | ≥24h block production + new-node sync with primary OFF |
| Hashrate + node operator diversity | **P2/P3** | 51% + bootstrap concentration | ~90%/~2 → many | NO | NO | no | HIGH (ecosystem) | largest miner <33%; ≥3 independent nodes; ≥2 explorers/RPC |
| SACS to mainnet (observability first) | **P2** | reorg/split detection & tx safety | research → live (alerts) | NO (observability) | YES | no | HIGH | getchainsafety live; alerts fire in adversarial lab |
| D5 S14 minimization | **P3** | admin gate on tokenization/DEX | gated → reduced | YES (future fork) | YES | no | HIGH | external audit passed; gated ops on testnet without admin key |
| D6 Adversarial independence (eclipse/partition) | **P3** | eclipse/split | untested → validated | NO (mostly) | YES | no | HIGH | node resists eclipse with seeds blocked; split-recovery evidence |

**P0 = before enabling any public critical function. P1 = high-priority post-#30,000 (all P2P/operational, no consensus change). P2 = network-maturity / external. P3 = long-term + the one future consensus item (S14).** No core/consensus change is proposed before #30,000.

---

## ENTREGA 5 — GLOBAL SEARCH (frontend, DONE)
Canonical = `website/sost-search.js` (`initInlineSearch()` auto-injects `.gs-search-bar` after `<nav>`; routes to explorer `?search=`). Added to 13 public pages missing it; 45 already had it; explorer keeps its own `#searchIn` (correctly excluded). 0 duplicates. Verified desktop + mobile 320/360/390/412. Commit `ae78a682`.

---

## I — PROPOSED News/Decentralization-Security update (NOT applied — audit only)
Update the News/Decentralization-Security section to a transparent 4-state model, no "as secure/decentralized as Bitcoin" and no "fully decentralized":
- **LIVE:** permissionless PoW consensus; independent full-node validation; per-node chain copy; configured-peer redial; base network (transfers/mining/DTD) has no admin key; operator web/admin surface hardened (2FA live); SHA256SUMS integrity; SEC2 fixes prepared + interim gateway mitigation live.
- **PARTIAL:** node/miner diversity (few operators, one dominant miner); reproducible build (path-dependent); SACS (LAB/RESEARCH, not mainnet).
- **PLANNED:** persistent peer store + ADDR/GETADDR gossip (D1); independent/fallback bootstrap + multi-domain seeds (D2); signed releases + mirrors (D3); 24h infra-independence test (D4); S14 minimization (D5, future fork).
- **REQUIRES EXTERNAL MATURITY:** independent security audit; thousands of operators; years of adversarial exposure; independent infrastructure — explicitly stated as not buildable by code alone.
Keep the honest frame: **engineering gaps vs network-maturity gaps**; SACS = automated safety/recovery, NOT PoW finality.
