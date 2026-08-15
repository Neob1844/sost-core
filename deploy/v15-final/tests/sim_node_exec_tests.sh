#!/usr/bin/env bash
# Simulation harness for the V15 node cutover/rollback scripts.
# Runs the REAL v15-node-exec.sh against a fake tree with stub systemctl/curl and
# a REAL background process standing in for the node, so the graceful-stop and
# crash-loop guards are genuinely exercised. Nothing here touches production.
set -uo pipefail

SIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DEPLOY="${SRC_DEPLOY:-$(cd "$SIM/../.." && pwd)}"
PASS=0; FAIL=0
chk() { if [ "$2" = "$3" ]; then echo "  [PASS] $1 ($2)"; PASS=$((PASS+1)); else echo "  [FAIL] $1: expected '$3' got '$2'"; FAIL=$((FAIL+1)); fi; }

setup() {
  R="$SIM/$1"; rm -rf "$R"; mkdir -p "$R"/{deploy,install,staging,state,bin,backup}
  cp "$SRC_DEPLOY"/v15-node-exec.sh "$SRC_DEPLOY"/v15-final.env "$R/deploy/"

  for b in sost-node sost-cli sost-miner sost-signtx; do
    printf 'OLD-%s-payload\n' "$b" > "$R/install/$b"; chmod 755 "$R/install/$b"
    printf 'NEW-%s-payload\n' "$b" > "$R/staging/$b"; chmod 755 "$R/staging/$b"
  done
  head -c 200000 /dev/urandom > "$R/install/chain.json"
  printf '{"wallet":"sim"}\n'  > "$R/install/wallet.json"
  printf '{"genesis":"sim"}\n' > "$R/install/genesis_block.json"
  printf '{"popc":"sim"}\n'    > "$R/install/popc_registry.json"

  for b in sost-node sost-cli sost-miner sost-signtx; do
    h="$(sha256sum "$R/staging/$b" | cut -d' ' -f1)"
    case "$b" in
      sost-node)   sed -i "s|^SHA_NODE=.*|SHA_NODE=\"$h\"|"       "$R/deploy/v15-final.env";;
      sost-cli)    sed -i "s|^SHA_CLI=.*|SHA_CLI=\"$h\"|"         "$R/deploy/v15-final.env";;
      sost-miner)  sed -i "s|^SHA_MINER=.*|SHA_MINER=\"$h\"|"     "$R/deploy/v15-final.env";;
      sost-signtx) sed -i "s|^SHA_SIGNTX=.*|SHA_SIGNTX=\"$h\"|"   "$R/deploy/v15-final.env";;
    esac
  done

  # a REAL process stands in for the node, so PID-gone checks mean something
  setsid sleep 3600 >/dev/null 2>&1 &
  echo $! > "$R/node.pid"
  echo active > "$R/svc.state"; echo 0 > "$R/svc.nrestarts"; echo success > "$R/svc.result"
  echo 0 > "$R/stop_refuse"          # 1 = process refuses to die (tests the abort)

  cat > "$R/bin/systemctl" <<'EOS'
#!/usr/bin/env bash
R="$SIMROOT"
prop=""; val=0
args=("$@")
for ((i=0;i<${#args[@]};i++)); do
  case "${args[$i]}" in -p) prop="${args[$((i+1))]}";; --value) val=1;; esac
done
case "$1" in
  stop)
    if [ "$(cat "$R/stop_refuse")" = "1" ]; then exit 0; fi   # returns 0 but never dies
    p="$(cat "$R/node.pid" 2>/dev/null || echo 0)"
    [ "$p" -gt 0 ] && kill "$p" 2>/dev/null
    for _ in $(seq 1 20); do [ -d "/proc/$p" ] || break; sleep 0.1; done
    echo inactive > "$R/svc.state"; echo 0 > "$R/node.pid"
    ;;
  start)
    setsid sleep 3600 >/dev/null 2>&1 &
    echo $! > "$R/node.pid"; echo active > "$R/svc.state"
    ;;
  is-active) cat "$R/svc.state";;
  show)
    case "$prop" in
      MainPID)   cat "$R/node.pid" 2>/dev/null || echo 0;;
      NRestarts) cat "$R/svc.nrestarts";;
      Result)    cat "$R/svc.result";;
      *) echo 0;;
    esac
    ;;
  *) : ;;
esac
exit 0
EOS
  echo 1000 > "$R/height"; echo 1 > "$R/peers"
  cat > "$R/bin/curl" <<'EOS'
