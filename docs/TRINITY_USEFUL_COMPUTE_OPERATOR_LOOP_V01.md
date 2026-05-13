# Trinity Useful Compute — Operator Loop v0.1

Sprint **5.19**. The Operator Loop is the bridge between
*"we ran the pipeline once by hand"* and *"Trinity can repeat the
cycle on its own under a safety cage"*.

## What it automates

`scripts/trinity/useful_compute_operator_loop.py` drives the full
Useful Compute pipeline end-to-end, in order, through `importlib`
calls to its seven sibling scripts:

| # | Step | Script | Output kind |
| --- | --- | --- | --- |
| 1 | Task builder | `useful_compute_task_builder` | `trinity-useful-compute-request/v0.1` |
| 2 | Worker (×N) | `useful_compute_worker` | `useful-compute-result/v0.4` + `useful-compute-pending-reward/v0.3` |
| 3 | Replay validator | `useful_compute_replay_validator` | `trinity-useful-compute-validation/v0.2` |
| 4 | Governance gate | `useful_compute_governance_gate` | `trinity-useful-compute-governance-batch/v0.1` |
| 5 | Reward budget policy | `useful_compute_reward_budget_policy` | `trinity-useful-compute-reward-budget/v0.1` |
| 6 | Payment proposal | `useful_compute_payment_proposal` | `trinity-useful-compute-payment-proposal/v0.1` |
| 7 | Payment draft | `useful_compute_payment_draft` | `trinity-useful-compute-payment-draft/v0.2` (signing_mode = `unsigned_only` or `dry_sign_placeholder`) |

Each step's output is written to disk under the run directory, hashed
with sha256, and appended to a `SHA256SUMS.txt` manifest plus the
`operator_run.json` state file (schema
`trinity-useful-compute-operator-run/v0.1`).

## What it does NOT do

- It NEVER touches a wallet.
- It NEVER signs in any mode beyond the v0.1 placeholder
  (Sprint 5.16 dry-sign) — the real-sign mode of Sprint 5.17
  is **not** reachable from this loop. The loop's source code
  contains no `--real-sign` literal anywhere outside the
  rejection list, and no real-sign confirmation token.
- It NEVER broadcasts. Sprint 5.18's human broadcast guard is
  not invoked by the loop in any mode.
- It NEVER calls `sost-cli` directly. The downstream
  `useful_compute_payment_draft` module can drive
  `sost-cli createtx` when given `--real-sign`, but the loop
  always passes `--unsigned-only` (default) or `--dry-sign`,
  neither of which spawns a subprocess.
- It refuses to start if its argv contains any of:
  `--broadcast`, `--send`, `--payout-now`, `--auto-pay`,
  `--sign-now`, `--export-private-key`, `--wallet`,
  `--from-label`, `--from-address`, `--allow-wallet-access`,
  `--allow-broadcast`. Pre-argparse scan; exit code 2.

The schema `useful-compute-operator-run/v0.1` locks three flags as
`const`:

| Flag | Value |
| --- | --- |
| `allow_wallet_access` | `const: false` |
| `allow_broadcast` | `const: false` |
| `human_review_required` | `const: true` |

## Why we draw the line here

The first end-to-end on-chain payment
(`txid 787cda89…`, block 8512 — see `TRINITY_FIRST_USEFUL_COMPUTE_PAYMENT_PROOF_20260513T190442Z/`)
was performed **manually**: the operator ran each step, reviewed
each artifact, then ran the real-signer with an exact token, then
ran the broadcast guard with another exact token. Two human
inflection points: real-sign and broadcast. Sprint 5.19 keeps the
manual inflection points exactly where they were — it only
automates the read/transform/dry-run plumbing between them.

If you want Trinity to autopay, you have to:

1. Run the operator loop to produce a fresh `payment_draft` with
   `signing_mode = unsigned_only`.
2. **Manually** invoke the real-signer with the operator token
   from Sprint 5.17 against that draft.
3. **Manually** invoke the broadcast guard with the broadcast
   token from Sprint 5.18 against that signed draft.

Each manual step is logged with its own audit receipt; the operator
loop never has the credentials to perform either.

## Resumability

```
<out-dir>/
├── operator_run.json           ← state file
├── SHA256SUMS.txt              ← per-artifact hash manifest
├── request.json                ← step 1
├── worker_out/                 ← step 2 (N files)
├── validation/                 ← step 3
├── governance/                 ← step 4
├── budget/                     ← step 5
├── proposal/                   ← step 6
└── draft/                      ← step 7
```

To resume a run:

```
python3 scripts/trinity/useful_compute_operator_loop.py \
  --mode local-dry-run \
  --out-dir /tmp/oprun-001 \
  --require-confirmation-token I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP \
  --candidate-id op-candidate-001 \
  --input-bundle ./input_bundle.json \
  --worker-address-map ./address_map.json \
  --max-total-stocks 1000000 \
  --pool-balance-stocks 10000000 \
  --resume /tmp/oprun-001/operator_run.json
```

The loop re-reads `operator_run.json`, re-hashes every recorded
artifact, and either:

- **All hashes match** → no step is re-run, the loop exits 0.
- **Some steps are missing** → the loop continues from the first
  missing step, using earlier artifacts as inputs.
- **A hash mismatches** → hard error, exit code 2. Someone (or
  something) modified an artifact after it was recorded. The
  operator must investigate before the loop can run again.

`operator_run_id` is a `sha16` of canonical(`mode`, `pinned_time`,
`candidate_id`, `worker_id[]`, `pool_balance_stocks`,
`max_total_stocks`). Same inputs → same id → reproducible state
file (modulo `git_head`).

## Dry-run usage

```
python3 scripts/trinity/useful_compute_operator_loop.py \
  --mode local-dry-run \
  --out-dir /tmp/oprun-001 \
  --require-confirmation-token I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP \
  --candidate-id op-candidate-001 \
  --input-bundle ./input_bundle.json \
  --worker-address-map ./address_map.json \
  --max-total-stocks 1000000 \
  --pool-balance-stocks 10000000 \
  --pinned-time 2026-05-13T00:00:00+00:00 \
  --worker-id worker-A --worker-id worker-B \
  --draft-mode unsigned-only
```

## Future autonomy

What this sprint deliberately defers:

- **Scheduled runs.** The loop must be invoked manually each time.
  No cron, no daemon. Sprint 5.20 (proposed) introduces a guarded
  scheduler with explicit per-day caps and a kill switch.
- **Real signing.** Future autonomy sprints will not enable
  auto-real-sign; the inflection point stays human.
- **Cross-pipeline aggregation.** v0.1 runs one
  request → one set of workers → one proposal → one draft. Sprint
  5.21 (proposed) will allow batching multiple pipelines into a
  single audit run while keeping the same per-step checkpoint
  shape.

## Files added in Sprint 5.19

| File | Purpose |
| --- | --- |
| `scripts/trinity/useful_compute_operator_loop.py` | orchestrator |
| `schemas/trinity/useful_compute_operator_run.schema.json` | strict v0.1 schema for the state file |
| `tests/trinity/test_useful_compute_operator_loop.py` | 21 functional tests covering happy path + resume + tamper detection + cli gates + determinism + schema validation |
| `tests/trinity/test_useful_compute_operator_loop_schema.py` | schema-level invariants |
| `tests/trinity/test_operator_loop_safety.py` | static safety surface (no subprocess, no sost-cli, no real-sign, no wallet tokens, no dynamic exec) |
| `docs/TRINITY_USEFUL_COMPUTE_OPERATOR_LOOP_V01.md` | this document |
