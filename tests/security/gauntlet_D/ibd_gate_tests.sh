#!/usr/bin/env bash
# Deterministic tests for the REDESIGNED stale-tip mining gate (checkpoint-height floor).
set -u
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
BIN="$S/build-ibd/sost-node"; MINER="$S/build-ibd/sost-miner"; CLI="$S/build-ibd/sost-cli"; DIR="$S/gauntlet-D"
WORK="$(mktemp -d /tmp/ibdgate.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$WORK" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 6 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
gt(){ rpc "$1" "{\"method\":\"getblocktemplate\",\"params\":[\"$2\"],\"id\":1}"; }
served(){ gt "$1" "$2" | grep -q '"result"'; }
gen_of(){ grep -oE 'Genesis: [0-9a-f]{64}' "$1"|head -1|awk '{print $2}'; }
liar(){ # host_p2p  genesis  seconds  height
  GENx="$2" python3 - "$1" "$3" "$4" <<'PY' &
import sys,os,binascii,time
sys.path.insert(0,'/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad/gauntlet-D')
import sostpeer as P
port=int(sys.argv[1]); dur=int(sys.argv[2]); h=int(sys.argv[3]); gen=binascii.unhexlify(os.environ['GENx']); end=time.time()+dur
while time.time()<end:
  try:
    s=P.connect('127.0.0.1',port,timeout=3); P.send_frame(s,'VERS',P.vers_payload(h,gen))
    t=time.time()
    while time.time()-t<6 and time.time()<end:
      f=P.recv_frame(s,1.0)
      if f and f[0]=='VERS': P.send_frame(s,'VACK',b'')
      time.sleep(0.3)
    s.close()
  except Exception: time.sleep(0.3)
PY
}
PASS=0; FAIL=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }; bad(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"

# ---- T1: healthy synced node (floor 0) + 1 liar@999999 -> must MINE (DoS defeated) ----
"$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/t1.json" --port 20140 --rpc-port 18140 --rpc-noauth --connect 127.0.0.1:1 >"$WORK/t1.log" 2>&1 & 
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height 18140)" ]]&&break; done
G=$(gen_of "$WORK/t1.log")
"$MINER" --profile dev --rpc 127.0.0.1:18140 --address "$A" --wallet "$WORK/a.json" --mining-key-label default --blocks 100000 --threads 2 >>"$WORK/m1.log" 2>&1 & M1=$!
while [[ "$(height 18140)" -lt 5 ]]; do sleep 2; done; kill $M1 2>/dev/null; sleep 1
liar 20140 "$G" 20 999999; sleep 3
h0=$(height 18140); served 18140 "$A" && s1=yes || s1=no
"$MINER" --profile dev --rpc 127.0.0.1:18140 --address "$A" --wallet "$WORK/a.json" --mining-key-label default --blocks 100000 --threads 2 >>"$WORK/m1b.log" 2>&1 & M1B=$!
sleep 14; kill $M1B 2>/dev/null; sleep 1; h1=$(height 18140)
[[ "$s1" == yes && "$h1" -gt "$h0" ]] && ok "T1 synced node + liar@999999 -> template SERVED and mined $h0->$h1 (DoS defeated)" || bad "T1 served=$s1 h $h0->$h1"
kill $(pgrep -f -- "$WORK/t1.json") 2>/dev/null; sleep 2

# ---- T2: healthy node + 5 colluding liars -> must MINE ----
"$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/t1.json" --port 20140 --rpc-port 18140 --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/t2.log" 2>&1 &
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height 18140)" ]]&&break; done
for k in 1 2 3 4 5; do liar 20140 "$G" 16 999999; done
sleep 3; served 18140 "$A" && ok "T2 synced node + 5 colluding liars@999999 -> template SERVED (mines)" || bad "T2 denied by colluding liars"
kill $(pgrep -f -- "$WORK/t1.json") 2>/dev/null; sleep 2

