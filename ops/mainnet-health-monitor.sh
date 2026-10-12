#!/usr/bin/env bash
# mainnet-health-monitor.sh — cross-observer health check for SOST MAINNET.
#
# It compares two independent *observers* of the one mainnet and reports any
# disagreement or degradation:
#
#   LOCAL   — the autossh tunnel on 127.0.0.1:<LOCAL_PORT> (default 18232) on
#             THIS host, which forwards to the mainnet node's RPC.
#   STRATO  — the production node on the VPS (root@212.132.108.244 via
#             ~/.ssh/sost_vps), queried over SSH against its own
#             127.0.0.1:<STRATO_PORT> (default 18232).
#
# Per observer it collects: node-alive, rpc-alive, height, tip hash, chainwork
# (only if the RPC exposes it — SOST's getblockchaininfo is auth-gated, so
# chainwork is usually "n/a"; this is reported honestly, never invented),
# last-block age, peer count, mempool size, version, and a block-acceptance
# proxy (did the tip advance since the previous sample). It then hands the
# combined snapshot to ops/mainnet_health_detect.py, which labels:
#   TIP_DIVERGENCE HEIGHT_STALL NODE_DOWN PEER_DROP RPC_FAILURE
#   CHAINWORK_DIVERGENCE OLD_VERSION   and raises ALERT on any disagreement.
#
# ===== HARD SAFETY INVARIANTS =====
#   * READ-ONLY. Only read-only JSON-RPC methods are called (getblockcount,
#     getbestblockhash, getblock, getpeerinfo, getmempoolinfo, getinfo,
#     and — if creds are supplied — getblockchaininfo). It NEVER writes,
#     submits, restarts, stops, kills, or reconfigures anything.
#   * MAINNET ONLY. It talks to port 18232 / STRATO. It NEVER binds a port,
#     NEVER starts a listener, and NEVER targets a devnet/regtest node.
#   * NO SECRETS PRINTED. If an RPC password file is supplied it is read into
#     a variable for the curl -u call only; it is never echoed or logged.
#
# Usage:
#   ops/mainnet-health-monitor.sh                 # one sample, human report
#   ops/mainnet-health-monitor.sh --json          # one sample, JSON findings
#   ops/mainnet-health-monitor.sh --local-only    # skip the SSH/STRATO leg
#   ops/mainnet-health-monitor.sh --help
#
# Env overrides (all optional):
#   LOCAL_PORT=18232  STRATO_PORT=18232
#   SSH_HOST=root@212.132.108.244  SSH_KEY=~/.ssh/sost_vps  SSH_TIMEOUT=10
#   RPC_USER=AdminNeoB  RPC_PASS_FILE=/etc/sost/rpc.pass   (STRATO-side, for chainwork)
#   STALL_SECS=1800  MIN_PEERS=1  MAX_HEIGHT_GAP=2  EXPECTED_VERSION=
#   HISTORY=~/.sost/mainnet-health-history.jsonl   (rolling, light, append-only)
#
# Exit: 0 = OK, 1 = ALERT (condition detected), 2 = usage/precondition error.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$HERE/mainnet_health_detect.py"

LOCAL_PORT="${LOCAL_PORT:-18232}"
STRATO_PORT="${STRATO_PORT:-18232}"
SSH_HOST="${SSH_HOST:-root@212.132.108.244}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/sost_vps}"
SSH_TIMEOUT="${SSH_TIMEOUT:-10}"
RPC_USER="${RPC_USER:-AdminNeoB}"
RPC_PASS_FILE="${RPC_PASS_FILE:-/etc/sost/rpc.pass}"
STALL_SECS="${STALL_SECS:-1800}"
MIN_PEERS="${MIN_PEERS:-1}"
MAX_HEIGHT_GAP="${MAX_HEIGHT_GAP:-2}"
EXPECTED_VERSION="${EXPECTED_VERSION:-}"
HISTORY="${HISTORY:-$HOME/.sost/mainnet-health-history.jsonl}"
HISTORY_MAX="${HISTORY_MAX:-500}"   # keep the last N samples only

