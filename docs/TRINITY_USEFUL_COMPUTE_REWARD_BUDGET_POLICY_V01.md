# Trinity Useful Compute Reward Budget Policy v0.1

## Why governance-approved is not enough

Sprint 5.9 introduced the governance gate: every accepted replay
validation can produce an approved item with
`approved_pending_reward_stocks`. Sprint 5.13 introduced the
benchmark ledger so the reward model can compute that number
honestly. Both are necessary but **not sufficient** before any
payment sprint touches a wallet.

What is still missing is a **global economic ceiling**:

- Approved batches grow over time. Without a cap, a busy week can
  drain the pool.
- Many small approved items can sum to a very large total.
- A single misbehaving day (e.g. an upstream bug that produces lots
  of accepted validations) can authorise far more stocks than the
  treasury can afford.
- An inflated benchmark or a saturated job can spike per-worker
  reward beyond what the policy intends.

Sprint 5.14 adds the **reward budget policy** that sits between
governance approval and any future payment. The policy is the brake
the treasury can pull *before* the wallet is even involved.

## What the budget policy v0.1 does

`scripts/trinity/useful_compute_reward_budget_policy.py` reads a
directory of governance-approved batches (Sprint 5.9 output) and
emits one deterministic budget plan:

```
TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_<budget_id>.json
TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_SUMMARY.md
```

The plan applies four caps **on top of** the governance decision:

| Cap | Default | Meaning |
|---|---|---|
| `max_daily_fraction_of_pool` | `0.0001` (0.01%) | of the current pool balance, per day |
| `fixed_daily_cap_stocks` | `100,000,000` (1 SOST) | hard absolute daily cap |
| `max_epoch_fraction_of_pool` | `0.001` (0.1%) | per epoch |
| `fixed_epoch_cap_stocks` | `1,000,000,000` (10 SOST) | hard absolute epoch cap |
| `max_job_reward_stocks` | `5,000,000` (0.05 SOST) | per request_id |
| `max_worker_reward_stocks` | `2,000,000` (0.02 SOST) | per worker_result_id |

The effective daily / epoch budgets are the minimum of the fraction
of the pool and the fixed cap:

```
effective_daily_budget_stocks = min(
  pool_balance_stocks × max_daily_fraction_of_pool,
  fixed_daily_cap_stocks,
)
effective_epoch_budget_stocks = min(
  pool_balance_stocks × max_epoch_fraction_of_pool,
  fixed_epoch_cap_stocks,
)
```

That way the policy never lets a large pool be drained by a single
big day, and never lets a small pool be drained by a single big
item.

## How an item is allocated

For each approved item in each governance batch (sorted
deterministically by request_id + batch_id), the policy walks four
caps in this order:

1. **Worker cap.** If `approved_pending_reward_stocks` per worker
   exceeds `max_worker_reward_stocks`, scale down per worker.
2. **Job cap.** If the per-job total (per-worker × number of
   matching workers) exceeds `max_job_reward_stocks`, scale down
   the per-worker amount evenly.
3. **Epoch cap.** If the running epoch total would exceed
   `effective_epoch_budget_stocks`, allocate only what fits;
   the remainder is deferred to a future budget cycle.
4. **Daily cap.** Same as epoch, applied to
   `effective_daily_budget_stocks`.

Of the resulting `allocated_stocks` per item, the v0.1 split is:

- **70% primary_workers_share_stocks** — split among the matching
  workers
- **20% replay_validator_reserve_stocks** — held for replay
  validators in a future sprint
- **10% governance_review_reserve_stocks** — held for the human
  review step in the payment sprint

These three sub-totals always sum exactly to `allocated_stocks`
thanks to integer-rounded math; the remainder lands in
`governance_review_reserve_stocks`.

## Allocation statuses

Each item carries one `allocation_status`:

| Status | Meaning |
|---|---|
| `approved_as_requested` | no cap hit, full allocation |
| `capped_by_worker` | worker cap reduced the per-worker amount |
| `capped_by_job` | job cap reduced the per-job total |
| `capped_by_epoch` | epoch cap deferred part or all |
| `capped_by_daily` | daily cap deferred part or all |
| `deferred` | nothing allocated this run; **not lost** |
| `rejected` | input was structurally invalid |

The `cap_reason` field is a free-form short string listing every
cap that fired for the item (e.g.
`"capped_by_worker,capped_by_daily"`), useful for debugging.

## Why we defer instead of rejecting

A deferred item is **not lost**. The next budget cycle (different
`epoch_id` or higher pool balance, or simply a different day) will
re-evaluate the same governance batches and may allocate the
deferred portion. The intent is: the treasury controls *when* a
batch becomes payable, not whether it becomes payable.

