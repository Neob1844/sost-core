# Trinity Useful Compute — Operator Loop Governor Observe Hook v0.1

**Sprint:** 5.24
**Status:** observe-only · audit-trail only · no behaviour change to the pipeline
**Depends on:** Sprint 5.23 (Trinity Autonomy Governor v0.1) and the
operator loop from Sprint 5.19 → 5.22

---

## 1. What this sprint adds

The Trinity Autonomy Governor v0.1 (Sprint 5.23, commit `b66352d6`)
shipped as a **standalone** evaluator: it was not wired into anything.
This sprint adds a thin, observe-only hook so the operator loop
(`scripts/trinity/useful_compute_operator_loop.py`) consults the
Governor **once per pipeline step** and records a decision JSON for
every consultation. The hook is opt-in via a new CLI flag and a
missing flag is a strict no-op.

```
                 ┌──────────────────┐
                 │ operator_loop    │
                 │ (Hands layer)    │
                 └────────┬─────────┘
                          │ before each of the 7 steps
                          ▼
                 ┌──────────────────┐
                 │ Autonomy Governor│ ← policy.json (sha-pinned at boot)
                 │ pin_policy() +   │ ← halt_file (/etc/trinity/HALT)
                 │ evaluate_decision│
                 └────────┬─────────┘
                          │ writes one
                          ▼
        TRINITY_AUTONOMY_GOVERNOR_DECISION_<id>.json
        (registered in SHA256SUMS.txt + operator_run.json
         artifacts.governor_decisions)
```

The Governor is loaded **by direct Python import** through the
operator loop's existing `_load_sibling()` helper. The loop does
**not** shell out to invoke it.

---

## 2. New CLI surface

Two new optional flags on `useful_compute_operator_loop.py`:

| Flag                            | Default | Effect |
|---------------------------------|---------|--------|
| `--governor-policy PATH`        | none    | Enable the observe hook. Pin sha256(PATH) at boot. |
| `--governor-decisions-dir DIR`  | `OUT_DIR/governor_decisions` | Where decision JSONs are written. Must resolve as a subpath of `--out-dir` so the manifest entries remain relative. |

Both flags are **optional**. Absence of `--governor-policy` keeps the
loop's behaviour byte-for-byte identical to Sprint 5.22d.

---

## 3. Extended `operator_run.json` shape

Four new optional properties land on the v0.1 operator-run schema:

```json
{
  "governor_enabled": true,
  "governor_policy_sha256": "<64-hex>",
  "governor_policy_path_basename": "trinity_autonomy_governor.example.json",
  "governor_decisions_count": 7,
  "artifacts": {
    "governor_decisions": [
      { "path": "governor_decisions/TRINITY_…_<id>.json", "sha256": "…" },
      …
    ]
  }
}
```

Hard rules:

- The **full path** of the policy file is **never** persisted — only
  its basename. This protects operator-private paths the same way
  `source_request_path_basename` did for v5.22.
- `governor_policy_sha256` is the pin established at boot. Subsequent
  decisions also re-hash the live file and compare. Any mismatch
  triggers a `policy_mutated_at_runtime` hard-block.
- `governor_decisions_count` equals the number of artefact entries.
- All four fields are present (with `null` / `false` / `0`) even when
  the governor is disabled, so consumers see a uniform schema.

---

## 4. The seven hooked steps

The hook fires before each pipeline step, in order:

```
task_builder → worker → replay_validator → governance_gate
  → reward_budget_policy → payment_proposal → payment_draft
```

A new action `pipeline_step` was added to the Governor's
`KNOWN_ACTIONS` with threat refs `["T15", "T16", "T17"]`
(audit-log tampering · governance bypass · budget cap bypass — the
three SECURITY.md entries that an audit hook is positioned to
surface). Each decision's `action_params` carries
`{"step_name": "<step>"}` so the audit trail is self-describing.

---

## 5. Hard-block semantics

The hook treats two reasons as **hard-blocks**: it refuses to start
the step and exits the operator loop with rc=3.

| `blocked_reason`              | When                                                 |
|-------------------------------|------------------------------------------------------|
| `halt_file_present`           | The `kill_switch.halt_file` (default `/etc/trinity/HALT`) exists at decision time. |
| `policy_mutated_at_runtime`   | sha256 of the policy file differs from the boot pin. |

