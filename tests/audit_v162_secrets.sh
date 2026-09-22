#!/usr/bin/env bash
# =============================================================================
# audit_v162_secrets.sh — the V16.2.0 credential promises, checked against the
# RELEASE binaries rather than against a report.
#
# Everything here runs on throwaway wallets, throwaway keys and a throwaway
# devnet on random high ports. It never reads, converts or touches a real
# wallet, never uses the production RPC port, and kills only the PIDs it
# started itself.
#
#   Env: BIN (directory holding sost-node / sost-miner / sost-cli)
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${BIN:-/home/sost/SOST/sostcore/rel-v162-a/build}"
NODE="$BIN/sost-node"; MINER="$BIN/sost-miner"; CLI="$BIN/sost-cli"
W="$(mktemp -d /tmp/v162audit.XXXXXX)"
P2P=$(( (RANDOM % 9000) + 34000 )); RPC=$(( P2P + 1 ))
PASS=0; FAIL=0
ok(){   printf '  [PASS] %s\n' "$*"; PASS=$((PASS+1)); }
bad(){  printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
sect(){ printf '\n=== %s ===\n' "$*"; }
NODE_PID=""
cleanup(){ [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; true; }
trap cleanup EXIT
for f in "$NODE" "$MINER" "$CLI"; do [[ -x "$f" ]] || { echo "FATAL missing $f"; exit 1; }; done

echo "binaries under audit:"
sha256sum "$NODE" "$MINER" "$CLI" | sed 's/^/  /'

# The RPC secret for this devnet. Random, disposable, never printed.
RPCPASS="auditoria-$RANDOM$RANDOM$RANDOM"
umask 077
printf '%s\n' "$RPCPASS" > "$W/rpc.pass"
printf '%s\n' "$RPCPASS" > "$W/rpc644.pass"; chmod 644 "$W/rpc644.pass"
printf 'no-es-la-buena\n' > "$W/rpcbad.pass"

rpcq(){ curl -s --max-time 15 -H 'content-type: application/json' \
         --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
rpca(){ curl -s --max-time 15 -u "AdminAudit:$1" -H 'content-type: application/json' \
         --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
hgt(){ rpcq getblockcount | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["result"])
except Exception: print("")'; }

sect "NODE — RPC credential out of argv"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/chain.json" \
  --port "$P2P" --rpc-port "$RPC" --rpc-user AdminAudit --rpc-pass-file "$W/rpc.pass" \
  --connect 127.0.0.1:1 >"$W/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(hgt)" ]] && break; done
[[ -n "$(hgt)" ]] && ok "node starts from --rpc-pass-file" || { bad "node did not start"; exit 1; }
tr '\0' ' ' < "/proc/$NODE_PID/cmdline" | grep -qF "$RPCPASS" \
  && bad "the RPC password IS in the node's argv" || ok "the RPC password is not in the node's argv"
rpca "$RPCPASS" sendrawtransaction '["00"]' | grep -q '"code":-22' \
  && ok "the node authenticates with the password from the file" || bad "authenticated call failed"
rpca "contrasena-mala" sendrawtransaction '["00"]' | grep -q '"code":-401' \
  && ok "a wrong password is rejected with 401" || bad "a wrong password was NOT rejected"
timeout 25 "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c2.json" \
  --port $((P2P+20)) --rpc-port $((RPC+20)) --rpc-user AdminAudit \
  --rpc-pass-file "$W/rpc644.pass" >"$W/node644.log" 2>&1
grep -q "readable by group or others" "$W/node644.log" \
  && ok "the node REFUSES to start from a world-readable secret file" || bad "the node accepted a 644 secret file"
grep -qF "$RPCPASS" "$W/node644.log" && bad "the refusal echoed the secret" || ok "the refusal never echoes the secret"

sect "WALLETS — v1 keeps working, v2 preserves the identity"
V1ADDR=$("$CLI" --wallet "$W/v1.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
[[ -n "$V1ADDR" ]] && ok "throwaway v1 wallet created ($V1ADDR)" || bad "could not create a v1 wallet"
printf 'frase-de-paso-de-prueba-9876\n' > "$W/pp"
printf 'frase-equivocada\n' > "$W/ppbad"
"$CLI" --wallet "$W/v1.json" wallet-export --encrypted --output "$W/v2.json" --passphrase-fd 5 5<"$W/pp" >"$W/export.log" 2>&1
[[ -s "$W/v2.json" ]] && ok "wallet-export --passphrase-fd produced an encrypted wallet" || bad "wallet-export failed"
python3 -c "import json,sys;d=json.load(open('$W/v2.json'));sys.exit(0 if d.get('version')==2 and d.get('encrypted') else 1)" \
  && ok "the exported wallet is version 2 / encrypted" || bad "the exported wallet is not v2"
grep -qF 'frase-de-paso-de-prueba-9876' "$W/v2.json" "$W/export.log" \
  && bad "the passphrase appears in the file or the output" || ok "the passphrase appears in neither the file nor the output"
python3 -c "import json,sys;d=json.load(open('$W/v2.json'));sys.exit(0 if 'privkey' not in json.dumps(d) else 1)" \
  && ok "no plaintext private key survives in the v2 file" || bad "a plaintext key is still in the v2 file"

# echo OFF: with no tty and no --passphrase-fd it must refuse, never read blindly
echo "una-frase" | "$CLI" --wallet "$W/v1.json" wallet-export --encrypted --output "$W/never.json" >"$W/noTTY.log" 2>&1
grep -q "not a terminal" "$W/noTTY.log" && ok "wallet-export refuses when it cannot turn the echo off" \
                                        || bad "wallet-export read a passphrase with echo on"
[[ ! -f "$W/never.json" ]] && ok "...and wrote nothing" || bad "...but wrote a file anyway"

"$CLI" --wallet "$W/v2back.json" newwallet >/dev/null 2>&1
"$CLI" --wallet "$W/v2back.json" wallet-import --encrypted --input "$W/v2.json" --passphrase-fd 5 5<"$W/pp" >/dev/null 2>&1
diff <("$CLI" --wallet "$W/v1.json" listaddresses 2>/dev/null) \
     <("$CLI" --wallet "$W/v2back.json" listaddresses 2>/dev/null) >/dev/null \
  && ok "export -> import round-trips to the SAME addresses" || bad "the round trip changed the addresses"

"$CLI" --wallet "$W/v2bad.json" newwallet >/dev/null 2>&1
"$CLI" --wallet "$W/v2bad.json" wallet-import --encrypted --input "$W/v2.json" --passphrase-fd 5 5<"$W/ppbad" >"$W/imp.log" 2>&1
grep -qi "decryption failed\|wrong passphrase" "$W/imp.log" && ok "a wrong passphrase is refused on import" \
                                                            || bad "a wrong passphrase was accepted"
# a damaged file must fail as damaged, not as a wrong passphrase and not as a crash
head -c $(( $(stat -c %s "$W/v2.json") / 2 )) "$W/v2.json" > "$W/v2trunc.json"
"$CLI" --wallet "$W/v2bad.json" wallet-import --encrypted --input "$W/v2trunc.json" --passphrase-fd 5 5<"$W/pp" >"$W/imptrunc.log" 2>&1
rc=$?
[[ $rc -ne 0 ]] && ok "a truncated wallet file is rejected (exit $rc)" || bad "a truncated wallet file was accepted"
grep -qiE "segmentation|core dumped|terminate called" "$W/imptrunc.log" \
  && bad "it crashed on damaged input" || ok "...without crashing"

sect "MINER — v1 and v2 wallets, RPC credential out of argv"
mine(){ # mine <wallet> <extra-args...> ; blocks=1
  local wal="$1"; shift
  timeout 300 "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --rpc-user AdminAudit \
    --address "$V1ADDR" --wallet "$wal" --mining-key-label default \
    --blocks 1 --threads 3 "$@" 2>&1
}
H0=$(hgt)
mine "$W/v1.json" --rpc-pass-fd 6 6<"$W/rpc.pass" >"$W/m_v1.log" 2>&1
grep -q "submitted to node OK" "$W/m_v1.log" && ok "a v1 (plaintext) wallet still mines" || bad "the v1 wallet did not mine"
grep -q "UNENCRYPTED (v1) wallet" "$W/m_v1.log" && ok "...and the miner warns about it once" || bad "no v1 warning"

H1=$(hgt)
mine "$W/v2.json" --rpc-pass-file "$W/rpc.pass" --wallet-passphrase-file "$W/pp" >"$W/m_v2.log" 2>&1
grep -q "submitted to node OK" "$W/m_v2.log" && ok "an ENCRYPTED (v2) wallet mines unattended" || bad "the v2 wallet did not mine"
V2ADDR=$(grep -oE 'sost1[a-z0-9]{20,}' "$W/m_v2.log" | head -1)
[[ "$V2ADDR" == "$V1ADDR" ]] && ok "the SbPoW identity and payout address are unchanged by encryption" \
                             || bad "encryption changed the address: $V1ADDR -> $V2ADDR"
grep -qF 'frase-de-paso-de-prueba-9876' "$W/m_v2.log" && bad "the passphrase leaked into the miner log" \
                                                      || ok "the passphrase never appears in the miner log"
grep -qF "$RPCPASS" "$W/m_v1.log" "$W/m_v2.log" && bad "the RPC password leaked into a miner log" \
                                                 || ok "the RPC password never appears in a miner log"

timeout 60 "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --rpc-user AdminAudit \
  --rpc-pass-file "$W/rpc.pass" --address "$V1ADDR" --wallet "$W/v2.json" \
  --mining-key-label default --wallet-passphrase-file "$W/ppbad" --blocks 1 >"$W/m_badpp.log" 2>&1
grep -qi "cannot decrypt" "$W/m_badpp.log" && ok "a wrong wallet passphrase stops the miner before it mines" \
                                           || bad "the miner started with a wrong passphrase"

timeout 120 "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --rpc-user AdminAudit \
  --rpc-pass-file "$W/rpcbad.pass" --address "$V1ADDR" --wallet "$W/v1.json" \
  --mining-key-label default --blocks 1 --threads 3 >"$W/m_bad401.log" 2>&1
grep -q "RPC AUTHENTICATION REJECTED" "$W/m_bad401.log" \
  && ok "a wrong RPC password is reported AS an authentication failure" || bad "the 401 was not explained"
H2=$(hgt)

timeout 25 "$MINER" --profile dev --rpc 127.0.0.1:1 --rpc-user u --rpc-pass x --rpc-pass-file "$W/rpc.pass" \
  --address "$V1ADDR" --wallet "$W/v1.json" --mining-key-label default --blocks 1 >"$W/m_excl.log" 2>&1
grep -q "use only one of" "$W/m_excl.log" && ok "the three RPC password sources are mutually exclusive" \
                                          || bad "two password sources were accepted at once"
timeout 25 "$MINER" --profile dev --rpc 127.0.0.1:1 --rpc-user u --rpc-pass secreto \
  --address "$V1ADDR" --wallet "$W/v1.json" --mining-key-label default --blocks 1 >"$W/m_warn.log" 2>&1
grep -q "visible to any local user via ps" "$W/m_warn.log" && ok "--rpc-pass still works and warns about ps" \
                                                           || bad "--rpc-pass does not warn"
timeout 25 "$MINER" --profile dev --rpc 127.0.0.1:1 --rpc-user u --rpc-pass-file "$W/rpc644.pass" \
  --address "$V1ADDR" --wallet "$W/v1.json" --mining-key-label default --blocks 1 >"$W/m_644.log" 2>&1
grep -q "readable by group or others" "$W/m_644.log" && ok "the miner refuses a world-readable secret file" \
                                                     || bad "the miner accepted a 644 secret file"

sect "NODE KEY — createnodebind / nodeheartbeat without a key in argv"
NK=$(openssl rand -hex 32)
printf '%s\n' "$NK" > "$W/nk.key"
printf '%s\n' "$NK" > "$W/nk644.key"; chmod 644 "$W/nk644.key"
printf '%s\n%s\n' "$NK" "$NK" > "$W/nk2lines.key"
printf 'no-es-una-clave\n' > "$W/nkbad.key"
B_ARGV=$("$CLI" --wallet "$W/v1.json" createnodebind 1 "$NK" 2>"$W/bind_argv.err")
B_FILE=$("$CLI" --wallet "$W/v1.json" createnodebind 1 --node-key-file "$W/nk.key" 2>"$W/bind_file.err")
B_FD=$("$CLI" --wallet "$W/v1.json" createnodebind 1 --node-key-fd 7 7<"$W/nk.key" 2>/dev/null)
[[ -n "$B_FILE" && "$B_ARGV" == "$B_FILE" && "$B_FILE" == "$B_FD" ]] \
  && ok "argv / --node-key-file / --node-key-fd produce a byte-identical NODE_BIND (${#B_FILE} hex chars)" \
  || bad "the three key sources produced different transactions"
grep -q "visible to any local user via ps" "$W/bind_argv.err" && ok "the positional hex form warns" || bad "no warning on the argv form"
[[ ! -s "$W/bind_file.err" ]] && ok "the file form is silent (nothing to warn about)" || bad "the file form printed something"
"$CLI" --wallet "$W/v1.json" createnodebind 1 --node-key-file "$W/nk644.key" >"$W/nk644.log" 2>&1
grep -q "readable by group or others" "$W/nk644.log" && ok "a world-readable node key file is refused" || bad "a 644 node key was accepted"
"$CLI" --wallet "$W/v1.json" createnodebind 1 --node-key-file "$W/nk2lines.key" >"$W/nk2l.log" 2>&1
grep -q "single line" "$W/nk2l.log" && ok "a multi-line key file is refused (ambiguous secret)" || bad "a multi-line key file was accepted"
"$CLI" --wallet "$W/v1.json" createnodebind 1 --node-key-file "$W/nkbad.key" >"$W/nkbad.log" 2>&1
grep -q "64 hex characters" "$W/nkbad.log" && ok "a malformed key is refused" || bad "a malformed key was accepted"
grep -qF "no-es-una-clave" "$W/nkbad.log" && bad "the error echoed the file content" || ok "...and the error never echoes the content"
"$CLI" --wallet "$W/v1.json" createnodebind 1 --node-key-file "$W/no-existe" >"$W/nkmiss.log" 2>&1
grep -q "cannot stat" "$W/nkmiss.log" && ok "a missing key file is an error, not an empty key" || bad "a missing key file was tolerated"
TIP=$(openssl rand -hex 32)
HB_F=$("$CLI" --wallet "$W/v1.json" nodeheartbeat --node-key-file "$W/nk.key" 7 "$TIP" 2>/dev/null)
HB_A=$("$CLI" --wallet "$W/v1.json" nodeheartbeat "$NK" 7 "$TIP" 2>/dev/null)
[[ -n "$HB_F" && "$HB_F" == "$HB_A" ]] \
  && ok "nodeheartbeat: file and argv forms agree byte for byte (${#HB_F} hex chars)" \
  || bad "nodeheartbeat differs between key sources"
timeout 25 "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c3.json" \
  --port $((P2P+30)) --rpc-port $((RPC+30)) --node-key-file "$W/nk644.key" >"$W/nodekey644.log" 2>&1
grep -q "readable by group or others" "$W/nodekey644.log" \
  && ok "the node refuses a world-readable --node-key-file" || bad "the node accepted a 644 node key"

sect "RESTART / RECOVERY"
TIP_BEFORE=$(hgt)
kill "$NODE_PID"; wait "$NODE_PID" 2>/dev/null; NODE_PID=""
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/chain.json" \
  --port "$P2P" --rpc-port "$RPC" --rpc-user AdminAudit --rpc-pass-file "$W/rpc.pass" \
  --connect 127.0.0.1:1 >>"$W/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 40); do sleep 1; [[ -n "$(hgt)" ]] && break; done
[[ "$(hgt)" == "$TIP_BEFORE" ]] && ok "the node restarts on the same chain at the same height ($TIP_BEFORE)" \
                                || bad "height changed across a restart: $TIP_BEFORE -> $(hgt)"
mine "$W/v2.json" --rpc-pass-file "$W/rpc.pass" --wallet-passphrase-file "$W/pp" >"$W/m_after_restart.log" 2>&1
grep -q "submitted to node OK" "$W/m_after_restart.log" \
  && ok "mining with the encrypted wallet resumes after the restart" || bad "mining did not resume"

sect "LOGS"
grep -qF "$RPCPASS" "$W/node.log" && bad "the RPC password appears in the node log" \
                                  || ok "the RPC password appears nowhere in the node log"
grep -qF "$NK" "$W"/*.log && bad "the node private key appears in a log" \
                          || ok "the node private key appears in no log"
grep -qF 'frase-de-paso-de-prueba-9876' "$W"/*.log && bad "the wallet passphrase appears in a log" \
                                                   || ok "the wallet passphrase appears in no log"

printf '\n=== %d passed, %d failed ===\n' "$PASS" "$FAIL"
echo "logs: $W"
[[ $FAIL -eq 0 ]] || exit 1