#!/usr/bin/env bash
R="$SIMROOT"
body=""
while [ $# -gt 0 ]; do case "$1" in --data) body="$2"; shift 2;; *) shift;; esac; done
[ "$(cat "$R/svc.state")" = "active" ] || exit 7
H="$(cat "$R/height")"
hashfor(){ printf '%064x' "$1"; }
case "$body" in
  *getblockcount*)    printf '{"jsonrpc":"2.0","id":1,"result":%s}' "$H";;
  *getbestblockhash*) printf '{"jsonrpc":"2.0","id":1,"result":"%s"}' "$(hashfor "$H")";;
  *getblockhash*)     n="$(printf '%s' "$body" | grep -oE '[0-9]+\]' | tr -d ']')"
                      printf '{"jsonrpc":"2.0","id":1,"result":"%s"}' "$(hashfor "${n:-$H}")";;
  *getpeerinfo*)      p="$(cat "$R/peers")"; printf '{"result":['
                      for i in $(seq 1 "$p"); do [ "$i" -gt 1 ] && printf ','; printf '{"addr":"1.2.3.%s:1"}' "$i"; done
                      printf ']}';;
  *) printf '{"result":null}';;
esac
EOS
  chmod +x "$R/bin/systemctl" "$R/bin/curl"
}

cleanup_node() { p="$(cat "$1/node.pid" 2>/dev/null || echo 0)"; [ "$p" -gt 0 ] && kill "$p" 2>/dev/null; true; }

run_exec() {
  local R="$1"; shift
  SIMROOT="$R" \
  VPS_INSTALL_DIR="$R/install" VPS_STAGING_DIR="$R/staging" \
  VPS_STATE_DIR="$R/state" VPS_LOCK_FILE="$R/lock" \
  VPS_RPC_ENV="$R/nonexistent-rpc.env" \
  SYSTEMCTL="$R/bin/systemctl" CURL="$R/bin/curl" \
  HEALTH_STABILITY_SECONDS="${STAB:-4}" HEALTH_STABILITY_POLL="${STABP:-2}" \
  NEXTBLOCK_WAIT_SECONDS="${NBW:-25}" STOP_GRACE_SECONDS="${SGS:-6}" \
  bash "$R/deploy/v15-node-exec.sh" "$@" >"$R/exec.out" 2>&1
  echo $?
}
sget() { grep -a "^$2=" "$1/state/"*.state 2>/dev/null | tail -1 | cut -d= -f2-; }

echo "=============================================================="
echo "V15 node cutover/rollback — simulation suite"
echo "=============================================================="

# --------------------------------------------------------------- T1 happy path
echo; echo "T1: cutover happy path — block arrives during the wait window"
setup t1; R="$SIM/t1"
( sleep 22; echo 1001 > "$R/height" ) &
rc="$(NBW=60 run_exec "$R" --mode cutover --run-id t1 --source "$R/staging" --backup "$R/backup/b1")"
wait; cleanup_node "$R"
chk "exit code" "$rc" "0"
chk "RESULT" "$(sget "$R" RESULT)" "SUCCESS"
chk "next block ACCEPTED" "$(sget "$R" NEXTBLOCK)" "ACCEPTED"
chk "node installed = new" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$(sha256sum "$R/staging/sost-node" | cut -d' ' -f1)"
chk "all four post-verified" "$(grep -ac '^INSTALLED_SHA_POST_' "$R/state/t1.state")" "4"
chk "peers checked" "$(sget "$R" HEALTH_PEERS_OK)" "yes"
chk "tip coherence checked" "$(sget "$R" HEALTH_TIP)" "OK"
echo "  -- graceful stop evidence --"
chk "no SIGKILL during stop" "$(sget "$R" SIGKILL_DURING_STOP)" "no"
chk "stop PID gone" "$(sget "$R" STOP_PID_ALIVE)" "no"
chk "unit result not timeout" "$(sget "$R" STOP_UNIT_RESULT)" "success"
echo "  stop elapsed: $(sget "$R" STOP_ELAPSED_SECONDS)s (budget ${SGS:-6}s, systemd SIGKILLs at 30s)"

# ----------------------------------------------- T2 data backup (requirement C)
echo; echo "T2: chain/wallet/genesis/popc backed up and verified"
for f in chain.json wallet.json genesis_block.json popc_registry.json; do
  chk "backup $f matches original" "$(sha256sum "$R/install/$f" | cut -d' ' -f1)" "$(sha256sum "$R/backup/b1/$f" | cut -d' ' -f1)"
done
chk "chain.json size recorded" "$(sget "$R" BACKUP_DATA_SIZE_chain.json)" "$(stat -c %s "$R/install/chain.json")"
chk "data manifest written" "$([ -f "$R/backup/b1/SHA256SUMS.data.txt" ] && echo yes || echo no)" "yes"

