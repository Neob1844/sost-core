#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_mempool.sh — runtime mempool-isolation proof for the V15 jackpot.
#
# Proves at the REAL node/RPC boundary that a TX_TYPE_JACKPOT can never enter the
# mempool or be relayed — it is authorized ONLY as tx[1] inside a validated jackpot
# block. Mines a real DEVNET_FAST chain to the first jackpot, extracts the exact
# canonical jackpot transaction from the accepted block, and then tries to inject it
# (and variants) via sendrawtransaction. Every attempt must be rejected and the
# mempool must stay empty.
#
# Usage: tests/run_v15_devnet_mempool.sh [--rpc-port P] [--p2p-port P]
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any failure; datadir/logs preserved on failure.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC_PORT=18972; P2P_PORT=19972
while [[ $# -gt 0 ]]; do case "$1" in
  --rpc-port) RPC_PORT="$2"; shift 2;; --p2p-port) P2P_PORT="$2"; shift 2;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15mempool.XXXXXX")"
FIRST_J=24; FAILED=0; NODE_PID=""; MINER_PID=""
log(){ printf '[mempool] %s\n' "$*"; }
ok(){ printf '[mempool] PASS  %s\n' "$*"; }
bad(){ printf '[mempool] FAIL  %s\n' "$*"; FAILED=1; }
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; }
die(){ printf '[mempool] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
mempool_n(){ rpc getrawmempool | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(len(r) if isinstance(r,list) else 0)
except Exception: print(-1)'; }

"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node down"
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  MINER_PID=$!
  while :; do local h; h="$(height)"; [[ "$h" -ge "$tgt" ]] && { stop_miner; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stop_miner; die "stuck reaching $tgt"; }; sleep 2; done; }

log "mining to the first jackpot (A then B)…"
mine_to "$A" "$WORK/a.json" "$((FIRST_J-11))" 120
mine_to "$B" "$WORK/b.json" "$FIRST_J" 150
BH="$(rpc getblockhash "[$FIRST_J]" | grep -oE '[a-f0-9]{64}')"
JTXID="$(rpc getblock "[\"$BH\"]" | python3 -c 'import sys,json
d=json.load(sys.stdin); ids=d.get("result",{}).get("txids",[]); print(ids[1] if len(ids)>1 else "")')"
[[ -n "$JTXID" ]] || die "no jackpot tx in block $FIRST_J (baseline broken)"
ok "canonical jackpot mined at height $FIRST_J (txid $JTXID)"

# Extract the exact canonical jackpot raw hex from the accepted block.
JHEX="$(rpc getrawtransaction "[\"$JTXID\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",""); print(r if isinstance(r,str) else "")
except Exception: print("")')"
[[ -n "$JHEX" && "$JHEX" =~ ^[0-9a-fA-F]+$ ]] && ok "extracted canonical jackpot raw hex (${#JHEX} chars)" \
  || die "could not extract canonical jackpot hex (getrawtransaction)"

MP0="$(mempool_n)"
[[ "$MP0" == "0" ]] && ok "mempool empty before attacks" || bad "mempool not empty at start ($MP0)"

# --- attack: inject the EXACT canonical jackpot tx into the mempool ---
try_send(){ # try_send <label> <hex>
  local label="$1" hex="$2" resp code
  resp="$(rpc sendrawtransaction "[\"$hex\"]")"
  code="$(echo "$resp" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); print("ERR" if d.get("error") else ("OK" if d.get("result") else "ERR"))
except Exception: print("ERR")')"
  local mp; mp="$(mempool_n)"
  if [[ "$code" == "ERR" && "$mp" == "0" ]]; then
    ok "$label REJECTED and mempool still empty"
  else
    bad "$label accepted/changed mempool (code=$code mp=$mp) resp=$(echo "$resp" | head -c 200)"
  fi
}

# M1: byte-exact canonical jackpot submitted standalone (outside its block).
try_send "M1 exact canonical jackpot (standalone)" "$JHEX"
# M2: same hex re-submitted (idempotent rejection, no partial admission).
try_send "M2 canonical jackpot re-submitted" "$JHEX"
# M3: canonical jackpot with a flipped trailing byte (still tx_type JACKPOT → rejected by type).
JHEX_MUT="${JHEX:0:$((${#JHEX}-2))}$(printf '%02x' $(( (16#${JHEX: -2} + 1) & 0xff )))"
try_send "M3 mutated jackpot bytes (still TX_TYPE_JACKPOT)" "$JHEX_MUT"

MPF="$(mempool_n)"
[[ "$MPF" == "0" ]] && ok "final mempool empty (no jackpot ever admitted or relayed)" || bad "final mempool not empty ($MPF)"

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — TX_TYPE_JACKPOT cannot enter the mempool via RPC (consensus-only, block-context authorized)"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi
