# V14 (block 15,000) + V15 (block 20,000) — Execution Plan

> **SCOPE SPLIT (2026-06-08).** V14 ships UNCHANGED at **block 15,000**: only the
> H3/H4 block-validation hardening (the dynamic fee floor already activated at
> 10,000). It is already in the deployed binaries — **no node re-update is needed**
> for it. The big automation track — **PoPC Model A/B, OTC/P2P Atomic Swap, and the
> full Gold Vault governance G1-G5** — is moved into a NEW gate **V15_HEIGHT = 20,000**
> so the already-shipped V14 fork is not disturbed and no forced re-coordination
> happens now. All V15 gates ship DEFERRED (INT64_MAX) on mainnet and flip to
> V15_HEIGHT only in the final, soaked, coordinated pre-fork commit. Testnet
> (`-DSOST_TESTNET_FORKS`) dry-runs V14 at 200 and V15 at 300.
>
> Status date: 2026-06-07 · Target height **15,000** (~2026-06-27, retractable).
> Principle: **consensus on a live chain with real value → a chain split is the #1 risk.**
> Therefore: build the **automated safety net first**, then implement each component
> behind a height gate that ships **deferred (no-op)** until it is proven on a testnet,
> replayed bit-identical, and flipped under a coordinated point release. **Never flip a
> gate blind.**

---

## 0. Component readiness (verified against code + branches, 2026-06-07)

| # | Component | Real state | V14 verdict |
|---|-----------|-----------|-------------|
| 1 | **H3/H4 block-validation hardening** | ✅ merged, gated at `V14_HEIGHT`, tested (`test-v14-h3-h4`) | **DONE — ships in V14** (the only consensus change that forces miners to upgrade) |
| 2 | **Dynamic fee floor 1→10** | ✅ merged (`DYNAMIC_FEE_BASE_V14`), policy-only, no fork | **DONE — ships in V14** |
| 3 | **Beacon II-A operator key** | ✅ installed (`src/beacon.cpp`, fp `bbb560e3…`) | **DONE** |
| 4 | **Gold Vault gov threshold 95→90** | ✅ `GV_THRESHOLD_EPOCH01=90` | **DONE (constant)** |
| 5 | **Gold Vault Phase I governance (enforcement)** | Slice 1 (G1/G2/G3a) wired but `GV_SLICE1_ACTIVATION_HEIGHT=INT64_MAX`; G4 (67-blk window), G5 (Guardian), G6 (Heritage) NOT implemented; `classify_gv_spend` is dead code | **PARTIAL — needs work + operator decisions** |
| 6 | **PoPC Model A on-chain migration + auto-audit/slash/settle** | 85-90% app-layer; state in `popc_registry.json` (non-deterministic); gate `DTD_POPC_GATE_CONSENSUS_ACTIVE=false` (correctly deferred) | **DEFER gate flip to post-V14 point release** |
| 7 | **DTD Emergency Pause/Resume** | designed+tested, `DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE=false` | **Stays deferred** |
| 8 | **Atomic Swap HTLC (OTC/P2P)** | SOST-side consensus complete+tested, EVM .sol complete (52 tests); BTC=stubs (no libwally), no testnet deploy, no external audit; branch says DO NOT FLIP | **DEFER to V15** |