# ------------------------------------------- T3 tampered binary aborts early
echo; echo "T3: TAMPERED staged binary — abort BEFORE touching anything"
setup t3; R="$SIM/t3"
before="$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)"
printf 'EVIL\n' > "$R/staging/sost-cli"
rc="$(run_exec "$R" --mode cutover --run-id t3 --source "$R/staging" --backup "$R/backup/b3")"
cleanup_node "$R"
chk "exit non-zero" "$rc" "1"
chk "RESULT" "$(sget "$R" RESULT)" "FAILED"
chk "phase = verify-source" "$(sget "$R" PHASE)" "verify-source"
chk "install dir UNTOUCHED" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$before"
chk "service never stopped" "$(cat "$R/svc.state")" "active"
chk "no backup dir created" "$([ -d "$R/backup/b3" ] && echo yes || echo no)" "no"

# ------------------------------------------- T4 timeout is NOT a failure
echo; echo "T4: no block in the window -> TIMEOUT_INCONCLUSIVE, exit 0, no rollback"
setup t4; R="$SIM/t4"
rc="$(NBW=8 run_exec "$R" --mode cutover --run-id t4 --source "$R/staging" --backup "$R/backup/b4")"
cleanup_node "$R"
chk "exit 0 (not a failure)" "$rc" "0"
chk "RESULT" "$(sget "$R" RESULT)" "SUCCESS_TIMEOUT_INCONCLUSIVE"
chk "NEXTBLOCK" "$(sget "$R" NEXTBLOCK)" "TIMEOUT_INCONCLUSIVE"

# ------------------------------------------- T5 crash-loop detection
echo; echo "T5: crash-loop DURING the stability window -> FAILED"
setup t5; R="$SIM/t5"
( sleep 14; echo 7 > "$R/svc.nrestarts" ) &
rc="$(STAB=30 STABP=2 run_exec "$R" --mode cutover --run-id t5 --source "$R/staging" --backup "$R/backup/b5")"
wait; cleanup_node "$R"
chk "exit non-zero" "$rc" "1"
chk "RESULT" "$(sget "$R" RESULT)" "FAILED"
chk "detected in stability phase" "$(sget "$R" PHASE)" "stability"
chk "reason mentions crash loop" "$([ "$(grep -ac 'crash loop' "$R/state/t5.state")" -ge 1 ] && echo yes || echo no)" "yes"

# ------------------------------------------- T5b node dies and comes back
echo; echo "T5b: node dies mid-window and is restarted (MainPID changes) -> FAILED"
setup t5b; R="$SIM/t5b"
( sleep 12; p="$(cat "$R/node.pid")"; kill "$p" 2>/dev/null; setsid sleep 3600 >/dev/null 2>&1 & echo $! > "$R/node.pid" ) &
rc="$(STAB=30 STABP=2 run_exec "$R" --mode cutover --run-id t5b --source "$R/staging" --backup "$R/backup/b5b")"
wait; cleanup_node "$R"
chk "exit non-zero" "$rc" "1"
chk "RESULT" "$(sget "$R" RESULT)" "FAILED"
chk "MainPID change detected" "$([ "$(grep -ac 'MainPID changed' "$R/state/t5b.state")" -ge 1 ] && echo yes || echo no)" "yes"

# ------------------------------------------- T6 empty-directory rollback
echo; echo "T6: EMPTY-DIRECTORY ROLLBACK TEST (the old glob bug)"
setup t6; R="$SIM/t6"
rc="$(NBW=8 run_exec "$R" --mode cutover --run-id t6 --source "$R/staging" --backup "$R/backup/b6")"
rm -f "$R/install/"*                        # catastrophic partial cutover
echo active > "$R/svc.state"
setsid sleep 3600 >/dev/null 2>&1 & echo $! > "$R/node.pid"
( sleep 22; echo 1001 > "$R/height" ) &
rc="$(NBW=60 run_exec "$R" --mode rollback --run-id t6r --source "$R/backup/b6")"
wait; cleanup_node "$R"
chk "rollback did NOT abort" "$rc" "0"
chk "RESULT" "$(sget "$R" RESULT)" "SUCCESS"
chk "old node restored" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$(sha256sum "$R/backup/b6/sost-node" | cut -d' ' -f1)"
chk "all four restored" "$(ls "$R/install" | grep -c '^sost-')" "4"
chk "data NOT restored by default" "$(sget "$R" DATA_RESTORED)" "no"

# ------------------------------------------- T7 rollback restores data too
echo; echo "T7: ROLLBACK RESTORES BINARIES + DATA (--restore-data)"
setup t7; R="$SIM/t7"
rc="$(NBW=8 run_exec "$R" --mode cutover --run-id t7 --source "$R/staging" --backup "$R/backup/b7")"
declare -A ORIG
for f in chain.json wallet.json genesis_block.json popc_registry.json; do
  ORIG[$f]="$(sha256sum "$R/install/$f" | cut -d' ' -f1)"
  printf 'CORRUPTED-%s\n' "$f" > "$R/install/$f"
