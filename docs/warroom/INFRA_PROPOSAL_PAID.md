# Real-infrastructure proposal (point 9) — STOP BEFORE SPENDING

Everything achievable WITHOUT buying services is already done (peer store, ADDR/GETADDR,
seeds.txt, redial, reproducible build, package verify, runbooks, VPS read-only observer,
loss-of-sostcore lab proof). What follows needs money/accounts — prepared, NOT purchased.
Nothing here is bought without explicit owner GO.

## 1. Independent seed node(s) — different ASN / country
- WHAT: 1–3 small VPS running sost-node as always-on seeds, on providers/ASNs/countries
  distinct from the current VPS, added to DEFAULT_SEEDS and/or operators' seeds.txt.
- WHY: removes the single-seed (sostcore.com) and single-ASN dependency — the biggest
  remaining operational centralization lever.
- COST: ~3–6 USD/mo each (1 vCPU / 1–2 GB / small disk).
- CONFIG: sost-node (V30000), open P2P 19333, firewall per docs/firewall.example, systemd
  per docs/systemd-node.example; publish host:port for seeds.txt; optional DNS seed record.
- BENEFIT: network can bootstrap even if sostcore.com and the primary VPS are both down.

## 2. Release mirror(s)
- WHAT: a 2nd download host + IPFS pin + torrent seed of the release + SHA256SUMS.
- WHY: so binaries/manifest survive if the primary host disappears; verifiable anywhere.
- COST: IPFS pin service ~free–5 USD/mo; or reuse a seed VPS (no extra cost); domain optional ~10 USD/yr.
- CONFIG: per docs/RELEASE_MIRROR_RUNBOOK.md; SHA256SUMS stays the single crypto truth.
- BENEFIT: distribution independence; no single download chokepoint.

## 3. External security audit / independent code review
- WHAT: paid third-party review of consensus + the new P2P peer-autonomy code.
- WHY: the one thing engineering discipline cannot self-provide — outside adversarial eyes.
- COST: variable (quote-based; ranges widely by scope/firm).
- CONFIG: scope = SbPoW consensus, fork-choice/SACS, P2P (D1/D2), RPC/SEC2.
- BENEFIT: independent assurance; closes the "self-reviewed only" gap toward BTC/ETH-style scrutiny.

## 4. (Optional) second independent chain observer host
- WHAT: a 2nd read-only height/health observer on a different machine/ASN.
- WHY: removes the single-observer dependency on the current VPS.
- COST: reuse a seed VPS (no extra cost).
- CONFIG: the same read-only observer service, pointed at its own local node.
- BENEFIT: redundant independent monitoring.

NONE of the above is required for the pre-#30,000 technical lock. All are OPERATIONAL /
EXTERNAL-MATURITY steps (post-#30,000). Awaiting owner GO before any purchase.
