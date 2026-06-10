# SOST V15 — Master status & activation plan

**Purpose:** one authoritative document for the whole V15 package — PoPC
(Model A/B), Gold Vault governance, and OTC/P2P Atomic Swap — stating exactly
what is built, what is gated OFF, what each gate's real value is, what a node
operator must do, what still requires external audit, and the ordered plan
before any activation ("flip"). **No new features; consolidation only.**

> **One-line status:** all three V15 subsystems are *built and tested*, and every
> consensus-affecting behaviour is *gated OFF or height-deferred to V15_HEIGHT =
> 20,000 (mainnet)*. The chain is well below that height, so **mainnet is
> byte-identical today**. Nothing here flips a gate.

Source of truth for every value below: the repo headers (`include/sost/…`) and
`CMakeLists.txt`, verified against the current tree.

---

## 1. Executive summary

- **What V15 does (once activated):** adds (a) PoPC Model A/B — Proof-of-Useful-
  Compute accounting + a DTD-PoPC eligibility path; (b) Gold Vault governance —
  miner-voted, capped, whitelisted spends of the constitutional gold reserve;
  (c) OTC/P2P Atomic Swap — non-custodial SOST↔BTC/EVM HTLC swaps.
- **What is built:** PoPC P0–P5 + tooling; Gold Vault W1–W4 + G4/G5 + the B3
  harness; OTC-1…OTC-5 (SOST HTLC consensus, wallet/orderboard/watcher, node RPC,
  BTC libwally signing, EVM contract, end-to-end coordinator, live rehearsal).
- **What stays OFF:** the OTC HTLC consensus gate (`INT64_MAX`), the DTD-PoPC
  consensus gate (`false`), BTC signing (compile flag default OFF), the EVM
  contract (not deployed). The PoPC-V15 and Gold-Vault gates are height-deferred
  to V15_HEIGHT = 20,000 (not yet reached).
- **What requires the operator:** running live testnet soaks/rehearsals,
  building the opt-in BTC-signing binary, deploying the EVM contract to a
  testnet, and (eventually) a coordinated mainnet release.
- **What requires external audit:** the OTC stack (BTC signing, EVM contract,
  timeout/economic model) — before any consideration of activation.

---

## 2. Gate table (verified against the source)

Mainnet values shown; several constants have a `TESTNET`-only override in
`params.h` (e.g. V14=200, V15=300) used by soak builds. Current mainnet tip is
well below V15_HEIGHT, so all height-gated items are **pending (not active)**.

| Gate / constant | Value (mainnet) | Source | Status today |
|---|---|---|---|
| `V11_PHASE2_HEIGHT` | 7,100 | `params.h:396` | active (past) |
| `V13_HEIGHT` | 12,000 | `params.h:840` | active (past) |
| `V14_HEIGHT` | 15,000 | `params.h:1001` | pending; H3/H4 hardening already in deployed binaries |
| `V15_HEIGHT` | 20,000 | `params.h:1017` | **pending** (target) |
| `DTD_POPC_GRACE_BLOCKS` | 1,000 | `params.h:1028` | — |
| `DTD_POPC_ELIGIBILITY_HEIGHT` | 21,000 (= V15+grace) | `params.h:1029` | pending |
| `DTD_POPC_GATE_CONSENSUS_ACTIVE` | **false** | `params.h:1006` | **OFF** (advisory only; no consensus effect even past the height) |
| `POPC_V15_ACTIVATION_HEIGHT` | 20,000 (= V15) | `popc_v15.h:31` | pending; consensus effect still gated by the boolean above |
| `GV_SLICE1_ACTIVATION_HEIGHT` | 20,000 (= V15) | `gold_vault_slice1.h:84` | pending |
| `GV_G4_ACTIVATION_HEIGHT` | 20,000 (= V15) | `gv_g4.h:55` | pending |
| `GV_G5_ACTIVATION_HEIGHT` | 20,000 (= V15) | `gv_g5.h:48` | pending |
| `GV_THRESHOLD_EPOCH01` / `_EPOCH2` | 90% / 90% | `consensus_constants.h:54-55` | param (applies once GV active) |
| `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` | **INT64_MAX** | `atomic_swap.h:107` | **OFF** (sentinel; HTLC tx types rejected, replay byte-identical) |
| `SOST_BTC_HTLC_SIGNING` (CMake) | **OFF** (default) | `CMakeLists.txt:375` | OFF; real signing only with `-DSOST_BTC_HTLC_SIGNING=ON` |

