# V13 Readiness Gates

Per-gate checklist. Each row maps to a checker in
`scripts/trinity/v13_readiness_check.py`. The script reads the live
tree and produces a `trinity-v13-readiness-report/v0.1` JSON + a
Markdown rendering.

**A gate that returns `unknown` is treated as a failure.** No item
ships at V13 with an `unknown` gate.

---

## Confirmed items (must be wired in code to allow V13 cut)

| id | rule | current status (commit-relative) |
|---|---|---|
| `casert_all_profiles_e7_h35` | `effective_profile_ceiling_at(height)` returns 35 for `height >= V13_HEIGHT`, OR a `CASERT_MAX_ACTIVE_PROFILE_V13` / `CASERT_V13_PROFILE_CEILING` constant lifts the ceiling. | WIRED at `include/sost/params.h` via the new `CASERT_MAX_ACTIVE_PROFILE_V13 = 35` constant plus `validator_profile_ceiling_at(height)` and `effective_profile_ceiling_at(height)` helpers. Both controller call sites in `src/pow/casert.cpp` and the validator gate in `src/sost-node.cpp` route through the helpers. Tests: `tests/test_casert_v13_ceiling.cpp` (heights 11999 / 12000 / 12001). |
| `dtd_cooldown_6` | `lottery_exclusion_window_at(height)` returns 6 for `height >= V13_HEIGHT`. | WIRED at `include/sost/params.h:835`. |
| `timestamp_drift_10s` | `max_future_drift_at(height)` returns 10 for `height >= V13_HEIGHT`. | WIRED at `include/sost/params.h:852`. |
| `beacon_phase_ii_a` | `BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT` AND `BEACON_PUBKEY_HEX` declared. | WIRED at `include/sost/params.h:828` and `include/sost/beacon.h:43`. |

---

## PoPC Model A + B — seven gates (a–g)

| id | rule | what passes it |
|---|---|---|
| `popc_a_audit_daemon` | A real polling daemon invokes `compute_audit_seed` / `is_audit_triggered` automatically. | systemd unit at `scripts/popc_daemon.service`, OR a daemon script with a poll loop that executes RPC calls (not "operator review" prints). |
| `popc_b_auto_slash` | Auto-slash on audit failure is wired and tested. | A code path in `src/` or `scripts/` calls `popc_slash` when `is_audit_triggered` reports failure, with a test. |
| `popc_c_auto_settlement` | Auto-settlement reward + bond release is scheduled. | `scripts/popc_auto_distribute.sh` invokes `popc_release` AND a cron/systemd timer is committed (`scripts/popc_release.cron` or `.service`). |
| `popc_d_escrow_deployment` | Model B Ethereum `SOSTEscrow` is deployed and recorded. | `contracts/SOSTEscrow.deployment.json` (or similar) with a valid `0x[a-fA-F0-9]{40}` address. |
| `popc_e_event_listener` | Ethereum event listener exists for `GoldDeposited`. | A Python or C++ file references both `GoldDeposited` and `escrow_register`. |
| `popc_f_consensus_gate` | `POPC_ACTIVATION_HEIGHT` constant exists. | `inline constexpr int64_t POPC_ACTIVATION_HEIGHT = V13_HEIGHT;` (or `= V15_HEIGHT;`) in `include/sost/{consensus_constants.h, params.h, popc.h}`. |
| `popc_g_e2e_test` | Full automated lifecycle integration test exists. | A test under `tests/` that exercises `register → audit → slash-or-settle → release` with no manual RPC intervention. |

If ANY of a–g fails or is `unknown`, `popc_v13_ready` becomes false and `popc_model_a_b` falls back to V15.

---

## Beacon Phase II-B — three gates

