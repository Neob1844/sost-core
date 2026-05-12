# Trinity Useful Compute Payment Proposal v0.1

## What a payment proposal is (and is not)

A **payment proposal** is the smallest possible bridge between
"governance approved a reward batch" (Sprint 5.9) and "a SOST
transaction was broadcast" (a future sprint that touches the
wallet). It lists, item by item:

- which `request_id` triggered the reward,
- which `worker_result_id`s are being paid,
- which `payout_address` each pile of stocks would go to,
- how many stocks, plus the same number in SOST units,
- which `budget_id` and `governance_batch_id` justify it,
- which stocks remain deferred or unresolved,
- a capsule summary text ready to be anchored later (NOT yet
  anchored).

A payment proposal is **not** a transaction. It does not sign, it
does not call any RPC, it does not move stocks, and it does not
touch any wallet or key store. The CLI explicitly rejects
`--broadcast`, `--payout`, `--send`, `--wallet`, `--network`,
`--sign`. The only accepted `--mode` is `local-dry-run`.

The proposal's `safety_status` carries seven `const: true` flags
locked by the schema: `no_private_keys`, `no_wallet_access`,
`no_signature`, `no_broadcast`, `proposal_only`,
`requires_manual_signing`, `requires_separate_broadcast`.

## Why this layer exists

Even with the budget policy in place, jumping straight from
"budget allocated 31,500 stocks for request X" to "broadcast a SOST
transaction that pays sost1...abc 31,500 stocks" is too fast. Two
classes of bug are easy to hit if the bridge is skipped:

1. **Address mapping bugs.** A wrong, stale, or duplicate address
   in the operator's wallet config would send stocks to someone
   else.
2. **Audit gap.** Without a stand-alone artefact between budget
   and tx, no reviewer can compare side-by-side what was decided
   vs. what was sent.

The payment proposal makes this visible. It is a single JSON file
the operator can read, diff against the budget, and only THEN sign
in a separate, governance-controlled sprint.

## How budget → proposal works

`scripts/trinity/useful_compute_payment_proposal.py`:

1. Loads the budget plan (`trinity-useful-compute-reward-budget/v0.1`).
2. Loads the worker address map
   (`trinity-worker-address-map/v0.1`).
3. Optionally loads a `--rewards-dir` directory; for every pending
   reward file in it, computes
   `worker_id_hash = sha16(worker_id)` on the fly so each
   `worker_result_id` can be linked back to a payout address.
4. For each `allocation_item` in the budget:
   - **rejected** → copied to `rejected_items`.
   - **deferred** → copied to `deferred_items`.
   - **capped or approved** → the `primary_workers_share_stocks`
     (70% of the allocated total) is divided evenly among the
     `worker_result_ids`. Each share is then routed to its
     `payout_address` via the address map. Shares whose address
     cannot be resolved land in `unresolved_items` (not rejected
     — they can be fixed by editing the address map and rerunning).
5. Workers sharing the same payout_address are merged into one
   `payable_item` per `(request_id, payout_address)` pair.

The 20% replay_validator_reserve and 10% governance_review_reserve
from the budget remain held back and do NOT appear in the
proposal. They are paid through different paths in future sprints.

## The worker address map

Schema `trinity-worker-address-map/v0.1`:

```
{
  "schema": "trinity-worker-address-map/v0.1",
  "workers": [
    {
      "worker_id_hash": "<16-hex>",
      "payout_address": "sost1...",
      "label": "optional human label"
    }
  ]
}
```

Each row binds one worker identity (via the sha16 of the plain
`worker_id` the worker used) to one SOST payout address.

`scripts/trinity/useful_compute_worker_address_map.py` has two
subcommands:

- `create-template` — writes a JSON template with placeholder
  entries the operator MUST replace before use.
- `validate` — checks the schema string, sost1 prefix, basic
  bech32 charset (no full checksum check in v0.1), uniqueness of
  `worker_id_hash` and `payout_address`.

The helper NEVER generates addresses, NEVER touches a wallet, and
NEVER signs.

## Determinism

