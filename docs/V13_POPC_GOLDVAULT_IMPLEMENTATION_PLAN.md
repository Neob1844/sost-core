# V13 PoPC + Gold Vault Implementation Plan

**Branch:** `protocol/v13-popc-goldvault-auto-implementation-v01`
**Status of this commit:** **PLAN ONLY, NO CODE.** Slice 1 is not yet implementable — three operator decisions are pending. See §3.1.
**Public commitment:** unchanged from website-v270 (`PoPC + Escrow + Gold Vault governance deferred to V14 / block 15,000`). No public docs will move back to V13 until the slices land and pass tests.

This document is the **operator-facing implementation plan** for attempting to close the deferred V13 items: Gold Vault spend-side governance, PoPC + Escrow automatic lifecycle, and the SOSTEscrow / Ethereum bridge. It splits the work into six slices with explicit dependencies, blockers, and safety gates, so the work can land incrementally without any single commit becoming the "consensus monster commit" that nobody can review.

The slice boundaries are intentional: each slice MUST be reviewable and testable in isolation, behind a sentinel-disabled gate that preserves bit-identical pre-V13 behaviour. Pre-V13 historical replay MUST be unchanged — that is the load-bearing safety invariant for this whole plan.

---

## 1. Current state (verified by direct code map)

The audit `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md` (commit `e059be32`, tag `v13-popc-escrow-vault-gap-analysis-v01`) said five of six gates are RED. A deeper inspection in this commit confirms:

| Item | Status | File:line |
|---|---|---|
| `classify_gv_spend()` function | **EXISTS** (4-value enum return) | `include/sost/gold_vault_governance.h:97-143` |
| Wired into `ValidateBlockTransactionsConsensus()` | **NO — dead code** | `src/block_validation.cpp:296-387` candidate insertion point |
| `GV_GOVERNANCE_ACTIVATION` constant | **EXISTS at block 10,000** | `include/sost/gold_vault_governance.h:106-108` |
| `GV_THRESHOLD_EPOCH01` constant | **EXISTS at 95** (raised from 75 during V6 review) | `include/sost/consensus_constants.h:39` |
| `GV_THRESHOLD_EPOCH2` constant | **EXISTS at 95** | `include/sost/consensus_constants.h:40` |
| `GV_MONTHLY_LIMIT_PCT` | **EXISTS at 10** | `include/sost/consensus_constants.h:48` |
| `GV_MONTHLY_WINDOW` | **EXISTS at 4320 blocks (~30 days)** | `include/sost/consensus_constants.h:49` |
| `GV_ALLOWED_RESERVE_DESTINATIONS[]` whitelist | **MISSING** | — |
| `GV_HARD_MAX_SPEND_BPS` per-spend cap | **MISSING** | — |
| `GV_COOLDOWN_BLOCKS` rate limit | **MISSING** | — |
| `Transitional Guardian` pubkey constant | **MISSING** | — |
| Tests | 17/17 pass but **100 % isolation-only** | `tests/test_gold_vault.cpp:1-244` |
| BIP9 signaling primitives | **EXIST** but RPC broken | `include/sost/proposals.h:50,58,71` |
| `POPC_ACTIVATION_HEIGHT` | **MISSING** | — |
| PoPC audit scheduler / auto-slash / auto-settlement | **NONE — all RPC-manual** | `src/sost-node.cpp:2805,2885,2821` |
| `SOSTEscrow.sol` | **EXISTS, not deployed** | `contracts/SOSTEscrow.sol` |
| Ethereum event listener | **MISSING** (only `eth_call_balance` poll) | `scripts/popc_daemon.py:74-105` |
| Ethereum→SOST bridge | **MISSING** | — |
| End-to-end no-human-RPC test | **MISSING** | — |

This map is the input to every slice decision below.

---

## 2. The six slices

Each slice MUST:
- Land in its own commit (no slice-combining).
- Compile and pass all existing tests on its own.
- Be sentinel-disabled below V13_HEIGHT so pre-V13 historical replay is bit-identical.
- Add validator-level tests, not only helper-isolation tests.
- Document the activation height it introduces.
- Document what the next slice depends on from it.

### Slice 1 — Gold Vault G1-G3 (pure validator safety)

