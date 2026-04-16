#!/bin/bash
# Full CASERT Validation Suite — runs all three test scripts in order
# Usage: bash scripts/run_full_casert_validation.sh
#        bash scripts/run_full_casert_validation.sh --blocks 5000 --seeds 50
set -e

BLOCKS="${BLOCKS:-2000}"
SEEDS="${SEEDS:-10}"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --blocks) BLOCKS="$2"; shift 2;;
    --seeds) SEEDS="$2"; shift 2;;
    *) shift;;
  esac
done

cd "$(dirname "$0")/.."
mkdir -p reports

echo "================================================================="
echo " CASERT FULL VALIDATION SUITE"
echo " Blocks: $BLOCKS | Seeds: $SEEDS | Variance: high"
echo "================================================================="
echo ""

echo "[1/3] Simulator Parity Audit..."
python3 scripts/validate_simulator_parity.py
echo "  → reports/simulator_parity_report.md"
echo ""

echo "[2/3] Miner Scaling Sweep..."
python3 scripts/miner_scaling_sweep.py --blocks "$BLOCKS" --seeds "$SEEDS"
echo "  → reports/miner_scaling_report.md"
echo ""

echo "[3/3] CASERT Shock Suite..."
python3 scripts/casert_shock_suite.py --blocks "$BLOCKS" --seeds "$SEEDS"
echo "  → reports/casert_shock_suite.md"
echo ""

echo "================================================================="
echo " ALL TESTS COMPLETE"
echo " Reports in: reports/"
echo "================================================================="
ls -la reports/
