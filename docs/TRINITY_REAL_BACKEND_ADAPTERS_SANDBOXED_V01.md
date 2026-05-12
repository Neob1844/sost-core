# Trinity Real Backend Adapters Sandboxed v0.1

## Why we don't jump straight to real DFT

A real density-functional-theory (or quantum, or large-scale
simulation) backend changes Trinity's profile in three irreversible
ways:

1. **Cost.** Each task suddenly takes minutes-to-hours of real CPU /
   GPU, not microseconds. Miners' machines feel it. So do their
   electricity bills.
2. **Non-determinism.** Real DFT codes carry floating-point
   variability across hardware. Two honest workers on different
   machines will NOT bit-match `compute_output_sha256` without a
   carefully specified canonical rounding policy. That breaks the
   Sprint 5.8 cross-worker replay invariant on day one.
3. **Trust drift.** The moment "Trinity ran DFT" appears in a
   public dashboard, a user reading it can plausibly believe the
   network is doing real chemistry. Without proper provenance,
   integration tests, and disclaimers, that becomes a credibility
   trap.

Sprint 5.12 does NOT solve any of those three. It introduces the
**plumbing** that future sprints will need so that, when real
backends arrive, the system already knows how to declare them,
enforce backend identity across workers, and reject inconsistent
submissions.

## What v0.1 actually ships

`scripts/trinity/useful_compute_backends.py` exposes a registry of
backend implementations. Each backend has:

- `name` (e.g. `placeholder_dft`, `local_dft_toy_v01`)
- `version` (e.g. `v0.1`)
- `kind`: `placeholder`, `sandbox_toy`, or `real_backend`
  (reserved — no backend uses this kind in v0.1)
- `task_types` it can handle
- `disclaimer` — embedded into every emitted result
- `experimental` flag — sandbox_toy backends require an explicit
  CLI opt-in (`--allow-experimental-backends`)

The worker (`useful_compute_worker.py`) is now a thin orchestrator
that:

1. validates the request
2. selects a backend via
   `useful_compute_backends.select_backend(task_type, backend_name,
   allow_experimental)`
3. runs it via `run_backend(spec, request=..., deterministic_seed=...)`
4. canonicalises the technical output → `compute_output_sha256`
5. records backend identity in the result + pending-reward files

Default is `--backend placeholder`. Any other backend requires the
opt-in flag.

## What is a placeholder backend

The placeholders moved here unchanged from Sprint 5.7. They produce
deterministic, zero-cost surrogate output for the six task_types:

```
placeholder_dft
placeholder_quantum
placeholder_structure_relaxation
placeholder_scoring
placeholder_simulation
placeholder_other
```

Their `backend_runtime_seconds` is pinned to `0.0` so byte-identical
tests on placeholder remain stable across machines.

## What is a sandbox toy backend

Three new opt-in implementations:

| Name                                       | Supports                 | What it does                                                          |
|--------------------------------------------|--------------------------|-----------------------------------------------------------------------|
| `local_python_numeric_v01`                 | scoring, simulation      | 4096-iteration stdlib LCG + sine accumulator                          |
| `local_structure_relaxation_toy_v01`       | structure_relaxation     | 32 atoms × 64 steps of centroid-pull damping (NOT a force field)      |
| `local_dft_toy_v01`                        | dft                      | Power-method eigenvalue of a small symmetric matrix (NOT real DFT)    |

Toy backends are deterministic functions of `(request_id,
input_bundle_sha256)`. They use only the Python standard library —
no `numpy`, no `scipy`, no subprocess, no shell, no network. Their
`backend_runtime_seconds` is measured wall-clock from
`time.monotonic`, so two runs on different machines will report
different runtime values — but `compute_output_sha256` matches.

Honest disclaimers attached to every emitted result:

> "Sandbox toy backend (stdlib-only). Performs more work than the
> placeholder but is NOT a real scientific computation, NOT
> validated science, NOT publishable."