**Scope:**
- Add `GV_ALLOWED_RESERVE_DESTINATIONS[]` constant table (the operator-decided list of legal spend destinations).
- Add a second mirror constant in a different file for cross-check (the "dual whitelist" of G2).
- Add `GV_PER_SPEND_CAP_PCT` and `GV_RATE_LIMIT_BLOCKS` constants (operator-decided numbers).
- Wire `classify_gv_spend()` into `ValidateBlockTransactionsConsensus()` at `src/block_validation.cpp:329-369`, behind a `height >= V13_HEIGHT` gate (NOT the existing `GV_GOVERNANCE_ACTIVATION = 10,000` gate — see §4 below for why this matters).
- Reject any spend from `ADDR_GOLD_VAULT` where: classification is `REJECTED`, destination not in BOTH whitelists, amount exceeds `GV_PER_SPEND_CAP_PCT`, or blocks-since-last-vault-spend less than `GV_RATE_LIMIT_BLOCKS`.

**Files changed:**
- `include/sost/params.h` — add 3 new `constexpr` blocks (whitelist 1, cap, rate-limit).
- `include/sost/consensus_constants.h` — add whitelist 2 (mirror of whitelist 1).
- `src/block_validation.cpp` — add the validator hook between lines 336 and 369.
- `tests/test_gold_vault_validator.cpp` — NEW file with validator-level tests (synthetic block + tx + utxoset).
- `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md` — flip G1-G3 from RED to GREEN when this lands.

**Slice 1 readiness gates — see §3.1.** Three operator decisions block this slice.

**Risk:** medium. Touches consensus. Mitigated by activation gate + new tests + isolation tests preserved.

**Estimated implementation:** 1 sprint after the three operator decisions are made.

### Slice 2 — Gold Vault G4 (block-based signaling, 67-block window, 90 % / 61-block threshold)

**Scope:**
- Specialise the existing `count_version_signals()` for vault spends with a 67-block window (NOT the BIP9 2016-block window).
- Add `GV_SIGNALING_WINDOW = 67`, `GV_SIGNALING_THRESHOLD_PCT = 90`, `GV_SIGNALING_FLOOR_BLOCKS = 61` constants.
- Add a vault-spend tx-type (or extend the existing `GVApprovalToken` shape) to carry `signaling_window_start_height` so validators can confirm the window matches the spend.
- Fix the broken signaling RPC (see `docs/internal/phase-2-vault-governance.md:66-74` — it hardcodes all block versions to 1 today).
- Cross-validator test: three independently-built validator binaries must reach the same accept/reject decision on the same set of signaling blocks.

**Dependencies on Slice 1:** wiring point in `ValidateBlockTransactionsConsensus()`, whitelist + cap + rate-limit constants.

**Risk:** medium-high. Touches signaling math + RPC surface. New consensus rule.

**Estimated implementation:** 1 sprint.

### Slice 3 — Gold Vault G5 (Transitional Guardian + auto-disconnect)

**Scope:**
- Add `GV_GUARDIAN_PUBKEY` compile-time constant (operator-supplied, separate from any wallet / mining / SOST release-signing key).
- Add a Guardian pronouncement tx-type with `pronouncement_kind ∈ {authorise, veto}` and signature against the Guardian key.
- Wire the 10-block grace window: a vault spend with 90 % signaling that has NO Guardian pronouncement within `[spend_block, spend_block + 10]` is accepted by default ("silence is consent to the miners' decision").
- Implement auto-disconnect at consensus level with three conditions A/B/C (gold-backing milestone placeholder; successful-spends-without-intervention placeholder; hard cap **block 25,000**). At/after block 25,000, any Guardian pronouncement is ignored by every validator.
- Tests: Guardian pronounces YES on signaling=NO; Guardian pronounces NO on signaling=YES; Guardian silent on signaling=YES; Guardian pronounces but signaling=NO and validator rejects because Guardian cannot bypass whitelist; auto-disconnect at block 25,000.

**Dependencies on Slice 2:** signaling result must be a deterministic input.

**Risk:** high. New tx-type, new key role, new state machine, auto-disconnect must be correct or the Guardian role becomes permanent.

**Estimated implementation:** 2-3 sprints.

### Slice 4 — PoPC P1-P4 (deterministic local lifecycle)

**Scope:**
- Add `POPC_ACTIVATION_HEIGHT = 12,000` constant in `include/sost/params.h`.
- Implement deterministic per-block audit scheduler: validator computes "which commitments are due for audit at this height" from chain state (height, commitment registry). No external trigger.
- Implement auto-slash: when a commitment's audit verdict is "fail" AND `height >= audit_block + POPC_AUDIT_GRACE_BLOCKS`, bond is redirected to slash destination by consensus.
- Implement auto-settlement: on "pass" verdict, bond returned to holder + reward paid out of PoPC Pool, by consensus.
- All of the above MUST be gated `height >= POPC_ACTIVATION_HEIGHT`. Below: existing application-layer behaviour preserved bit-for-bit.
- Tests: per-block determinism (same height + same commitment registry → same scheduler output), reorg-safety (a 6-block reorg must not double-credit a slash or a settlement), end-to-end local lifecycle without RPC.