done
echo active > "$R/svc.state"
setsid sleep 3600 >/dev/null 2>&1 & echo $! > "$R/node.pid"
( sleep 22; echo 1001 > "$R/height" ) &
rc="$(NBW=60 run_exec "$R" --mode rollback --run-id t7r --source "$R/backup/b7" --restore-data)"
wait; cleanup_node "$R"
chk "rollback exit 0" "$rc" "0"
chk "DATA_RESTORED" "$(sget "$R" DATA_RESTORED)" "yes"
for f in chain.json wallet.json genesis_block.json popc_registry.json; do
  chk "$f restored by hash" "$(sha256sum "$R/install/$f" | cut -d' ' -f1)" "${ORIG[$f]}"
done
chk "binaries restored too" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$(sha256sum "$R/backup/b7/sost-node" | cut -d' ' -f1)"

# ------------------------------------------- T8 corrupt backup refuses
echo; echo "T8: corrupted backup -> rollback REFUSES"
setup t8; R="$SIM/t8"
rc="$(NBW=8 run_exec "$R" --mode cutover --run-id t8 --source "$R/staging" --backup "$R/backup/b8")"
printf 'CORRUPT\n' > "$R/backup/b8/sost-cli"
nb="$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)"
echo active > "$R/svc.state"; setsid sleep 3600 >/dev/null 2>&1 & echo $! > "$R/node.pid"
rc="$(run_exec "$R" --mode rollback --run-id t8r --source "$R/backup/b8")"
cleanup_node "$R"
chk "exit non-zero" "$rc" "1"
chk "RESULT" "$(sget "$R" RESULT)" "FAILED"
chk "install dir untouched" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$nb"

# ------------------------------------------- T9 concurrency lock
echo; echo "T9: second concurrent run refused by the lock"
setup t9; R="$SIM/t9"
( NBW=12 run_exec "$R" --mode cutover --run-id t9a --source "$R/staging" --backup "$R/backup/b9" >/dev/null ) &
sleep 3
rc="$(run_exec "$R" --mode cutover --run-id t9b --source "$R/staging" --backup "$R/backup/b9b")"
wait; cleanup_node "$R"
chk "second run refused" "$rc" "1"
chk "reason is the lock" "$([ "$(grep -ac 'holds' "$R/state/t9b.state")" -ge 1 ] && echo yes || echo no)" "yes"

# ------------------------- T10 node refuses to stop -> abort, no SIGKILL, no install
echo; echo "T10: node will not exit -> ABORT without installing and without SIGKILL"
setup t10; R="$SIM/t10"
echo 1 > "$R/stop_refuse"
before="$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)"
chainb="$(sha256sum "$R/install/chain.json" | cut -d' ' -f1)"
rc="$(SGS=5 run_exec "$R" --mode cutover --run-id t10 --source "$R/staging" --backup "$R/backup/b10")"
cleanup_node "$R"
chk "exit non-zero" "$rc" "1"
chk "RESULT" "$(sget "$R" RESULT)" "FAILED"
chk "phase = stop" "$(sget "$R" PHASE)" "stop"
chk "aborted without forcing" "$([ "$(grep -ac 'WITHOUT forcing' "$R/state/t10.state")" -ge 1 ] && echo yes || echo no)" "yes"
chk "binary NOT installed" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$before"
chk "chain.json untouched" "$(sha256sum "$R/install/chain.json" | cut -d' ' -f1)" "$chainb"

# ------------------------- T11 systemd reports a stop timeout (SIGKILL happened)
echo; echo "T11: systemd Result=timeout after stop -> abort before installing"
setup t11; R="$SIM/t11"
before="$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)"
echo timeout > "$R/svc.result"
rc="$(run_exec "$R" --mode cutover --run-id t11 --source "$R/staging" --backup "$R/backup/b11")"
cleanup_node "$R"
chk "exit non-zero" "$rc" "1"
chk "RESULT" "$(sget "$R" RESULT)" "FAILED"
chk "SIGKILL detected" "$([ "$(grep -ac 'SIGKILLed' "$R/state/t11.state")" -ge 1 ] && echo yes || echo no)" "yes"
chk "binary NOT installed" "$(sha256sum "$R/install/sost-node" | cut -d' ' -f1)" "$before"

echo
echo "=============================================================="
echo "  simulation results: $PASS passed, $FAIL failed"
echo "=============================================================="
[ "$FAIL" -eq 0 ]
