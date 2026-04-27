# SOST Useful Compute — Miner Participation (TESTING ONLY)

> ## ⚠️ Trial scope update — 2026-04-27
>
> **All Useful Compute rewards are postponed.**
>
> After internal audit and empirical analysis, **no SOST will be
> distributed for Useful Compute activity at this stage**. This applies
> to both Light and Heavy worker modes. The infrastructure remains live
> as a **public dry-run / testing environment only**.
>
> Concretely:
>
> - **Light worker = testing only.** Submitted Light results appear in
>   public stats but are **not paid**. There is no Light reward window
>   tied to blocks `[7000, 8000)`.
> - **Heavy worker = testing only.** Heavy infrastructure remains
>   available for those who want to validate worker behaviour, but no
>   SOST is paid for any Heavy task this trial.
> - **No payout manifest** will be generated for current testing
>   activity. Submitted results are not eligible for retroactive
>   inclusion in any future rewarded phase.
>
> **Future rewarded windows will be announced individually.** Each will
> ship with its own task definitions, eligibility rules, activation
> window and audit process, with public advance notice. SOST will not
> reward weak, symbolic or artificial CPU work, and will not retroactively
> compensate testing-phase activity. Each future heavy family — and any
> future light reward window — must be announced before its window opens.
>
> Funds originally earmarked for the trial reward pool remain in the
> Gold Vault / PoPC pool structure aligned with the protocol's stated
> purpose. Nothing is being spent, redirected or distributed prematurely.

---

## What this is

The SOST Useful Compute infrastructure is a voluntary computation layer
where part of the network's CPU is directed toward real scientific
workloads (Materials Engine and GeaSpirit research). Right now it is
running as a **public dry-run / testing system**.

You participate by running a small extra program — the **Useful Compute
Worker** — alongside your normal SOST miner. It uses *only your public
miner address*. It does **not** ask for your private keys, your wallet
file, or any signed message.

**Participation is optional.** Miners who don't run the worker keep
mining normally and receive their normal block reward. Nothing changes
for them.

## Quick rules

- Voluntary opt-in. No penalty for not participating.
- No fork. No consensus change. No coinbase change. No mining change.
- No private keys required, ever.
- Same SOST address you use for mining rewards.
- Public ranking visible at `https://sostcore.com/api/useful-compute/ranking`.
- **All Useful Compute rewards are postponed.** Both Light and Heavy
  modes are currently testing only.
- Submitted results during this phase are **not eligible** for any
  retroactive reward.

## Reward model — postponed (testing only)

There is **no active Useful Compute reward window** at this stage. The
infrastructure is intentionally running for public verification of the
task server, the worker, the N=2 cross-verification path, and the
public audit endpoints — without any SOST paid out.

When the rewarded phase becomes ready, a separate public announcement
will publish: final task definitions, eligibility rules, reward formula,
worker version, activation window, and audit process. Until that
announcement, treat this guide as a description of the testing
infrastructure, not as a description of any active reward path.

What does NOT change in the meantime:

- Normal SOST mining and the standard 3.92550433 SOST coinbase reward
  per block remain unchanged for every miner.
- Funds in the Gold Vault and PoPC pool stay where they are, aligned
  with the protocol's original purpose. Nothing is spent prematurely.

## Quick start — testing the worker

You need Python 3.6+ and `git`. No `pip install` required — the worker
is self-contained, stdlib-only.

```bash
# 1. Get the public worker
git clone https://github.com/Neob1844/sost-core.git
cd sost-core

# 2. (Optional) one-shot smoke test against the public server
python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
    --mode trial --once

# 3. Run continuously alongside your miner — Light mode
python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
    --worker-mode light \
    --mode trial \
    --poll-interval 30
```

Replace `sost1YOURADDRESS` with the SOST address you want associated
(typically the same address that receives your mining rewards).

Heavy mode is also available for those who want to test the Heavy
dispatch path:

```bash
python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
    --worker-mode heavy \
    --mode trial \
    --poll-interval 60
```

If you previously saw `--capabilities cpu,mlip` in earlier examples,
note that `--capabilities` REPLACES the default rather than adding to
it. Heavy tasks today require `stdlib,cpu`. Either omit
`--capabilities` entirely (recommended) or pass `--capabilities
stdlib,cpu` explicitly to receive heavy tasks.

