# Web Audit v1 — Cross-Domain Parity & Bug Verification

**Date:** 2026-03-28
**Auditor:** NeoB + automated verification
**Domains:** sostcore.com, sostprotocol.com

---

## A. EXECUTIVE SUMMARY

**Domains are EQUIVALENT.** Both serve identical content from the same nginx root (`/opt/sost/website`). SHA-256 hashes match for all tested pages. RPC `/rpc` endpoint works on both domains (confirmed with live getinfo returning height 1823).

**Confirmed bugs: 2** (low severity)
**False positives: 4** (things that look like bugs but aren't)
**Cross-domain risk: LOW** (domain-aware RPC fallback handles it)

---

## B. DOMAIN PARITY MATRIX

| Route | sostcore.com | sostprotocol.com | Same Content | Same RPC | Cross-Domain Links | Risk |
|-------|-------------|-----------------|-------------|---------|-------------------|------|
| / | 200 | 200 | ✓ IDENTICAL | ✓ | 36 refs to sostcore.com | LOW |
| /sost-explorer.html | 200 | 200 | ✓ IDENTICAL | ✓ (fallback) | RPC fallback to sostcore | LOW |
| /sost-markets.html | 200 | 200 | ✓ IDENTICAL | N/A | None | NONE |
| /sost-wallet.html | 200 | 200 | ✓ IDENTICAL | ✓ /rpc relative | None | NONE |
| /sost-app/ | 200 | 200 | ✓ IDENTICAL | ✓ (fallback) | 5 to sostcore, 2 to sostprotocol | LOW |
| /sost-contact.html | 200 | 200 | ✓ IDENTICAL | N/A | mailto only | NONE |
| /sost-geaspirit.html | 200 | 200 | ✓ IDENTICAL | N/A | None | NONE |
| /sost-materials-engine.html | 200 | 200 | ✓ IDENTICAL | API /api/ | None | LOW |
| /sost-tokenomics.html | 200 | 200 | ✓ IDENTICAL | N/A | None | NONE |
| /sost-quickstart.html | 200 | 200 | ✓ IDENTICAL | N/A | None | NONE |

**RPC Response Times:**
- sostcore.com/rpc: 0.275s (HTTP 200)
- sostprotocol.com/rpc: 0.237s (HTTP 200)

---

## C. CONFIRMED BUGS

### BUG 1: Wallet pages use only relative `/rpc` — no domain fallback
**Severity:** LOW
**Affected:** wallet.html, sost-wallet.html
**Domain:** sostprotocol.com (if nginx /rpc proxy wasn't configured)
**Status:** RESOLVED — nginx now proxies /rpc on both domains
**Detail:** Unlike explorer.html and sost-app which have `hostname === 'sostcore.com' ? '/rpc' : 'https://sostcore.com/rpc'` fallback, the wallet pages use only `/rpc` relative. This works now because nginx was fixed, but if nginx config is lost, wallet would break on sostprotocol.com while explorer/app would still work via fallback.
**Recommendation:** Add same domain-aware fallback to wallet pages (low priority since nginx is fixed).

### BUG 2: No `<link rel="canonical">` on any page
**Severity:** LOW (SEO only)
**Affected:** All pages on both domains
**Detail:** No canonical URL tag exists. Google may index both domains as separate sites, potentially splitting SEO authority.
**Recommendation:** Add `<link rel="canonical" href="https://sostcore.com/...">` to all pages.

---

## D. NOT A BUG / EXPECTED BEHAVIOR

### 1. "connecting..." / "loading..." on Home page
**Verdict:** EXPECTED — transient state
The home page shows "CHAIN STATUS · LIVE" with "connecting..." for gold price and SOST price. These are placeholders because SOST is pre-market (no exchange data). The chain status loads correctly within 1-3 seconds showing real block height.

### 2. "0 UTXOs" / "not loaded" in Wallet
**Verdict:** EXPECTED — wallet not initialized
The wallet shows empty state because no wallet has been created/loaded yet. This is the correct initial UX — user must create or import a wallet first. The Quick Guide explains this.

### 3. Explorer "LOADING DATA..." for 5-15 seconds
**Verdict:** EXPECTED — sequential RPC calls
The explorer makes ~58 sequential RPC calls to load the dashboard (getinfo + 50 block hashes + 50 block details + balances). At ~0.25s per call, total load is 10-15 seconds. Not a bug — it's the cost of live data without caching.

### 4. App SESSION ENDED on EXIT
**Verdict:** EXPECTED — design intent
The EXIT button shows "SESSION ENDED" for 3 seconds, then attempts window.close() (works in PWA), or shows "Close tab manually" toast (browser limitation). This is correct behavior.

---

## E. CROSS-DOMAIN RISKS

| Risk | Severity | Detail |
|------|----------|--------|
| 36 hardcoded sostcore.com links in website pages | LOW | Intentional — sostcore.com is the primary domain |
| App links mix sostcore and sostprotocol | LOW | Markets links go to sostprotocol, WEB/EXPL go to sostcore |
| No canonical tag | LOW | SEO risk — duplicate content across domains |
| RPC fallback only in explorer/app, not wallet | LOW | Mitigated by nginx fix |
| contact@sostcore.com hardcoded in contact form | NONE | Correct — email doesn't depend on serving domain |

---

## F. ASSET VERIFICATION

All critical assets return HTTP 200 on both domains:

| Asset | Status |
|-------|--------|
| sost-logo.png | ✓ 200 |
| icon-192.png | ✓ 200 |
| icon-512.png | ✓ 200 |
| manifest.json | ✓ 200 |
| sw.js (v63) | ✓ 200 |
| sost-search.js | ✓ 200 |
| js/materials-data.js | ✓ 200 |

---

## G. RPC LIVE DATA VERIFIED

| Field | Value | Status |
|-------|-------|--------|
| Block height | 1823 | ✓ Live |
| Difficulty | 755,891 | ✓ |
| Connections | 0 | Expected (solo miner) |
| Mempool | 0 | Expected (no pending TX) |
| cASERT Profile | B0 | ✓ Normal |
| Version | 0.3.2 | ✓ |
| Block 1823 hash | c075f542... | ✓ Verified |
| Block 1823 time | 1774692035 | ✓ |
| Block 1823 TXs | 1 (coinbase only) | ✓ Expected |

---

## H. NAVIGATION VERIFICATION

| Button/Link | Source Page | Target | Works | Opens |
|-------------|------------|--------|-------|-------|
| Open Explorer | Home | /sost-explorer.html | ✓ | Same tab |
| Quick Start | Home | /sost-quickstart.html | ✓ | Same tab |
| Start Mining | Home | /sost-getting-started.html | ✓ | Same tab |
| Read Whitepaper | Home | /sost-whitepaper.html | ✓ | Same tab |
| WEB (app header) | App | sostcore.com | ✓ | New tab |
| EXPL (app header) | App | sost-explorer.html | ✓ | New tab |
| EXIT (app) | App | close/toast | ✓ | — |
| BLOCK EXPLORER (markets) | App | /sost-explorer.html | ✓ | New tab |
| OFFICIAL SITE (markets) | App | sostprotocol.com | ✓ | New tab |
| VIEW FULL MARKETS | App | sostprotocol.com/sost-markets.html | ✓ | New tab |
| Contact form | Contact | mailto: link | ✓ | Email client |

---

## I. RECOMMENDATION — PRIORITIZED FIXES

| # | Fix | Priority | Effort | Type |
|---|-----|----------|--------|------|
| 1 | Add canonical URL tags to all pages | LOW | 1 hour | SEO |
| 2 | Add domain-aware RPC fallback to wallet pages | LOW | 30 min | Resilience |
| 3 | Consider explorer data caching (reduce 58 RPC calls) | MEDIUM | 4 hours | Performance |
| 4 | Unify domain references (pick one canonical domain) | LOW | 2 hours | Consistency |
| 5 | Add loading skeleton to explorer (instant visual) | LOW | 2 hours | UX |

**None of these are blocking for launch.** The site works correctly on both domains.

---

## Document History
- 2026-03-28: Initial audit — NeoB
