#!/usr/bin/env bash
# validate-v14-replay.sh — V14 safety net (A3, docs/V14_EXECUTION_PLAN.md).
#
# Proves a candidate sost-node binary replays a chain bit-identically to a
# baseline binary: same final height AND same deterministic UTXO-set root.
# Run this BEFORE deploying any consensus-touching binary. Non-zero exit = DO
# NOT DEPLOY (a divergent UTXO set means a chain split risk).
#
# Usage:
#   scripts/validate-v14-replay.sh <candidate-node> <baseline-node> [chain.json] [genesis.json]
#
# Notes:
#   * Both binaries run with --dry-run-replay (loads chain, replays via
#     ConnectBlock, prints UTXO root, exits before P2P/RPC).
#   * chain.json is read-only here; copies are used so neither binary mutates it.
set -euo pipefail

CAND="${1:?candidate sost-node binary required}"
BASE="${2:?baseline sost-node binary required}"
CHAIN="${3:-}"
GENESIS="${4:-}"

[ -x "$CAND" ] || { echo "ERROR: candidate not executable: $CAND" >&2; exit 2; }
[ -x "$BASE" ] || { echo "ERROR: baseline not executable: $BASE"  >&2; exit 2; }

run() {  # $1 = binary -> prints "<height> <root>"
  local bin="$1" args=(--profile mainnet --dry-run-replay --rpc-noauth)
  [ -n "$GENESIS" ] && args+=(--genesis "$GENESIS")
  if [ -n "$CHAIN" ]; then
    local tmp; tmp=$(mktemp); cp "$CHAIN" "$tmp"; args+=(--chain "$tmp")
    local out; out=$("$bin" "${args[@]}" 2>/dev/null); rm -f "$tmp"
  else
    local out; out=$("$bin" "${args[@]}" 2>/dev/null)
  fi
  local h r
  h=$(printf '%s\n' "$out" | awk '/DRYRUN final_height:/{print $3}')
  r=$(printf '%s\n' "$out" | awk '/DRYRUN utxo_set_root:/{print $3}')
  printf '%s %s' "${h:-NA}" "${r:-NA}"
}

echo "[v14-replay] candidate: $CAND"
echo "[v14-replay] baseline : $BASE"
echo "[v14-replay] chain    : ${CHAIN:-<genesis only>}"

read -r CH CR <<<"$(run "$CAND")"
read -r BH BR <<<"$(run "$BASE")"

echo "[v14-replay] candidate -> height=$CH root=$CR"
echo "[v14-replay] baseline  -> height=$BH root=$BR"

if [ "$CR" = "NA" ] || [ "$BR" = "NA" ]; then
  echo "[v14-replay] FAIL: a binary did not emit a UTXO root (replay error?)" >&2; exit 1
fi
if [ "$CH" != "$BH" ]; then
  echo "[v14-replay] FAIL: height mismatch (candidate=$CH baseline=$BH)" >&2; exit 1
fi
if [ "$CR" != "$BR" ]; then
  echo "[v14-replay] FAIL: UTXO-set divergence — DO NOT DEPLOY" >&2; exit 1
fi
echo "[v14-replay] PASS: bit-identical replay (height=$CH)"
exit 0
