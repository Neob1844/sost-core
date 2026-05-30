# Trinity Routines — Stand-By Registry

**Status:** STAND-BY. No routines activated. No `CronCreate` called.
**Recorded:** 2026-05-30.
**Last reviewed:** 2026-05-30.

This document preserves the analysis and proposed routines so they can be
re-evaluated and activated later without re-doing the audit. Nothing in
this file changes consensus, executes any action, or modifies node state.

---

## 1. Why stand-by

Trinity v0.1 is operationally ready for **read-only observation** but
the decision was made to defer activation until after V13/V14 fork work
is complete and the public launch phase (2026-06-16+) is stable.

Reasons:

- V13 anti-dominance changes are higher priority than routines
- `TRINITY_AUTONOMY_LEDGER.jsonl` is empty today — most routines need
  real data before they add value
- Operator attention bandwidth is currently committed to V13/V14 +
  Hannah/SafeTrade outreach
- Routines compete with interactive Claude Code budget; activating
  before launch risks contention at the worst moment

---

## 2. Frame: what Trinity should do

> Trinity observes and proposes. Operator decides.
> Nothing is executed autonomously. Ever.

The four canonical objectives are already wired in
`config/trinity/objectives/`:

- `geaspirit.json` — autonomous AOI proposals with hard disclaimers
- `materials_engine.json` — autonomous material candidate proposals
- `useful_compute.json` — manifest validation, never on-chain payouts
- `sost_ai.json` — central planner using free-tier AI council as critic

All four have explicit `NEVER` hard rules (no broadcast, no wallet, no
paid providers, no consensus override).

---

## 3. Routine catalog (14 proposed)

Each routine is a Claude Code `CronCreate` invocation. None are
currently active. Token costs are estimates assuming Sonnet 4.6.

