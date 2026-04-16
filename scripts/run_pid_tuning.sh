#!/usr/bin/env bash
# Run the CASERT PID tuning campaign.
#
# Usage:
#   ./scripts/run_pid_tuning.sh              # full campaign (Phase 1 + Phase 2)
#   ./scripts/run_pid_tuning.sh --phase 1    # coarse sweep only (faster)
#   ./scripts/run_pid_tuning.sh --phase 0    # sanity check only
#
# Sensible defaults: 4 workers, 1.3 kH/s, medium variance.
# Override with env vars:
#   WORKERS=8 HASHRATE=2.0 VARIANCE=high ./scripts/run_pid_tuning.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

WORKERS="${WORKERS:-4}"
HASHRATE="${HASHRATE:-1.3}"
VARIANCE="${VARIANCE:-medium}"

echo "CASERT PID Tuning Campaign"
echo "  Workers:  $WORKERS"
echo "  Hashrate: $HASHRATE kH/s"
echo "  Variance: $VARIANCE"
echo ""

cd "$PROJECT_DIR"

python3 scripts/pid_tuning_campaign.py \
    --workers "$WORKERS" \
    --hashrate "$HASHRATE" \
    --variance "$VARIANCE" \
    "$@"

echo ""
echo "Output files:"
ls -la reports/pid_tuning_* 2>/dev/null || echo "  (no output files found)"