| id | rule | what passes it |
|---|---|---|
| `beacon_iib_design_closed` | Design doc closed. | `docs/BEACON_PHASE_IIB_SPEC.md` (or equivalent) exists. |
| `beacon_iib_implementation` | Implementation present + gated. | An II-B activation constant (e.g., `BEACON_PHASE2B_ACTIVATION_HEIGHT`) and/or capability tokens (`expires_at_height`, `notice_threshold_sig`) found in `include/sost/` or `src/`. |
| `beacon_iib_tests_green` | Tests green. | A test under `tests/` mentioning "phase ii b" / "phase 2b". |

---

## Beacon Phase III — four gates

| id | rule | what passes it |
|---|---|---|
| `beacon_iii_p2p_implementation` | Scaffold + impl present. | `include/sost/beacon_p2p.h` + `src/beacon_p2p.cpp` both exist. |
| `beacon_iii_activation_constant` | Activation constant lowered from `INT64_MAX`. | `BEACON_P2P_ACTIVATION_HEIGHT` set to a non-dormant height (V13 or V15). |
| `beacon_iii_safety_invariants` | Safety tests cover the privilege model. | A test under `tests/` mentions Phase III / P2P and asserts the may/may-not boundaries. |
| `beacon_iii_anti_dos_tests` | Anti-DoS bounds covered. | A test exercises `BEACON_P2P_PEER_RATE_PER_MIN` and `BEACON_P2P_CACHE_MAX_NOTICES`. |

---

## Memory-Lock per-instance — four gates

| id | rule | what passes it |
|---|---|---|
| `memlock_design_doc` | Dedicated design doc exists. | `docs/MEMORY_LOCK_PER_INSTANCE_SPEC.md` (or `MEMORY_LOCK_SPEC.md` / `MEMLOCK_SPEC.md`). |
| `memlock_simulation_artifact` | Independent simulation in repo. | A directory `simulations/memory_lock/` or `scripts/simulations/` or `docs/simulations/` with at least one artifact (script + result). |
| `memlock_implementation` | Implementation gated at a constant. | `MEMORY_LOCK_ACTIVATION_HEIGHT` / `MEMLOCK_ACTIVATION_HEIGHT` constant present in `include/sost/` or `src/`. |
| `memlock_small_miner_safety` | Small-miner safety test exists. | A test file under `tests/` whose name contains `memory_lock` or `memlock`. |

`docs/V11_SPEC.md` already requires "independent simulation" before activation. Do not ship Memory-Lock without it.

---

## How the script decides

```
For each confirmed item:
  if wired_in_code == True → ready
  else                     → ready = False, warning

v13_ready_for_confirmed_items = all(confirmed_items[*].ready)

For each gated item:
  v13_ready                = all(gates[*].status == "pass")
  resolved_activation_height = 12000 if v13_ready else 15000

popc_v13_ready          = gated[popc_model_a_b].v13_ready
beacon_iib_v13_ready    = gated[beacon_phase_ii_b].v13_ready
beacon_iii_v13_ready    = gated[beacon_phase_iii].v13_ready
memory_lock_v13_ready   = gated[memory_lock_per_instance].v13_ready

overall_decision:
  if not v13_ready_for_confirmed_items:
      v13_confirmed_items_not_ready_block_fork
  elif all four gated items are V13-ready:
      v13_all_ready
  else:
      v13_confirmed_items_ready_gated_items_fallback_to_v15

safety_status:
  warning if any item is not ready or warnings exist
  ok      otherwise
  (failed is reserved for future use)
```

---

## Adding a new gate

1. Define the rule and a unique gate id in `config/v13_activation.json` under the right item.
2. Implement a `_check_<gate_id>(repo_root) -> {"status": ..., "evidence": ..., "blocker_note": ...}` function in `scripts/trinity/v13_readiness_check.py`.
3. Register it in `GATE_CHECKERS`.
4. Add a unit test that the gate is wired and a schema test if the report shape grows.
5. Document the gate in this file.

The script is deliberately strict — gates without a registered checker return `unknown` and force a manual review.
