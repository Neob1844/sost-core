#!/usr/bin/env bash
# SOST SECURITY GAUNTLET orchestrator (Phase H).
# Runs the REAL checks that exist today and prints the standardized summary.
# Pieces not yet implemented are reported PENDING (never silently PASS).
# Usage: tests/security-gauntlet.sh [repo_root]   (build/ must exist for ctest pieces)
set -u
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"
CONS_DIV=0 INVALID_ACC=0 VALID_REJ=0 MONEY_FAIL=0 CRASHES=0 ASAN=0 UBSAN=0 TSAN="n/a" OOM=0 CORRUPT=0 REPRO_FAIL=0
declare -a PENDING
step(){ printf "\n=== %s ===\n" "$1"; }

step "Release unit+consensus (ctest, btc-* excluded: need bitcoind)"
if [ -d build ]; then
  if ctest --test-dir build -E "btc-watch|btc-funding|bitcoin-backend|btc-swap-state" >/tmp/g_ct.log 2>&1; then
    echo "  PASS ($(grep -oE '[0-9]+ tests passed' /tmp/g_ct.log | tail -1))"
  else echo "  FAIL"; grep -E 'FAILED' /tmp/g_ct.log|head; VALID_REJ=1; fi
else echo "  SKIP (no build/)"; PENDING+=("release-ctest: build/ missing"); fi

step "Monetary invariants (Phase B) + subsidy differential model (Phase C)"
if bash tests/security/reference_model/run_subsidy_diff.sh "$ROOT" >/tmp/g_sub.log 2>&1 && \
   python3 tests/security/invariants/monetary_invariants.py >/tmp/g_inv.log 2>&1; then
   echo "  PASS ($(tail -1 /tmp/g_sub.log); $(tail -1 /tmp/g_inv.log))"
else echo "  FAIL"; tail -3 /tmp/g_sub.log /tmp/g_inv.log; MONEY_FAIL=1; fi

step "PENDING phases (declared, not executed here)"
PENDING+=("A fuzzing: mempool/NODE_BIND/heartbeat/Jackpot/reorg/persistence harnesses")
PENDING+=("C model: cASERT/difficulty, DTD, Jackpot, NODE_BIND, heartbeat, UTXO transition")
PENDING+=("D adversarial lab at scale (100s of peers, eclipse, partition/heal)")
PENDING+=("E chaos/persistence (kill -9, disk-full, truncation, restart)")
PENDING+=("F CPU-DoS full audit + explicit limits table")
PENDING+=("G reproducible build path-independence + SBOM + signing")
PENDING+=("ASan/UBSan/TSan full halt_on_error, fuzz-smoke: run via CI or the sanitizer build")
for p in "${PENDING[@]}"; do echo "  PENDING: $p"; done

cat <<SUMMARY

SOST SECURITY GAUNTLET
======================

Consensus divergence       $CONS_DIV
Invalid blocks accepted    $INVALID_ACC
Valid blocks rejected      $VALID_REJ
Money invariant failures   $MONEY_FAIL
Crashes                    $CRASHES
ASan findings              $ASAN
UBSan findings             $UBSAN
TSan findings              $TSAN
OOM                        $OOM
State corruption           $CORRUPT
Reproducibility failures   $REPRO_FAIL

Pending phases: ${#PENDING[@]} (see above)
SUMMARY
if [ $((CONS_DIV+INVALID_ACC+VALID_REJ+MONEY_FAIL+CRASHES+ASAN+UBSAN+OOM+CORRUPT+REPRO_FAIL)) -eq 0 ]; then
  echo "PARTIAL-PASS (executed checks clean; ${#PENDING[@]} phases PENDING)"
else echo "FAIL"; fi
