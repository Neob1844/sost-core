# V13 Activation Plan

**Status:** preparation only — no consensus state mutated by this artifact.
**Target activation height:** **block 12,000**
**Fallback for gated items:** **V15 at block 15,000** (proposed final hardfork, not guaranteed)
**Companion artifacts:**
- `config/v13_activation.json` — machine-readable source of truth
- `docs/V13_READINESS_GATES.md` — per-gate checklist
- `scripts/trinity/v13_readiness_check.py` — preflight verifier
- `schemas/trinity/v13_readiness_report.schema.json` — report schema

---

## 1. Prime directive

This plan prepares the repository so the V13 activation set is **explicit, testable, machine-readable, and safe**. It does NOT silently activate unfinished systems. Confirmed items may activate at block 12,000. Target/fallback items must be behind readiness gates and remain inactive unless every gate passes; if any gate fails, the item slides to V15 (block 15,000) or stays disabled.

---

## 2. Activation set

### 2.1 Confirmed at block 12,000

| id | label | gating evidence (existing) |
|---|---|---|
| `casert_all_profiles_e7_h35` | All cASERT equalizer profiles E7–H35 active | **WIRED**: `include/sost/params.h` declares `CASERT_MAX_ACTIVE_PROFILE_V13 = 35` plus `validator_profile_ceiling_at(height)` (validator side) and `effective_profile_ceiling_at(height)` (controller side). Both return H35 for `height >= V13_HEIGHT`. The validator gate in `src/sost-node.cpp` and the two controller gates in `src/pow/casert.cpp` route through the helpers. Boundary tests live in `tests/test_casert_v13_ceiling.cpp`. |
| `dtd_cooldown_6` | DTD lottery cooldown 5 → 6 blocks | `include/sost/params.h:835` `lottery_exclusion_window_at(height)` returns 6 for `height >= V13_HEIGHT`. |
| `timestamp_drift_30s` | Future-drift cap 60 s → 30 s | `include/sost/params.h:852` `max_future_drift_at(height)` returns 30 for `height >= V13_HEIGHT`. |
| `beacon_phase_ii_a` | Beacon Phase II-A — local notices, file-only, signed | `include/sost/params.h:828` `BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT`; `include/sost/beacon.h:43` `BEACON_PUBKEY_HEX` declared. |

The readiness-check script (`scripts/trinity/v13_readiness_check.py`) inspects each of these against the live tree on every run. The script is the authority — this table is documentation. **If the script reports `casert_all_profiles_e7_h35` as `wired_in_code: false`, that item is NOT ready and must be wired or the V13 cut delays.**

### 2.2 Target V13 / fallback V15

| id | target | fallback | rule |
|---|---|---|---|
| `popc_model_a_b` | 12,000 | 15,000 | If any of seven PoPC gates (a–g) fails, ship at V15. |
| `beacon_phase_ii_b` | 12,000 | 15,000 | If design + implementation + tests not closed by V13 cut, ship at V15. |
| `beacon_phase_iii`  | 12,000 | 15,000 | If P2P implementation + activation constant + safety tests + anti-DoS tests not green by V13 cut, ship at V15. |
| `memory_lock_per_instance` | 12,000 | 15,000 | If design + independent simulation + implementation + small-miner safety test not present, ship at V15. |

### 2.3 NOT in V13

- Beacon Phase III with `BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX` (current state). Brought forward as a V13 candidate gated by readiness checks.
- Any item not listed in §2.1 or §2.2.

---

## 3. PoPC gating checklist (seven gates a–g)

PoPC may target block 12,000 only if **all seven** are true:

```
a) Audit daemon exists and is production-wired.
b) Auto-slash on audit failure is wired and tested.
c) Auto-settlement reward + bond release is wired and tested.
d) Model B Ethereum SOSTEscrow deployment checklist is complete
   for the intended network (Sepolia or mainnet) with a verified
   deployment record file.
e) Ethereum event listener exists and is tested for the
   GoldDeposited -> SOST escrow_register path.
f) Consensus-level POPC_ACTIVATION_HEIGHT (or equivalent named
   gate) exists in include/sost/ and is referenced by the
   lifecycle code.
g) Full automated lifecycle integration test exists:
   register -> mature -> audit -> slash-or-settle -> close,
   with NO manual RPC call from the test.
```

If any of a–g is missing, **PoPC activation height is V15 (block 15,000)** and the report must say why. The other V13 items in §2.1 do NOT depend on PoPC and ship on schedule regardless.

---

## 4. Beacon safety invariants (all phases)

Enforced at validator + static safety lint:

```
- Beacon MAY inform an operator.
- Beacon MAY NOT restart a node or miner.
- Beacon MAY NOT block any block or transaction.
- Beacon MAY NOT change consensus rules.
- Beacon MAY NOT execute commands on the host.
```

