# Operational decentralization — SPOF map, options, engineering vs external maturity

## 1. SPOF / dependency table (what is real, before #30,000)

| Component | Current owner/provider | Dependency today | Independent alternative | Cost | Deploy before #30k? | Needs owner GO |
|-----------|------------------------|------------------|--------------------------|------|---------------------|----------------|
| Consensus / PoW | permissionless | NONE (any miner) | already independent | — | already | no |
| Peer discovery | sostcore.com default seeds | soft (convenience) | peers.txt + seeds.txt + ADDR gossip (D1/D2) | free | **done (code)** | no |
| Bootstrap seed | sostcore.com (1 VPS, 1 ASN) | HARD if alone | independent seed VPS, other ASN/region | ~3–6 USD/mo | yes (if purchased) | **YES ($)** |
| Full node (RPC) | 1 VPS | medium | independent node, other provider | ~5–10 USD/mo | yes (if purchased) | **YES ($)** |
| DNS zone | sostcore.com | soft | 2nd domain / DNS seed record | ~10 USD/yr | yes (if purchased) | **YES ($)** |
| Release download | sostcore.com | medium | 2nd mirror host + IPFS pin + torrent | free–5 USD/mo | yes | partial ($ optional) |
| Chain observer | VPS (1) | low | 2nd observer on other host | reuse seed VPS | yes (if seed bought) | YES ($) |
| Release signing | owner key (offline) | owner step | minisign/GPG tooling prepared | free | prepared | owner key custody |

**Residual HARD dependency after all free work:** a brand-new node with EMPTY peers.txt AND
empty seeds.txt AND sostcore.com down cannot bootstrap — it needs **at least one reachable
peer or seed from ANY source**. Removing that residual requires ≥1 independent seed on a
different provider/ASN (a paid step). Everything else is already code-independent.

## 2. Free now — IMPLEMENT/PREPARE/TEST (no money, no new account)
DONE or prepared: seeds.txt.example, connect-peers.example, systemd/firewall/health-check
examples, peer store, ADDR/GETADDR, redial, independent-node + independent-seed + release-mirror
+ primary-infra-failure runbooks, VPS read-only observer, SHA256SUMS manifest, reproducible
build, package self-verify, sostcore-total-failure lab test (see SOSTCORE_DISAPPEARS). No paid
service or new account used.

## 3. Paid options (NOT purchased — proposal only)

### OPTION A — MINIMUM REAL INDEPENDENCE (removes the single-seed/ASN SPOF)
- 1 independent seed+node VPS, provider ≠ current, different ASN + region.
- cost: ~3–6 USD/mo. role: always-on sost-node seed in DEFAULT_SEEDS/seeds.txt + read-only observer.
- benefit: network bootstraps even if sostcore.com AND the primary VPS are both down.

### OPTION B — STRONGER INDEPENDENCE
- 2–3 seed+node VPS across 2–3 providers / regions / ASNs.
- 1–2 release mirrors (one can be a seed VPS) + IPFS pin.
- cost: ~10–20 USD/mo total.
- benefit: no single provider/region/ASN is a SPOF for bootstrap or distribution; redundant observers.

*I do not need large infrastructure — only enough to eliminate the real SPOFs. Nothing is
bought without explicit owner GO.*

## 4. ENGINEERING COMPLETE vs EXTERNAL MATURITY PENDING (do not conflate)

**ENGINEERING COMPLETE (code + tests, in the candidate):** peer autonomy (D1/D2), bounded
hostile input, adversarial/eclipse/poisoning tests, partition/heal, OLD↔NEW, bootstrap-without-
sostcore, reproducible build, package verify, rollback, SEC2, SACS V2, fuzz, sanitizers.

**EXTERNAL MATURITY PENDING (cannot be finished by code before #30,000):** third-party node
operators, more independent miners, geographic diversity, ASN/provider diversity, external
code review, external security audit, and months/years of real adversarial exposure. These
require independent operators, money, and time — not C++. This is the frontier to attack
*after* the lock.
