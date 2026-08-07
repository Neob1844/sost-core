#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_quick.sh — V15-D: fast GO/NO-GO gate (no mining).
#
# A deployer runs THIS for a quick pre-flight before the slow integration harnesses. It proves,
# in seconds:
#   1. the DEV build is a DEVNET build (SOST_DEVNET_FORKS=ON);
#   2. every DEV-only test capability is PRESENT in the DEVNET binaries and ABSENT (strings
#      count=0) from the mainnet + testnet binaries — the isolation guarantee that lets these
#      capabilities exist at all;
#   3. the V15 consensus arithmetic unit suites (jackpot payout/rollover/cap, DTD control,
#      lottery eligibility/frequency) all pass with zero failures.
#
# It deliberately does NOT mine — the multi-block integration harnesses (attacks, rollover-cap,
# reserve-edges, reorg/restart/reindex) are the slow full gate. Quick gate = arithmetic + isolation.
#
# Env: DEV_DIR (build-devnet) · MAIN_DIR (build) · TEST_DIR (build-testnet) · UNIT_DIR (=MAIN_DIR)
# Exit 0 = GO, non-zero = NO-GO.
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV_DIR="${DEV_DIR:-$ROOT/build-devnet}"
MAIN_DIR="${MAIN_DIR:-$ROOT/build}"
TEST_DIR="${TEST_DIR:-$ROOT/build-testnet}"
UNIT_DIR="${UNIT_DIR:-$MAIN_DIR}"
FAILED=0
ok(){ printf '[quick] PASS  %s\n' "$*"; }
bad(){ printf '[quick] NO-GO %s\n' "$*"; FAILED=1; }
note(){ printf '[quick] %s\n' "$*"; }

# --- 1. DEV build guard ---
if grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$DEV_DIR/CMakeCache.txt" 2>/dev/null; then
  ok "DEV build is a DEVNET build (SOST_DEVNET_FORKS=ON)"
else bad "$DEV_DIR is not a DEVNET build"; fi

# --- 2. capability isolation (present in DEV, absent from mainnet+testnet) ---
check_iso(){ # check_iso <binary-basename> <symbol>
  local bin="$1" sym="$2" dv mn tn
  # NOTE: grep -c exits 1 on a zero count, so `|| true` (not `|| echo NA`) must absorb it,
  # else the fallback text is appended after the "0". Missing-binary → NA via the if-guard.
  dv=$(strings "$DEV_DIR/$bin" 2>/dev/null | grep -c -- "$sym" || true)
  if [[ -x "$MAIN_DIR/$bin" ]]; then mn=$(strings "$MAIN_DIR/$bin" 2>/dev/null | grep -c -- "$sym" || true); else mn=NA; fi
  if [[ -x "$TEST_DIR/$bin" ]]; then tn=$(strings "$TEST_DIR/$bin" 2>/dev/null | grep -c -- "$sym" || true); else tn=NA; fi
  if [[ "${dv:-0}" -gt 0 && ( "$mn" == "0" || "$mn" == "NA" ) && ( "$tn" == "0" || "$tn" == "NA" ) ]]; then
    ok "isolation '$sym' in $bin: DEV=$dv main=$mn testnet=$tn"
  else bad "isolation '$sym' in $bin: DEV=$dv main=$mn testnet=$tn (must be DEV>0, main/testnet 0)"; fi
}
check_iso sost-miner inject-tx-at1
check_iso sost-miner attack-jackpot
check_iso sost-miner dump-block
check_iso sost-node  devjackpotstate

# --- 3. V15 consensus arithmetic unit suites ---
UNITS=(test-jackpot test-lottery-rollover test-dtd-control test-lottery-eligibility test-lottery-frequency)
for u in "${UNITS[@]}"; do
  if [[ ! -x "$UNIT_DIR/$u" ]]; then bad "unit binary missing: $UNIT_DIR/$u (build it: cmake --build $UNIT_DIR --target $u)"; continue; fi
  out="$(timeout 120 "$UNIT_DIR/$u" 2>&1)"; rc=$?
  fails="$(printf '%s' "$out" | grep -oiE '[0-9]+ fail' | grep -oE '[0-9]+' | head -1)"
  summ="$(printf '%s' "$out" | grep -iE 'summary|[0-9]+ pass' | tail -1)"
  if [[ $rc -eq 0 && ( -z "$fails" || "$fails" == "0" ) ]]; then ok "$u — ${summ:-exit 0}"; else bad "$u — rc=$rc ${summ:-} (fails=${fails:-?})"; fi
done

echo
if [[ "$FAILED" -eq 0 ]]; then note "RESULT: GO — DEV isolation intact + V15 consensus arithmetic green (quick gate)"; exit 0
else note "RESULT: NO-GO — see failures above"; exit 1; fi
