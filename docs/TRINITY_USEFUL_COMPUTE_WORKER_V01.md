# Trinity Useful Compute Worker v0.1

## What it does

`scripts/trinity/useful_compute_worker.py` converts a Trinity dry-run
request into the first real local artefact a miner can produce:

1. Reads a `trinity-useful-compute-request/v0.1` manifest from disk.
2. Validates it strictly against the request schema (every field,
   every type, every range, every enum).
3. If the caller supplies `--input-bundle`, verifies its SHA-256
   matches the `input_bundle_sha256` field of the manifest.
4. Executes a **deterministic placeholder** for the requested
   `task_type` (`dft`, `quantum`, `structure_relaxation`, `scoring`,
   `simulation`, `other`). Placeholders are clearly labelled as
   placeholders — they are not real DFT, not real quantum, not real
   physics.
5. Emits a `trinity-useful-compute-result/v0.1` JSON file.
6. Emits a `trinity-useful-compute-pending-reward/v0.1` JSON file
   computed via the existing reward model.

The placeholder output is byte-identical across runs for the same
`(request_id, worker_id, input_bundle_sha256)` tuple, so cross-worker
replay validation is possible without any back-end.

## What it does NOT do

This worker:

- does NOT pay
- does NOT sign, broadcast, send, or activate any transaction
- does NOT touch any wallet, private key, or seed phrase
- does NOT make any network call (no HTTP, no socket, no RPC)
- does NOT spawn subprocesses
- does NOT run real DFT / quantum / simulation backends in v0.1
- does NOT register anything on-chain
- does NOT modify consensus, tx_validation, tx_signer or transaction
  format

The CLI explicitly rejects `--broadcast`, `--payout`, `--send`,
`--network`, `--wallet` and `--worker-id-from-wallet`. The only
accepted `--mode` is `local-dry-run`.

## Miner flow, step by step

1. Pick a request to work on. Trinity's orchestrator emits these
   files:
   ```
   TRINITY_USEFUL_COMPUTE_REQUESTS.json
   TRINITY_USEFUL_COMPUTE_REQUEST_<request_id>.json
   ```
2. Run the worker locally:
   ```
   python3 scripts/trinity/useful_compute_worker.py \
     --mode local-dry-run \
     --request TRINITY_USEFUL_COMPUTE_REQUEST_<id>.json \
     --worker-id miner-local-001 \
     --out-dir /tmp/trinity-uc-worker-test
   ```
3. The worker writes:
   ```
   TRINITY_USEFUL_COMPUTE_RESULT_<id>.json
   TRINITY_USEFUL_COMPUTE_PENDING_REWARD_<id>.json
   ```
4. Open `website/trinity-useful-compute.html` in a browser. The page
   never connects to the network; it only parses the JSON files you
   load. Step 1 → request, Step 2 → CLI command, Step 3 → result,
   Step 4 → pending reward.
5. The reward is **pending**. v0.1 does not pay it.

## How pending rewards in stocks are measured

The worker delegates to
`scripts/trinity/useful_compute_reward_model.compute_pending_reward`,
which is the same deterministic model the orchestrator uses.

Hard rules baked into it:

- `result_validated=false` → 0 stocks
- `duplicate_result=true` → 0 stocks (default duplicate factor is 0)
- benchmark below the manual-review floor → manual review flag
- normalised seconds capped (anti-DoS)
- benchmark capped (anti-gaming)
- reward capped at the request's `max_reward_stocks`

1 SOST = 100,000,000 stocks.

## Why there is no automatic payment yet

Two reasons, neither of them solvable inside this sprint:

1. **Verification.** v0.1 does not yet implement cross-worker
   replay. Until two independent workers can replay the same task
   and agree on `output_sha256`, no payout is safe.
2. **Governance.** Any move from `pending_reward_stocks` into actual
   stock issuance must go through an explicit governance step. v0.1
   deliberately refuses to ship that step.

## Duplicate detection

If you pass `--seen-results <path>`, the worker treats it as an
append-only list of previously observed `output_sha256` values. If
the new output hashes to a SHA already in the list, the worker sets
`duplicate_result=true` and the reward report comes out as `0`.

This is local-only and intentionally naive in v0.1. A network-wide
duplicate filter is a separate sprint.

## Risks

- **Gaming.** A miner can claim arbitrary benchmarks. The reward
  model caps normalised seconds and benchmark, flags suspicious
  values for manual review, but a determined attacker can still
  inflate within the caps. This is acceptable because v0.1 does not
  pay.
- **False results.** Without cross-worker replay, a malicious miner
  can submit any output. v0.1 forbids automatic payout for this
  reason.
- **Duplicates.** A miner could re-submit identical work and claim
  again. The local `--seen-results` list mitigates this for a single
  operator; a network-wide solution is needed before any actual
  payout.
- **Energy cost.** The placeholder is cheap. Real DFT or simulation
  back-ends will be expensive; operators must opt in explicitly.
- **Human review.** Every result still needs a human reviewer
  before being treated as scientifically meaningful.

## Outputs (canonical JSON, sort_keys, no trailing newline)

### `TRINITY_USEFUL_COMPUTE_RESULT_<id>.json`

```
{
  "schema": "trinity-useful-compute-result/v0.1",
  "request_id": "uc-...",
  "worker_id": "miner-local-001",
  "task_type": "scoring",
  "input_bundle_sha256": "<64-hex>",
  "output_sha256":       "<64-hex>",
  "started_at":          "...",
  "finished_at":         "...",
  "elapsed_seconds":     300.0,
  "result_validated":    true,
  "duplicate_result":    false,
  "deterministic_result_id": "<16-hex>",
  "public_summary":      "placeholder scoring result for ...",
  "safety_status": {
    "no_wallet_access":       true,
    "no_private_keys":        true,
    "no_automatic_payout":    true,
    "no_network_required":    true,
    "manual_review_required": true
  }
}
```

### `TRINITY_USEFUL_COMPUTE_PENDING_REWARD_<id>.json`

```
{
  "schema": "trinity-useful-compute-pending-reward/v0.1",
  "request_id": "uc-...",
  "worker_id": "miner-local-001",
  "pending_reward_stocks": 45000,
  "reason": "standard reward",
  "requires_manual_review": false,
  "reward_model_schema": "trinity-useful-compute-reward/v0.1",
  "reward_model_deterministic_id": "<16-hex>",
  "safety_status": {
    "no_wallet_access":       true,
    "no_private_keys":        true,
    "no_automatic_payout":    true,
    "no_network_required":    true,
    "manual_review_required": true
  }
}
```

## What is still missing before production

- Real back-ends per `task_type` (DFT, quantum, simulation) behind
  explicit feature flags.
- Network-wide duplicate detection.
- Cross-worker replay verifier that signs off `result_validated`
  based on agreement of at least two independent workers.
- Governance gate that promotes `pending_reward_stocks` into actual
  stocks.
- A submission protocol that lets miners post results without an
  on-chain transaction, then settle later in a batch.
