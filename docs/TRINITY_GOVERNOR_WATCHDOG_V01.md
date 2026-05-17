# Trinity Governor Watchdog v0.1

**Sprint:** 5.25
**Status:** read-only · local-only by default · webhook gated and not yet wired
**Depends on:** Sprint 5.23 (Autonomy Governor) and Sprint 5.24
(Operator Loop Governor Observe Hook)

---

## 1. Why it exists

The Trinity Autonomy Governor (Sprint 5.23) is intentionally
network-free: it never opens a socket, never heartbeats anything,
never imports `requests` / `urllib` / `subprocess`. That is the
right design for the Governor — but it means a stuck Governor, a
tampered decision file, or a halt event are invisible to anything
outside the box.

The Watchdog is the missing external eye. It runs in its own
process, reads the audit trail the Governor already produced, and
is free to talk to the network in a strictly bounded way (v0.2+).
v0.1 does **not** dispatch externally — it only summarises and
reports locally. The flag `--send` is wired and tested so the
contract is auditable before the daemon arrives.

```
                ┌────────────────────────┐
                │  operator_loop run     │
                │  + Governor hook (5.24)│
                └──────────┬─────────────┘
                           │ writes one per step
                           ▼
        TRINITY_AUTONOMY_GOVERNOR_DECISION_<id>.json
                           │
                           ▼
                ┌────────────────────────┐
                │  governor_watchdog.py  │  ← read-only
                │  (this sprint)         │  ← may have network in v0.2+
                └──────────┬─────────────┘
                           │
                           ▼
        TRINITY_GOVERNOR_WATCHDOG_REPORT_<id>.json
                           │
                           ▼
                  (future external dispatch — v0.2+)
```

---

## 2. What v0.1 does and does NOT do

| Capability                                  | v0.1 |
|---------------------------------------------|------|
| Read decision JSONs from a directory        | yes  |
| Count allowed / blocked / malformed         | yes  |
| Detect `halt_file_present`                  | yes — `safety_status=critical` |
| Detect `policy_mutated_at_runtime`          | yes — `safety_status=critical` |
| Detect stale audit trail vs `--pinned-time` | yes — `safety_status=stale` |
| Detect malformed / wrong-schema decisions   | yes — `safety_status=warning` |
| Write a deterministic report JSON           | yes  |
| Print one-line status to stdout             | yes  |
| Modify any decision file                    | NO   |
| Mutate operator_run.json                    | NO   |
| Touch wallet / signing / broadcast / payment| NO   |
| Shell out / subprocess / eval               | NO   |
| Open the network                            | NO (v0.1) — gated for v0.2+ |
| Follow paths into wallets / secrets / .git  | NO — refused at startup |

---

## 3. CLI surface

```
python3 scripts/trinity/governor_watchdog.py \
    --decisions-dir DIR        # required, the audit-trail dir
    --out-dir DIR              # required, where the report is written
    --pinned-time ISO          # default = now (operators should pin)
    --max-age-seconds N        # default 3600 = 1 hour
    --config PATH              # optional, JSON config file
    --webhook-url URL          # optional, host-redacted in report
    --send                     # double-gate; required alongside --webhook-url
```

`--config` loads a JSON file with the same field names. CLI flags
always win over the file. The example config lives at
`config/trinity_governor_watchdog.example.json`.

**Webhook double-gate.** In v0.1 the URL is recorded
(scheme + host only, path / query stripped) but never fetched —
even with `--send`. The flag is wired so that when the future
daemon sprint lands, the contract is already exercised. A regression
test asserts no `urlopen` / `urllib.request` / `requests.post` /
`http.client` / `socket.socket` ever appears in the source.

---

## 4. Report contract

`schemas/trinity/governor_watchdog_report.schema.json` (draft-07)

```json
{
  "schema": "trinity-governor-watchdog-report/v0.1",
  "report_id": "wd-<16hex>",
  "pinned_time": "2026-05-17T00:00:00+00:00",
  "decisions_dir_basename": "governor_decisions",
  "max_age_seconds": 3600,

  "decisions_seen": 7,
  "malformed_count": 0,
  "allowed_count": 7,
  "blocked_count": 0,
  "human_approval_required_count": 0,
  "policy_mutation_detected_count": 0,
  "halt_detected_count": 0,

  "newest_decision_time": "2026-05-16T00:00:00+00:00",
  "newest_decision_age_seconds": 86400,
  "stale": false,

  "decision_ids": ["abc...", ...],
  "threat_refs_seen": ["T15","T16","T17"],
  "actions_seen": ["pipeline_step"],

  "warnings": [],
  "safety_status": "ok",

  "webhook_configured": false,
  "webhook_url_redacted": null,
  "webhook_sent": false,
  "webhook_status": "not_configured"
}
```

Hard rules in the schema:

- `webhook_sent` is `"const": false` in v0.1. Any code change that
  flips it without bumping the schema fails CI.