A future sprint will introduce the cross-cycle ledger that ages
deferrals and decides when to write them off vs. carry them.

## Determinism

`budget_id = "bud-" + sha16(canonical(policy, pinned_time, epoch_id,
pool_balance_stocks, policy_caps, allocations))`.

Two runs on the same inputs produce byte-identical plans.

## How to adjust the policy

The defaults are deliberately tight. To relax them:

1. Edit `_DEFAULT_POLICY_CAPS` in
   `scripts/trinity/useful_compute_reward_budget_policy.py` for a
   new long-term default, OR
2. Pass a custom `policy_caps` dict to `run_budget_policy()` for a
   single-run override.

Any new value must keep `primary_worker_share +
replay_validator_share + governance_review_reserve == 1.0` (a
strict invariant the function checks at start).

The CLI only exposes the `conservative` policy in v0.1. New named
policies (e.g. `expansive` for a future growth phase) will be
added via separate sprints after governance review.

## What the web console shows

`website/trinity-useful-compute.html` (badge bumped to v0.8):

- **Three new counters** in the Miner Compute Console:
  `governance_approved_stocks`, `budget_allocated_stocks`,
  `budget_deferred_stocks`.
- **New panel** "Reward Budget Policy": load a budget plan JSON,
  see pool / daily / epoch budgets, every allocation row, and the
  aggregate caps_hit counts.
- **Disclaimer** above the panel: "Budget allocation is not
  payment. Payment requires a separate signed/on-chain sprint."

## CLI reference

```
python3 scripts/trinity/useful_compute_reward_budget_policy.py \
  --mode local-dry-run \
  --pool-balance-stocks 1000000000000 \
  --policy conservative \
  --governance-dir /tmp/trinity-daemon-console/governance \
  --out-dir /tmp/trinity-budget-test \
  --pinned-time 2026-05-12T00:00:00+00:00 \
  --epoch-id epoch-demo-001
```

The CLI explicitly rejects `--broadcast`, `--payout`, `--send`,
`--wallet`, `--network`. The only accepted `--mode` is
`local-dry-run`.

## Risks (read before scaling)

- **Pool too low.** When the pool shrinks, the effective daily and
  epoch budgets shrink with it. Workers may see large deferred
  totals. Mitigation: increase the pool, or relax the daily/epoch
  fractions via governance.
- **Rewards not attractive.** Tight caps mean small per-worker
  payouts. If miners disengage, the network falls back to
  placeholders. Mitigation: tune the policy after a governance
  review; never via an unsigned default change.
- **Gaming.** A worker cannot game the budget policy alone (caps
  are global), but a coalition can submit many small jobs to
  saturate daily / epoch budgets. The reward model + benchmark
  ledger sit upstream; the policy is the last brake, not the only
  one.
- **Collusion across cycles.** A deferred item can be re-allocated
  in a later epoch with a higher cap. A future sprint must add an
  age-out / write-off rule so deferrals do not accumulate forever.
- **Float vs. integer math.** Shares are floats but their products
  are integer-floored to keep allocation deterministic across
  machines. A small remainder lands in
  `governance_review_reserve_stocks`; this is intentional.

## What is NOT in this sprint

- No payment sprint exists yet. The plan never pays.
- No wallet, no broadcast, no on-chain registration.
- No automatic governance-policy change. Caps stay where they are
  until a future sprint changes them under explicit human review.
- No cross-cycle deferral ledger. Each budget run is independent;
  deferrals are visible in the report but not tracked across runs.

## Reference run

```
$ python3 scripts/trinity/useful_compute_reward_budget_policy.py \
    --mode local-dry-run \
    --pool-balance-stocks 1000000000000 \
    --policy conservative \
    --governance-dir <one gov batch with one accepted item> \
    --out-dir /tmp/budget \
    --pinned-time 2026-05-12T00:00:00+00:00 \
    --epoch-id epoch-demo-001

budget_id        bud-770194361350bec6
pool             1,000,000,000,000 stocks
daily_budget     100,000,000        (= 1 SOST)
epoch_budget     1,000,000,000      (= 10 SOST)
requested        135,000
allocated        135,000   (under all caps)
deferred         0

allocation status     approved_as_requested
primary 70%           94,500
replay 20%            27,000
governance 10%        13,500
```

With a small pool (e.g. 100,000 stocks), the daily budget drops to
10 stocks and the same item lands at:

```
allocated 9, deferred 134,991, status capped_by_daily
cap_reason "capped_by_epoch,capped_by_daily"
```

The pool is preserved.