The worker prints one status line per cycle:

```
local_done=42 submitted=42 accepted=42 verified=12 disputed=0 score=18.0 eligible=False
```

These counters are visible in the public ranking but are not
reward-eligible at this stage. They are useful to verify that:

- The worker is connecting to the public server.
- Tasks are being received and processed.
- Submissions are accepted and persisted.
- N=2 cross-verification is working when a second miner processes the
  same task.

## Run as a background service (Linux)

Create `/etc/systemd/system/sost-useful-compute.service`:

```
[Unit]
Description=SOST Useful Compute Worker (testing)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/sost-core
ExecStart=/usr/bin/python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
    --worker-mode light \
    --mode trial \
    --poll-interval 30
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sost-useful-compute
journalctl -u sost-useful-compute -f
```

## Inspecting the system

Anyone can check the public state of any address:

```bash
curl -s "https://sostcore.com/api/useful-compute/check_eligible?address=sost1YOUR..."
```

Returns JSON:

```json
{
  "miner_address":   "sost1YOUR...",
  "submitted_tasks": 240,
  "verified_tasks":  118,
  "disputed_tasks":  3,
  "weighted_score":  192.5,
  "eligible":        true,
  "min_verified_tasks": 100,
  "max_disputed_ratio": 0.10
}
```

The `eligible` flag here reflects the threshold logic of the underlying
infrastructure (≥100 verified tasks, dispute ratio under 10%). It does
**not** mean any SOST is being paid — at this stage no rewards are
active. The flag is a future-facing field that will become meaningful
once a rewarded phase is announced.

Public endpoints (read-only, no authentication):

```
https://sostcore.com/api/useful-compute/health
https://sostcore.com/api/useful-compute/queue_stats
https://sostcore.com/api/useful-compute/ranking
https://sostcore.com/api/useful-compute/audit_export
```

## What the worker actually computes

Every Light task names a chemical formula and a research mission
(catalysts, photovoltaics, lithium extraction, hydrogen storage, CO₂
capture, desalination). The worker:

1. Parses the formula into elements + counts.
2. Looks up the elements' crustal abundance and relative cost (public
   geochemistry data, embedded in the script itself).
3. Computes a deterministic mission score.
4. Hashes the canonical result (sorted JSON → SHA-256, first 16 hex
   chars).

The computation is **identical on every machine** running the same
worker version, which is what makes cross-worker N=2 verification work.

## Frequently asked

**Is this mining a different coin?** No. You keep mining SOST normally.
The worker is a separate, voluntary contribution layer.

**Will it slow my miner down?** Light mode does small arithmetic. The
default poll interval is 30 seconds and the worker idles 99% of the
time.

**Do I need to register?** No. The first time the worker contacts the
server, your address is added automatically.

**Can I run multiple workers from the same address?** Yes, but it
won't increase your verified-task count more than running a single one
— the server tracks each `(task_id, miner_address)` pair only once.

**Can I cheat by sending fake hashes?** No. Each task is dispatched to
two miners. If your hash doesn't match the other miner's, the task is
marked `DISPUTED`, counted against your dispute ratio, and excluded
from your verified count.

**What happens to my private key?** Nothing. The worker never reads it,
never asks for it, and never writes it. Only your public address travels
over the wire.

**Will I get paid for this testing activity?** No. All Useful Compute
rewards are postponed. Submitted results during this phase are not
eligible for any retroactive reward. The future rewarded phase will be
announced separately with its own rules and activation window.

**Why is everything postponed?** SOST will not reward weak, symbolic
or artificial CPU work. The current Heavy task design produces per-task
runtimes too short to count as real heavy compute, and activating Light
rewards alone would be inconsistent with that decision. Real Heavy
tasks (DFT-grade, expanded formula pools, real per-task runtime,
scientifically actionable output) need to be designed and validated
properly before any SOST is paid for them. Each future reward family
will be announced separately before its window opens.

## Stopping

Press `Ctrl-C` or:

```bash
sudo systemctl stop sost-useful-compute
```

Already-submitted entries remain on your record. Stopping does not
erase verified contributions in the public stats.

## Files

- `scripts/useful_compute_worker.py` — public worker (this is what you run)
- This document — `docs/miner-useful-compute-trial.md`
- cASERT calibration decision (no consensus fork) — `docs/casert_calibration_decision.md`
