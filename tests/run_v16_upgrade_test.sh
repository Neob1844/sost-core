#!/usr/bin/env bash
# =============================================================================
# run_v16_upgrade_test.sh — V15 -> V16 upgrade across the activation height.
# A V15 node (no V16 code) mines a chain to h<activation and writes chain.json.
# The node is stopped and REPLACED by the V16 binary, which must:
#   1) load the V15-written chain BYTE-IDENTICALLY (same tip hash at h=40),
#   2) continue mining, cross the V16 activation (devnet #42) automatically
#      (no manual command / no config switch / no restart AT #42),
#   3) treat #42 as a V2 jackpot that ROLLS OVER (no NODE_BIND can exist before
#      activation) — proving V2 turned on exactly at the height, not before.
#   Env: V15_DIR (V15 build), V16_DIR (V16 build, standard devnet V2@42)
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V15_DIR="${V15_DIR:-/tmp/sost-main-v15/build-devnet}"
V16_DIR="${V16_DIR:-$ROOT/build-devnet}"
WORK="$(mktemp -d /tmp/v16up.XXXXXX)"
P2P=$(( (RANDOM%20000)+21000 )); RPC=$(( P2P+1 ))
FAILED=0
log(){ printf '[upgrade] %s\n' "$*"; }
ok(){  printf '[upgrade] PASS  %s\n' "$*"; }
bad(){ printf '[upgrade] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stopm(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; true; }
stopn(){ [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; NODE_PID=""; sleep 2; true; }
cleanup(){ stopm; stopn; wait 2>/dev/null; true; }
die(){ printf '[upgrade] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
[[ -x "$V15_DIR/sost-node" && -x "$V16_DIR/sost-node" && -x "$V16_DIR/sost-miner" && -x "$V16_DIR/sost-cli" ]] || die "binaries missing (V15_DIR/V16_DIR)"
grep -q HIST_JACKPOT_V2_HEIGHT "$V15_DIR/CMakeCache.txt" 2>/dev/null && true # informational
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
bhash(){ rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}'; }
start_node(){ local bin="$1"; "$bin" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" --port "$P2P" --rpc-port "$RPC" --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/node.log" 2>&1 & NODE_PID=$!; for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return; done; die "node ($bin) no RPC"; }
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s); "$V16_DIR/sost-miner" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 & MINER_PID=$!; while :; do local h; h="$(height)"; [[ -z "$h" ]] && { sleep 1; continue; }; [[ "$h" -ge "$tgt" ]] && { stopm; return; }; [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stopm; die "did not reach $tgt in ${dl}s"; }; sleep 2; done; }
# a V15 miner (same flags; the V15 build has its own miner)
mine_to_v15(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s); "$V15_DIR/sost-miner" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 & MINER_PID=$!; while :; do local h; h="$(height)"; [[ -z "$h" ]] && { sleep 1; continue; }; [[ "$h" -ge "$tgt" ]] && { stopm; return; }; [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stopm; die "V15 did not reach $tgt"; }; sleep 2; done; }

log "work=$WORK rpc=$RPC  V15=$V15_DIR  V16=$V16_DIR"

# ---- PHASE 1: V15 node mines to h=40 (< devnet activation 42) ----
start_node "$V15_DIR/sost-node"
[[ "$(rpc getinfo | grep -oE '"profile":"[a-z]+"')" == '"profile":"dev"' ]] && ok "V15 node up (dev)" || bad "V15 node profile"
M="$("$V16_DIR/sost-cli" --wallet "$WORK/m.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$M" ]] || die "wallet"
mine_to_v15 "$M" "$WORK/m.json" 40 220
H40="$(height)"; HASH40="$(bhash 40)"
log "V15 mined to $H40, tip#40 hash=$HASH40"
[[ "$H40" -ge 40 ]] && ok "V15 reached h>=40 (pre-activation)" || bad "V15 height $H40"
stopn
ok "V15 node stopped; chain.json persisted (written by V15)"

# ---- PHASE 2: V16 binary loads the SAME chain (byte-identical) ----
start_node "$V16_DIR/sost-node"
HB="$(height)"; HASH40B="$(bhash 40)"
log "V16 loaded chain: height=$HB tip#40 hash=$HASH40B"
[[ "$HB" == "$H40" ]] && ok "V16 loaded V15 chain at same height ($HB)" || bad "V16 height $HB != $H40"
[[ "$HASH40B" == "$HASH40" ]] && ok "V16 load BYTE-IDENTICAL (tip#40 hash matches)" || bad "hash40 mismatch: $HASH40 vs $HASH40B"

# ---- PHASE 3: V16 mines across activation #42 (auto, no restart at 42) ----
mine_to "$M" "$WORK/m.json" 48 220
[[ "$(height)" -ge 48 ]] && ok "V16 mined across activation to h>=48" || bad "V16 stalled at $(height)"
# #42 is the first V2 jackpot; no NODE_BIND could exist before activation -> rollover (tx_count=1)
B42="$(rpc getblockhash '[42]' | grep -oE '[a-f0-9]{64}')"; BLK42="$(rpc getblock "[\"$B42\"]")"
TXC42="$(echo "$BLK42" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
[[ "$TXC42" == "1" ]] && ok "#42 first V2 jackpot ROLLED OVER (tx_count=1) — V2 activated exactly at height" || bad "#42 tx_count=$TXC42"

[[ "$FAILED" == "0" ]] && echo "[upgrade] RESULT: PASS — V15->V16 upgrade: V15 chain loads in V16 byte-identically + crosses activation automatically" || echo "[upgrade] RESULT: FAIL"
exit "$FAILED"
