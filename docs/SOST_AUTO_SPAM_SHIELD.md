# SOST — Automatic Adaptive Anti-Spam Shield

## Overview

Fully automatic, no manual activation. Policy-only (not consensus).
Activates at block 10,000 alongside the dynamic fee policy.

## Levels

| Level | Pressure | Relay Floor | Peer Limit | Addr Limit |
|-------|----------|-------------|------------|------------|
| GREEN | 0-19 | 1x (1 stock/byte) | 30 tx/min | 25 tx |
| YELLOW | 20-39 | 3x | 20 tx/min | 15 tx |
| ORANGE | 40-59 | 10x | 12 tx/min | 10 tx |
| RED | 60-79 | 50x | 6 tx/min | 5 tx |
| BLACK | 80-100 | 250x → 1000x → 5000x | 3 tx/min | 2 tx |

## BLACK Escalation (automatic)

- Enter BLACK: 250x relay floor
- After 5 min sustained: 1000x
- After 15 min sustained: 5000x
- No manual intervention needed

## Pressure Score (0-100)

Computed from:
- Mempool fill ratio (0-30 pts)
- TX arrival rate (0-25 pts)
- Low-fee ratio (0-15 pts)
- RBF churn rate (0-10 pts)
- Peer concentration (0-10 pts)
- Reject rate (0-10 pts)

## Hysteresis

- **Escalation:** fast — 2 consecutive ticks above threshold
- **Relaxation:** slow — 10 min stable below threshold, drops 1 level at a time

## Files

- `include/sost/spam_guard.h` — SpamGuard class, SpamLevel enum, metrics
- `src/spam_guard.cpp` — pressure calculation, level transitions, BLACK escalation
- `include/sost/params.h` — all constants (configurable without recompiling logic)

## Key Design Decisions

1. **Automatic** — no operator activation needed
2. **Policy, not consensus** — blocks with low-fee tx remain valid
3. **Fast up, slow down** — hardens quickly, relaxes gradually
4. **5000x ceiling** — at $0.22/SOST, a 250-byte tx at 5000x costs ~$0.000275 — still cheap for real users, expensive for sustained spam
5. **Per-level admission controls** — not just fee, also peer limits and address limits
