#!/usr/bin/env bash
# SIGPIPE_REMOTE_DISCONNECT — permanent regression for the SIGPIPE remote-DoS fix.
# A peer that abruptly closes/RSTs while the node writes MUST NOT kill the node.
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
L=$(mktemp -d /tmp/sigreg.XXXXXX); d="$L/n"; PASS=0; FAIL=0
RES="$L/res"; :>"$RES"
ok(){ echo "  PASS  $*"; echo P>>"$RES"; }; bad(){ echo "  FAIL  $*"; echo F>>"$RES"; }
mkdir -p "$d"
"$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$d/c.json" --port 21903 --rpc-port 21904 --rpc-noauth --p2p-bind 127.0.0.61 --connect 127.0.0.1:1 >"$d/log" 2>&1 & NP=$!
trap 'kill $NP 2>/dev/null' EXIT
for _ in $(seq 1 15); do curl -s --max-time 2 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21904/ >/dev/null 2>&1 && break; sleep 1; done
FD0=$(ls /proc/$NP/fd 2>/dev/null|wc -l)
alive(){ kill -0 $NP 2>/dev/null && curl -s --max-time 4 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21904/ 2>/dev/null | grep -q result; }
scen(){ # $1=name ; reads python on stdin
  python3 - 2>/dev/null; sleep 1
  if alive; then local fd=$(ls /proc/$NP/fd 2>/dev/null|wc -l); ok "$1 — node+RPC ALIVE, FD=$fd"; else bad "$1 — node DIED (rc via wait: $(wait $NP 2>/dev/null; echo $?))"; fi
}
echo "=== SIGPIPE_REMOTE_DISCONNECT regression (port 21903) FD0=$FD0 ==="
echo 'import socket
c=socket.create_connection(("127.0.0.61",21903),timeout=1);c.sendall(b"\x54\x53\x4f\x53");c.close()' | scen "1 abrupt close"
echo 'import socket
[ (lambda c:(c.sendall(b"\x54\x53\x4f\x53"),c.close()))(socket.create_connection(("127.0.0.61",21903),timeout=1)) for _ in range(10)]' | scen "10 abrupt closes"
echo 'import socket
[ (lambda c:(c.sendall(b"\x54\x53\x4f\x53"),c.close()))(socket.create_connection(("127.0.0.61",21903),timeout=1)) for _ in range(100)]' | scen "100 abrupt closes"
echo 'import socket,threading
def one():
 try:
  c=socket.create_connection(("127.0.0.61",21903),timeout=1);c.sendall(b"\x54\x53\x4f\x53VERS");c.close()
 except: pass
ts=[threading.Thread(target=one) for _ in range(200)]
[t.start() for t in ts];[t.join() for t in ts]' | scen "burst (200 parallel)"
echo 'import socket,struct
# partial handshake then close: magic+VERS header claiming payload, send none, close
c=socket.create_connection(("127.0.0.61",21903),timeout=1);c.sendall(b"\x54\x53\x4f\x53VERS"+struct.pack("<I",41));c.close()' | scen "partial handshake + close"
echo 'import socket,time
# connect, let node start responding, then close mid-response
for _ in range(20):
 try:
  c=socket.create_connection(("127.0.0.61",21903),timeout=1);c.sendall(b"\x54\x53\x4f\x53VERS"+b"\x29\x00\x00\x00"+b"\x00"*41);time.sleep(0.02);c.close()
 except: pass' | scen "close during response"
echo 'import socket,struct
# RST: SO_LINGER 0 -> close sends RST instead of FIN
for _ in range(50):
 try:
  c=socket.create_connection(("127.0.0.61",21903),timeout=1)
  c.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack("ii",1,0))
  c.sendall(b"\x54\x53\x4f\x53");c.close()
 except: pass' | scen "RST (SO_LINGER 0)"
FD1=$(ls /proc/$NP/fd 2>/dev/null|wc -l)
[[ "$FD1" -lt $((FD0+10)) ]] && ok "FD stable end-to-end ($FD0 -> $FD1, no leak)" || bad "FD leak ($FD0 -> $FD1)"
[[ "$(grep -ciE 'abort|segfault|terminate|sanitizer' "$d/log")" -eq 0 ]] && ok "no crash keywords in log" || bad "crash in log"
[[ "$(wc -l <"$d/log")" -lt 2000 ]] && ok "no log flood ($(wc -l <"$d/log") lines)" || bad "log flood"
echo "SIGPIPE_REGRESSION: $(grep -c P "$RES") passed, $(grep -c F "$RES") failed"
