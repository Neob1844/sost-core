# Gold Vault Governance — Audit & Automation (DRAFT, mainnet OFF)

Status: **DRAFT / SIMULATOR ONLY.** This documents the existing G1–G5 code, adds a
dry-run validator + tests, and **activates nothing**. All gates stay `INT64_MAX` on
mainnet. No funds move; nothing is signed or broadcast.

## What the Gold Vault is

The **Metals Reserve / Gold Vault** receives **25% of every coinbase** at a hardcoded,
consensus-enforced address (`ADDR_GOLD_VAULT`, params.h). Accumulation is **live since
genesis**. *Spending* that reserve is what G1–G5 govern — so no person can move the funds
freely. Spend-governance is **deferred** (not active on mainnet).

## The five rules (audited from code)

### G1 — Purpose restriction / whitelist  (`include/sost/gold_vault_slice1.h`)
A vault spend's external destinations must be in a whitelist. Default whitelist =
**one** entry, the genesis/founder miner PKH (`GV_SLICE1_WHITELIST_PRIMARY`, ≤5 max).
Helper: `gv_slice1_destination_allowed(dest)`.

### G2 — Dual whitelist cross-check (fail-closed)
The whitelist lives in **two** independent tables (PRIMARY in the header, MIRROR in a
separate translation unit). `gv_slice1_whitelists_agree()` must return true or the
validator **rejects every vault spend**. This catches operator misconfiguration (edit one
table, forget the other) before it can split consensus. Two empty tables agree vacuously.

### G3a — Per-spend cap
- **Absolute:** `GV_SLICE1_PER_SPEND_CAP_STOCKS = 1000 SOST` — the canonical Phase-I limit.
  Helper `gv_slice1_amount_within_abs_cap(amount)`.
- **Relative:** `GV_SLICE1_PER_SPEND_CAP_BPS` (bps of vault balance), **0 = disabled** by
  default. Helper `gv_slice1_amount_within_cap(amount, vault_balance)`.

### G3b — Rate limit (timelock)
`gv_slice1_rate_limit_ok(blocks_since_last_spend)` — minimum blocks between vault spends.
Canonical value **144 (~24h)**; currently `GV_SLICE1_RATE_LIMIT_BLOCKS = 0` (disabled) and
**not wired** into block validation (needs a new `StoredBlock.gold_vault_last_spend_height`
field — a separate follow-up). The helper is pure and tested; it is **not** enforced yet.

### G4 — Miner signaling  (`include/sost/gv_g4.h`)
An affirmative approval layer on top of G1–G3: a spend needs **≥90% miner approval over a
67-block window** (floor **61/67**), with a **+10% foundation quality boost**. Miners signal
by including a 0-value coinbase **approval marker** (`GV_G4_APPROVAL_PKH`, unspendable).
Helpers: `gv_g4_count_window(...)`, `gv_g4_window_approved(miner_yes, foundation_signaled)`.

### G5 — Transitional Guardian veto  (`include/sost/gv_g5.h`)
The last, most sensitive layer — a **temporary** developer/genesis veto, boxed in so it can
never become a permanent control door:
- **silence = accept** — a G4-approved spend stands unless an explicit valid veto lands.
  The Guardian can only **block**, never **force**, a spend.
- **grace window** = `GV_G5_GRACE_BLOCKS` (10) preceding blocks.
- **AUTO-DISCONNECT** at `GV_G5_AUTO_DISCONNECT_HEIGHT = 100,000` — the Guardian turns OFF
  **forever**; no key, flag or vote can re-enable it.
- **signed** — a veto is an ECDSA pronouncement by the hardcoded Guardian key, replay-safe
  (the digest commits to destination + expiry under a domain tag). Helper:
  `gv_g5_spend_blocked(g5_active, valid_veto_present)`.

## Current activation status (audited)

| Gate | Mainnet | Testnet (`-DSOST_TESTNET_FORKS`) |
|---|---|---|
| `GV_SLICE1_ACTIVATION_HEIGHT` (G1/G2/G3) | **`INT64_MAX`** (off) | `V15_HEIGHT` (300) |
| `GV_G4_ACTIVATION_HEIGHT` (G4) | **`INT64_MAX`** (off) | `V15_HEIGHT` (300) |
| `GV_G5_ACTIVATION_HEIGHT` (G5) | **`INT64_MAX`** (off) | `V15_HEIGHT` (300), < auto-disconnect 100,000 |
| Coinbase 25% accumulation | **LIVE** (since genesis) | live |

**Live now:** only the 25% accumulation. **Deferred:** all spend-governance (G1–G5) and any
gold purchase / Heritage Reserve. Gold Vault governance is part of the **V15** bundle
(block 20,000) — **NOT** V14. It is **not** coupled to PoPC's `POPC_SINGLE_MODEL_HEIGHT`.

## A spend's full decision (how the layers compose)

```
spend allowed  ⇔  G2 whitelists agree
              AND every external destination ∈ G1 whitelist
              AND amount ≤ G3a absolute cap (and ≤ relative cap if enabled)
              AND blocks-since-last ≥ G3b rate-limit            (when wired)
              AND G4 window approved (≥61/67 effective, incl. +10% foundation)
              AND NOT G5 vetoed (silence = accept)
```

## Safe activation path (later, not now)

1. Build + soak the full G1–G5 on **testnet** (`-DSOST_TESTNET_FORKS=ON`, gates at 300).
2. Wire G3b rate-limit (`StoredBlock.gold_vault_last_spend_height`) — currently unenforced.
3. Wire G4 coinbase-marker counting + G5 veto-payload verification into block validation
   under the gates.
4. Populate the MIRROR whitelist + final cap/rate values in a single reviewable commit.
5. In a **final, soaked, coordinated** pre-fork commit, flip the three
   `GV_*_ACTIVATION_HEIGHT` from `INT64_MAX` → `V15_HEIGHT` (20,000). Announce the window.
6. Never reuse PoPC's height; never move funds before soak.

## Automation architecture (dry-run first)

```
proposal.json ──▶ scripts/gold_vault_governance_dry_run.py ──▶ APPROVED / REJECTED + reasons
                 (pure rules: whitelist · cap · timelock · G4 signaling · G5 veto)
                 NEVER signs · NEVER broadcasts · reads only
```

The dry-run mirrors the **canonical rule parameters** (whitelist = genesis miner, abs cap
1000 SOST, rate-limit 144, G4 61/67 + foundation, G5 veto). It answers "would this proposal
pass governance?" without touching the chain. A future **automation runner** would observe
proposals, run exactly these checks, and only then build a transaction — but that is a later
phase and is **out of scope** here.

## Files in this draft

| File | Purpose |
|---|---|
| `scripts/gold_vault_governance_dry_run.py` | proposal validator (APPROVED/REJECTED, no signing) |
| `scripts/fixtures/gv_*.json` | valid · bad-whitelist · over-cap · before-timelock · vetoed |
| `tests/test_gv_governance_audit.cpp` | rule + gate-state assertions (mainnet `INT64_MAX`) |
| `docs/GOLD_VAULT_GOVERNANCE_AUTOMATION.md` | this audit |

Nothing here changes consensus, `emission.cpp`, the PoPC gates, or the `GV_*` mainnet gates.
