# Trinity Useful Compute Benchmark Ledger v0.1

## Why elapsed_seconds alone is not enough

Until Sprint 5.12 the reward model trusted three caller-supplied
inputs:

- `verified_compute_seconds` — how long the worker says it ran
- `benchmark_score` — a free-form `0.1..10` multiplier
- `difficulty_class` — picked from the request manifest

Two unsupervised inputs (`verified_compute_seconds` and
`benchmark_score`) are enough to inflate a reward by orders of
magnitude. A malicious worker can pin them at the upper cap and
report "60 minutes at 10x benchmark" without doing any work.

Sprint 5.12 added the backend metadata layer (so replay validator
and governance gate can enforce backend consistency across workers),
but reward calculation was still based on whatever the caller said.

Sprint 5.13 closes this by introducing a **benchmark ledger** that
makes the work itself measurable on the same machine, with the same
backend, in a deterministic way the network can audit later.

## What the benchmark ledger measures

`scripts/trinity/useful_compute_benchmark.py` runs a deterministic
micro-benchmark for one (backend, task_type) pair on the local
machine. The emitted report
(`TRINITY_USEFUL_COMPUTE_BENCHMARK_<benchmark_id>.json`, schema
`trinity-useful-compute-benchmark/v0.1`) carries:

| Field | Meaning | Deterministic? |
|---|---|---|
| `backend_name` / `backend_version` / `backend_kind` | which backend was benchmarked | yes |
| `task_type` | which task type the iterations exercised | yes |
| `iterations` | how many backend invocations were chained | yes |
| `operations_count` | counts iterations 1:1 | yes |
| `deterministic_work_units` | sum of canonical-output byte lengths across iterations | yes |
| `normalized_work_score` | `work_units / iterations / 100`, clamped to `[0.1, 10.0]` | yes |
| `wall_time_seconds` | real wall-clock elapsed | **no** |
| `machine_fingerprint_hash` | sha16 of `platform.platform() \| machine \| processor \| python_impl \| python_version` | yes per machine |
| `worker_id_hash` | sha16 of the worker_id (never stored verbatim) | yes per worker_id |
| `benchmark_id` | sha16 of canonical(backend, task_type, iterations, work_units) | yes — same across machines |
| `safety_status` | `{no_wallet_access, no_private_keys, no_network_required, no_automatic_payout, benchmark_only}` all `const: true` | locked |

Two honest workers running the same `--backend` + `--task-type` +
`--iterations` produce the **same benchmark_id**, **same work_units**
and **same normalized_work_score**. They produce different
`wall_time_seconds` (real time varies) and different
`worker_id_hash` / `machine_fingerprint_hash` (those are intentional
per-worker / per-machine anchors).

## What the benchmark does NOT measure

- It does NOT prove the backend produced correct output.
- It does NOT prove the worker used a CPU rather than a stored
  table.
- It does NOT prove the result was scientifically useful.
- It does NOT prove the worker honestly executed the request the
  benchmark refers to.

The benchmark ledger is a comparable signal of "how much
deterministic work this backend does for N iterations", nothing
more.

## How the reward model uses it

`useful_compute_reward_model.compute_pending_reward()` gains four
new keyword arguments in v0.13, all defaulted to `None` so existing
callers keep their Sprint 5.7 behaviour:

```python
compute_pending_reward(
    ...,
    benchmark_report=None,         # full report dict or None
    normalized_work_score=None,    # convenience scalar override
    backend_kind=None,             # placeholder|sandbox_toy|real_backend
    backend_runtime_seconds=None,  # carried for diagnostics only
)
```

When at least one of `benchmark_report` or `normalized_work_score`
is supplied, the model applies a backend-kind-aware policy AFTER
its existing per-task cap:

| backend_kind | Policy | manual_review |
|---|---|---|
| `placeholder` | reward is overridden to **0** | preserved |
| `sandbox_toy` | reward kept, **manual_review forced True** | True |
| `real_backend` | reserved; reward kept but **manual_review forced True** | True |
| (unknown) | reward kept, manual_review forced True | True |

Without a benchmark, the model reverts to the Sprint 5.7 behaviour
and writes nothing into the reason about benchmark policy.

## Worker integration

```
python3 scripts/trinity/useful_compute_worker.py \
  --mode local-dry-run \
  --request <request.json> \
  --worker-id <id> \
  --out-dir <dir> \
  --backend <backend_name> \
  --allow-experimental-backends \
  --benchmark-report <benchmark.json>
```

When `--benchmark-report` is supplied:

1. The worker validates the file against the v0.1 benchmark schema.
2. The result file (v0.4) carries `benchmark_id`,
   `normalized_work_score`, and `benchmark_source="report"`.
3. The pending-reward file (v0.3) carries the same three fields.
4. The reward model applies the policy table above.