**What V14 actually ships as enforced:** #1 + #2 (+ #3/#4 already in). Everything else either
stays deferred (#6, #7, #8) or needs the work below before it can be enforced (#5).

---

## 1. PHASE A — Automated safety net (build FIRST; ~17h; ZERO consensus risk)

This is the foundation every later consensus change depends on. All test/CI/script work.

| Task | Deliverable | Status |
|------|-------------|--------|
| A1 | **Fork-gate constant pins** `tests/test_v14_fork_gates.cpp` — `static_assert` on `V14_HEIGHT`, `DYNAMIC_FEE_BASE_V14`, deferred-gate flags. Build fails if a constant drifts without a conscious edit. | ▶ DONE in this commit |
| A2 | **`--dry-run-replay` flag** on `sost-node`: load `chain.json`, replay 0..tip via `ConnectBlock`, print final height + deterministic UTXO-set root (rolling SHA-256 over the ordered map), exit (no P2P/RPC). | ✅ DONE (verified deterministic) |
| A3 | **`scripts/validate-v14-replay.sh`** — replay candidate + baseline binaries, assert bit-identical (height + UTXO root). Pre-deploy gate. | ✅ DONE |
| A4 | **Testnet with low fork height** — compile-time `-DSOST_TESTNET_FORKS=ON` lowers `V14_HEIGHT` to 200; mainnet build byte-identical at 15000 (`V14_HEIGHT` stays `constexpr`, no call-site changes). | ✅ DONE (mainnet=15000, testnet=200 verified) |
| A5 | **CI** `.github/workflows/v14-fork-safety.yml` — builds + runs `test-v14-fork-gates` + `test-v14-h3-h4` (hard gate) and best-effort full `ctest` on every push/PR. | ✅ DONE |
| A6 | **Beacon V14 notice template** `docs/V14_BEACON_NOTICE_TEMPLATE.md` + unsigned JSON (II-A advisory to miners). | ✅ DONE |
| A7 | **`docs/V14_DEPLOYMENT_CHECKLIST.md`** — operator runbook (build → replay-validate → testnet → sign beacon notice → deploy → verify → rollback). | ✅ DONE |

**Phase A COMPLETE (A1-A7).** Safety net in place: pinned constants + CI, deterministic replay +
bit-identical pre-deploy gate, throwaway-testnet build (V14 @ block 200), beacon notice + deploy
checklist. Testnet: `cmake -S . -B build-testnet -DSOST_TESTNET_FORKS=ON && cmake --build build-testnet`.
All consensus work below now builds on this.

**Discipline to copy (proven V11/V12/V13):** height constant → `static_assert` pin → `..._at(height)`
helper returning pre/post value → call sites use the helper → boundary test for every regime →
pre-fork path immutable (old blocks replay bit-identical).

---

## 2. PHASE B — Gold Vault Phase I governance (component #5)

**Decisions needed from operator (blocking, genuinely yours):**
- **D1 — Whitelist addresses** for G1/G2 (3-5 reserve destinations; committed to BOTH the primary
  and mirror arrays; immutable post-activation).
- **D2 — Per-spend cap** `GV_SLICE1_PER_SPEND_CAP_BPS` (e.g. 200 bps = 2% of vault per spend).
- **D3 — Scope for V14:** ship **only Slice 1** (G1 whitelist + G2 dual-check + G3a per-spend cap),
  OR the full governance (G4 67-block signaling window + G5 transitional Guardian)?

**Work (after decisions), most-automated form:**
- B1: ✅ DONE — Slice 1 configured (whitelist=[genesis miner ADDR_MINER_FOUNDER], abs cap=1,000 SOST,
  mirror filled, G3a absolute-cap check wired). Mainnet gate stays DEFERRED (INT64_MAX, replay
  byte-identical); testnet (`-DSOST_TESTNET_FORKS`) activates it at block 200. Tests:
  `test-gv-slice1-activation` (whitelist == decode(ADDR_MINER_FOUNDER), cap, dual-whitelist) +
  `test-v13-gold-vault-slice1` (mainnet 45/45, testnet 30/30) + CI hard-gate. The mainnet
  activation flips to 15000 only in the final pre-fork commit (after G4+G5 + soak).
- B2 (G4): ▶ IN PROGRESS — pure tally module DONE (`include/sost/gv_g4.h`, `test-gv-g4`, in CI):
  67-block window, 90% floor (61/67), +10% foundation boost, version-bit signaling, deferred on
  mainnet / active on testnet. Design: `docs/V14_GOLD_VAULT_G4_DESIGN.md`. **Next:** wire the tally
  into block validation (track pending proposal, count `GV_G4_SIGNAL_BIT` over the window, reject a
  vault spend lacking 61/67) — replay byte-identical pre-activation.
- B2 (G5): G5 Guardian pronouncement tx-type + 10-block grace + **silence=accept** + **auto-disconnect
  at block 100,000** (operator decision 2026-06-07). Add cross-validator agreement test.
- B3: testnet soak across the activation height; replay-validate; then enable on mainnet via the gate.

**DECISION (operator, 2026-06-07): V14 ships the FULL Gold Vault Phase I governance (G1/G2/G3a
Slice 1 + G4 67-block signaling window with silence=accept auto-tally + G5 transitional Guardian
with auto-disconnect at block 100,000).** This is the largest piece of V14 and depends on the Phase A
node testnet/replay harness (A2-A4) being in place first. Execution order: A2-A4 → B1 (Slice 1) →
B2 (G4 auto-tally) → B2 (G5 Guardian) → B3 (testnet soak + replay) → enable via the gate.

---

## 2b. PHASE B — WIRING FINDINGS (2026-06-07, must address before enforcing G1-G5)

Two architectural findings surfaced while wiring G4. They change WHERE the Gold Vault
governance must be enforced. **Neither affects mainnet today** (everything is gated/deferred),
but both must be handled before any flip:

1. **`ValidateBlockTransactionsConsensus` (block_validation.cpp) has NO callers** — it is an
   orphan/test-only L3 function. The running node validates blocks via `process_block`
   (`src/sost-node.cpp`) → `UtxoSet::ConnectBlock` + `tx_validation.cpp` CB rules. **The Slice 1
   (G1/G2/G3a) check currently lives only in that orphan function**, so it is NOT enforced by the
   node binary. Consequence: Gold Vault governance (Slice 1 + G4 + G5) must be **integrated into
   the node's real path** (`process_block`, alongside the V14 H3/H4 block, gated by
   `gv_slice1_active_at` / `gv_g4_active_at`). The `gv_slice1.*` and `gv_g4.h` modules are correct
   and reusable as-is — only the enforcement CALL SITE moves.
