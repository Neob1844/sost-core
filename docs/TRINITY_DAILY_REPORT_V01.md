# Trinity Daily Report v0.1

**Sprint:** 5.39 (Part C of combined sprint 5.37-5.39)
**Status:** additive · audit-only · zero hash / payment / consensus changes
**Depends on:** Sprint 5.28 (Queue Dashboard) · 5.33 (Materials Engine Result Surfacing) · 5.34 (Materials Cache Surfacing)

---

## 1. Why it exists

The dashboard (Sprint 5.28+) is interactive and HTML-shaped: good
for at-a-glance ops, less good for "what happened today" sharing.
The daily report turns the same dashboard JSON into a Markdown
summary the operator can paste into a notebook, an email, or a
status update without sending any HTML or JS.

---

## 2. CLI

```
python3 scripts/trinity/trinity_daily_report.py \
    --dashboard-json /var/lib/trinity/dashboards/TRINITY_TASK_QUEUE_DASHBOARD_<id>.json \
    --queue-dir      /var/lib/trinity/queues/main \
    --out-json       /var/lib/trinity/daily-reports/TRINITY_DAILY_REPORT_<id>.json \
    --out-md         /var/lib/trinity/daily-reports/TRINITY_DAILY_REPORT_<id>.md \
    --pinned-time    2026-05-18T00:00:00+00:00
```

- `--queue-dir` is optional. When given, the report also walks
  the per-item `operator_run/` directories for any
  `TRINITY_PAYMENT_DRAFT_*.json` / `TRINITY_PAYMENT_PROPOSAL_*.json`
  artifacts and surfaces the count + basenames.

---

## 3. Output

Two files:

```
<out-json>   trinity-daily-report/v0.1   (JSON)
<out-md>     human-readable Markdown
```

The JSON includes:

- `report_id` (`tdr-<16hex>`)
- `source_dashboard_basename` (no absolute path)
- `queue_dir_basename`
- `source_dashboard_id`
- `counts` (pending / running / completed / failed / batches)
- `completed_items[]` (per-item top_material + cache counts +
  workers_seen)
- `failed_items[]` (per-item watchdog_safety_status)
- `top_materials[]` (dedup, sorted)
- `cache_hits_total`, `cache_misses_total`
- `workers_seen_total`, `worker_ids[]` (truncated to 32 chars)
- `warnings[]` (from the dashboard)
- `drafts_proposals_count`, `drafts_proposals_basenames[]`
- `safety_status`, `safety_flags` (six const-true flags)
- `latest_batches_count`

The Markdown has the same content organised under section
headers: `# Trinity Daily Report`, `## Counts`,
`## Top materials`, `## Materials cache`, `## Workers seen`,
`## Completed items`, `## Failed items`,
`## Drafts / proposals`, `## Warnings`, `## Safety flags`.

---

## 4. Safety contract

Static tests assert:

- The script contains no network primitive, no subprocess, no
  shell, no eval/exec, no wallet/sign/broadcast tokens.
- The script does NOT emit HTML or JavaScript. The Markdown
  rendering contains no `<html>`, no `<script>`, no `<style>`,
  no `javascript:` literal.
- The script imports NO sibling Trinity modules — it is a pure
  consumer of on-disk JSON.
- The Markdown contains NO absolute `/tmp/` paths; only
  basenames are surfaced.
- All six `safety_flags` are const-true at both the script and
  the schema level.

---

## 5. Non-goals for v0.1

- The report does NOT modify any source artifact. It is purely
  derived.
- The report does NOT compute a new safety judgment — it surfaces
  the dashboard's existing `safety_status` directly.
- The report does NOT introduce a new payment, reward, or
  governance signal.
- The report does NOT include a 64-hex blob that is not bound to
  a sha256 field; private-key-shaped strings are rejected
  structurally.
