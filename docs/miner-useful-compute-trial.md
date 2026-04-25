# SOST Useful Compute Trial — Miner Participation

## What this is

From **block 7,000 to block 8,000**, SOST runs a 1,000-block voluntary
trial where part of the network's computational power is directed toward
real scientific workloads (Materials Engine and GeaSpirit research).

You participate by running a small extra program — the **Useful Compute
Worker** — alongside your normal SOST miner. It uses *only your public
miner address*. It does **not** ask for your private keys, your wallet
file, or any signed message.

**Participation is optional.** Miners who don't run the worker keep
mining normally and receive their normal block reward. Nothing changes
for them.

## Quick rules

- Trial blocks: **7,000 → 8,000** (inclusive start, exclusive end).
- Voluntary opt-in. No penalty for not participating.
- No consensus changes. No coinbase changes.
- No private keys required, ever.
- Same SOST address you use for mining rewards.
- Public ranking will be visible at `https://sostcore.com/api/useful-compute/ranking`.

## Reward model

| Item | SOST |
|------|-----:|
| Normal coinbase reward (every miner, paid live) | 3.92550433 |
| **Extra** — Gold Vault allocation (post-trial only) | +1.96275215 |
| **Extra** — PoPC Pool allocation (post-trial only) | +1.96275215 |
| **Total extra per eligible mined block** | **+3.92550430** |
| Effective full block allocation for eligible miners | 7.85100863 |

The extra is paid **after block 8,000** by a normal wallet TX batch from
the Gold Vault and PoPC operator wallets. It is **not** automatic per
block during the trial. Miners who do not run the worker simply receive
the normal 3.92550433 SOST coinbase reward.

## Eligibility

A miner address is eligible for the post-trial bonus only if **all**:

1. The address mined at least one block during `[7000, 8000)`.
2. The address ran the Useful Compute Worker.
3. The address has at least **100 verified tasks** in the public ranking.
4. The address has a dispute ratio under **10 %**
   (`disputed / submitted < 0.10`).

A "verified" task is one where **two distinct miners** computed the same
task and submitted matching result hashes. This cross-worker check is
the trial's anti-cheat: a single miner returning fake hashes cannot
inflate their own score because no one will match them.

## Quick start

You need Python 3.6+ and `git`. No pip install required — the worker is
self-contained.

```bash
# 1. Get the public worker
git clone https://github.com/Neob1844/sost-core.git
cd sost-core

# 2. (Optional) one-shot smoke test against the public server
python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
    --mode trial --once

# 3. Run continuously alongside your miner
python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
    --mode trial \
    --poll-interval 30
```

Replace `sost1YOURADDRESS` with the SOST address you want credited
(typically the same address that receives your mining rewards).

The worker prints one status line per cycle:

```
local_done=42 submitted=42 accepted=42 verified=12 disputed=0 score=18.0 eligible=False
```

- `verified` increases only after a *second* miner submits the same hash
  for the same task.
- `disputed` increases if your hash disagrees with another miner's hash.
- `eligible=True` once you cross 100 verified tasks with a clean dispute
  ratio.

## Run as a background service (Linux)

Create `/etc/systemd/system/sost-useful-compute.service`:

```
[Unit]
Description=SOST Useful Compute Worker
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/sost-core
ExecStart=/usr/bin/python3 scripts/useful_compute_worker.py \
    --server https://sostcore.com/api/useful-compute \
    --miner-address sost1YOURADDRESS \
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

## Checking your progress

Anyone can check eligibility status of any address:

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

Public ranking and global stats:

```
https://sostcore.com/api/useful-compute/ranking
https://sostcore.com/api/useful-compute/stats
```

## What the worker actually computes

Every task names a chemical formula and a research mission (catalysts,
photovoltaics, lithium extraction, hydrogen storage, CO₂ capture,
desalination). The worker:

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

**Will it slow my miner down?** It does light arithmetic. The default
poll interval is 30 seconds and the worker idles 99 % of the time.

**Do I need to register?** No. The first time the worker contacts the
server, your address is added automatically.

**Can I run multiple workers from the same address?** Yes, but it
won't increase your verified-task count more than running a single one
— the server tracks each `(task_id, miner_address)` pair only once.

**Can I cheat by sending fake hashes?** No. Each task is dispatched to
two miners. If your hash doesn't match the other miner's, the task is
marked `DISPUTED`, counted against your dispute ratio, and excluded
from your verified count. Above 10 % disputes you lose eligibility.

**What happens to my private key?** Nothing. The worker never reads it,
never asks for it, and never writes it. Only your public address travels
over the wire.

**When do I get the extra reward?** After block 8,000 the team takes a
public ranking snapshot, runs the post-trial reward distributor in
dry-run mode, publishes the manifest for review, and then signs the
batch TXs offline from the Gold Vault and PoPC wallets.

## Stopping

Press `Ctrl-C` or:

```bash
sudo systemctl stop sost-useful-compute
```

Already-submitted tasks remain on your record. Stopping does not erase
verified contributions.

## Files

- `scripts/useful_compute_worker.py` — public worker (this is what you run)
- This document — `docs/miner-useful-compute-trial.md`
- Trial banner in the explorer with the validated scientific
  achievements that motivated the trial.