**Dependencies on Slice 1-3:** none (PoPC is orthogonal to Gold Vault governance).

**Risk:** high. New consensus state machine. Reorg-safety is the load-bearing test.

**Estimated implementation:** 2-3 sprints.

### Slice 5 — PoPC P5-P8 + Escrow bridge

**Scope:**
- Deploy `SOSTEscrow.sol` to Sepolia (operator-manual, off-chain).
- Pin deployed address as `ETH_ESCROW_ADDRESS` constant in `include/sost/params.h`.
- Commit Solidity ABI under `contracts/abi/SOSTEscrow.json`.
- Build event listener in Trinity (Python, public-RPC read-only): subscribe to `GoldDeposited` / `GoldWithdrawn` events, apply N-confirmation depth, handle reorgs idempotently.
- Build bridge tx-type that carries a verified Ethereum-side fact (`event_hash + block + log_index + signature_from_listener`) and that validators accept as a consensus-valid PoPC state input.
- End-to-end test: synthetic Ethereum event → listener → bridge tx → SOST consensus accepts → PoPC commitment created → mature → audit → settle, all WITHOUT operator intervention between steps.

**Dependencies on Slice 4:** PoPC lifecycle must be deterministic locally.

**Risk:** very high. Cross-chain bridge with reorg-safety on both sides. The hardest piece of V13 scope.

**Estimated implementation:** 3-4 sprints (PLUS the operator-manual Ethereum deploys which are not agent work).

### Slice 6 — Public docs flip from V14 deferral to V13

**Scope:**
- ONLY runs after Slices 1-5 are all green on `main`.
- Updates `docs/V13_PUBLIC_SCOPE_UPDATE.md`, `docs/V13_RELEASE_CANDIDATE.md`, `website/sost-explorer.html`, `website/sost-protocol-spec.html` to move PoPC, Escrow, Gold Vault governance from "DEFERRED to V14" to "CONFIRMED for V13".
- Bumps explorer_version.

**Dependencies on Slices 1-5:** all green.

**Risk:** zero technical risk; pure docs sweep. But: this commit is the **public commitment**. Until it lands, the public record says V14. Slices 1-5 can land internally without changing public expectations.

**Estimated implementation:** 1 sprint, after everything else.

---

## 3. Readiness gates per slice

### 3.1. Slice 1 readiness — three operator decisions BLOCK this slice

**The following three decisions MUST be made by the operator (NeoB) before Slice 1 can be implemented. The agent cannot decide these — they have legal, economic, and reputational implications that belong to the protocol's human operator.**

#### Decision A — Whitelist of legal Gold Vault spend destinations

The validator will reject any spend from `ADDR_GOLD_VAULT` whose destination is NOT in this whitelist. The whitelist MUST be small (the public-scope appendix in the whitepaper says ≤ 5 addresses), auditable publicly, and immutable post-V13 fork.

Candidate categories (operator chooses):
1. **OTC conversion address** — a Schnorr-aggregated multisig that the operator uses to convert SOST to XAUT/PAXG via an OTC desk. Must be a hardware-key-backed address, not a hot wallet.
2. **Heritage Reserve deposit address on SOST** — the SOST-side address that mirrors the Ethereum Heritage Reserve contract. Pre-Slice 5 this can be a sentinel; post-Slice 5 it becomes the live address.
3. **Allowlist of XAUT / PAXG bridge addresses** — if the operator uses bridge contracts rather than OTC.
4. **Emergency catastrophe address** — kept empty `[]` at V13 launch per `docs/internal/v6-signature-bound-pow.md:419-431`.

**Operator must supply:** the actual SOST-format `PubKeyHash` for each address, the rationale for each, and a commitment to public auditability (the list MUST appear in the whitepaper, not only in the commit message).

#### Decision B — Per-spend cap and rate limit

The existing `GV_MONTHLY_LIMIT_PCT = 10` (10 % over a 4320-block window) is already in code. Slice 1 adds two more bounds:

- `GV_PER_SPEND_CAP_PCT` — the maximum % of vault balance that a single spend tx can move. Default proposal: **2 %** (from `docs/internal/v6-signature-bound-pow.md:436-448`).
- `GV_RATE_LIMIT_BLOCKS` — the minimum blocks between two vault spends. Default proposal: **144 blocks** (~24h at the target block time) for routine spends; emergency spends are gated by signaling + Guardian, not by rate limit.