All other allowed=false outcomes are treated as **observe-only**:
the decision is still written to disk, the loop appends a
`[governor:observe] …` line to `operator_run.json["warnings"]`,
and the step proceeds normally. v0.1 is explicitly an audit trail —
it does not yet veto anything outside the two hard-block reasons.

When a resume runs against an operator_run whose policy file has
mutated between the original boot and the resume, the loop refuses
the resume with `ValueError` (turned into rc=2). The recorded
sha256 in operator_run.json is left intact.

---

## 6. Two new public helpers in `autonomy_governor.py`

Both are pure-Python, no I/O beyond the policy file and the
optional decision file. Both are safe for in-process callers.

```python
boot_sha, policy = pin_policy(policy_path)

decision = evaluate_decision(
    policy_path=policy_path,
    action="pipeline_step",
    action_params={"step_name": "worker"},
    pinned_time="2026-05-16T00:00:00+00:00",
    boot_policy_sha256=boot_sha,
    out_dir=decisions_dir,   # optional
)
# decision["_decision_path"] is set when out_dir is supplied; callers
# pop it before persisting the decision verbatim.
```

These exist so the operator loop can talk to the Governor without
re-implementing boot-pin logic, file naming or schema validation.
External callers (future watchdog, future REST shim) use the same
two functions.

---

## 7. Test coverage added in Sprint 5.24

| File                                                       | New tests | What they cover |
|------------------------------------------------------------|-----------|-----------------|
| `tests/trinity/test_autonomy_governor.py`                  | +9        | `pipeline_step` action, `pin_policy()`, `evaluate_decision()` happy + tamper + determinism |
| `tests/trinity/test_autonomy_governor_schema.py`           | +3        | `pipeline_step` decision validates · KNOWN_ACTIONS coverage · threat-ref alignment |
| `tests/trinity/test_operator_loop_governor_hook.py`        | +11 (new) | End-to-end: baseline parity · decisions per step · path-basename privacy · halt-file hard-block · policy mutation refuses resume · resume carries sha forward · schema-shape · no subprocess invoked |
| `tests/trinity/test_operator_loop_safety.py`               | unchanged | Re-asserts the loop still has zero subprocess / sost-cli / wallet / signing tokens after the hook landed. |

`pytest tests/trinity/` was green on the deployment host:
**96 / 96 passing** (33 governor + 16 governor-schema + 11 operator-loop hook + 13 operator-loop safety + the existing 23 operator-loop tests).

---

## 8. Explicit non-goals for v0.1

- **No vetoes outside hard-block reasons.** allowed=false for any
  other reason is recorded and warned but does not stop the loop.
- **No background watchdog.** The hook fires synchronously inside
  the operator loop process. A separate watchdog process is
  reserved for a later sprint and is the only thing allowed to
  do external heartbeating.
- **No audit log writes.** Decisions live as filesystem artefacts.
  No syslog / journald / remote ship.
- **No mode change.** The Governor is still locked to
  `mode=observe` and `caps_per_day.autonomous_sost_stocks=0`.
- **No new attack surface.** The operator loop does not gain
  network, shell, wallet, signing, or broadcasting capability.
  The static safety test continues to enforce this.

---

## 9. Deployment notes

- The policy file must be owned by `root` and not writable by the
  Trinity process. The loop trusts the sha256 pin established at
  boot; the kernel must keep the file from being silently swapped.
- The halt file path (default `/etc/trinity/HALT`) must be in a
  directory the Trinity process cannot create files in — only the
  operator should be able to drop the halt file.
- The decisions directory should be on the same volume as the run
  output (it usually is by default). Operators who want a separate
  audit volume should symlink rather than relocate, so the manifest
  paths remain relative.

---

## 10. Traceability

- Sprint 5.23 = the Governor that this sprint plugs in
  (commit `b66352d6`, tag `sprint-5.23`).
- The threat refs used by the new `pipeline_step` action map to the
  threat model that landed in commit `35f5a23c` (SECURITY.md
  T15 / T16 / T17).
- Pure docs+scripts+schemas+tests merge. Zero `src/`, zero
  consensus / wallet / payment / broadcast changes.