JSON_OUT=0
LOCAL_ONLY=0
for a in "$@"; do
  case "$a" in
    --json)       JSON_OUT=1 ;;
    --local-only) LOCAL_ONLY=1 ;;
    -h|--help)    sed -n '2,45p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $a (see --help)" >&2; exit 2 ;;
  esac
done

NOW_EPOCH="$(date -u +%s)"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- tiny JSON field extractors (no jq dependency; robust enough for these) --
jq_num() { grep -oE "\"$2\":[0-9]+" <<<"$1" | head -1 | grep -oE '[0-9]+'; }
jq_str() { grep -oE "\"$2\":\"[0-9a-zA-Z._-]+\"" <<<"$1" | head -1 | sed 's/.*:"//; s/"$//'; }

# Build one observer JSON object from a "caller" that runs an RPC method.
# $1 = observer name, $2 = rpc runner function name.
build_observer() {
  local name="$1" run="$2"
  local reachable="true" rpc_alive="false" node_alive="false"
  local height="null" tip="null" chainwork="null" age="null"
  local peers="null" mempool="null" version="null" accept="null" err="null"

  local gi bc bbh blk pinfo minfo bcinfo
  gi="$("$run" getinfo '[]')"
  if [ -z "$gi" ]; then
    reachable="false"; err="\"observer unreachable (no RPC response)\""
  else
    bc="$(jq_num "$gi" blocks)"
    if [ -n "$bc" ]; then
      rpc_alive="true"; node_alive="true"; height="$bc"
      version="\"$(jq_str "$gi" version)\""
      peers="$(jq_num "$gi" connections)"
      mempool="$(jq_num "$gi" mempool_size)"
    else
      # getinfo answered but without blocks -> treat as RPC degraded
      err="\"getinfo returned no block height (RPC degraded?)\""
    fi

    if [ "$rpc_alive" = "true" ]; then
      bbh="$("$run" getbestblockhash '[]')"
      local th; th="$(grep -oE '[0-9a-f]{64}' <<<"$bbh" | head -1)"
      [ -n "$th" ] && tip="\"$th\""

      if [ -n "$th" ]; then
        blk="$("$run" getblock "[\"$th\"]")"
        local bt; bt="$(jq_num "$blk" time)"
        [ -n "$bt" ] && age="$(( NOW_EPOCH - bt ))"
      fi

      # chainwork: only if an authenticated getblockchaininfo answers.
      bcinfo="$("$run" getblockchaininfo '[]')"
      local cw; cw="$(grep -oE '"chainwork":"[0-9a-fx]+"' <<<"$bcinfo" | sed 's/.*:"//; s/"$//')"
      [ -n "$cw" ] && chainwork="\"$cw\""
    fi
  fi

  # block-acceptance proxy from rolling history: did the tip advance vs the
  # previous sample for THIS observer? (honest label; the authoritative reject
  # counter lives only in the node's own log, not over RPC).
  if [ "$height" != "null" ] && [ -f "$HISTORY" ]; then
    local prevh
    prevh="$(grep -oE "\"observer\":\"$name\"[^}]*\"height\":[0-9]+" "$HISTORY" 2>/dev/null | tail -1 | grep -oE '"height":[0-9]+' | grep -oE '[0-9]+')"
    if [ -n "${prevh:-}" ]; then
      if [ "$height" -gt "$prevh" ]; then accept='"advancing"';
      elif [ "$height" -eq "$prevh" ]; then accept='"flat-since-last-sample"';
      else accept='"height-went-backwards(REORG?)"'; fi
    fi
  fi

  printf '{"observer":"%s","reachable":%s,"rpc_alive":%s,"node_alive":%s,"height":%s,"tip_hash":%s,"chainwork":%s,"last_block_age_secs":%s,"peers":%s,"mempool":%s,"version":%s,"block_acceptance":%s,"error":%s}' \
    "$name" "$reachable" "$rpc_alive" "$node_alive" "${height:-null}" "$tip" "$chainwork" \
    "${age:-null}" "${peers:-null}" "${mempool:-null}" "$version" "$accept" "$err"
}

# --- LOCAL observer: curl the tunnel on 127.0.0.1:LOCAL_PORT (read-only) -----
run_local() { # $1 method  $2 params-json
  curl -s --max-time 8 -H 'content-type: application/json' \
    --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":$2}" \
    "http://127.0.0.1:$LOCAL_PORT/" 2>/dev/null
}

# --- STRATO observer: run the same read-only RPC over SSH on the VPS ---------
# Uses creds from RPC_PASS_FILE *on the VPS* so auth-gated getblockchaininfo
# (chainwork) can answer. The password is read remotely and never leaves the
# VPS / never printed here.
run_strato() { # $1 method  $2 params-json
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout="$SSH_TIMEOUT" "$SSH_HOST" \
      "pass=\$(cat '$RPC_PASS_FILE' 2>/dev/null); \
       auth=''; [ -n \"\$pass\" ] && auth=\"-u $RPC_USER:\$pass\"; \
       curl -s --max-time 8 \$auth -H 'content-type: application/json' \
         --data '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":$2}' \
         'http://127.0.0.1:$STRATO_PORT/'" 2>/dev/null
}

OBS_LOCAL="$(build_observer LOCAL run_local)"

OBSERVERS="$OBS_LOCAL"
if [ "$LOCAL_ONLY" -eq 0 ]; then
  # Pre-check SSH reachability so a down VPS reads as NODE_DOWN, not a crash.
  if ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
         -o ConnectTimeout="$SSH_TIMEOUT" "$SSH_HOST" true >/dev/null 2>&1; then
    OBS_STRATO="$(build_observer STRATO run_strato)"
  else
    OBS_STRATO="$(printf '{"observer":"STRATO","reachable":false,"rpc_alive":false,"node_alive":false,"height":null,"tip_hash":null,"chainwork":null,"last_block_age_secs":null,"peers":null,"mempool":null,"version":null,"block_acceptance":null,"error":"SSH to %s unavailable (BatchMode/ConnectTimeout failed)"}' "$SSH_HOST")"
  fi
  OBSERVERS="$OBS_LOCAL,$OBS_STRATO"
fi

SNAPSHOT="$(printf '{"ts":"%s","ts_epoch":%s,"thresholds":{"stall_secs":%s,"min_peers":%s,"max_height_gap":%s,"expected_version":%s},"observers":[%s]}' \
  "$NOW_ISO" "$NOW_EPOCH" "$STALL_SECS" "$MIN_PEERS" "$MAX_HEIGHT_GAP" \
  "$( [ -n "$EXPECTED_VERSION" ] && printf '"%s"' "$EXPECTED_VERSION" || printf 'null' )" \
  "$OBSERVERS")"

# --- rolling history (light, append-only, trimmed) ---------------------------
mkdir -p "$(dirname "$HISTORY")" 2>/dev/null || true
printf '%s\n' "$SNAPSHOT" >> "$HISTORY" 2>/dev/null || true
if [ -f "$HISTORY" ]; then
  tail -n "$HISTORY_MAX" "$HISTORY" > "$HISTORY.tmp" 2>/dev/null && mv "$HISTORY.tmp" "$HISTORY" 2>/dev/null || true
fi

# --- detect + render ---------------------------------------------------------
if [ ! -f "$DETECT" ]; then
  echo "WARN: detector not found at $DETECT — emitting raw snapshot only." >&2
  echo "$SNAPSHOT"
  exit 2
fi

if [ "$JSON_OUT" -eq 1 ]; then
  printf '%s' "$SNAPSHOT" | python3 "$DETECT" --snapshot - --json
else
  printf '%s' "$SNAPSHOT" | python3 "$DETECT" --snapshot -
fi
exit $?