2. **Coinbase shape is strict (CB11: Phase-2 PAYOUT coinbase = exactly 2 outputs; CB12 fixes the
   amounts).** The G4 coinbase approval marker (a 3rd 0-value output) therefore needs a **gated
   CB11/CB12 relaxation**: when `gv_g4_active_at(height)`, allow exactly one extra output that is
   the `GV_G4_APPROVAL_PKH` 0-value marker (and nothing else). Pre-activation, CB11 is byte-identical.

**Corrected wiring plan (high-risk, do deliberately + replay byte-identical):**
- W1: ✅ DONE — Slice 1 G1/G2/G3a enforcement is now on the node's REAL block path
  (`process_block`, `src/sost-node.cpp`), inside the `v14_txrules` branch and gated by
  `gv_slice1_active_at(height)`. The composite check was extracted to a single shared inline
  helper `gv_slice1_check_block_spend()` (+ `GvSlice1Verdict` / `gv_slice1_verdict_reason`) in
  `include/sost/gold_vault_slice1.h`, used by BOTH `process_block` AND the orphan
  `ValidateBlockTransactionsConsensus` so the two cannot drift. Mainnet stays a pure no-op
  (`GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX`): the guard is false at every height, so live
  block acceptance is byte-identical and `--dry-run-replay` (which replays via `ConnectBlock`,
  not `process_block`) is unaffected. Tests: `test-gv-slice1-block` (6 W1 scenarios: non-vault
  unaffected, whitelist OK, non-whitelist reject, abs-cap boundary OK, abs-cap+1 reject,
  change-to-vault OK) — in CI hard-gate. The orphan L3 function is kept for now (test-only) and
  will be removed once G4/G5 wiring lands. G3b rate-limit still deferred (needs last-spend height).
- W2: ✅ DONE — `ValidateCoinbaseConsensus` (src/tx_validation.cpp) now RECOGNIZES the G4
  approval marker: when `gv_g4_active_at(height)`, the coinbase may carry exactly ONE extra
  trailing 0-value output to `GV_G4_APPROVAL_PKH`. It is stripped via `real_outs` from all
  shape (CB7/CB11) and R5/R6 amount checks; index-based amount checks (outputs[0]/[1]) are
  untouched because the marker is forced to the LAST position. Pre-activation the marker is
  rejected (extra output → shape fail) → replay BYTE-IDENTICAL; mainnet deferred (gv_g4 at
  INT64_MAX). Rejects: amount>0, wrong pkh, two markers, marker-not-last. Tests:
  `test-gv-g4-coinbase` (mainnet 4/4 + testnet 10/10) in the CI hard-gate. W2 only RECOGNIZES
  the marker — counting it over the 67-block window + enforcing 61/67 is W3.
- W3: ✅ DONE — in `process_block`, when `gv_g4_active_at(height)` AND the block contains a
  Gold Vault spend (flagged by the W1 Slice-1 check), count the G4 markers in the coinbases of
  the preceding 67 blocks `[h-67, h-1]` (deserialized from `g_blocks[hh].tx_hexes[0]` via
  `gv_g4_coinbase_approves`) and require `gv_g4_window_approved(count, foundation=false)` — else
  reject the block. Counting is the new pure helper `gv_g4_count_window(h, approves)` (current h
  excluded, no off-by-one, negative heights skipped). Mainnet DEFERRED (gv_g4 INT64_MAX) → pure
  no-op, replay byte-identical; testnet active at V15_HEIGHT. Tests: `test-gv-g4` +9 window cases
  (h-1/h-67 inside, h-68 outside, current-h excluded, 61→approve/60→reject, genesis-safe).
  Mainnet ctest 66/66; testnet build green. Foundation +10% boost (G5) not wired yet.
  **Reorg note:** the window reads `g_blocks` (active chain); the final V15 mainnet flip must
  re-verify behaviour under reorg replay before activation.