Beacon is the protocol's loudspeaker. Not its remote control. The full three-phase specification (II-A confirmed, II-B and III gated) lives in the forum announcement and in `docs/BEACON_PHASE_IIB_SPEC.md` / `docs/BEACON_PHASE_III_SPEC.md` (to be added before activation).

---

## 5. Memory-Lock per-instance — anti-pool

The only anti-pool mechanism the project ships besides SbPoW. Forces the 4 GB ConvergenceX dataset to be per-thread rather than shared across threads — concentration of hashrate is mathematically penalised, not masked. `docs/V11_SPEC.md` already says: "earliest activation, if it ever ships, is block 12,000+ after independent simulation."

Activation requires:

- Dedicated design doc (`docs/MEMORY_LOCK_PER_INSTANCE_SPEC.md`).
- Independent simulation artifact in the repo (script + result file).
- Implementation in `src/` behind a height-gated path.
- Test proving the 8 GB RAM floor still holds for legitimate solo miners.

If any of these is missing, fallback to V15 (or stays inactive).

---

## 6. Operator warnings

- **NTP synchronisation is strongly recommended post-V13.** Future-drift cap drops from 60 s to 30 s at `V13_HEIGHT`. A host whose clock is more than 30 s ahead of true time will produce candidate blocks that validators reject. Operators must verify NTP before V13 lands.
- **No half-enabled gated items.** If a gated item's checks do not all pass, it does NOT ship at V13. It either slides to V15 or stays inactive. There is no middle position.
- **The reservation may fire late in the V13 window.** The honest stance is: design and per-component code for PoPC are tested, but the operational orchestration layer is the gating work. If the gates do not all close in time, the slip is announced from the BitcoinTalk thread the moment the decision is made, with the same ≥30-day rule applied to V15.

---

## 7. DTD lottery decision at block 12,100

The DTD lottery was not in the original SOST design. It was added in V11 Phase 2 as a redistribution mechanism while PoPC and Useful Compute reached production. At block 12,100 — ~100 blocks after V13 has stabilised — the operator opens a community decision in the announcement thread:

```
OPTION A — Keep the DTD lottery at 1-of-3 blocks permanent.
  Cooldown stays at 6 (V13). Continues as supplementary
  redistribution, in parallel with PoPC.

OPTION B — Disable the DTD lottery.
  Protocol returns to a clean 50/25/25 split on every block.
  Extra-coinbase rewards stay on the original path: PoPC
  contracts + Useful Compute (when each activates).
```

If PoPC slides to V15, the decision opens at 12,100 anyway but the substance changes — keeping the lottery as redistribution is more defensible while the original reward path is not yet live.

---

## 8. V15 — proposed final hardfork (not guaranteed)

V15 is the proposed **final** hardfork of the SOST protocol. "Final" means no further consensus changes are planned after V15. All evolution beyond that point lives in non-consensus surfaces.

V15 is **not guaranteed**:

- If every V13 candidate ships cleanly at block 12,000, V15 may not be needed.
- If any candidate defers, V15 catches the remainders and closes the consensus-evolution chapter.

The commitment is identical either way: no fork after V15. Critical-security incidents that require hard mitigation are the only override, and that is the bar, not feature requests.

---

## 9. Safety invariants for the readiness-check script itself

The script in `scripts/trinity/v13_readiness_check.py`:

```
- NEVER touches a wallet.
- NEVER touches a private key.
- NEVER signs anything.
- NEVER broadcasts.
- NEVER opens the network.
- NEVER calls the GitHub API.
- NEVER uses subprocess.
- NEVER mutates git state (no push, no merge, no tag).
- NEVER uses shell-string subprocess (shell=True is forbidden,
  and the script does not use subprocess at all).
```

All eleven safety flags are const-locked at the schema level. The static safety test refuses to let the script regress.

---

## 10. Operator deploy sequence

When the V13 cut is ready:

1. Run the readiness check from the repo root:
   ```bash
   python3 scripts/trinity/v13_readiness_check.py \
       --repo-root /opt/sost \
       --out-json /tmp/sost-v13-readiness/report.json \
       --out-md   /tmp/sost-v13-readiness/report.md \
       --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
   ```
2. Read the report. Confirm `v13_ready_for_confirmed_items: true` and that every item in `fallback_to_v15_items` is intentionally deferred.
3. Cut the V13 binary tag with `min_commit` set so outdated miners see the banner.
4. Publish the announcement to BitcoinTalk + Beacon Phase II-A notices.
5. After block 12,000 + a stability window, open the DTD lottery decision at 12,100.
6. If any gated item is still in flight, prepare V15 work and announce ≥30 days before block 15,000.

---

## 11. NOT in scope

- This branch does NOT push to remote, merge, or tag.
- This branch does NOT modify consensus behavior. The already-wired V13 items (cooldown / drift cap / Beacon II-A activation gates) are documented in code from prior commits.
- The readiness-check script does not deploy, sign, broadcast, or contact GitHub.
- The Solidity contract is not deployed by this branch.
