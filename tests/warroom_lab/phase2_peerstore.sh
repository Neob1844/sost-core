#!/usr/bin/env bash
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
PASS=0; FAIL=0
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
rpc(){ curl -s --max-time 6 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" getblockcount | grep -oE '[0-9]+' | head -1; }
# start a node with a given peers.txt content, confirm it boots (RPC answers) and doesn't crash
boot_with_peers(){ local label="$1" content="$2"; local dd=$(mktemp -d /tmp/ps.XXXXXX)
  printf '%b' "$content" > "$dd/peers.txt"
  "$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$dd/chain.json" --port 0 --rpc-port 20490 --rpc-noauth --connect 127.0.0.1:1 >"$dd/node.log" 2>&1 & local pid=$!
  local up=0; for _ in $(seq 1 15); do [[ -n "$(height 20490)" ]] && { up=1; break; }; sleep 1; done
  local crash=0; grep -qiE "Segmentation|abort|terminate|ASAN|runtime error|std::bad_alloc" "$dd/node.log" && crash=1
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  if [[ $up -eq 1 && $crash -eq 0 ]]; then ok "$label — node booted, no crash"; else bad "$label — up=$up crash=$crash ($(tail -1 $dd/node.log))"; fi
  rm -rf "$dd"; }
echo "=== PHASE 2 — PEER STORE TORTURE ==="
boot_with_peers "empty peers.txt" ""
boot_with_peers "garbage random" "$(head -c 500 /dev/urandom | base64)"
boot_with_peers "no colon lines" "hostonly\nanotherhost\n"
boot_with_peers "huge line (10k)" "$(python3 -c 'print("a"*10000+":19333")')"
boot_with_peers "400 entries (>256 cap)" "$(python3 -c 'print("\n".join("10.0.%d.%d:19333"%(i//256,i%256) for i in range(400)))')"
boot_with_peers "invalid ports" "1.2.3.4:99999\n5.6.7.8:-1\n9.9.9.9:abc\n"
boot_with_peers "control chars" "$(printf '1.2.3.4:19333\n\x01\x02bad:1\n')"
boot_with_peers "duplicates" "$(python3 -c 'print("\n".join(["1.2.3.4:19333"]*300))')"
boot_with_peers "IPv6-ish" "[::1]:19333\nfe80::1:19333\n"
boot_with_peers "incomplete tmp present" "1.2.3.4:19333\n"
echo "=== PHASE 2: $PASS passed, $FAIL failed ==="