> "Sandbox toy relaxation. Iterates a centroid-pull damping loop
> on synthetic coordinates. NOT a real force-field minimisation."

> "Sandbox toy 'DFT' surrogate. Power-method eigenvalue of a small
> symmetric matrix. NOT a density functional theory calculation.
> Real DFT requires a separate sprint."

## Guarantees v0.1 preserves

- `compute_output_sha256` is **worker-independent** (depends only on
  `request_id` + `input_bundle_sha256` and the backend
  implementation). Sprint 5.8's replay invariant is preserved.
- Two workers using the **same backend** on the **same request**
  reach the **same `compute_output_sha256`**.
- Two workers using **different backends** on the same request will
  almost always produce **different** `compute_output_sha256` —
  not bit-coincident.
- The pending-reward report carries `backend_name`,
  `backend_version`, `backend_kind` so the web console can group
  rewards by backend without loading result files.
- The replay validator's accepted-validation report carries
  `accepted_backend_name` and `accepted_backend_version` so the
  governance gate can enforce backend consistency.

## How to activate an experimental backend manually

```
python3 scripts/trinity/useful_compute_worker.py \
  --mode local-dry-run \
  --request <TRINITY_USEFUL_COMPUTE_REQUEST_*.json> \
  --worker-id miner-toy-001 \
  --backend local_structure_relaxation_toy_v01 \
  --allow-experimental-backends \
  --out-dir /tmp/trinity-toy
```

Without `--allow-experimental-backends`, the worker rejects with a
clear error:

```
[useful_compute_worker] backend error: backend
'local_structure_relaxation_toy_v01' is experimental and requires
--allow-experimental-backends to use
```

The CLI also rejects backends that do not support the requested
`task_type` (e.g. asking `local_python_numeric_v01` to handle a
`dft` request).

## How the replay validator enforces backend consistency

After grouping results by `compute_output_sha256`, the validator
inspects the `(backend_name, backend_version)` pair of every
result in the agreeing group:

- If all matching results share the same pair → `status=accepted`,
  the validation report carries `accepted_backend_name` and
  `accepted_backend_version`.
- If two different backends coincide on a single
  `compute_output_sha256` (extraordinarily unlikely but possible)
  → `status=mismatch`, the rejection rows mention
  `backend_mismatch`, and `manual_review_required=true`.

This is defence in depth: even if a malicious miner forges the
output bytes of another backend, the explicit backend identity
field makes the divergence visible.

## How the governance gate enforces backend consistency

For every `accepted` validation the gate now also requires:

1. `accepted_backend_name` and `accepted_backend_version` are
   non-empty strings.
   - Otherwise → `governance_rejected_missing_backend`.
2. Each matching pending-reward report's
   `(backend_name, backend_version)` matches the validation's
   accepted pair.
   - Otherwise → `governance_rejected_backend_mismatch`.

These are recorded into `trinity_error_memory` with appropriate
causes (`bad_input` for missing, `overclaim_risk` for mismatch).

## Risks (read before scaling)

- **False scientific validation.** Sandbox toy backends can be
  mistaken for real science by users skimming the dashboard. The
  result file's `backend_disclaimer` is the load-bearing honesty
  surface. Do not strip it.
- **Energy.** Real backends in future sprints will dwarf the v0.1
  cost. Operators must opt in machine-by-machine.
- **Cross-machine divergence.** Real DFT will not bit-match across
  hardware without canonical rounding. The replay validator will
  need a tolerance bracket or a canonicalisation pass before any
  real backend can land.
- **Backend supply.** A single dominant backend producer (one
  team, one binary build) re-introduces centralisation. Future
  sprints must enforce backend provenance (signed manifests, build
  hashes).
- **Forward compatibility.** The reserved `real_backend` kind
  cannot ship until at least one accepted backend exists; until
  then the web console's `real_backend_rewards` counter must
  remain 0. Tests enforce this.