`proposal_id = "prop-" + sha16(canonical(pinned_time +
source_budget_id + payable_items + unresolved_items +
deferred_items + rejected_items))`.

Two runs with the same inputs produce byte-identical proposals.

## Capsule summary

Each proposal carries a `capsule_summary` block:

```
{
  "template": "useful_compute_reward_batch_v1",
  "text": "Trinity Useful Compute reward proposal <id>; payable=...",
  "referenced_files": {
    "budget_id": "bud-...",
    "governance_batch_ids": ["gov-..."],
    "validation_ids": []
  }
}
```

The capsule is **not published** in v0.1. A future Proof Registry
sprint will take this summary and anchor it on SOST via a capsule
transaction. For now it just makes the audit chain visible:
proposal → budget → governance batch → (validations).

## Risks

- **Wrong address map.** The biggest risk in v0.1. If a worker's
  `worker_id_hash` maps to someone else's address, the proposal
  will payably send stocks to the wrong place. Mitigation: the
  operator must reconcile the address map by hand BEFORE running
  the proposal; the human review step in the future payment sprint
  must double-check before signing.
- **Sybil workers.** A single operator can register multiple
  `worker_id` values and collect them all under one address. The
  proposal does not prevent this. Future sprints must add a
  worker-identity attestation step.
- **Manual mistakes.** Anyone with the proposal JSON can hand-edit
  it. The signing sprint must verify the proposal hash against an
  independently-loaded budget + address map before broadcasting.
- **Stale state.** A proposal generated today may be obsolete next
  week (new deferrals, new budgets). The signing sprint must check
  that the source budget is still current.
- **Charset gaps.** The v0.1 address regex enforces the bech32
  charset but does NOT verify the bech32 checksum. A typo of "1"
  vs "l" inside an address slips through. Future sprints will
  delegate to the wallet code for full bech32 verification.

## CLI reference

```
python3 scripts/trinity/useful_compute_payment_proposal.py \
  --mode local-dry-run \
  --budget-plan /tmp/trinity-budget-test/TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_<id>.json \
  --worker-address-map /tmp/trinity-address-map.json \
  --rewards-dir /tmp/trinity-daemon-console/work/rewards \
  --out-dir /tmp/trinity-payment-proposal \
  --pinned-time 2026-05-12T00:00:00+00:00
```

Helper:

```
python3 scripts/trinity/useful_compute_worker_address_map.py \
  create-template --out /tmp/trinity-address-map.json --entries 3

python3 scripts/trinity/useful_compute_worker_address_map.py \
  validate --path /tmp/trinity-address-map.json
```

Both reject every payment-style flag (`--broadcast`, `--payout`,
`--send`, `--wallet`, `--network`, `--sign`). Both only accept
`local-dry-run` mode where applicable.

## Reference run

With three honest workers (alice / bob / carol) on the same
request, address map mapping each to a distinct
`sost1...`:

```
budget        bud-01c91797a49c5985
allocated     135,000  (45,000 per worker × 3)
proposal      prop-4cae757c8b9d399f
payable       94,500   (70% primary share)
deferred      0
unresolved    0
payable rows  3
  alice → 31,500 = 0.000315 SOST
  bob   → 31,500 = 0.000315 SOST
  carol → 31,500 = 0.000315 SOST
capsule       "Trinity Useful Compute reward proposal
               prop-4cae757c8b9d399f; payable=94500 stocks; ..."
```

The remaining 40,500 stocks (`135,000 - 94,500`) stay in the
budget plan as `replay_validator_reserve` + `governance_review_reserve`
and are routed through different sprints.

## What this sprint does NOT do

- No transaction is signed.
- No transaction is broadcast.
- No RPC is called.
- No wallet, no private key, no recovery phrase.
- No consensus / tx_validation / tx_signer change.
- No automatic payment scheduling.
- No on-chain capsule anchor (the summary is prepared, not
  published).

The next sprint will introduce a **governance-signed payment**
artefact that takes one or more payment proposals plus a human
signature and produces a single signed-tx envelope for a separate
broadcast step.
