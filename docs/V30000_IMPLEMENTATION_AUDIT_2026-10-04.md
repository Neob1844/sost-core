# V30000 Implementation Audit — SECURITY · DEX · TOKENIZATION · REGULATORY · EXPLORER · RELEASES
**AUDIT-FIRST · READ-ONLY · 2026-10-04 · no code/consensus/binary changed**

Verified against code, served web (https://sostcore.com, curl), runtime, tests and git (tags/branches).
Live chain at audit: **height 29,194 → ~806 blocks to #30,000** (`chain-stall.json`).
Status vocabulary: IMPLEMENTED / IMPLEMENTED·PARTIAL / UI ONLY / LAB VERIFIED / SERVER-SIDE VERIFIED / CONFIGURED / PLANNED / NOT FOUND.
("LAB VERIFIED" = engine exists and passes unit tests, but is **not wired into the served product**.)

## Provenance note (critical)
The V30000 native-asset / DEX / S14 code lives in the **`v30000` tag (c9e0d629)** and branch `feat/v30000-native-assets`, **NOT in `main`** (`v30000` is not an ancestor of `main`). The release binaries were built from that tag. The `v30000` tag **does** contain the S14 admin-gate (`tx_validation.h:132` reject `=214`; `params.h:716/723` `ADMIN_AUTHORITY_PKH`; activation #30000). A grep of the `main` working tree finds none of it — correct for `main`, but the shipped release has it.

## FEATURE | STATUS | EVIDENCE | GAP | ACTION NEEDED

### A. Tokenization / Regulatory
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| A1 Regulatory gate (block passport if ack/hashes missing) | UI ONLY | engine `regulatory-record.js:259-277 assertCanGenerate`; page never calls it (served: 0 refs) | gate not wired to UI; on-page gate is prose+ASCII mockup | wire engine into page |
| A1 Regulatory record server-side (ack/ts/jurisdiction/class/checklist ver/identity/doc hashes/history) | NOT FOUND | record built in-memory `regulatory-record.js:154-193`; 0 persistence (localStorage/IDB/fetch/on-chain) anywhere | no durable audit trail exists at runtime | add durable store (server and/or on-chain anchor) before any "audit trail" claim |
| A1 Passport + manifestHash integration (reg record) | LAB VERIFIED | `regulatory-record.js:282-322`; test #6 PASS (deterministic) | engine unwired to served page | wire + anchor |
| A2 Versioning / no-overwrite / prev-hashes / timestamps | LAB VERIFIED | `passport-versioning.js:48-114`; reg tests 3,4,4b PASS | unwired; timestamps = client clock | wire + trusted time |
| A2 Superseded / revoked lifecycle state | NOT FOUND | grep supersede/revoke = 0 in versioning engine | append-only w/ free-text reason only | add lifecycle enum if required |
| A2 manifestHash test-vector contract | LAB VERIFIED | `tests/fixtures/canon_vectors.json` + `asset_passport_v2.test.js` 77/0 | covers Passport v2 canon, no reg-record-specific fixture | add reg fixture |

### B. DEX / Atomic Swap
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| B3 Human-readable signing | IMPLEMENTED·PARTIAL (EVM console, auth-gated) / UI ONLY (SOST leg) | `atomic-swap-console.html:751-762` shows network/chainId + HTLC contract + raw calldata; `atomic-swap.html:488-537` review table (confirm disabled) | EVM shows raw calldata not decoded term sheet; pay/receive/rate/counterparty/expiry/fee/nonce not echoed decoded | decode term sheet pre-sign |
| B4 Anti-replay (signed offer) | LAB VERIFIED | `dex-rfq.js:68-81 canonicalOffer`; `tests/dex_rfq.test.js` 30/0; binds domain(string)/version/network/amount/maker/nonce/expiry | does NOT bind numeric chainId, taker, HTLC contract, explicit price; ETH↔BNB mainnet offer not distinguished; devnet→mainnet IS blocked (network field) | bind chainId+taker+HTLC (ideally EIP-712) before public trading |
| B5 Quote lifecycle states | LAB VERIFIED | all states `dex-rfq.js:25-27`; cancel rules `dex-relay.js:80-85`; tests PASS | **~90s quote + countdown NOT FOUND** (default expiry 24h `dex-trade-engine.js:53`); served dashboard fails closed/DEMO | add 90s quote + countdown before public trading |
| B6 Token/contract allowlist (chainId+contract+decimals+mode) | IMPLEMENTED·PARTIAL | identity split: `asset-registry.js:27-51` (symbol+decimals+mode) + `atomic-swap-evm.js:45-70` (chainId+addr); decimals read live | no single {chainId,contract,decimals,mode,version} tuple; no version field; dead link `docs/dex/ASSET_COMPATIBILITY.md` | unify asset identity |
| B6 USDC / USDT / PAXG / XAUT state | IMPLEMENTED (disabled as designed) | `asset-registry.js:39-50`: USDC=caveat, USDT/PAXG/XAUT=disabled; `ERC20_ENABLED=false`, `BTC_ENABLED=false`, all `htlc:null` | keep disabled until verified | — (correct) |
| B7 Contract destination pinning | IMPLEMENTED·PARTIAL | shown pre-sign `:753-755`; bytecode verify `eth_getCode` vs runtime `:693-696`; operator-pinned, no remote-replace vector | `verifyCode==='EXACT'` not a HARD gate on LOCK (soft warning) | make verifyCode hard precondition |

### C. Releases / Monitoring / Single Source of Truth
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| C8 Signed-release TOOLING | IMPLEMENTED | `scripts/sign-release.sh`, `verify-release.sh`, `docs/RELEASE_SIGNING.md` | — | — |
| C8 SIGNED RELEASE available | NOT FOUND | 0 `.minisig/.asc` over any V16/V30000 SHA256SUMS; only a May-2026 v13-RC `.asc` | release binaries not cryptographically signed | sign SHA256SUMS + publish key |
| C8 OFFLINE CUSTODY complete | NOT FOUND | `docs/RELEASE_SIGNING.md:1-5` "no real release key created/stored/shipped"; no published pubkey (`/keys/sost-release.pub` = SPA fallback) | custody asserted not proven | generate key offline + publish pubkey; never claim "offline secured" until true |
| C9 Cross-observer health monitor | IMPLEMENTED·PARTIAL | `ops/mainnet-health-monitor.sh`+`mainnet_health_detect.py`; unit test `mainnet_health_monitor_test.sh` | NOT deployed; no alert sink (0 mail/tg/webhook); 2 observers NOT independent (both = same VPS node via tunnel); history local-only | deploy + add alert destination + add a truly independent observer |
| C9 Single-node stall monitor | IMPLEMENTED (live) | `scripts/ops/chain_stall_monitor.sh` cron; `chain-stall.json` live (fresh ts) + `sost-health.timer` | single-node only | (works) |
| C10 Explorer network/upgrade panel | IMPLEMENTED | `sost-explorer.html loadNetworkHealth ~8076-8130`; height/version/tip/peers live RPC; activation from manifest; refuses adoption% | height hardcode fallback only if manifest fetch fails | — |
| C11 protocol-status.json canonical | IMPLEMENTED·PARTIAL | file controls release/activation/trading/gate/mode; bound at runtime by only `index.html:1115` + `sost-explorer.html:8040` | ~30 pages hardcode (consistent now, fragile); dashboards (dex/tokenization/decentralization) duplicate strings | bind dashboards to manifest + add drift test |

### F. Admin / S14
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| F12 Admin authority separate from daily wallet | IMPLEMENTED | `src/beacon.cpp:31 BEACON_PUBKEY_HEX`; constitutional PKHs `params.h:790-791`; wallet.json holds none | — | — |
| F12 Operational authority enforced (S13 reserve freeze) | IMPLEMENTED | `TxValCode::S13_RESERVE_FROZEN=213` enforced `tx_validation.cpp:375-401` + node mirrors | — | — |
| F12 Encrypted storage / permissions | IMPLEMENTED·PARTIAL | `~/SOST/secrets` 700, wallet.json 600 | plaintext `miner.json` mode 644; regenesis `*.enc` 644; `.devnet/rpc.pass` not in .gitignore | chmod 600; add gitignore (owner, off-repo) |
| F12 Offline backup | CONFIGURED | doc-asserted (`BEACON_CUSTODY_STATUS.md`) | second off-site backup is recommendation only | verify custody |
| F12 Multisig / multi-admin | PLANNED | Beacon 3-of-5 placeholders `TO_BE_REPLACED_BEFORE_V15`, activation INT64_MAX | not active | post-#30000 |
| F12 S14 gate (ADMIN_AUTHORITY_PKH, reject 214) | IMPLEMENTED·PARTIAL (release-only, unaudited) | **present in tag `v30000`**: `tx_validation.h:132 =214`, `params.h:716 ADMIN_AUTHORITY_PKH`, #30000; **NOT in main**; `S14_ROADMAP.md` "documentation only" + "no external audit exists" | unmerged to main; no external security audit of gated feature set; fail-closed/public-disabled at #30000 | external audit before any PUBLIC use; keep public-disabled at #30000 |

### G. Regulatory Requirements by Jurisdiction (public section)
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| G13 All 21 jurisdictions present | IMPLEMENTED (UI, static) | `sost-universal-assets.html:204-256`; all 21 present, none missing | static `<details>` text | — |
| G14 Regulators + conditional wording | IMPLEMENTED | per-card regulators+links; "may apply depending on asset/structure/rights/offering/investor location" `:209` | shared verify-list, not per-juris line tables | — |
| G15 Disclaimers | IMPLEMENTED | NOT LEGAL ADVICE `:205`; tech≠legal `:220`; NOT DETERMINED BY SOST (×10); last reviewed 2026-10-02 | — | — |
| G16 Asset checklists dynamic by class | UI ONLY (served static) / LAB VERIFIED (engine) | served checklists static `:251-258`; `deriveChecklist` `regulatory-record.js:59` tested but unwired | page can't tailor checklists live | wire deriveChecklist |
| G17 Official sources | IMPLEMENTED | real official regulator domains; last-reviewed date; some non-200 (site-side: sec.gov 403 UA, vara.ae 301) | periodic link review | — |

### H. Professional Attestation
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| H18 Model LEGAL/OWNERSHIP/VALUATION | IMPLEMENTED (UI) + LAB VERIFIED (engine) | `:342-345,:383`; engine `asset-passport.js:42-81` | engine persists simpler {by,statement,issuedAt,expiresAt,revoked} | wire richer fields |
| H18 Registry fields (type/issuer/credential/jurisdiction/scope/hash/date/sig/expiry/status) | IMPLEMENTED·PARTIAL | UI describes all `:281,415-428`; engine persists subset | UI advertises more than loaded engine persists | reconcile UI↔engine |
| H18 States ACTIVE/SUPERSEDED/REVOKED/EXPIRED | IMPLEMENTED (UI) / PARTIAL (engine) | UI `:284,425-428`; engine does expiry+revoked filter, not 4 named states | — | add named states if required |
| H18 "verifies WHO issued WHICH opinion", never "SOST certifies legal" | IMPLEMENTED | `:270,299-305,311,427`; reg test #7 (forbidden auto-states rejected) PASS | — | — |

### I. Explorer / Traceability
| Feature | Status | Evidence | Gap | Action |
|---|---|---|---|---|
| I19 Explorer nav | IMPLEMENTED | served: brand "SOST EXPLORER" + global canonical nav; 5 destinations (Tokenization/CX/DTD/Atomix/News) as global modules; 0 custom markup | spec asked "5 circular tiles"; superseded by owner decision to use global nav (5 destinations preserved) | — |
| I20 Cache self-invalidation | IMPLEMENTED | build ver `2026-10-04-globalnav`; no-store version check; one-time sessionStorage reload guard; try/catch anti-loop | — | — |

## COUNTS (≈36 feature rows)
- IMPLEMENTED: 14
- IMPLEMENTED·PARTIAL: 11
- LAB VERIFIED (engine, unwired): 9
- UI ONLY: 2
- CONFIGURED: 1
- PLANNED: 1
- NOT FOUND: 5

## TOP 5 REAL GAPS
1. **Regulatory audit-trail + passport-versioning engines are ORPHANED and nothing is persisted** (A1/A2) — not server-side, client-side, or on-chain. The "regulatory record / audit trail" is not a shipped runtime feature (engines LAB VERIFIED only).
2. **No signed release + no published public key** (C8) — operators cannot cryptographically verify the V30000 binaries they must run at #30,000; offline custody asserted, not proven.
3. **S14 admin-gate is release-tag-only (not in main) and has NO external security audit** (F12) — ship-safe only because it activates fail-closed with public access disabled at #30,000.
4. **DEX signed-offer anti-replay omits numeric chainId + taker + HTLC contract; no ~90s quote; bytecode-verify not hard-gated; no EIP-712** (B4/B5/B7) — all blockers before PUBLIC trading (post-#30,000).
5. **Cross-observer health monitor not deployed / no alert sink / observers not independent** (C9) + **canonical status bound by only 2/71 pages** (C11) — during the ~806-block activation window the only live automated watch is a single-node stall monitor.

## VERDICT
- CRITICAL BEFORE #30000: **NO** — nothing blocks the already-live chain; the gated native-asset/DEX layer activates fail-closed with public access disabled (S14 present in the release). Items above become critical **before PUBLIC enablement** of DEX/tokenization and **before representing the release as independently verifiable/audited**.
- CONSENSUS CHANGE REQUIRED: **NO**
- BINARY CHANGE REQUIRED: **NO** (fixes are web/tooling/branch + non-consensus client JS; consensus untouched)
- RESTART REQUIRED: **NO**
