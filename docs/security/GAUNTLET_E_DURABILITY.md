# Gauntlet E — durability / chaos (fail-safe on corrupted chain state)

Property tested: a corrupted, truncated, empty, or garbage `chain.json` must **fail safe** —
recover the valid prefix OR fall back to genesis and re-sync — and must NEVER crash, hang,
crash-loop, or silently accept a corrupted chain as valid/longer.

## Results (combined sec2 devnet node; valid baseline chain @ height 12)
| variant | outcome | crash | loaded | verdict |
|---|---|---|---|---|
| truncated 50% | RUNNING h=6 | no | valid prefix (7 blocks) | ✅ recovered valid prefix, rejected corrupt tail |
| truncated to 1 byte | RUNNING h=0 | no | failed to load → genesis | ✅ fresh start, re-syncs |
| empty file | RUNNING h=0 | no | failed to load → genesis | ✅ |
| valid JSON, garbage content | RUNNING h=0 | no | failed to load → genesis | ✅ |
| not JSON at all | RUNNING h=0 | no | failed to load → genesis | ✅ |
| random byte-flips (~2%) | RUNNING h=0 | no | detected error → genesis | ✅ |
| control (good chain) | RUNNING h=12 | no | 13 blocks, height=12 | ✅ loads correctly |

**0 crashes, 0 hangs, 0 silent acceptance of corruption** across all variants. The truncated-50%
case is the important one: the node loaded only the intact/verified prefix (h=6) and stopped at
the truncation boundary — it did NOT accept the corrupted tail, and will re-sync the rest from
peers.

## Combined with prior E evidence
- SIGKILL mid-reorg: 5/5 clean recoveries to a valid chain.json (atomic .tmp+rename).
- Write-interruption: kill during save leaves the previous valid chain.json intact.

## Not run here (environment / privilege)
- Disk-full during save (needs a privileged tmpfs mount): BLOCKED-on-env; recommend a
  size-capped tmpfs run before release. The atomic .tmp+rename means a failed write leaves the
  old file intact, so the expected outcome is a failed-save warning + old state preserved.

## Reproduce
`tests/security/gauntlet_E_chaos.sh`