**Operator must supply:** confirmed numbers (or explicit "use defaults"). The numbers must be re-evaluated against the actual vault balance projected at block 12,000.

#### Decision C — Activation height reconciliation

The existing `GV_GOVERNANCE_ACTIVATION = 10,000` (V6) is hardcoded in `include/sost/gold_vault_governance.h:106-108`. The chain has not yet reached block 10,000 (current tip ~9,300 per the explorer at last check). The new public commitment is V13 / block 12,000.

**Two options:**
- **C1 — bump activation to V13_HEIGHT (12,000).** Slice 1 changes the constant from 10,000 to 12,000. Cleanest, no risk of double-activation. Recommended.
- **C2 — keep the gate at 10,000 but require BOTH `height >= GV_GOVERNANCE_ACTIVATION` AND `height >= V13_HEIGHT` AND `whitelist_present`.** More conservative but the dual gate is confusing.

**Operator must supply:** the choice (C1 recommended).

#### Decision D — Threshold reconciliation

The existing `GV_THRESHOLD_EPOCH01 = 95` and `GV_THRESHOLD_EPOCH2 = 95` reflect the V6 review decision. The new public commitment is 90 % over a 67-block window (Slice 2 work, not Slice 1). Slice 1 itself does not touch thresholds — but the operator should commit to 90 % publicly (which would also require a sweep of legacy "95 %" docs already enumerated in `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md:184` ff.).

**Operator must supply:** confirmation that the threshold sweep 95 → 90 is acceptable, plus willingness to publish a BitcoinTalk + Telegram update post explaining the historical 75 → 95 → 90 trajectory.

---

### 3.2. Slice 2 readiness — depends on Slice 1 + one decision

- Slice 1 landed and green.
- **Decision E** — signaling-window semantics: a vault spend at block H requires 90 % of blocks in `[H-67, H-1]` to have signalled approval. The signaling bit (which bit position in block.version) MUST be decided. Today `proposals.h:44` reserves bit 8 for `post_quantum`. Slice 2 needs an unused bit (e.g. bit 9).

### 3.3. Slice 3 readiness — depends on Slice 2 + two decisions

- Slice 2 landed and green.
- **Decision F** — Guardian pubkey: operator-generated off-line on the secure host, separate from any other key, published in the whitepaper.
- **Decision G** — auto-disconnect thresholds A and B (gold-backing milestone X, successful-spends Z). Condition C (hard cap block 25,000) does not need a decision — the value is already in the public scope update.

### 3.4. Slice 4 readiness — depends on no Gold Vault slice + four decisions

- **Decision H** — `POPC_AUDIT_GRACE_BLOCKS` value (default proposal: 144 blocks = ~24h).
- **Decision I** — audit-trigger determinism: per-commitment fixed-cycle vs randomised by chain state. Affects reorg-safety design.
- **Decision J** — slash redistribution: 50 % PoPC Pool + 50 % Gold Vault (current whitepaper) vs another split.
- **Decision K** — reward source: PoPC Pool direct payout vs intermediate escrow. Affects whether Slice 5 is a hard dependency.

### 3.5. Slice 5 readiness — depends on Slice 4 + operator-manual work

- Slice 4 landed and green.
- Operator deploys `SOSTEscrow.sol` to **Sepolia** for end-to-end testing.
- Sepolia E2E green (propose → 90 % signal → Guardian pronouncement → relay → execute) BEFORE mainnet deploy.
- Operator deploys to **Ethereum mainnet** (costs real ETH, requires signing key, NOT agent work).
- Operator pins the deployed address as `ETH_ESCROW_ADDRESS` in `include/sost/params.h` via a separate commit.

### 3.6. Slice 6 readiness

- All of Slices 1-5 green on `main`.
- Full trinity suite green.
- All affected legacy docs (whitepaper, BitcoinTalk ANN, threat model, security audit) updated in the same docs sweep.

---

## 4. Cross-cutting concerns

### 4.1. Activation height reconciliation (critical)

The single most dangerous footgun in this plan: the existing code uses `GV_GOVERNANCE_ACTIVATION = 10,000` but the new public commitment is V13 / block 12,000. The chain reaches block 10,000 BEFORE block 12,000 — so wiring `classify_gv_spend()` without changing the activation constant would mean the V6 governance rule activates at block 10,000 with placeholder constants and breaks every legitimate vault spend between block 10,000 and block 12,000.

**Resolution required before any slice lands:** the operator must pick Decision C1 (bump to 12,000) or C2 (dual gate). C1 is recommended.

### 4.2. Threshold reconciliation