**Two independent OFF mechanisms** keep mainnet inert: (1) **height** —
PoPC/Gold-Vault behaviours don't trigger until block 20,000; (2) **boolean /
sentinel** — `DTD_POPC_GATE_CONSENSUS_ACTIVE=false` and
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT=INT64_MAX` keep those subsystems off even
past the height, until an explicit flip.

---

## 3. PoPC Model A/B

- **Built (P0–P5):** PoPC accounting + V15 lifecycle (register/pending,
  owner-authorised carriers, staged 20000/21000 activation), `popc_v15` module,
  read-only observability.
- **Tooling:** `tools/popc15_carrier.cpp` (`popc15-carrier`, carrier-payload
  generator), `getpopcv15status` RPC (wired in `src/sost-node.cpp`),
  `scripts/run_testnet_soak.sh`, plus the off-chain PoPC daemon/oracle scripts
  under `scripts/` (advisory, off-chain).
- **Status:** code complete; consensus effect gated by
  `DTD_POPC_GATE_CONSENSUS_ACTIVE=false` and height 20,000/21,000. Soak notes in
  `docs/V15_POPC_SOAK_REPORT.md`, `docs/V15_POPC_TESTNET_SOAK_GUIDE.md`,
  design in `docs/V15_POPC_MODEL_AB_DESIGN.md`.
- **Missing before any flip:** a sustained live multi-node testnet soak with
  replay verification, and an explicit decision on whether/when to enable the
  DTD-PoPC consensus path (the optional flip of the boolean). Useful-Compute
  **rewards remain POSTPONED** — infra is dry-run only; a rewarded phase needs a
  separate redesign.

---

## 4. Gold Vault governance

- **Built (W1–W4 + G4/G5 + slice 1):** spend-side governance — miner approval
  (90% over a 67-block window), quality vote / single-signer veto from
  developer/genesis, single-destination whitelist (genesis miner), per-spend and
  weekly caps, G5 veto digest. Modules: `gold_vault_slice1`, `gv_g4`, `gv_g5`,
  `gold_vault_governance`.
- **Harness:** the B3 integration harness + `gv-g5` / `gold-vault` /
  `v13-gold-vault-slice1` ctest targets.
- **Status:** code complete; all activations height-deferred to V15_HEIGHT =
  20,000 (replay byte-identical until then). Soak notes in
  `docs/V15_GOLD_VAULT_SOAK_REPORT.md`, G4 design in
  `docs/V14_GOLD_VAULT_G4_DESIGN.md`.
- **Behaviour to keep visible (governance optics):** the whitelist (single
  destination = genesis miner) and the developer/genesis veto are **Phase-I**
  calibrations for a pre-CEX asset; the spec states they are temporary and to be
  removed once SOST has exchange listings and the vault can route to exchange
  addresses. The per-spend (1,000 SOST) and weekly (5,000 SOST/1,008-block) caps
  bound worst-case exposure.
- **Missing before any flip:** live soak with reorg + replay coverage on a
  multi-node testnet; explicit governance-optics sign-off.

---

## 5. OTC / P2P Atomic Swap

| Phase | Built | Status |
|---|---|---|
| OTC-1 | SOST HTLC consensus (LOCK/CLAIM/REFUND), gated | ✅ gated `INT64_MAX` |
| OTC-2 | wallet builders + orderboard + watcher (pure) | ✅ |
| OTC-2.5 | node RPC `gethtlcstatus` / `listhtlclocks` (read-only) | ✅ live on node |
| OTC-3a | BTC signing (libwally), OFF default, submodule pinned | ✅ ON only with flag |
| OTC-3b | EVM `AtomicSwapHTLC.sol`, 52 Foundry tests | ✅ not deployed |
| OTC-4 | end-to-end session coordinator (`otc-coordinator`) | ✅ pure |
| OTC-5 | live rehearsal (EVM in-process, BTC vectors, coordinator) | ✅ PASS |

- **Docs:** `V15_OTC_ATOMIC_SWAP_DESIGN.md`, `V15_OTC_BTC_REGTEST_GUIDE.md`,
  `V15_OTC_EVM_TESTNET_GUIDE.md`, `V15_OTC_E2E_SWAP_GUIDE.md`,
  `V15_OTC_LIVE_REHEARSAL_REPORT.md`.
- **Status:** fully built and rehearsed in a closed loop; non-custodial; nothing
  on mainnet (HTLC gate `INT64_MAX`, BTC signing OFF, EVM undeployed).
- **Missing before any flip:** full live-daemon rehearsals (anvil + Bitcoin-Core
  regtest + a SOST regtest node), and an **external cryptographic / economic
  audit** of the BTC signing, the EVM contract, and the timeout/fee model.
- **Issuer-freeze (must never be hidden):** USDT/USDC/PAXG/XAUT can be frozen by
  their issuer; atomicity is **not** guaranteed for those legs (the orderboard /
  session / contract all surface `ISSUER_FREEZE_RISK`). BTC/ETH/BNB/SOST have no
  asset-level freeze.

---

## 6. Activation plan (ordered; nothing skipped)

- **Step 0 — now:** **No flip.** Mainnet byte-identical; all gates OFF/deferred.
- **Step 1 — live rehearsals:** multi-node testnet soak of PoPC + Gold Vault;
  full live-daemon OTC rehearsals (anvil, Bitcoin-Core regtest, SOST regtest
  node with a regtest-only gate override).
- **Step 2 — replay mainnet:** full `--dry-run-replay` of the candidate binary
  against the mainnet chain to prove byte-identical validation up to the gate
  heights.
- **Step 3 — external audit:** independent cryptographic/economic audit of the
  OTC stack (BTC signing, EVM contract, timeout model) and a review of the
  Gold-Vault governance optics + PoPC accounting.
- **Step 4 — operator notice:** publish a dated upgrade notice (chain banner +
  channels) telling miners/nodes the exact binary and the activation heights.
- **Step 5 — coordinated release:** ship the binary; confirm supermajority of
  nodes/miners updated before the relevant height.
- **Step 6 — finite gates:** only then set finite activation heights (and/or
  flip `DTD_POPC_GATE_CONSENSUS_ACTIVE` / `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`),
  each as a separate, explicit, reversible change. Rollback = restore the
  sentinel/`false`; no fork at sub-activation heights.

---

## 7. Go / No-Go checklist

| Item | Gate to GO |
|---|---|
| PoPC | multi-node soak + replay clean; DTD-PoPC flip decision made explicitly |
| Gold Vault | soak incl. reorg + replay clean; governance-optics sign-off |
| OTC | live-daemon rehearsals pass on operator machines; external audit clear |
| Replay | `--dry-run-replay` byte-identical against mainnet up to gate heights |
| CI | full ctest green (OFF default) + Foundry green + BTC-ON green |
| Operator comms | dated notice published; supermajority confirmed updated |
| Rollback plan | documented and tested: restore `false`/`INT64_MAX`, no fork below activation height |

**NO-GO if any row is unmet.** Activation is per-subsystem and independent — PoPC,
Gold Vault and OTC can flip on different schedules.

---

## 8. Risk register

| Risk | Mitigation in place |
|---|---|
| **Issuer-freeze** (USDT/USDC/PAXG/XAUT) breaks EVM-leg atomicity | surfaced everywhere as `ISSUER_FREEZE_RISK`; SOST leg still settles cryptographically; never promise atomicity for these |
| **Bad gate flip** (premature/uncoordinated) | two independent OFF mechanisms (height + boolean/sentinel); flips are separate, explicit, reversible; replay + supermajority before any height |
| **Timeout mis-ordering** (T2 ≥ T1) | rejected at offer/session creation (`TIMEOUT_ORDER_INVALID`); margin ≥ 6 enforced |
| **Off-chain truth gap for PoPC** | DTD-PoPC consensus path kept OFF (`false`); rewards POSTPONED; on-chain accounting only advisory until audited |
| **Gold-Vault governance centralization optics** | caps + whitelist + veto are explicit, documented Phase-I temporary measures with a stated removal condition (CEX listing) |
| **EVM contract risk** | no owner/admin/upgrade/pause/drain; 52 Foundry tests incl. reentrancy/fee-on-transfer/forced-ETH; not deployed; external audit required |
| **BTC signing risk** (fund-loss-prone primitives) | delegated to vendored, pinned, GPG-verified libwally (release_1.5.3); OFF by default; BIP-143 known-answer vectors; external audit required |

---

## 9. Commands appendix

```bash
# --- Default OFF build (mainnet-identical; what nodes/CI run) ---
cmake -S . -B build && cmake --build build -j"$(nproc)"
( cd build && ctest )                       # full suite, OFF default