| # | Routine | Cadence | What it does | Tools | Tokens/run |
|---|---|---|---|---|---|
| R1 | trinity-ledger-health | every 3h | Tail last 50 entries of `TRINITY_AUTONOMY_LEDGER.jsonl`; flag ERROR/BLOCKED to inbox | Read, Bash | ~2k |
| R2 | materials-canary-nightly | 1×/day 03:00 | Run `canary_canonical_minerals.py --in-process`; alert if <33/33 | Bash | ~3k |
| R3 | sost-node-pulse | every 4h | curl getblockcount; flag if chain lag >2h | Bash, WebFetch | ~1.5k |
| R4 | pr-watch-github | 2×/day | `gh pr list` Neob1844/*; summarise opens, comments, CI status | Bash (gh) | ~3k |
| R5 | slip-0044-pr-watch | 1×/day 12:00 | `gh api /repos/satoshilabs/slips/pulls/2004`; alert on mergeable change or new review | Bash (gh) | ~1k |
| R6 | trinity-orchestrator-dry-run | 1×/day 04:00 | Execute `trinity_orchestrator.py --dry-run --max-decisions 10`; summarise emerging decisions | Bash | ~5k |
| R7 | useful-compute-queue-stats | every 6h | Read pending rewards json; summarise queue + manual_review | Read | ~1.5k |
| R8 | geaspirit-dossier-summary | 1×/day 06:00 | Recent dossier outputs; AOIs candidates with score >80 | Read, Glob | ~2k |
| R9 | explorer-health-check | every 4h | curl explorer page + verify chain status responsive | WebFetch | ~1k |
| R10 | whitepaper-pdf-integrity | 1×/week Mon 08:00 | `curl -I` whitepaper.pdf, verify Content-Length | Bash | ~0.5k |
| R11 | multi-ai-test-regression | 1×/day 02:00 | `cd materials-engine-private && pytest tests/test_multi_ai_*.py -q`; alert on fail | Bash | ~4k |
| R12 | operator-inbox-summary | 1×/day 07:30 | Read last 24h of `trinity_operator_inbox.jsonl`; prioritised daily brief | Read | ~3k |
| R13 | trinity-error-memory-review | 1×/week Fri | Read `trinity_error_memory.json`; categorise failure patterns; propose mitigations | Read | ~3k |
| R14 | mainnet-launch-checklist | disabled until 2026-06-14, then daily | Verify V13 RC1 binaries uploaded, SLIP-0044 merged, whitepaper coherent, canaries green | Bash, Read, WebFetch | ~5k |

---

## 4. Recommended rollout (when re-activated)

### Stage 1 — first 72 hours of activation

Activate **3 routines only**, lowest risk:

- R5 slip-0044-pr-watch (1×/day 12:00)
- R3 sost-node-pulse (every 8h, with double-failure confirmation
  before alerting)
- R9 explorer-health-check (every 8h, with double-failure confirmation
  before alerting)

Total: ~5 runs/day. Well under Max plan's 15 routine/day cap.

**Promotion gate to Stage 2:** zero false positives for 72 hours,
operator interactive budget unaffected.

### Stage 2 — week 2-3 of activation

Add 4 routines:

- R1 trinity-ledger-health
- R2 materials-canary-nightly
- R4 pr-watch-github
- R12 operator-inbox-summary

Total acumulado: ~15 runs/day. Exactly the Max cap.

### Stage 3 — post-launch

Add the heavier routines only if Stages 1-2 ran clean for ≥2 weeks:

- R6 trinity-orchestrator-dry-run
- R11 multi-ai-test-regression
- R13 trinity-error-memory-review

R14 mainnet-launch-checklist runs in its own window 2026-06-14 → 16,
then retires.

---

## 5. Token budget guard (deferred to Stage 2)

A simple counter persisted at `data/trinity/routine_budget_state.json`:

```
{"date": "YYYY-MM-DD", "tokens_spent": N, "runs_completed": K}
```

Each routine calls `check_budget(estimated_tokens)` at start. If today's
spend would exceed the configured cap (recommended: 50 % of estimated
daily Max budget), the routine writes a LOW-severity inbox entry and
exits silently.

Not implemented in Stage 1 — frequency cap of 5-9 runs/day is itself
sufficient protection at that point. Implement before promoting to
Stage 2 (15 runs/day).

---

## 6. Aborto manual

To kill all Trinity routines at any time:

```
CronList | grep trinity | awk '{print $1}' | xargs -I{} CronDelete {}
```

Or per-routine: `CronDelete <id>`.

---

## 7. Hard invariants — never violate when activating

- Every routine prompt must end with: *"NEVER broadcast, NEVER modify
  chain state, NEVER call paid_judge_provider, NEVER `gh pr merge` or
  any GitHub write."*
- Every routine must have `max_tokens_per_run` and `max_runtime_seconds`
  caps configured at `CronCreate` time.
- No routine may execute Trinity's `useful_compute_task_builder.py`
  outside `--dry-run` mode.
- No routine may write to `popc_registry.json` or any consensus-relevant
  file.
- Routines are read-mostly. The only writes allowed are:
  - `data/trinity/trinity_operator_inbox.jsonl` (severity-tagged)
  - `data/trinity/routine_budget_state.json` (Stage 2+ only)
  - `data/trinity/TRINITY_AUTONOMY_LEDGER.jsonl` (only via the
    orchestrator's own logger, never directly)

---

## 8. Re-activation checklist

Before flipping these routines from STAND-BY to ACTIVE:

1. Confirm V13 fork has activated cleanly at block 12,000 and the
   chain is stable at V13 rules for ≥1,000 blocks
2. Confirm public launch phase (2026-06-16+) has begun without
   incident
3. Confirm `TRINITY_AUTONOMY_LEDGER.jsonl` has ≥100 real entries from
   manual orchestrator runs (otherwise R1/R12 have nothing to read)
4. Confirm operator interactive budget headroom — measure 7-day
   average usage and ensure routines fit in remaining 50 %
5. Run Stage 1 routines manually (`tick` from interactive session)
   for 48 hours to validate output shape before scheduling
6. Document the activation date and Stage 1 routine IDs at the bottom
   of this file

---

## 9. Activation log (append here when activating)

```
[ no activations recorded yet ]
```
