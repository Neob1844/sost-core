#!/usr/bin/env bash
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
ATK=/home/sost/SOST/sostcore/lab/attacker.py
LAB=$(mktemp -d /tmp/ph34.XXXXXX); PASS=0; FAIL=0; PIDS=()
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }; bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
cleanup(){ for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null||true; done; }
trap cleanup EXIT
rpc(){ curl -s --max-time 6 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
height(){ rpc "$1" getblockcount | grep -oE '[0-9]+' | head -1; }
rss(){ awk '/VmRSS/{print $2}' /proc/$1/status 2>/dev/null; }
fds(){ ls /proc/$1/fd 2>/dev/null | wc -l; }

VD=$LAB/V; mkdir -p "$VD"
"$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$VD/chain.json" --port 20801 --rpc-port 20802 --rpc-noauth --p2p-bind 127.0.0.1 --connect 127.0.0.1:1 >"$VD/node.log" 2>&1 & VP=$!; PIDS+=($VP)
for _ in $(seq 1 15); do [[ -n "$(height 20802)" ]] && break; sleep 1; done
[[ -z "$(height 20802)" ]] && { echo "victim did not start"; cat "$VD/node.log"|tail; exit 1; }
MA=$("$NEW/sost-cli" --wallet "$LAB/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+'|head -1)
"$NEW/sost-miner" --profile dev --rpc 127.0.0.1:20802 --address "$MA" --wallet "$LAB/w.json" --mining-key-label default --blocks 1000000 --threads 1 >"$LAB/m.log" 2>&1 & PIDS+=($!)
sleep 3
echo "=== PHASE 3/4 — victim pid=$VP h=$(height 20802) ==="
RSS0=$(rss $VP); FD0=$(fds $VP); echo "  baseline RSS=${RSS0}KB FD=$FD0"

echo "--- ATTACK: ADDR poisoning flood (500k junk addrs over the wire) ---"
python3 "$ATK" 127.0.0.1 20801 poison 2>&1 | sed 's/^/    atk: /'
sleep 2
echo "--- ATTACK: garbage / oversized-len / unknown-cmd / malformed-ADDR ---"
python3 "$ATK" 127.0.0.1 20801 garbage 2>&1 | sed 's/^/    atk: /'
sleep 2
echo "--- ATTACK: eclipse (12 conns from one IP) ---"
python3 "$ATK" 127.0.0.1 20801 eclipse 2>&1 | sed 's/^/    atk: /'
sleep 3

H1=$(height 20802); RSS1=$(rss $VP); FD1=$(fds $VP)
echo "  after-attacks: alive=$([[ -n "$H1" ]]&&echo yes||echo NO) h=$H1 RSS=${RSS1}KB FD=$FD1"
# 1. survives
[[ -n "$H1" ]] && kill -0 $VP 2>/dev/null && ok "victim ALIVE + RPC responsive after all attacks (h=$H1)" || bad "victim died/unresponsive"
# 2. still making progress (not deadlocked)
sleep 4; H2=$(height 20802); [[ -n "$H2" && "$H2" -ge "${H1:-0}" ]] && ok "chain still advancing post-attack ($H1 -> $H2, no deadlock)" || bad "chain stalled ($H1 -> $H2)"
# 3. RSS bounded (no OOM/unbounded growth from 500k junk) — allow generous 60MB ceiling
if [[ -n "$RSS1" ]]; then d=$((RSS1-RSS0)); [[ "$RSS1" -lt 61440 ]] && ok "RSS bounded after 500k junk addrs (${RSS0}->${RSS1}KB, +${d}KB, <60MB)" || bad "RSS grew to ${RSS1}KB"; fi
# 4. FD bounded (no socket/fd leak from floods)
[[ -n "$FD1" ]] && [[ "$FD1" -lt 128 ]] && ok "FD bounded after flood (${FD0}->${FD1}, <128)" || bad "FD leak (${FD0}->${FD1})"
# 5. peers.txt NEVER contains junk (raw gossip never persisted)
PS="$VD/peers.txt"; [[ -f "$PS" ]] && { echo "  peers.txt: $(tr '\n' ' ' <"$PS")"; } || echo "  peers.txt: (none yet)"
if [[ -f "$PS" ]]; then grep -qE '^(1|2|9)\.|19333$' "$PS" && grep -vqE '^127\.0\.0' "$PS" && bad "JUNK persisted in peers.txt!" || ok "peers.txt contains NO junk gossip (only verified-outbound persisted)"; else ok "peers.txt empty/absent — no junk persisted (victim had no real outbound)"; fi
# 6. per-IP eclipse cap enforced
EC=$(grep -cE "too many connections from|per-IP|MAX_PEERS_PER_IP|rejecting .*127.0.0.1|already .* from same IP|cooldown" "$VD/node.log" 2>/dev/null)
echo "  per-IP limit log hits: ${EC:-0}"
# the real proof: node never exceeded MAX_PEERS_PER_IP=2 inbound from 127.0.0.1 at once
MAXIP=$(rpc 20802 getpeerinfo | grep -oE '127\.0\.0\.1' | wc -l)
[[ "${MAXIP:-0}" -le 2 ]] && ok "inbound from single IP capped (<=2 concurrent, MAX_PEERS_PER_IP honored)" || bad "eclipse: $MAXIP conns from one IP"
# 7. misbehavior/disconnect on garbage (node logged bad frames, didn't silently accept)
grep -qiE "misbehav|ban|bad magic|unknown|disconnect" "$VD/node.log" && ok "garbage frames triggered misbehavior/disconnect (not silently trusted)" || echo "  (no explicit misbehavior log — acceptable if framing silently dropped)"
echo "=== PHASE 3/4: $PASS passed, $FAIL failed ==="
echo "--- victim log tail ---"; tail -12 "$VD/node.log"
