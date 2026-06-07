# V14 (block 15,000) — Execution Plan

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
| A2 | **`--dry-run-replay` flag** on `sost-node`: load `chain.json`, replay 0..tip via `ConnectBlock`, print final height + a UTXO-set root hash, exit (no P2P/RPC). | TODO |
| A3 | **`scripts/validate-v14-replay.sh`** — build candidate + baseline binaries, replay both to 14,999, assert bit-identical (height + UTXO root). Pre-deploy gate. | TODO |
| A4 | **Testnet with low fork height** — `fork_height_at(profile, fork)` helper so `TESTNET` activates V14 at e.g. block 200; mine a small chain across the boundary. | TODO |
| A5 | **CI** `.github/workflows/v14-fork-safety.yml` — build + `ctest` (all ~69 tests) + fork-gate test on every push/PR. | TODO |
| A6 | **Beacon V14 notice template** `docs/V14_BEACON_NOTICE_TEMPLATE.md` + unsigned JSON (II-A advisory to miners). | TODO |
| A7 | **`docs/V14_DEPLOYMENT_CHECKLIST.md`** — operator runbook (build → replay-validate → testnet → sign beacon notice → deploy → verify → rollback). | TODO |

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
- B1: land Slice 1 in one reviewed commit (set `GV_SLICE1_ACTIVATION_HEIGHT=15000`, fill both
  whitelists + lengths, set cap). Add a validator integration test (real block+tx+UTXO, gate ON).
- B2 (if D3 = full): implement G4 auto-tally (67-block window, 90% threshold, **silence=accept**
  automatic at the validator), G5 Guardian pronouncement tx-type + 10-block grace + **auto-disconnect
  at block 25,000** (automation the operator wants). Add cross-validator agreement test.
- B3: testnet soak across the activation height; replay-validate; then enable on mainnet via the gate.

**Recommendation:** V14 ships **Slice 1 only** (G1/G2/G3a) — it's wired and testable now. Defer
G4/G5 to a later point release; they are large and need the testnet harness from Phase A.

---

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
