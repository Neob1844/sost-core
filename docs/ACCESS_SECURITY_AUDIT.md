# Access Security Audit — GeaSpirit + Materials Engine

**Date:** 2026-03-24
**Scope:** Access gates, secret hygiene, frontend exposure, git history

---

## GeaSpirit Access Gate

| Check | Status |
|-------|--------|
| Password in plaintext in HTML | **NO** |
| Password in plaintext in JS | **NO** |
| Password in plaintext in any repo file | **NO** |
| SHA-256 hash in frontend HTML | **YES** (line ~970) |
| Hash reversible to password | **NO** (SHA-256 one-way) |
| Client-side only verification | **YES** |
| Session timer | **YES** (10 min, auto-lock) |
| Bypassable via DOM edit | **YES** (cosmetic gate) |

**Verdict: PARTIALLY SECURE** — Password not exposed, but gate is client-side only. Acceptable for research access gating. Not suitable for financial security.

## Materials Engine Access Gate

| Check | Status |
|-------|--------|
| Same hash as GeaSpirit | **YES** |
| Same passphrase accepted | **YES** |
| Password in plaintext | **NO** |
| Client-side only | **YES** |
| Session timer | **YES** (10 min) |

**Verdict: PARTIALLY SECURE** — Same level as GeaSpirit.

## Worktree Exposure Scan

| Pattern | Found | Severity |
|---------|-------|----------|
| `PASSWORD=` / `SECRET=` in HTML/JS | No | — |
| Direct string comparison (`=== "password"`) | No | — |
| `.env` files | No | — |
| Private key files (`.key`, `.pem`) | No | — |
| Inline credentials | No | — |
| Founder private key in docs | **Yes** (WEB_WALLET_AUDIT.md) | **MEDIUM** — now REDACTED |

**Action taken:** Founder key redacted in docs/WEB_WALLET_AUDIT.md. Key was already documented as compromised in SOST_MASTER_PLAN.md (V2 keys are active).

## Git History Scan

| Check | Result |
|-------|--------|
| `.env` committed | **No** |
| Plaintext password committed | **No** |
| SHA-256 hash in history | **Yes** (since GeaSpirit access gate) |
| Founder private key in history | **Yes** (commit 711075b, in audit doc) |
| Key already known compromised | **Yes** (SOST_MASTER_PLAN.md) |
| History rewrite needed | **No** (key was already rotated to V2) |

## Architecture: Admin vs User Access

### Current State

```
Admin/Operator: SHA-256 hash gate (client-side)
  → Same passphrase for GeaSpirit + Materials Engine
  → Acceptable for research-phase access control
  → NOT suitable for production financial access

User via Escrow: NOT YET IMPLEMENTED
  → Architecture prepared (SOST escrow tiers defined on web)
  → No backend validation yet
  → Future: server-side session issuance from escrow verification
```

### Recommended Architecture (Future)

```
1. Public page (no auth)
2. Access selection:
   a. Admin/Operator → server-side auth (not client-side hash)
   b. User via SOST Escrow → escrow verification → session token
3. Restricted console → token-gated, server-validated
```

## .gitignore Hardening

Added patterns: `.env`, `.env.*`, `*.key`, `*.pem`, `credentials.json`, `secrets.json`, `access.json`, `trusted_addresses.json`, `wallet_policy.json`

## Final Assessment

| System | Status | Note |
|--------|--------|------|
| GeaSpirit gate | **Partially secure** | No plaintext password exposed. Client-side only. |
| Materials Engine gate | **Partially secure** | Same system as GeaSpirit. |
| Worktree secrets | **Clean** (after redaction) | Founder key redacted. |
| Git history | **Acceptable** | Compromised key was already rotated. |
| .gitignore | **Hardened** | Secret patterns now covered. |
| Server-side auth | **Not implemented** | Future requirement for production. |
