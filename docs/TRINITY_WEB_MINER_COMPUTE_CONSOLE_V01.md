# Trinity Web Miner Compute Console v0.1

## What it is

`website/trinity-useful-compute.html` ships a top-level panel called
**Miner Compute Console**. It is a read-only, browser-local
dashboard that reads files produced by the Trinity Background
Autonomy Daemon (Sprint 5.10) and renders a live picture of where
the miner stands:

- daemon state and per-cycle counters
- the **stock totals** broken into four buckets
- the **approved pending reward stocks** headline (governance
  batches)
- a per-task status table
- a recent-events timeline
- the lessons aggregated by `(vertical, cause)`

The console is **not** a wallet, not a sender, not a signer, not a
miner runner. It is a viewer.

## Files it can load

| Loader                  | Accepts                                                  |
|-------------------------|----------------------------------------------------------|
| daemon state JSON       | `TRINITY_BACKGROUND_DAEMON_STATE.json`                   |
| events JSONL            | `TRINITY_BACKGROUND_EVENTS.jsonl`                        |
| pending reward JSONs    | `TRINITY_USEFUL_COMPUTE_PENDING_REWARD_<rid>_<wrid>.json` |
| validation JSONs        | `TRINITY_USEFUL_COMPUTE_VALIDATION_<rid>.json`           |
| governance batch JSONs  | `TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_<batch_id>.json` |
| lessons / summary       | `*.jsonl` lesson ledger OR any `.md` summary             |

Every load uses `FileReader.readAsText` only — no `fetch`, no
`XMLHttpRequest`, no `WebSocket`, no `EventSource`, no
`navigator.sendBeacon`. Files never leave the browser.

## How the stock counters are calculated

Each loaded pending-reward file is bucketed by the highest tier its
`worker_result_id` has reached:

1. **governance_approved_stocks** — `worker_result_id` appears in
   the `matching_result_ids` of an approved item in any loaded
   governance batch.
2. **replay_accepted_stocks** — `worker_result_id` appears in the
   `matching_result_ids` of an accepted validation but is NOT yet
   in a governance approved item.
3. **rejected_or_manual_review_stocks** — the matching validation is
   `mismatch` for this `request_id`, OR the reward itself carries
   `requires_manual_review=true`.
4. **pending_unvalidated_stocks** — none of the above; the reward
   exists but has not yet been validated nor approved.

The headline counter **approved_pending_reward_stocks** is the sum
of every loaded governance batch's `total_approved_reward_stocks`.
It is shown in stocks and in SOST (1 SOST = 100,000,000 stocks) for
human readability.

> Even when this counter is positive, **no payment has happened**.
> It is governance review input, not an authorisation.

## Per-task status table

For every loaded reward the console renders one row:

- `request_id`
- `worker_result_id` (parsed from filename)
- `worker_id`
- `compute_output_sha256` (short, sourced from the matching
  validation when available)
- `pending_reward_stocks`
- validation status (from the matching validation)
- governance status (`approved` / `rejected` / `(none)`)
- `manual_review_required`
- final status badge: `pending`, `replay accepted`,
  `governance approved`, `mismatch`, `insufficient workers`,
  `manual review`

## Event timeline

The events JSONL is parsed line by line. Any line that fails JSON
parsing increments a malformed counter; the console displays a
warning like `"3 malformed event lines ignored"` without crashing.
The first 200 well-formed events are rendered with timestamp,
stage, kind, and identifying ids.

## Lessons

When the lessons file is a JSONL error ledger, the console
aggregates entries by `(vertical, cause)` and shows count + latest
detail per cause. When it is a Markdown summary, the console
renders the text inside a `<pre>` (escaped via `textContent`).

## Reset / Export

- **Reset Console** clears every loaded artefact and rerenders the
  empty state.
- **Export Summary JSON** downloads a deterministic local file
  `TRINITY_MINER_CONSOLE_SUMMARY.json` containing:
  ```
  schema: trinity-web-miner-console-summary/v0.1
  loaded_counts: { ... }
  stock_totals: { ... }
  task_statuses: [ ... ]
  malformed_events_count: <int>
  safety_status: {
    local_dry_run_only: true,
    no_wallet_access: true,
    no_private_keys: true,
    no_automatic_payout: true,
    no_broadcast: true,
    no_network_required: true,
    no_consensus_changes: true,
    human_review_required_before_payment: true
  }
  ```
  The export is generated entirely in the browser and is never
  uploaded.

## How to use it with the daemon

```bash
# 1) Run one cycle of the daemon (locally)
python3 scripts/trinity/trinity_background_daemon.py \
  --mode local-dry-run \
  --run-once \
  --workspace /tmp/trinity-daemon-console \
  --objectives config/trinity/objectives \
  --seed trinity-autonomy-v0.1 \
  --pinned-time 2026-05-12T00:00:00+00:00 \
  --count 25 \
  --worker-id miner-console-001 \
  --reviewer-id reviewer-console-001

# 2) Open website/trinity-useful-compute.html in your browser.
# 3) In Miner Compute Console:
#    - "Choose state..."           → /tmp/trinity-daemon-console/TRINITY_BACKGROUND_DAEMON_STATE.json
#    - "Choose events..."          → /tmp/trinity-daemon-console/TRINITY_BACKGROUND_EVENTS.jsonl
#    - "Choose rewards..."         → /tmp/trinity-daemon-console/work/rewards/*.json
#    - "Choose validations..."     → /tmp/trinity-daemon-console/validation/*.json
#    - "Choose batches..."         → /tmp/trinity-daemon-console/governance/*.json
#    - "Choose lessons/summary..." → /tmp/trinity-daemon-console/lessons/TRINITY_AUTONOMY_ERROR_LEDGER.jsonl
```

## How to read errors and lessons

The events warning surfaces "N malformed event lines ignored" when
the JSONL contains noise. The lessons aggregator surfaces causes by
frequency:

| Cause                     | Means                                                |
|---------------------------|------------------------------------------------------|
| `compute_failed`          | a stage threw                                         |
| `validation_failed`       | the replay validator could not produce a report      |
| `insufficient_evidence`   | fewer workers than `--min-workers`                    |
| `overclaim_risk`          | mismatch or manual_review                             |
| `bad_input`               | malformed JSON / wrong schema in inbox or rewards    |
| `duplicate_candidate`     | duplicate or extra reward submission                  |

## Limits (read before scaling)

- **Read-only.** The console does not execute a worker, does not
  emit a request, does not start the daemon. The user opens it
  AFTER running daemon cycles on their machine.
- **No watcher.** The browser does not poll the filesystem; you must
  re-load files to refresh. A future sprint may add a folder watch
  via the File System Access API behind an explicit opt-in.
- **No live network.** Even an `accepted` validation does not pay.
  A separate, human-signed payment sprint is required.
- **No cross-tab gossip.** Two browser tabs reading the same files
  do not coordinate; each one is independent.
- **Manual file selection.** This is intentional — it keeps the
  browser sandbox honest and forces the user to think about which
  daemon run they are inspecting.