- `decision_ids[*]` must match `^[a-f0-9]{32}$`.
- `threat_refs_seen[*]` must match `^T[0-9]{2}$`.
- `decisions_dir_basename` carries only the basename; the full path
  is never persisted (same privacy rule as
  `governor_policy_path_basename` from Sprint 5.24).

---

## 5. `safety_status` precedence

The watchdog assigns one of four values, with this precedence:

1. **`critical`** — any decision has `blocked_reason` in
   `{halt_file_present, policy_mutated_at_runtime}`. Page the
   operator.
2. **`warning`** — at least one decision is malformed, fails
   schema, or has `policy_hashes_match=false`.
3. **`stale`** — the newest valid decision is older than
   `max_age_seconds` (computed from `pinned_time − newest`), or
   there are zero decisions in the directory.
4. **`ok`** — none of the above.

The watchdog itself always exits **rc=0** unless the watchdog
*couldn't run at all* (missing dir, denylisted path, IO error
opening the report file). The report's `safety_status` field is
the source of truth on whether action is needed — same shape as
the Governor's own decision contract (allowed=true plus
blocked_reason=None ⇒ no veto).

---

## 6. Refusal denylist

The watchdog refuses to look at any directory whose basename or
any path segment matches (case-insensitive):

```
wallets · wallet · secrets · keys · private · .git · .ssh
```

This is belt-and-braces, not a security boundary. The kernel and
the filesystem permissions are the real defence. The denylist
catches operator typos and accidental wiring before they hit IO.

Triggers `WatchdogError` at startup → exit code 2. No partial
report is written.

---

## 7. Tests added in Sprint 5.25

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_governor_watchdog.py` | 15 | Happy path · halt-detected ⇒ critical · policy-mutation ⇒ critical · malformed ⇒ warning · stale ⇒ stale · empty dir ⇒ stale · denylist refuses (parametrised over 4 segments) · read-only on inputs · webhook double-gate · webhook URL redaction · determinism · CLI main · CLI missing dir ⇒ rc 2 · CLI config-file load |
| `tests/trinity/test_governor_watchdog_schema.py` | 12 | Schema is valid draft-07 · v0.1 id · safety_status enum · webhook_sent const false · decision_ids pattern · threat_refs_seen pattern · webhook_status enum · all four safety states validate end-to-end · webhook redacted form validates |
| `tests/trinity/test_governor_watchdog_safety.py` |  7 | Watchdog source has no wallet/signing/broadcast/payment/shell/eval/mutating-fs tokens · does not import sibling Trinity modules · declares v0.1 schema string · `PATH_DENYLIST` wired · no network primitives in v0.1 · cross-check that the Governor's safety surface did not regress |

Total: **34 new tests**.

---

## 8. Explicit non-goals for v0.1

- **No external dispatch.** Even with `--send`, the watchdog
  records the URL and returns. Dispatch lives in v0.2 as a
  separate `governor_watchdog_daemon.py` process.
- **No long-running mode.** v0.1 is a one-shot scanner suitable
  for cron, systemd timers, CI checks. The daemon arrives later.
- **No state.** v0.1 does not remember prior reports. Each run
  produces a fresh deterministic report for its inputs.
- **No `--fail-on critical` flag.** rc=0 always (unless the
  watchdog itself can't start). Callers read `safety_status` from
  the report. v0.2 may add a fail-mode flag for CI use.
- **No Slack / PagerDuty / email integration.** That belongs in
  the daemon sprint.
- **No write to the decisions dir.** Even structurally — the
  scan function never opens any input file in write mode.

---

## 9. Deployment notes

- Run as the same Linux user as the Governor. The watchdog needs
  read on the decisions dir and write on `--out-dir`.
- A cron line every minute is fine; the watchdog is O(N) over
  the file count and writes one small JSON.
- Point `--out-dir` somewhere the operator already monitors —
  `/var/lib/trinity/watchdog/` is a reasonable default.
- Pin `--pinned-time` from the cron wrapper or systemd unit
  (`date -u +%Y-%m-%dT%H:%M:%S+00:00`). If omitted, the watchdog
  uses `now()`, which is fine but breaks determinism between
  parallel scans.
- Do NOT point `--out-dir` at the decisions dir or any sibling
  of `wallets/` / `secrets/` / `.ssh/` — the denylist will refuse
  and exit 2.

---

## 10. Traceability

- The Watchdog reads the decision contract that landed in
  Sprint 5.23 (commit `b66352d6`, schema
  `trinity-autonomy-governor-decision/v0.1`).
- The `pipeline_step` action and threat refs `T15 / T16 / T17`
  come from Sprint 5.24 (merged into main at `a866ce36`,
  tag `sprint-5.24`).
- The Watchdog is the **first** Trinity component allowed to have
  network egress; v0.1 ships with the surface gated and tested
  but not exercised, so the audit point is reviewable before any
  real socket is opened.
- Pure scripts+schemas+docs+tests merge. Zero `src/`, zero
  consensus / wallet / payment / broadcast changes.
