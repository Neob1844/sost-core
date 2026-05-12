# Trinity Useful Compute Governance Gate v0.1

## What problem this solves

Sprint 5.8 added the cross-worker replay validator. An `accepted`
validation means two or more independent workers agreed on the same
`compute_output_sha256` for the same request. That is a strong
signal — but it is *not* an authorisation to pay.

Several gaps must close before any pending reward becomes real
stocks:

- **Per-worker reward divergence.** Two honest replicators can
  report different `pending_reward_stocks` values for the same task
  if their local benchmark differs. Without a policy, the protocol
  has no answer to "which one do we trust?".
- **Reward / validation drift.** A reward file might exist without a
  matching validation, or vice versa. A duplicate reward file could
  let a worker double-claim.
- **Manual review surface.** Even when validations are clean,
  Trinity must still let a human reviewer hold the batch before
  payment. v0.9 deliberately makes that the only path.
- **No automatic payment in v0.9.** A separate, governance-signed
  payment sprint is still required.

The governance gate v0.1 is the smallest piece of code that turns
"accepted validations + pending rewards" into a **deterministic,
review-only batch** that a human can read, sign, and feed into a
future payment sprint.

## How a governance batch is built

`scripts/trinity/useful_compute_governance_gate.py`:

1. Scans `--validations-dir` for
   `TRINITY_USEFUL_COMPUTE_VALIDATION_*.json`.
2. Scans `--rewards-dir` for
   `TRINITY_USEFUL_COMPUTE_PENDING_REWARD_*.json`. The
   `worker_result_id` is extracted from the canonical file name.
3. Accepts a validation only when ALL of these hold:
   - `validation_status == "accepted"`
   - `manual_review_required == false`
   - `accepted_compute_output_sha256` is a 64-hex string
   - `unique_workers >= min_workers`
   - `safety_status` carries all six v0.8 flags as `true`
4. For every `worker_result_id` listed in `matching_result_ids`, the
   gate requires a matching pending-reward file for the SAME
   `request_id`. Missing → reject. Duplicate (two files for the
   same `(rid, wrid)`) → reject. A pending reward for a
   `worker_result_id` NOT in `matching_result_ids` → reject as
   `governance_rejected_extra_reward`.
5. Under `--policy conservative`, the gate sets
   `approved_pending_reward_stocks = min(pending_reward_stocks)` over
   the matching workers.
6. Emits a deterministic batch file
   `TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_<batch_id>.json` plus a
   human-readable
   `TRINITY_USEFUL_COMPUTE_GOVERNANCE_SUMMARY.md`.

The `batch_id` is `gov-<16-hex>` derived from the canonical-JSON of
the (sorted) approved + rejected items, the reviewer id, the policy
and the pinned timestamp. Two runs on the same inputs produce the
same batch_id and identical bytes on disk.

## Why `conservative = min(pending rewards)`

Two honest workers can submit different `pending_reward_stocks`
because:

- their local benchmarks differ
- their declared `verified_compute_seconds` differs slightly
- their difficulty tier was the same but their reward model run had
  different `manual_review` outcomes that the model penalised

Under the *conservative* policy v0.1 picks the **lowest** of the
matching pending values. This is intentionally a floor:

- No worker is ever promised more than the cheapest honest
  replicator computed for them.
- Inflation attacks (one worker tries to print 10× stocks by
  claiming a wild benchmark) cannot reach payment without a second
  worker corroborating the same number.
- Honest workers slightly losing out is acceptable in v0.1; once a
  smarter policy (median, trimmed mean, manual override) is needed,
  it can be added as a new `--policy` value without changing the
  schema.

## What is left for the payment sprint

`safety_status.requires_separate_payment_sprint = true` is the
load-bearing flag for this gate. The next sprint must implement,
behind explicit governance sign-off:

- Aggregation of an approved batch into a payable list.
- A signed payment proposal (the signing surface must NOT live in
  Trinity itself; it goes through the normal SOST wallet flow).
- A registry entry that records: batch_id, total stocks, list of
  worker_id → stocks, payment proof, governance signer.
- A way to *unwind* a payment if a later audit invalidates a result
  the gate had accepted.

v0.9 deliberately ships none of those. Trinity stops at the gate.

## CLI

```
python3 scripts/trinity/useful_compute_governance_gate.py \
  --mode local-dry-run \
  --validations-dir /tmp/uc-val \
  --rewards-dir /tmp/uc-test \
  --out-dir /tmp/uc-gov \
  --reviewer-id reviewer-local-001 \
  --policy conservative
```

The CLI explicitly rejects `--broadcast`, `--payout`, `--send`,
`--wallet`, `--network`. The only accepted `--mode` is
`local-dry-run`.

## Outputs

- `TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_<batch_id>.json`
- `TRINITY_USEFUL_COMPUTE_GOVERNANCE_SUMMARY.md`

If `--error-memory-ledger <path>` is supplied, every rejection is
appended as a lesson into the existing Trinity error memory
ledger. Causes used:

| Rejection                                | Lesson cause            |
|------------------------------------------|-------------------------|
| `governance_rejected_mismatch`           | `overclaim_risk`        |
| `governance_rejected_manual_review`      | `overclaim_risk`        |
| `governance_rejected_insufficient_workers` | `insufficient_evidence` |
| `governance_rejected_missing_reward`     | `bad_input`             |
| `governance_rejected_duplicate_reward`   | `duplicate_candidate`   |
| `governance_rejected_extra_reward`       | `duplicate_candidate`   |
| `governance_rejected_invalid_structure`  | `bad_input`             |

## Risks (read before scaling)

- **Collusion.** Two workers controlled by the same operator can
  agree on a fabricated `compute_output_sha256` AND on an inflated
  pending reward. The min policy still picks the inflated number if
  both submissions agree. Mitigation: require third-party submitters
  from different operators; human review remains required.
- **Inflated benchmarks within caps.** The reward model in v0.7 caps
  per-task stocks and per-task seconds. The gate respects those
  caps but does not re-validate them. A malicious operator could
  saturate to the cap repeatedly. Mitigation: throttling and
  reputation, both outside the v0.1 gate.
- **Reviewer compromise.** The reviewer_id is a free-form string
  with no signature in v0.1. A future sprint must replace it with a
  governance-signed identity.
- **Energy cost.** Approved batches grow as Useful Compute scales.
  The gate is cheap; the network effect is not. Operators must opt
  in.
- **Human review fatigue.** A high approved_count tempts reviewers
  to rubber-stamp. Mitigation: keep batches small, schedule a
  separate review cadence.

## What the gate does NOT do

- does NOT pay
- does NOT sign, broadcast, send, or activate any transaction
- does NOT touch any wallet, private key, or seed phrase
- does NOT make any network call (HTTP, socket, RPC, beacon)
- does NOT spawn subprocesses
- does NOT register anything on-chain
- does NOT modify consensus, tx_validation, tx_signer or transaction
  format
- does NOT decide that a result is *scientifically valid*; it only
  decides that the validation report passes the v0.1 acceptance
  gates
