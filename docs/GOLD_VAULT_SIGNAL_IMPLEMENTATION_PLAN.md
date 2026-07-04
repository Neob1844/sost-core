# Gold Vault Signal — Implementation Plan (audit + next steps, NOT ACTIVE)

**Status: PLANNED. No voting is implemented.** This document audits exactly what
exists today, what is only a visual preview, and what is missing, then specifies the
next implementation step (Phase 2). It implements nothing, touches no consensus, and
deploys nothing.

Related: [`GOLD_VAULT_SIGNAL_DESIGN.md`](GOLD_VAULT_SIGNAL_DESIGN.md),
[`TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md`](TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md),
[`GOLD_ACCUMULATION_AUCTION_PROGRAM.md`](GOLD_ACCUMULATION_AUCTION_PROGRAM.md) (Gold
Reserve Forge), [`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md).

---

## 1. Current state — audit (exists / preview / missing)

| Item | State | Evidence |
|---|---|---|
| Gold & Metals Reserve dashboard | **EXISTS** (live) | `website/sost-gold-reserve.html`, deployed |
| Gold Reserve Forge (product) | **EXISTS as design + web section, NOT ACTIVE** | doc + page module |
| Tokenized Gold Safe | **DESIGN ONLY — NOT CREATED** | `docs/TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md` |
| Gold Vault Signal — design | **EXISTS** | `docs/GOLD_VAULT_SIGNAL_DESIGN.md` |
| Gold Vault Signal — web | **PREVIEW ONLY** | mock GV-001, vote buttons `disabled` |
| Real wallet connection | **MISSING** in the Signal panel | no connect flow on the page |
| Message signing capability | **EXISTS (reusable)** | `website/sost-wallet.html` `geaSignMessage()` — ECDSA secp256k1 low-S, client-side |
| Signature verification | **DOABLE CLIENT-SIDE** (no node change) | secp256k1 already bundled for signing → `secp.verify` |
| `verifymessage` RPC | **MISSING** | not in `src/sost-rpc.cpp` (not required — verify in JS) |
| Snapshot balance (balance at height) | **MISSING — the real blocker** | `getbalance`/`getaddressinfo` are current-balance only; no height param, no historical index |
| Vote storage endpoint | **MISSING** | explorer is static + read-only node RPC; no write path |
| Result registry / export | **MISSING** | — |
| Safe execution / timelock | **MISSING (by design)** | Safe not created; consensus untouched |
| Consensus changes | **NONE** | intact |

**Plain summary:** we have the *visual preview* (a disabled button and mock card).
We do **not** yet have: real wallet connect in the panel, real signature collection,
snapshot-weighted vote power, vote storage, results, or execution.

---

## 2. What the next dashboard will be (design)

**Location:** primarily **inside the explorer** (`website/sost-explorer.html`), with a
link from `website/sost-gold-reserve.html`. Name: **Gold Vault Signal**.

**UI sections:**
- Active Proposal
- Connect Wallet
- Your Voting Power
- Snapshot Block
- YES / NO bars
- Vote YES / Vote NO buttons
- Vote Receipt (the signed proof the voter keeps)
- Public Results
- Safety Rules
- Registry Export

Card sketch:
```
Gold Vault Signal — Proposal GV-001
Convert up to 100 SOST into PAXG → verified Tokenized Gold Safe
Mode: Founder Test / Preview        Status: Voting Not Live
Your wallet: not connected          Your voting power: —
Snapshot block: —                   Voting closes: —
YES 0%   NO 0%
[Connect Wallet]  [Vote YES] [Vote NO] (disabled until Phase 2 verified)
```

---

## 3. Voting mechanics (target)

- **Not** mining/hashrate-based. Wallet-signed message.
- Message format: `GVOTE:<proposal_id>:YES` or `GVOTE:<proposal_id>:NO`.
- One wallet = one active vote per proposal; **last valid vote before close replaces**.
- Weight = SOST balance at `snapshot_height`; `snapshot_height = voting_start_height − 1`.
- **Normal:** 24 h window · quorum 10% · YES ≥ 60% · weekly cap 1% · timelock 24 h.
- **Emergency:** 6 h window · quorum 20% · YES ≥ 90% · up to 100% but only to an
  emergency-allowlisted Safe · timelock 6 h.
- (Hardening from the design doc, to decide before real votes: per-wallet weight cap,
  votable-supply denominator excluding vault/genesis/PoPC, guardian emergency fast-path.)

---

## 4. Data model

**Proposal JSON**
```json
{
  "proposal_id": "GV-001",
  "title": "Convert up to 100 SOST into PAXG",
  "type": "convert|move|emergency",
  "status": "draft|voting_open|passed|failed|timelock|executed|cancelled|emergency",
  "snapshot_height": 0,
  "voting_start_height": 0,
  "voting_end_height": 0,
  "asset": "PAXG|XAUT",
  "max_amount": "100 SOST",
  "destination": "0x… verified Safe",
  "safety_flags": { "allowlisted": true, "within_weekly_cap": true, "timelock": "24h" }
}
```

**Vote JSON**
```json
{
  "proposal_id": "GV-001",
  "address": "sost1…",
  "vote": "YES|NO",
  "signature": "<DER hex>",
  "message": "GVOTE:GV-001:YES",
  "voting_power": 0,
  "snapshot_height": 0,
  "timestamp": "…",
  "valid": true
}
```

---

## 5. Phases

- **Phase 1 — DONE:** preview only, disabled buttons, mock proposal.
- **Phase 2 — NEXT:** real wallet message signing + **client-side verification** +
  static/mock proposal; votes stored as JSON (export first, lightweight endpoint
  later). **No execution.** Buttons only produce a signed **Vote Receipt**.
- **Phase 3:** public registry/export, results JSON, Forge Proof linkage.
- **Phase 4:** Safe/timelock execution checklist — still **not automatic** until
  legal + security review (and the Safe actually exists).

---

## 6. Stop conditions — required plumbing (findings)

1. **Signing — AVAILABLE.** `geaSignMessage()` in `sost-wallet.html` already signs a
   message client-side (SHA-256 → ECDSA secp256k1 low-S, DER output, key never leaves
   the browser). Phase 2 reuses this exact code for the `GVOTE:` message. **No new
   wallet plumbing required** to *sign*; the work is wiring a signer into the Signal
   panel (or "sign in the wallet, paste into the explorer").

2. **Verification — AVAILABLE client-side.** The page already bundles secp256k1 for
   signing, so `secp.verify(sig, sha256(message), pubkey)` + deriving the address from
   the pubkey gives full JS verification. **No `verifymessage` RPC and no node change
   required.** (A `verifymessage` RPC could be added later for server-side tallies, but
   is optional.)

3. **Snapshot balance — MISSING (the blocker).** There is **no RPC/indexer that
   returns an address's SOST balance at a past block height**. `getbalance` /
   `getaddressinfo` are current-balance only. Real weighted voting needs one of:
   - **(A, recommended)** a read-only indexer/RPC `getbalanceatheight(address, height)`
     (or a scan-address-history endpoint) — node/indexer work, **not consensus**;
   - **(B, interim)** use **current** balance labelled clearly as *indicative, snapshot
     pending* — weaker and gameable, acceptable only for a non-binding Phase-2 signal;
   - **(C)** an external indexer that reconstructs balances to a height.
   Until (A) or (C) exists, Phase 2 can collect **real signed votes** but must **not**
   present a snapshot-weighted tally as final.

4. **Vote storage — MISSING.** The explorer is static + read-only RPC; there is no
   write path. Phase-2 fallback: **client-side collection + JSON export** (each voter
   downloads/pastes their signed Vote Receipt; a curator aggregates), or a **lightweight
   append-only endpoint** (a tiny service that accepts a signed vote and appends it to a
   public JSON). Recommend export-first, endpoint later.

**Hard rules:** do not fake real voting; do not enable the Vote buttons until full
signing **and** verification exist; do not present a weighted result without a real
snapshot source; no consensus changes.

---

## 7. Recommended next PR scope (Phase 2)

A single, safe, docs+web PR that makes voting **real but non-binding**:
1. Add a **Connect Wallet + Sign** flow to the Gold Vault Signal panel, reusing the
   `geaSignMessage` secp256k1 signer to produce a `GVOTE:<id>:YES/NO` **Vote Receipt**.
2. **Client-side verify** the signature + show the derived address.
3. Drive the card from a **static proposal JSON** (§4).
4. Votes: **JSON export** of the signed receipt (no server write yet); tally shown as
   *unweighted / indicative* with a visible "snapshot weighting pending" note.
5. Buttons produce a receipt only — **no execution, no Safe, no consensus.** Keep all
   NOT-ACTIVE / not-a-peg / no-claim-on-gold guardrails.

**Explicitly out of Phase 2:** snapshot-weighted tally (blocked on §6.3), server vote
storage, results registry, any Safe/timelock execution.

---

## 8. Risks

- Presenting an **indicative tally as if final** before the snapshot RPC exists →
  mitigate with clear labelling and disabled binding.
- **Whale/exchange capture** once weighting is live → per-wallet cap + votable-supply
  denominator (design doc §8) must be decided first.
- **Emergency quorum freeze** → guardian fast-path (design doc §8).
- **Cross-chain gap** (SOST vote → Ethereum Safe) → off-chain-first trusted signers +
  Safe timelock/allowlist backstops now; Reality.eth later (Safe design).
- **Phishing/blind-sign** → the message is human-readable (`GVOTE:GV-001:YES`), and the
  wallet already shows a confirm dialog before signing.

---

## 9. Required RPC / API hooks (summary)

| Need | Status | Action |
|---|---|---|
| Sign `GVOTE` message | ✅ exists (`geaSignMessage`) | reuse in the Signal panel |
| Verify signature → address | ✅ client-side JS | implement with bundled secp256k1 |
| Current balance | ✅ `getbalance` / `getaddressinfo` | already used by the explorer |
| **Balance at snapshot height** | ❌ **missing** | add read-only `getbalanceatheight` (indexer/RPC) — the gating item |
| Store a vote | ❌ missing | export-first; optional append-only endpoint later |
| Publish results | ❌ missing | results JSON + export (Phase 3) |

**Bottom line:** Phase 2 (real signing + client-side verification + receipts, no
execution) is buildable now with **zero consensus changes**. The one real blocker for a
*weighted* result is a snapshot-balance (balance-at-height) read endpoint — a node/
indexer addition, not a consensus change. Until it exists, keep Phase-2 voting explicitly
non-binding.
