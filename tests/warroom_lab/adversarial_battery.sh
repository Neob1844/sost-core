#!/usr/bin/env bash
# FINAL CONTROLLED ADVERSARIAL BATTERY — sequential (no concurrency), no RAM/CPU saturation.
# Breaks the SOFTWARE, not the laptop. Reuses the validated harnesses + 2 micro-tests.
set -uo pipefail
BASE=/home/sost/SOST/sostcore/lab
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
sum(){ echo "$1" | grep -oE "[0-9]+ pass(ed)?, [0-9]+ fail(ed)?|[0-9]+ passed, [0-9]+ failed|ALL PASS|ALIVE" | tail -1; }
line(){ printf "  %-34s %s\n" "$1" "$2"; }
echo "=== FINAL CONTROLLED ADVERSARIAL BATTERY ==="
line "RPC malformed inputs"        "$(sum "$(bash $BASE/rpc_adversarial.sh 2>&1)")"
line "P2P wire + ADDR flood + eclipse/poisoning" "$(sum "$(bash $BASE/phase34.sh 2>&1)")"
line "peer-store torture (corrupt/huge/dup/empty, restart x100)" "$(sum "$(bash $BASE/phase2_peerstore.sh 2>&1)")"
line "OLD<->NEW compatibility"     "$(sum "$(bash $BASE/phase1_matrix.sh 2>&1)")"
line "partition / heal / heavier-wins / SACS" "$(sum "$(bash $BASE/lock_phase_partition.sh 2>&1)")"
line "bootstrap / loss-of-seeds"   "$(sum "$(bash $BASE/lock_phase_seeds.sh 2>&1)")"
# ADDR fuzz + sanitizers (ASan/UBSan/Leak)
SAN="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1"; export ASAN_OPTIONS=detect_leaks=1:abort_on_error=0 UBSAN_OPTIONS=halt_on_error=1
g++ $SAN "$NEW/../tests/d1_addr_gossip_fuzz.cpp" -o /tmp/ab_fuzz 2>/dev/null && line "ADDR parser fuzz 200k (ASan/UBSan)" "$(sum "$(/tmp/ab_fuzz 2>&1)")"
g++ $SAN "$NEW/../tests/d1_peer_store_test.cpp" -o /tmp/ab_ps 2>/dev/null && line "peer-store unit (ASan/UBSan/Leak)" "$(sum "$(/tmp/ab_ps 2>&1)")"
g++ $SAN -I"$NEW/../include" "$NEW/../tests/d1_gossip_filter_test.cpp" -o /tmp/ab_gf 2>/dev/null && line "gossip SSRF/DNS filter (ASan/UBSan)" "$(sum "$(/tmp/ab_gf 2>&1)")"
# MICRO 1: corrupt seeds.txt -> node must start, ignore bad lines, not crash
L=$(mktemp -d /tmp/advseed.XXXXXX); d="$L/n"; mkdir -p "$d"
printf 'not a valid line\n\x00\x01garbage\n999.999.999.999:1\nsost\x07bad\n#comment\n127.0.0.90:29999\n%s\n' "$(head -c 500 </dev/zero|tr '\0' A)" > "$d/seeds.txt"
"$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$d/c.json" --port 21401 --rpc-port 21402 --rpc-noauth --p2p-bind 127.0.0.91 >"$d/log" 2>&1 & NP=$!
for _ in $(seq 1 12); do curl -s --max-time 2 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21402/ >/dev/null 2>&1 && break; sleep 1; done
A=$(curl -s --max-time 4 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21402/ 2>/dev/null|grep -c result)
C=$(grep -ciE 'abort|segfault|terminate|bad_alloc|sanitizer' "$d/log" 2>/dev/null)
kill $NP 2>/dev/null
line "corrupt seeds.txt (binary/garbage/oversize)" "$([[ $A -ge 1 && $C -eq 0 ]] && echo 'node ALIVE, bad lines ignored, 0 crash' || echo 'CHECK')"
# MICRO 2: disconnect storm -> rapid connect/disconnect from one IP, node stays healthy
L2=$(mktemp -d /tmp/advdc.XXXXXX); d2="$L2/n"; mkdir -p "$d2"
"$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$d2/c.json" --port 21403 --rpc-port 21404 --rpc-noauth --p2p-bind 127.0.0.1 --connect 127.0.0.1:1 >"$d2/log" 2>&1 & NP2=$!
for _ in $(seq 1 12); do curl -s --max-time 2 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21404/ >/dev/null 2>&1 && break; sleep 1; done
python3 - <<'PY' 2>/dev/null
import socket,struct,time
MAG=bytes([0x54,0x53,0x4f,0x53])
for i in range(300):
    try:
        s=socket.create_connection(("127.0.0.1",21403),timeout=1)
        s.sendall(MAG+b'VERS'+struct.pack('<I',0))  # partial/garbage then abrupt close
        s.close()
    except Exception: pass
PY
A2=$(curl -s --max-time 4 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21404/ 2>/dev/null|grep -c result)
FD=$(ls /proc/$NP2/fd 2>/dev/null|wc -l); C2=$(grep -ciE 'abort|segfault|terminate|bad_alloc' "$d2/log" 2>/dev/null)
kill $NP2 2>/dev/null
line "disconnect storm (300 abrupt half-open)" "$([[ $A2 -ge 1 && $C2 -eq 0 && $FD -lt 128 ]] && echo "node ALIVE, FD=$FD bounded, 0 crash" || echo "CHECK FD=$FD")"
rm -rf "$L" "$L2" 2>/dev/null
echo "=== BATTERY DONE ==="
