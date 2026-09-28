#!/usr/bin/env bash
# SACS P8-P9 — Delivery B: two segments split by MORE than MAX_REORG_DEPTH (=8)
# reconverge AUTOMATICALLY (no operator/checkpoint/quorum) when --sacs-recovery-mode
# is set, selecting the highest fully-validated work. Control: same split WITHOUT the
# flag stays permanently partitioned (the P2 reject_d9 behaviour). Devnet only; V16
# mainnet cap untouched.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"
trap 'rm -rf "$ROOT"' EXIT
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1" | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
str(){ echo "$1" | grep -oE '"result":"[0-9a-f]+"' | grep -oE '[0-9a-f]{16,}' | head -1; }
h(){ num "$(rpc $1 getblockcount)"; }
tip(){ str "$(rpc $1 getbestblockhash)"; }
softwait(){ ( sleep "$1" ) & wait $!; }
sw(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
snode(){ local REC=""; [ "${4:-}" = "rec" ] && REC="--sacs-recovery-mode"
  nice -n 19 "$BIN/sost-node" --profile dev --noseed $REC --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 300 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 3 >> "$1/miner.log" 2>&1; }
wr(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; }
wh(){ for i in $(seq 1 150); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; }
utxoroot(){ "$BIN/sost-node" --profile dev --dry-run-replay --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" 2>/dev/null | grep -oE 'utxo_set_root: [0-9a-f]+' | grep -oE '[0-9a-f]{16,}'; }

run(){ local NAME=$1 MODE=$2   # MODE = rec | norec
  local DA=$ROOT/$NAME/A DB=$ROOT/$NAME/B; rm -rf "$ROOT/$NAME"; mkdir -p "$DA" "$DB"
  printf p>"$DA/pass"; printf p>"$DB/pass"; chmod 600 "$DA/pass" "$DB/pass"; sw "$DA"; sw "$DB"
  echo "=================================================================="
  echo "RUN $NAME  (recovery-mode=$MODE)  A=10 blocks, B=9 blocks -> disconnect 9 (> cap 8)"
  echo "=================================================================="
  local RA="" RB=""; [ "$MODE" = "rec" ] && { RA=rec; RB=rec; }
  local NA=$(snode "$DA" 19931 19932 "$RA"); wr 19932; mine "$DA" 19932 10; wh 19932 10
  local NB=$(snode "$DB" 19941 19942 "$RB"); wr 19942; mine "$DB" 19942 9; wh 19942 9
  local TA=$(tip 19932) TBpre=$(tip 19942)
  echo "  PRE  A: h=$(h 19932) tip=$(echo $TA|cut -c1-16)  B: h=$(h 19942) tip=$(echo $TBpre|cut -c1-16)"
  python3 "$FEED" 19932 19942 10 >/dev/null; softwait 4
  local TBpost=$(tip 19942) HBpost=$(h 19942)
  echo "  REORG/ALERT LOG (B):"
  grep -E "SACS-RECOVERY|exceeds REORG_LIMIT|Disconnecting [0-9]+ blocks|Connecting [0-9]+ blocks|Success: new tip" "$DB/node.log" | tail -6 | sed 's/^/     /'
  echo "  POST B: h=$HBpost tip=$(echo $TBpost|cut -c1-16)   (A tip=$(echo $TA|cut -c1-16))"
  echo "  DEEP_REORG_ALERT events: $(rpc 19942 getsacsstatus | grep -oE '"DEEP_REORG_ALERT":[0-9]+')"
  kill -9 $NB 2>/dev/null; softwait 1
  local URA=$(utxoroot "$DA") URB=$(utxoroot "$DB")
  echo "  UTXO ROOT equal(A,B)=$([ "$URA" = "$URB" ] && echo YES || echo NO)"
  NB=$(snode "$DB" 19941 19942 "$RB"); wr 19942; softwait 1
  echo "  RESTART B: h=$(h 19942) tip=$(echo $(tip 19942)|cut -c1-16) stable=$([ "$(tip 19942)" = "$TBpost" ] && echo YES || echo NO)"
  kill -9 $NA $NB 2>/dev/null; softwait 1
  if [ "$MODE" = "rec" ]; then
    [ "$TBpost" = "$TA" ] && echo "  >>> $NAME: CONVERGED at depth 9 (> cap 8) — automatic reconvergence, no operator. PASS" || echo "  >>> $NAME: FAIL (expected convergence)"
  else
    [ "$TBpost" = "$TBpre" ] && [ "$TBpost" != "$TA" ] && echo "  >>> $NAME: STAYED SPLIT (control: hard cap rejects depth 9). PASS" || echo "  >>> $NAME: unexpected"
  fi
  echo
}
rm -rf "$ROOT"; mkdir -p "$ROOT"
run control_norecovery norec
run deliveryb_recovery rec
echo ALLDONE
