#!/usr/bin/env bash
# sost-relay-watchdog — keeps a NON-MINING relay node following the chain.
#
# Why it exists (v16.3.0, verified in lab): a node only refreshes a peer's height
# from that peer's VERSION message and from blocks it ACCEPTS from that peer. A
# relay node never originates blocks, so the node it follows keeps its handshake
# height forever and, 50 blocks later (~8 h at 600 s), stops relaying to it as
# "still syncing". The relay stays connected, stops advancing, and nothing in the
# node recovers it. A restart re-sends VERSION, which resets that height and
# catches up with GETB. Restart is also what clears the two other stalls seen in
# the lab (orphan dead-end, missed redial). This script only ever restarts the
# relay node it runs next to; it never touches the reference node.
#
# Fixed at the source (sender side) on branch lab/p2p-static-peers; this timer
# becomes unnecessary once the reference node runs that fix.
#
# Config (environment, e.g. from /etc/sost/relay.env):
#   LOCAL_RPC     local node RPC            (default http://127.0.0.1:$RPC_PORT/, RPC_PORT default 18232)
#   LOCAL_AUTH    user:pass for local RPC   (default: read from RPC_USER + /etc/sost/rpc.pass)
#   REF_RPC       reference height source   (default https://sostcore.com/rpc/public)
#   MAX_LAG       blocks behind before acting          (default 2)
#   STRIKES       consecutive lagging checks required  (default 2)
#   MIN_GAP_S     minimum seconds between restarts     (default 900)
#   RESTART_CMD   how to restart the node   (default: systemctl restart sost-relay-node)
#   STATE         state file                (default /var/lib/sost-relay-watchdog/state)
set -uo pipefail
LOCAL_RPC="${LOCAL_RPC:-http://127.0.0.1:${RPC_PORT:-18232}/}"
REF_RPC="${REF_RPC:-https://sostcore.com/rpc/public}"
MAX_LAG="${MAX_LAG:-2}"; STRIKES="${STRIKES:-2}"; MIN_GAP_S="${MIN_GAP_S:-900}"
RESTART_CMD="${RESTART_CMD:-systemctl restart sost-relay-node}"
STATE="${STATE:-/var/lib/sost-relay-watchdog/state}"
if [[ -z "${LOCAL_AUTH:-}" && -r /etc/sost/rpc.pass ]]; then
  LOCAL_AUTH="${RPC_USER:-sost}:$(cat /etc/sost/rpc.pass)"
fi

height(){ # height <url> [auth]
  local args=(-s -m 15 -H 'content-type: application/json'
              --data '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}')
  [[ -n "${2:-}" ]] && args+=(-u "$2")
  curl "${args[@]}" "$1" | python3 -c 'import sys,json
try:
  r=json.load(sys.stdin)["result"]; print(r if isinstance(r,int) else "")
except Exception: print("")'
}
log(){ echo "[relay-watchdog] $*"; }

mkdir -p "$(dirname "$STATE")"
strikes=0; last_restart=0
[[ -r "$STATE" ]] && read -r strikes last_restart < "$STATE" || true
strikes=${strikes:-0}; last_restart=${last_restart:-0}

ref=$(height "$REF_RPC")
loc=$(height "$LOCAL_RPC" "${LOCAL_AUTH:-}")
now=$(date +%s)

if [[ -z "$ref" ]]; then
  # No reference: never act on missing information.
  log "reference unreachable ($REF_RPC); no action"; exit 0
fi
if [[ -z "$loc" ]]; then
  # Local RPC down or still loading: systemd's Restart= owns process death.
  log "local RPC not answering; leaving it to systemd"; exit 0
fi

lag=$(( ref - loc ))
if (( lag >= MAX_LAG )); then strikes=$((strikes+1)); else strikes=0; fi
log "local=$loc ref=$ref lag=$lag strikes=$strikes/$STRIKES"

if (( strikes >= STRIKES )); then
  if (( now - last_restart < MIN_GAP_S )); then
    log "lagging but last restart was $((now-last_restart))s ago (< ${MIN_GAP_S}s); waiting"
  else
    log "restarting local node: $RESTART_CMD"
    $RESTART_CMD && last_restart=$now
    strikes=0
  fi
fi
echo "$strikes $last_restart" > "$STATE"