The legacy 75 → 95 → 90 trajectory is documented in `docs/V13_PUBLIC_SCOPE_UPDATE.md` and `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md`. Slice 1 does not touch thresholds; Slice 2 does. Slice 2's commit must include the consequential edit of `consensus_constants.h:39-40` (`GV_THRESHOLD_EPOCH01 = 95` → `90`, `GV_THRESHOLD_EPOCH2 = 95` → `90`) and the matching legacy-docs sweep in the same PR.

### 4.3. Foundation veto vs Transitional Guardian

`foundation_veto` exists in `proposals.h:36, 70-94` as the developer veto on BIP9-style protocol proposals (expires at block 263,106). The Transitional Guardian in this plan is a NEW concept that operates only on vault spends, with a separate key, separate auto-disconnect, and separate hard cap (block 25,000). These two roles are orthogonal — Slice 3 MUST NOT couple them, or the auto-disconnect of one accidentally affects the other.

### 4.4. Reorg-safety

Every new consensus rule introduced by Slices 1-5 MUST be reorg-safe: a 6-block reorg must not produce a different final state. Specifically:
- Rate-limit accounting (Slice 1) — must read from the canonical chain, not from a cache.
- Signaling-window math (Slice 2) — must use the post-reorg block.version values, not the pre-reorg ones.
- Auto-disconnect (Slice 3) — the "Z successful spends" counter must be recomputable from canonical chain state.
- PoPC audit scheduler (Slice 4) — must produce the same trigger set on the same height after a reorg.
- Ethereum bridge (Slice 5) — must handle Ethereum reorgs AND SOST reorgs; the N-confirmation depth on the Ethereum side is the load-bearing parameter.

Reorg-safety is the **first test** for every slice. If a slice cannot pass a synthetic reorg test, it does not land.

### 4.5. Safety contract (applies to every slice)

The following safety rules apply to every commit in this implementation plan:

- NO private keys anywhere in node code.
- NO wallet auto-signing by consensus.
- NO broadcast from consensus.
- NO Ethereum deploy from agent. Operator-manual only.
- NO GitHub API calls from any script.
- NO `shell=True` / `eval(` / `exec(` in any Python.
- NO destructive git verbs (`push`, `merge`, `tag`, `reset`, `checkout`, `rm`, `clean`, `commit`, `add`, `stash`) hardcoded in any script.
- Every new consensus rule MUST have at least one validator-level test that exercises it on a synthetic block, not only an isolation test on the helper.
- Every new constant MUST have a "what happens below activation height" test that confirms pre-activation behaviour is bit-identical.
- Every Python script MUST be readable-only and pass the existing FORBIDDEN_TOKENS lint pattern from prior trinity scripts.

---

## 5. What this commit IS and IS NOT

### This commit IS

- A documented implementation plan splitting the work into six slices.
- An explicit list of three operator decisions (A, B, C) that block Slice 1.
- An explicit list of seven additional operator decisions (D, E, F, G, H, I, J, K) that block Slices 2-5.
- A cross-cutting concerns section that captures the reorg-safety and activation-height-reconciliation footguns.

### This commit IS NOT

- **NOT** an implementation of any slice. No source code is modified.
- **NOT** a change to any consensus rule.
- **NOT** a public docs flip. Website still says V14 deferral.
- **NOT** a commitment to V13 timing. The plan's purpose is to clarify what would be required to attempt V13; the operator may still choose V14 explicitly.
- **NOT** an Ethereum deploy. Slice 5's Sepolia/mainnet deploys remain operator-manual.

---

## 6. Recommendation

**Stop here. Do not implement Slice 1 until Decisions A, B, C are made.**

The three decisions are not technical — they are governance/economic decisions that belong to the protocol's operator. The cleanest next step is:

1. The operator reads this plan.
2. The operator decides A (whitelist addresses), B (cap + rate limit), C (activation height C1 recommended).
3. A follow-up branch `protocol/v13-goldvault-slice-1-v01` lands the actual Slice 1 implementation with those decided values, behind the V13_HEIGHT gate, with validator-level tests, in a single reviewable commit.
4. After Slice 1 is green on main, Slice 2 can start under its own branch.

This sequencing keeps every commit small, every review tractable, and every consensus change behind a reviewable activation gate. The opposite — bundling all of Slices 1-5 into one branch — would produce a thousand-line consensus diff that nobody can review safely.

If the operator decides Slice 1's three blockers are too costly to resolve before V13 RC freeze, the V14 deferral stated in `docs/V13_PUBLIC_SCOPE_UPDATE.md` remains correct and no further work in this branch is needed.

— NeoB
