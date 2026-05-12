# Trinity Useful Compute Cross-Worker Replay Validator v0.1

## Why a single worker is not enough

A single Useful Compute submission cannot be trusted. The worker:

- knows the request manifest in full and can fabricate any output
  that *looks* well-formed
- can spend zero CPU and still claim a benchmark
- can replay an old result and present it as new
- has no incentive to refuse a misconfigured task

Even with a clean reward model and the strict result schema from
Sprint 5.7, an adversarial worker can claim
`pending_reward_stocks > 0` for nonsense. v0.7 of Trinity is
deliberately built so this never converts into actual stocks, but
the protocol still needs a way to distinguish honest replicable work
from a unilateral claim.

## Why two independent workers raise the bar

If two unrelated workers run the same task on the same input and
arrive at the **same** `compute_output_sha256`, several conditions
must have held simultaneously:

- both workers actually executed the task (or both colluded
  perfectly, which is harder than acting alone)
- both produced deterministic output bytes (any non-deterministic
  step in their implementation would have produced different hashes)
- neither tampered with the result, or both tampered identically

This is not proof. Two workers can still lie if they collude. But it
is an order of magnitude harder than a single rogue submission. The
replay validator implements that bar: it only declares `accepted`
when at least `--min-workers` independent submissions agree, and it
still leaves the payment gate to governance.

## v0.2 schema split that makes replay possible

Sprint 5.7 had a flaw: the worker's deterministic seed included the
worker_id, so two honest workers necessarily produced different
`output_sha256` values. v0.8 of the worker (this sprint, schema v0.2)
fixes that by splitting two distinct ids:

- **`compute_output_sha256`** — SHA-256 of the canonical-JSON of the
  pure technical task output. Depends only on `request_id` and
  `input_bundle_sha256`. Two honest workers MUST get the same value.
- **`worker_result_id`** — 16-hex id binding (request_id, worker_id,
  compute_output_sha256, elapsed_seconds). Depends on worker_id and
  is unique per submission. This is how the network identifies a
  specific worker's submission for the same task.

The validator groups by `compute_output_sha256` and uses
`worker_result_id` as the per-submission key in its report.

## Decision matrix

| Outcome                  | Meaning                                                   |
|--------------------------|-----------------------------------------------------------|
| `accepted`               | ≥ `min_workers` agree on the same `compute_output_sha256` and no other group exists |
| `mismatch`               | Two or more distinct `compute_output_sha256` groups exist |
| `insufficient_workers`   | Fewer unique workers than `min_workers`                   |
| `rejected`               | Every loaded result was structurally invalid               |
| `manual_review`          | Anomalies that warrant human inspection                    |

`manual_review_required=true` is set in any of: `mismatch`,
self-reported `result_validated=false`, duplicate worker_id
detection.

Even `accepted` does NOT pay. The `safety_status` of the validation
report explicitly carries `governance_required_before_payment=true`.

## Outputs

- `TRINITY_USEFUL_COMPUTE_VALIDATION_<request_id>.json` — the report
- `TRINITY_USEFUL_COMPUTE_VALIDATION_SUMMARY.md` — human-readable
  summary

If `--error-memory-ledger <path>` is supplied, the validator appends
lessons to that ledger so the orchestrator's planner can use them
in later runs:

- `mismatch` → cause `overclaim_risk`
- `insufficient_workers` → cause `insufficient_evidence`
- duplicate-worker submissions → cause `duplicate_candidate`

## Command

```
python3 scripts/trinity/useful_compute_replay_validator.py \
  --mode local-dry-run \
  --request TRINITY_USEFUL_COMPUTE_REQUEST_<id>.json \
  --results-dir <dir-with-result-files> \
  --out-dir /tmp/trinity-uc-validation \
  --min-workers 2
```

The validator scans `--results-dir` for files matching
`TRINITY_USEFUL_COMPUTE_RESULT_<request_id>_*.json`. Every such file
must conform to the v0.2 result schema or it lands in
`rejected_result_ids` with a clear reason.

## What it does NOT do

- does NOT pay
- does NOT sign, broadcast, send, or activate any transaction
- does NOT touch any wallet, private key, or seed phrase
- does NOT make any network call (HTTP, socket, RPC, beacon)
- does NOT spawn subprocesses
- does NOT register anything on-chain
- does NOT modify consensus, tx_validation, tx_signer or transaction
  format
- does NOT decide on its own that a task is "scientifically valid";
  it only declares agreement on bytes

## How this connects to a governance gate

A separate sprint must implement the governance step that:

1. Reads a batch of `accepted` validation reports.
2. Confirms `manual_review_required=false` on each.
3. Confirms no overlapping anomaly flag in `trinity_error_memory`.
4. Aggregates pending rewards across the batch.
5. Issues a single signed proposal that humans sign off on, BEFORE
   any stocks are actually moved.

v0.8 deliberately does not ship that gate, so there is no path from
`accepted` to on-chain reward inside this sprint's surface.

## Limitations

- **Collusion.** Two workers controlled by the same operator can
  agree on a fabricated output. Mitigation: cross-validate against
  third-party submissions from different operators; human review
  remains required.
- **Coordinated network attack.** A coalition large enough to
  outnumber honest workers can force `accepted` on bad outputs.
  Mitigation: governance gate, batch sampling.
- **Hardware non-determinism.** Real DFT or quantum back-ends can
  produce floating-point variations even on the same input. v0.8
  uses deterministic placeholders for this reason; real back-ends
  will need a tolerance bracket and a canonical rounding policy.
- **Time skew.** `elapsed_seconds` is pinned to the request's
  estimated cost in v0.8 to keep cross-worker matching trivial. A
  later sprint must introduce a real measurement that survives
  cross-worker comparison.
- **Replay of old work.** A miner could resubmit an old result file
  unchanged. The local seen-set in the worker, and the duplicate-
  worker detection in the validator, mitigate this for honest
  operators; a network-wide nonce tracker is a separate sprint.