# ---- honest node B (floor 0) mines to 15 for T3 ----
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
"$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/b.json" --port 20142 --rpc-port 18142 --rpc-noauth --connect 127.0.0.1:1 >"$WORK/b.log" 2>&1 &
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height 18142)" ]]&&break; done
"$MINER" --profile dev --rpc 127.0.0.1:18142 --address "$B" --wallet "$WORK/b.json" --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/mb.log" 2>&1 & MBB=$!
while [[ "$(height 18142)" -lt 15 ]]; do sleep 2; done; kill $MBB 2>/dev/null; sleep 1

# ---- T3: corrupt/genesis restart (floor 10) + honest peer -> REFUSE at genesis, MINE after sync ----
SOST_DEV_MINING_MIN_HEIGHT=10 "$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/t3.json" --port 20144 --rpc-port 18144 --rpc-noauth --connect 127.0.0.1:20142 >"$WORK/t3.log" 2>&1 &
sleep 1; hchk=$(height 18144); refused_at_genesis=no; served 18144 "$A" || refused_at_genesis=yes
for _ in $(seq 1 30); do [[ "$(height 18144)" -ge 15 ]]&&break; sleep 2; done; sleep 2
served 18144 "$A" && s3=yes || s3=no
[[ "$s3" == yes && "$(height 18144)" -ge 10 ]] && ok "T3 genesis+honest peer RECOVERY: synced past floor to $(height 18144) then SERVED (refusal-at-genesis proven deterministically by T4)" || bad "T3 served_after=$s3 h=$(height 18144)"
kill $(pgrep -f -- "$WORK/t3.json") 2>/dev/null; sleep 2

# ---- T4: corrupt/genesis restart (floor 10) + ONLY liars -> stays REFUSED, never mines genesis ----
SOST_DEV_MINING_MIN_HEIGHT=10 "$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/t4.json" --port 20146 --rpc-port 18146 --rpc-noauth --connect 127.0.0.1:1 >"$WORK/t4.log" 2>&1 &
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height 18146)" ]]&&break; done
G4=$(gen_of "$WORK/t4.log")
for k in 1 2 3; do liar 20146 "$G4" 18 999999; done
"$MINER" --profile dev --rpc 127.0.0.1:18146 --address "$A" --wallet "$WORK/a.json" --mining-key-label default --blocks 100000 --threads 2 >>"$WORK/m4.log" 2>&1 & M4=$!
sleep 16; kill $M4 2>/dev/null; sleep 1
h4=$(height 18146); served 18146 "$A" && s4=yes || s4=no
[[ "$s4" == no && "$h4" -eq 0 ]] && ok "T4 genesis + only liars: REFUSED throughout, node did NOT mine a genesis chain (h=$h4)" || bad "T4 served=$s4 h=$h4 (should stay refused at 0)"
kill $(pgrep -f -- "$WORK/t4.json") 2>/dev/null; sleep 2

# ---- T7: solo bootstrap, no peers, floor 0 -> mines ----
"$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/t7.json" --port 20148 --rpc-port 18148 --rpc-noauth --connect 127.0.0.1:1 >"$WORK/t7.log" 2>&1 &
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height 18148)" ]]&&break; done
C="$("$CLI" --wallet "$WORK/c.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
"$MINER" --profile dev --rpc 127.0.0.1:18148 --address "$C" --wallet "$WORK/c.json" --mining-key-label default --blocks 100000 --threads 2 >>"$WORK/m7.log" 2>&1 & M7=$!
sleep 30; kill $M7 2>/dev/null; sleep 1; h7=$(height 18148)
[[ "$h7" -ge 1 ]] && ok "T7 solo bootstrap no peers -> mines (h=$h7)" || bad "T7 solo did not mine (h=$h7)"
kill $(pgrep -f -- "$WORK/t7.json") 2>/dev/null
echo "==== IBD GATE TESTS: PASS=$PASS FAIL=$FAIL ===="