- W4: G5 transitional Guardian veto.
  - W4a ✅ DONE — pure module `include/sost/gv_g5.h` + `src/gv_g5.cpp` (ECDSA verify against the
    Beacon II-A operator/Guardian key) + `test-gv-g5` (mainnet 12/12, testnet 19/19). Defines:
    grace = 10 blocks, **silence = accept**, **AUTO-DISCONNECT at block 100,000** (gv_g5_active_at
    is unconditionally false from 100,000 — the veto cannot become permanent), replay-safe signed
    digest = sha256(DOMAIN || dest_pkh || expiry_height). Gated: mainnet DEFERRED (INT64_MAX),
    testnet active at V15_HEIGHT. Carrier = a 0-value coinbase output to `GV_G5_VETO_PKH` whose
    payload is [expiry u64 LE][compact ECDSA sig].
  - W4b ✅ DONE — enforcement wired into the real block path:
    * `ValidateCoinbaseConsensus` (gated) now also recognizes the G5 veto carrier alongside the
      G4 marker: both are stripped via `real_outs` from CB shape, CB10 payload and R5/R6 checks
      (the veto carries a payload). Pre-activation neither is recognized → rejected → replay
      byte-identical. Tests: `test-gv-g4-coinbase` (mainnet 6/6 + testnet 13/13).
    * `process_block`: when `gv_g5_active_at(height)` AND the block has a Gold Vault spend, scan
      the grace window `[h-10, h-1]` for a Guardian-signed, unexpired veto for the spend's
      destination (`gv_g5_verify_veto_payload`); if present → reject. silence = accept.
    * Mainnet DEFERRED + auto-disconnect ≥100,000 → pure no-op. full ctest 67/67 (mainnet+testnet).
  - Remaining: cross-validator agreement test + testnet soak (B3); then the single final flip
    of all V15 gates (Slice 1, G4, G5) to V15_HEIGHT, re-verified under reorg replay.

> Status: gv_g4 pure module + coinbase-marker channel + detector DONE & tested (`test-gv-g4`,
> 18/18). **W1 DONE** (Slice 1 enforced on the real block path via the shared helper,
> mainnet no-op, `test-gv-slice1-block` in CI). W2-W3 (G4 coinbase marker + 67-block window)
> are next — they touch the coinbase rules, so done carefully with replay verification, not rushed.

## 3. PHASE C — PoPC Model A (component #6) — DEFER gate flip, build the rails

The DTD-PoPC eligibility gate must NOT read `popc_registry.json` from consensus (it is per-node,
non-deterministic → instant chain split). Prerequisites (ordered):
- C1: define a deterministic on-chain PoPC commitment (a new output/UTXO class with a fixed payload).
- C2: `chain_active_popc_set(height)` pure function, recomputed from chain state on every node.
- C3: consensus **auto-audit / auto-slash (grace 1,000 blocks) / auto-settlement** rules in block
  validation (replaces today's manual RPC + cron). Reorg-undo data.
- C4: E2E lifecycle test (register→audit→slash/settle, zero RPC) + 4-week testnet soak.
- C5: coordinated point release flips `DTD_POPC_GATE_CONSENSUS_ACTIVE=true` at a **separate** height
  (e.g. 15,100), announced, after Phase A replay/testnet are green.

**Estimate ~6-7 weeks.** V14 keeps the gate **deferred** (it already does). This is the right call.

---

## 4. PHASE D — Atomic Swap HTLC (component #8) — TARGET V15

SOST-side + EVM contract are done/tested, but BTC signing is stubs (libwally not wired), there are
no testnet deployments, and no external crypto/contract/economic audits. The branch
(`feat/atomic-swap-htlc-v13-candidate`) explicitly records **DO NOT FLIP THE GATE**.
- Keep `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX`.
- V15 path: libwally integration (Phase C) → BTC + EVM testnet E2E for all 7 pairs → 3 external
  audits → flip the gate. Wallet UI must surface the issuer-freeze risk on USDT/USDC/PAXG/XAUT.

---

## 5. Sequencing (what to do, in order)

1. **Phase A (safety net)** — now, in parallel with decisions. Unblocks everything safely.
2. **Operator decisions D1/D2/D3** (Gold Vault) + V14-scope sign-off.
3. **Phase B1 (Gold Vault Slice 1)** if chosen for V14 — small, testable.
4. Ship **V14 = H3/H4 + fees (+ Slice 1 if ready)**; everything else stays deferred.
5. **Phase C (PoPC rails)** as a post-V14 program → gate flip at 15,100+.
6. **Phase D (Atomic Swap)** → V15.

> The mainnet binary for block 15,000 only strictly needs H3/H4 + fees. Each additional component
> joins only when its gate can be flipped safely (replayed, testnet-proven, announced).
