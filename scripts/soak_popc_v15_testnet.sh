#!/usr/bin/env bash
# =============================================================================
# soak_popc_v15_testnet.sh — end-to-end PoPC V15 soak on a TESTNET-forks build.
#
# Validates, on a build where V15_HEIGHT=300 (all gates active at 300):
#   lock -> settle -> base_reward, and the Gold Boost gating:
#     - gold_verified_days = 0 (snapshot)         -> gold_boost = 0  (base only)
#     - gold_verified_days >= 91 (fixture-set)     -> gold_boost > 0  (if eligible + surplus)
#
# MAINNET IS UNAFFECTED: this only exercises a TESTNET_FORKS=ON binary. On mainnet
# the Gold Boost stays INT64_MAX (off). Do NOT point this at a mainnet node.
#
# This script is a TEMPLATE. Fill the parameters below for your environment and
# run it on the VPS/WSL. It does not assume your miner/RPC; those are injected.
# =============================================================================
set -euo pipefail

# ---- Parameters (fill these) ------------------------------------------------
RPC_URL="${RPC_URL:-http://127.0.0.1:18299/rpc}"   # node JSON-RPC endpoint
RPC_AUTH="${RPC_AUTH:-}"                            # e.g. "-u user:pass" if your RPC needs auth
# MINER_CMD must mine exactly $1 blocks to address $2. Examples you might use:
#   MINER_CMD='/path/to/sost-miner --rpc '"$RPC_URL"' --blocks $1 --address $2'
MINER_CMD="${MINER_CMD:-}"                          # REQUIRED — your miner invocation (uses $1=count $2=addr)
WALLET_ADDR="${WALLET_ADDR:-}"                      # SOST address to receive (blank -> getnewaddress)
ETH_ADDR="${ETH_ADDR:-0xd38955822b88867CD010946F0Ba25680B9DfC7a6}"  # declared EOA (any test EOA)
POPC_REGISTRY="${POPC_REGISTRY:-popc_registry.json}"               # registry path (for the fixture step)
BUILD_DIR="${BUILD_DIR:-build-testnet}"
GOLD_TOKEN="${GOLD_TOKEN:-PAXG}"
GOLD_MG="${GOLD_MG:-50000}"        # ~1.6 oz: well above the 0.25 oz dust floor (eligibility)
MONTHS="${MONTHS:-12}"             # base reward tier (12mo = 20%)
TARGET_START="${TARGET_START:-320}"  # mine past V15=300 before registering

req() { command -v "$1" >/dev/null || { echo "missing dependency: $1" >&2; exit 1; }; }
req curl; req jq
[ -n "$MINER_CMD" ] || { echo "Set MINER_CMD (mines \$1 blocks to \$2). Aborting." >&2; exit 2; }

rpc() { # rpc METHOD [param ...] -> raw JSON result
  local method="$1"; shift
  local params; params=$(printf '%s\n' "$@" | jq -R . | jq -s .)
  curl -s $RPC_AUTH "$RPC_URL" -H 'content-type:application/json' \
    -d "{\"method\":\"$method\",\"params\":$params}"
}
height() { rpc getblockcount | jq -r '.result // .'; }
mine_to() { # mine until height >= $1
  local target="$1"
  while [ "$(height)" -lt "$target" ]; do
    local need=$(( target - $(height) )); [ "$need" -lt 1 ] && need=1
    eval "${MINER_CMD//\$1/$need}" >/dev/null 2>&1 || { c="${MINER_CMD/\$1/$need}"; eval "${c/\$2/$WALLET_ADDR}"; }
  done
}

echo "== 1. Build testnet (V15=300) =="
cmake -S . -B "$BUILD_DIR" -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" -j"$(nproc)"

echo "== 2. Full ctest =="
ctest --test-dir "$BUILD_DIR" --output-on-failure
# NOTE: atomic-swap-htlc-lock is known to fail under TESTNET_FORKS=ON (it asserts
# mainnet activation heights); it is unrelated to PoPC and passes on the mainnet build.