When `--benchmark-report` is NOT supplied:

1. Result + reward carry `benchmark_id=null`,
   `normalized_work_score=null`, and `benchmark_source="none"`.
2. The reward model behaves exactly as in Sprint 5.7.

## How the web console surfaces this

`website/trinity-useful-compute.html` (Miner Compute Console,
badge bumped to v0.7):

- The per-task table grows two columns: `benchmark` (short id) and
  `work_score`.
- A new "rewards by benchmark source" grid shows three counters:
  `unbenchmarked_rewards`, `benchmarked_rewards` and
  `experimental_rewards` (sandbox_toy + report).
- A visible disclaimer: "Benchmark score is not proof of useful
  scientific output. Experimental rewards (sandbox_toy backends
  with a benchmark attached) require manual review before any
  payment."
- The exported summary JSON now includes `benchmark_source_counts`.

## Schema bumps

| Schema | Before 5.13 | After 5.13 |
|---|---|---|
| `trinity-useful-compute-result` | v0.3 | **v0.4** (adds `benchmark_id`, `normalized_work_score`, `benchmark_source`) |
| `trinity-useful-compute-pending-reward` | v0.2 | **v0.3** (adds the same three fields) |
| `trinity-useful-compute-benchmark` | (new) | **v0.1** |
| `trinity-useful-compute-validation` | v0.2 | v0.2 (unchanged) |
| `trinity-useful-compute-governance-batch` | v0.1 | v0.1 (unchanged) |

The replay validator's structural check now requires v0.4 results
and rejects v0.3. The governance gate's reward check now requires
v0.3 and rejects v0.2. Sprint 5.13 is a **breaking schema bump**
across these two parsers.

## Risks

- **Gaming.** A worker can run the benchmark once and then submit
  forever. The normalized_work_score does not depend on time — only
  on output bytes — so a static benchmark cannot inflate the score.
  But a benchmark is per `(backend, task_type, iterations)`, NOT per
  actual request, so a worker could in principle benchmark cheaply
  and claim the same score for an expensive task. Mitigation:
  governance gate still enforces backend consistency cross-worker,
  and payments still require human review.
- **Hardware spoofing.** `machine_fingerprint_hash` is a sha16 of
  `platform.*` output; a coordinated attacker can spoof it. Use it
  for visibility, not for security.
- **Benchmark inflation.** Sandbox toy backends can be tweaked to
  produce larger outputs and therefore higher work_units. The
  toy backends are versioned (`backend_version`); any change is
  visible in the benchmark_id and replay validator.
- **Colusion.** Two workers can agree to submit the same benchmark
  + same fake result. Cross-worker replay catches the result
  divergence but only when the benchmarks are honest. The governance
  gate's `requires_separate_payment_sprint=true` flag remains the
  final defence.
- **Energy.** v0.1 benchmarks run 1000s of iterations of stdlib-only
  code; cheap. Real-backend benchmarks (future sprints) will be
  expensive.
- **Manual review fatigue.** sandbox_toy + benchmark always forces
  `manual_review=True`. As volume grows, reviewers will be tempted
  to rubber-stamp. Keep batches small, schedule reviews.

## What is NOT in this sprint

- Real DFT / quantum / simulation back-ends remain disabled.
- No on-chain registration, no automatic payout, no broadcasts.
- The benchmark report does not influence cross-worker replay; the
  validator still groups by `compute_output_sha256` and per-backend
  agreement.
- No web execution of the benchmark — the user runs the CLI on
  their machine and the console reads the artefacts.

## Reference run

```
python3 scripts/trinity/useful_compute_benchmark.py \
  --mode local-dry-run \
  --backend local_python_numeric_v01 \
  --task-type scoring \
  --iterations 1000 \
  --worker-id miner-benchmark-001 \
  --out-dir /tmp/trinity-benchmark-test
```

Emits a `TRINITY_USEFUL_COMPUTE_BENCHMARK_bench-<16hex>.json` with:

- `benchmark_id = bench-b3be34240c845d5d` (stable across machines
  for these inputs)
- `deterministic_work_units = 418542`
- `normalized_work_score = 4.18542`
- `wall_time_seconds ≈ varies per machine`

Feeding the same benchmark into the worker with `--backend
local_python_numeric_v01 --allow-experimental-backends
--benchmark-report <path>` yields:

- pending_reward_stocks = capped at max
- reason = "reward hit max_reward_stocks cap; sandbox_toy backend
  benchmark; flagged experimental for manual review"
- requires_manual_review = **True**

Feeding the same benchmark with `--backend placeholder` yields:

- pending_reward_stocks = **0**
- reason = "placeholder backend benchmark; reward zeroed by policy"
- requires_manual_review = False (zero is unambiguous, no review
  needed)