# --- BTC signing ON (OTC-3a; regtest/review only) ---
git submodule update --init --recursive vendor/libwally-core
cmake -S . -B build-on -DSOST_BTC_HTLC_SIGNING=ON && cmake --build build-on -j"$(nproc)"
( cd build-on && ctest -R atomic-swap-btc )

# --- PoPC testnet soak ---
bash scripts/run_testnet_soak.sh            # see docs/V15_POPC_TESTNET_SOAK_GUIDE.md

# --- Gold Vault soak ---
( cd build && ctest -R "gold-vault|gv-g5" ) # see docs/V15_GOLD_VAULT_SOAK_REPORT.md

# --- OTC rehearsals ---
bash scripts/otc_rehearsal_evm_anvil.sh     # EVM (anvil live / forge-test fallback)
bash scripts/otc_rehearsal_btc_regtest.sh   # BTC (regtest live / ON-vectors fallback)
bash scripts/otc_rehearsal_sost_local.sh    # SOST suites + coordinator drive

# --- Verify gates are OFF/deferred (paranoia check) ---
grep -nE "ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT *=" include/sost/atomic_swap.h     # INT64_MAX
grep -nE "DTD_POPC_GATE_CONSENSUS_ACTIVE *=" include/sost/params.h              # false
grep -nE "V15_HEIGHT *=" include/sost/params.h                                  # 20000 (mainnet)
grep -nE "option\(SOST_BTC_HTLC_SIGNING" CMakeLists.txt                         # OFF
```

---

## 10. Bottom line

V15 is **built, tested, rehearsed, and entirely OFF on mainnet**. The pieces —
PoPC, Gold Vault, OTC — are ready to *review*, not yet to *activate*. The next
real work is operational (live soaks/rehearsals, replay, operator comms) and
**external audit**, not more code. Every activation remains a separate,
explicit, reversible step taken only after this checklist is green.
