#!/usr/bin/env bash
# =============================================================================
# soak_popc_v15_testnet.sh — PoPC V15 settle soak on a TESTNET-forks node.
#
# Run this ON THE VPS (where the node + popc_registry.json live). The chain only
# needs to be PAST V15 (testnet=300); it does NOT need to reach a real end_height
# (PoPC durations are 144*30*months blocks — thousands — and are NOT scaled on
# testnet, so we use a registry FIXTURE for end_height, the same way we fixture
# gold_verified_days). This avoids mining thousands of blocks and the cASERT
# slingshot that appears when many blocks are mined back-to-back.
#
# Validates the popc_release settle path + Gold Boost gating:
#   Scenario A: gold_verified_days = 0   -> gold_boost = 0  (base only)
#   Scenario B: gold_verified_days = 120 -> gold_boost > 0  (if eligible + surplus)
#
# MAINNET IS UNAFFECTED. Do NOT point this at a mainnet node.
# Usage: cp scripts/soak_popc_v15_testnet.env.example .env && edit .env
#        set -a; . ./.env; set +a; ./scripts/soak_popc_v15_testnet.sh
# =============================================================================
set -euo pipefail

RPC_URL="${RPC_URL:-http://127.0.0.1:18399/rpc}"
RPC_AUTH="${RPC_AUTH:-}"                           # e.g. "-u user:pass"
POPC_REGISTRY="${POPC_REGISTRY:-/opt/sost/testnet-soak/popc_registry.json}"
WALLET_ADDR="${WALLET_ADDR:-}"                     # SOST address (blank -> getnewaddress)
ETH_ADDR="${ETH_ADDR:-0xd38955822b88867CD010946F0Ba25680B9DfC7a6}"
NODE_RESTART_CMD="${NODE_RESTART_CMD:-}"           # optional: command to restart the node so it
                                                  # reloads the patched registry. If empty, the
                                                  # script pauses and you restart it by hand.
GOLD_TOKEN="${GOLD_TOKEN:-PAXG}"
GOLD_MG="${GOLD_MG:-50000}"                        # ~1.6 oz, well above the 0.25 oz dust floor
MONTHS_A="${MONTHS_A:-12}"                         # distinct months => distinct commitment_id
MONTHS_B="${MONTHS_B:-9}"

req() { command -v "$1" >/dev/null || { echo "missing dependency: $1" >&2; exit 1; }; }
req curl; req jq
[ -f "$POPC_REGISTRY" ] || { echo "POPC_REGISTRY not found: $POPC_REGISTRY (run on the VPS)" >&2; exit 2; }

rpc() { local m="$1"; shift; local p; p=$(printf '%s\n' "$@" | jq -R . | jq -s .)
  curl -s $RPC_AUTH "$RPC_URL" -H 'content-type:application/json' -d "{\"method\":\"$m\",\"params\":$p}"; }
height() { rpc getblockcount | jq -r '.result // .'; }
is_zero() { case "$1" in 0|0.0|0.00000000|""|null) return 0;; *) return 1;; esac; }
reg_id() { echo "$1" | jq -r '.result.commitment_id // .result.id // empty'; }
restart_node() {
  if [ -n "$NODE_RESTART_CMD" ]; then eval "$NODE_RESTART_CMD"; sleep 3
  else echo ">>> STOP the node, it is safe now to keep the patched registry, then START it again."
       echo ">>> Press Enter once the node is back up..."; read -r _; fi
}

H=$(height); echo "chain height = $H"
[ "$H" -ge 301 ] || { echo "Chain must be past V15 (testnet=300). Mine a few blocks first." >&2; exit 3; }
[ -n "$WALLET_ADDR" ] || WALLET_ADDR="$(rpc getnewaddress | jq -r '.result // .')"
echo "receiver: $WALLET_ADDR"

echo "== Register A (months=$MONTHS_A) and B (months=$MONTHS_B) =="
CID_A=$(reg_id "$(rpc popc_register "$WALLET_ADDR" "$ETH_ADDR" "$GOLD_TOKEN" "$GOLD_MG" "$MONTHS_A")")
CID_B=$(reg_id "$(rpc popc_register "$WALLET_ADDR" "$ETH_ADDR" "$GOLD_TOKEN" "$GOLD_MG" "$MONTHS_B")")
echo "  A = $CID_A"; echo "  B = $CID_B"
[ -n "$CID_A" ] && [ -n "$CID_B" ] || { echo "registration failed (check popc_register response)" >&2; exit 4; }

echo "== FIXTURE: set end_height<=current for both; gold_verified_days=120 for B (TEST FIXTURE) =="
echo ">>> STOP the node now (so it does not overwrite the registry), then press Enter to patch..."; read -r _
H=$(height); H=${H:-$H}
tmp=$(mktemp)
jq --arg a "$CID_A" --arg b "$CID_B" --argjson h "$H" '
  (.commitments[] | select(.commitment_id==$a) | .end_height) = $h |
  (.commitments[] | select(.commitment_id==$b) | .end_height) = $h |
  (.commitments[] | select(.commitment_id==$b) | .gold_verified_days) = 120
' "$POPC_REGISTRY" > "$tmp" && mv "$tmp" "$POPC_REGISTRY"
echo "  patched end_height=$H (A,B) and gold_verified_days=120 (B)"
restart_node

echo "== Settle A (snapshot) and B (verified) =="
OUT_A=$(rpc popc_release "$CID_A"); OUT_B=$(rpc popc_release "$CID_B")
BA=$(echo "$OUT_A" | jq -r '.result.base_reward // empty'); GA=$(echo "$OUT_A" | jq -r '.result.gold_boost // empty')
BB=$(echo "$OUT_B" | jq -r '.result.base_reward // empty'); GB=$(echo "$OUT_B" | jq -r '.result.gold_boost // empty')
SA="FAIL"; ! is_zero "$BA" && is_zero "$GA" && SA="PASS"
SB="FAIL"; if ! is_zero "$BB"; then if ! is_zero "$GB"; then SB="PASS"; else SB="WARN"; fi; fi

echo
echo "================ SOAK RESULT ================"
echo "Scenario A: $SA — gold_verified_days=0,   gold_boost=$GA, base_reward=$BA"
echo "Scenario B: $SB — gold_verified_days=120, gold_boost=$GB, base_reward=$BB"
[ "$SB" = "WARN" ] && echo "  (B=WARN: boost 0 — check gold>=max(25% bond,0.25oz) eligibility AND PoPC Pool surplus)"
echo "============================================="
echo "raw A: $OUT_A"; echo "raw B: $OUT_B"
[ "$SA" = "PASS" ] && { [ "$SB" = "PASS" ] || [ "$SB" = "WARN" ]; } || { echo "SOAK FAILED"; exit 5; }
echo "SOAK OK"