echo "== 3. Node must be running this TESTNET binary at $RPC_URL =="
[ -n "$WALLET_ADDR" ] || WALLET_ADDR="$(rpc getnewaddress | jq -r '.result // .')"
echo "   miner/receiver address: $WALLET_ADDR"

echo "== 4. Mine past V15 (>=$TARGET_START) =="
mine_to "$TARGET_START"; echo "   height = $(height)"

settle_and_report() { # $1 = label ; echoes base_reward / gold_boost
  local cid="$1"
  local end; end=$(rpc popc_status "$cid" | jq -r '.result.end_height // .result.commitments[0].end_height // empty')
  [ -n "$end" ] && { echo "   advancing to end_height=$end"; mine_to "$((end+1))"; }
  rpc popc_release "$cid"
}

echo "== 5/6/7/8. Commitment A — snapshot (gold_verified_days=0) => boost must be 0 =="
RA=$(rpc popc_register "$WALLET_ADDR" "$ETH_ADDR" "$GOLD_TOKEN" "$GOLD_MG" "$MONTHS")
CID_A=$(echo "$RA" | jq -r '.result.commitment_id // .result.id // empty'); echo "   commitment_id A = $CID_A"
OUT_A=$(settle_and_report "$CID_A")
BASE_A=$(echo "$OUT_A" | jq -r '.result.base_reward'); BOOST_A=$(echo "$OUT_A" | jq -r '.result.gold_boost')
echo "   A base_reward=$BASE_A  gold_boost=$BOOST_A"
[ "$BASE_A" != "0" ] && [ "$BASE_A" != "0.00000000" ] || { echo "FAIL: base_reward must be > 0" >&2; exit 3; }
case "$BOOST_A" in 0|0.00000000) echo "   PASS: snapshot gold -> no boost";; *) echo "FAIL: snapshot must give 0 boost (got $BOOST_A)" >&2; exit 3;; esac

echo "== 9. Commitment B — fixture sets gold_verified_days>=91 => boost must be > 0 (if eligible+surplus) =="
RB=$(rpc popc_register "$WALLET_ADDR" "$ETH_ADDR" "$GOLD_TOKEN" "$GOLD_MG" "$MONTHS")
CID_B=$(echo "$RB" | jq -r '.result.commitment_id // .result.id // empty'); echo "   commitment_id B = $CID_B"
# TEST FIXTURE ONLY: in production gold_verified_days is set by the verification
# pipeline (see docs/GOLD_BOOST_CONTINUOUS_VERIFICATION_STUB.md). Here we inject it
# to exercise the boost path. Patch the registry, then have the node reload it.
echo "   patching $POPC_REGISTRY: gold_verified_days=120 for $CID_B (TEST FIXTURE)"
tmp=$(mktemp)
jq --arg cid "$CID_B" '(.commitments[] | select(.commitment_id==$cid) | .gold_verified_days) = 120' \
   "$POPC_REGISTRY" > "$tmp" && mv "$tmp" "$POPC_REGISTRY"
echo "   >>> restart the node (or trigger a registry reload) so it picks up the patched value, then press Enter"; read -r _
OUT_B=$(settle_and_report "$CID_B")
BASE_B=$(echo "$OUT_B" | jq -r '.result.base_reward'); BOOST_B=$(echo "$OUT_B" | jq -r '.result.gold_boost')
echo "   B base_reward=$BASE_B  gold_boost=$BOOST_B"
[ "$BASE_B" != "0" ] && [ "$BASE_B" != "0.00000000" ] || { echo "FAIL: base_reward must be > 0" >&2; exit 4; }
case "$BOOST_B" in 0|0.00000000) echo "WARN: boost=0 — check eligibility (gold>=max(25% bond,0.25oz)) and PoPC Pool surplus";; *) echo "   PASS: verified gold -> boost > 0";; esac

echo "== SOAK DONE =="
echo "Summary: A(snapshot) base=$BASE_A boost=$BOOST_A ; B(verified) base=$BASE_B boost=$BOOST_B"
echo "Expected: base>0 always; A boost=0; B boost>0 (given eligible gold + pool surplus)."
