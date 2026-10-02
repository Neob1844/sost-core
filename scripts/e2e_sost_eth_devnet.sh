#!/usr/bin/env bash
# =============================================================================
# e2e_sost_eth_devnet.sh — REAL headless end-to-end atomic swap: SOST <-> ETH
#                          (+ a SOST/USDC mock-ERC20 leg) on a FULLY LOCAL devnet.
#
#   NO EVM mainnet · NO public testnet · NO public trading · NO real funds ·
#   NO custody · NO server keys. Both legs run against processes this script
#   starts on loopback and tears down at the end.
#
#     SOST leg : local SOST devnet node (--profile dev, DEVNET_FORKS build —
#                HTLC activates at height 11) + miner. The HTLC builders emit
#                UNSIGNED txs; they are signed with the repo's consensus signer
#                (tools/sost-signtx) and broadcast via sendrawtransaction. The
#                hashlock is sha256(preimage) — identical to the EVM contract.
#     EVM  leg : local Anvil + AtomicSwapHTLCv2 (anvil account #0 TEST key only).
#
#   Covers, for BOTH legs:
#     * HAPPY PATH  — lock both legs, reveal P to claim the EVM leg, reuse the
#                     SAME P to claim the SOST leg; verify CLAIMED + funds moved.
#     * REFUND PATH — a second swap nobody claims; advance past timeout; refund
#                     both legs; verify REFUNDED.
#     * NEGATIVE    — a wrong-secret claim is rejected on both legs.
#     * SOST/USDC   — a MINIMAL mock ERC20 (NOT USDT/PAXG/XAUT): mint, approve,
#                     lockERC20 + claimERC20(minReceive), verify balance delta.
#
#   Prints a PASS/FAIL line per step and a final summary. Exit 0 iff all PASS.
#
# Usage:  bash scripts/e2e_sost_eth_devnet.sh
#   Env:  BUILD_DIR (default build-devnet-v2e), KEEP=1 (keep workdir/logs)
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet-v2e}"
NODE="$BUILD_DIR/sost-node"
MINER="$BUILD_DIR/sost-miner"
CLI="$BUILD_DIR/sost-cli"
SIGN="$BUILD_DIR/sost-signtx"
SWAP_SRC="$ROOT/contracts/atomic-swap"

RPC_PORT="${RPC_PORT:-18250}"; P2P_PORT="${P2P_PORT:-19350}"; ANVIL_PORT="${ANVIL_PORT:-8550}"
ANVIL_RPC="http://127.0.0.1:$ANVIL_PORT"
# anvil deterministic accounts — WELL-KNOWN TEST KEYS, never real funded keys.
PK0=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80   # Bob  (ETH side)
PK1=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d   # Alice(ETH side)
A0=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266                           # addr of PK0
A1=0x70997970C51812dc3A010C7d01b50e0d17dc79C8                           # addr of PK1

# consensus money constants (stocks; 1 SOST = 1e8 stocks)
LOCK_AMT=100000000     # 1 SOST locked per SOST-HTLC
FEE=2000               # tx fee (stocks)
MARKER=10000           # HTLC_CLAIM_WITNESS dust (== DUST_THRESHOLD)

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sost-eth-e2e.XXXXXX")"
NODE_PID=""; ANVIL_PID=""; PASS=0; FAIL=0
GEN=""; HTLC=""; TOKEN=""
ALICE=""; BOB=""; APKH=""; BPKH=""; APRIV=""; BPRIV=""

c_g=$'\033[1;32m'; c_r=$'\033[1;31m'; c_c=$'\033[1;36m'; c_0=$'\033[0m'
say(){ printf '%s[e2e]%s %s\n' "$c_c" "$c_0" "$*"; }
pass(){ printf '%s  PASS%s %s\n' "$c_g" "$c_0" "$*"; PASS=$((PASS+1)); }
fail(){ printf '%s  FAIL%s %s\n' "$c_r" "$c_0" "$*"; FAIL=$((FAIL+1)); }
# check <label> <condition-true?> — assert a boolean
chk(){ local label="$1"; shift; if "$@"; then pass "$label"; else fail "$label"; fi; }

cleanup(){
  [ -n "$NODE_PID" ]  && kill "$NODE_PID"  2>/dev/null
  [ -n "$ANVIL_PID" ] && kill "$ANVIL_PID" 2>/dev/null
  pkill -P $$ sost-miner 2>/dev/null
  wait 2>/dev/null
  if [ "${KEEP:-0}" = "1" ]; then say "workdir kept: $WORK"; else rm -rf "$WORK"; fi
}
trap cleanup EXIT
die(){ printf '%s[e2e] FATAL%s %s\n' "$c_r" "$c_0" "$*" >&2; say "logs in $WORK"; KEEP=1; exit 1; }

# ---- RPC + helpers ----------------------------------------------------------
srpc(){ curl -s --max-time 20 -H 'content-type: application/json' \
        --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
res(){ python3 -c "import sys,json;print(json.load(sys.stdin).get('result',''))"; }
sendres(){ python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('result') or ('ERR:'+json.dumps(d.get('error'))))"; }
height(){ srpc getblockcount | res; }
mine(){ # mine <addr> <wallet> <n>
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$1" --wallet "$2" \
    --mining-key-label default --blocks "$3" --threads 2 --realtime >>"$WORK/miner.log" 2>&1; }
to_stocks(){ python3 -c "print(int(round(float('$1')*100000000)))"; }
# DETERMINISTIC coinbase-UTXO picker for Alice. Prints "txid vout amount_stocks".
#   Source of truth is the node's getaddressutxos RPC, whose integer
#   "amount_stocks" field is EXACTLY the value stored in the UTXO set and used
#   to build the input sighash — no float/SOST-decimal round-trip (the old
#   listunspent $6 awk column could round to a stock value the node disagreed
#   with, breaking the signer's sighash -> E6). We take the FIRST UNSPENT,
#   MATURE, non-locked coinbase UTXO with amount_stocks >= LOCK_AMT+FEE that has
#   not already been consumed by an earlier lock this run (deduped by txid:vout
#   in $WORK/used_utxos), and record it so the next call cannot reuse it.
pick_utxo(){
  local need=$((LOCK_AMT + FEE)) used_file="$WORK/used_utxos"
  srpc getaddressutxos "[\"$ALICE\"]" \
  | python3 -c '
import sys, json, os
need = int(sys.argv[1]); used_file = sys.argv[2]
used = set()
if os.path.exists(used_file):
    with open(used_file) as f:
        used = set(x.strip() for x in f if x.strip())
try:
    utxos = json.load(sys.stdin).get("result", []) or []
except Exception:
    utxos = []
for u in utxos:
    if not u.get("coinbase"): continue
    if not u.get("mature"): continue
    if u.get("spendable") is False: continue
    amt = u.get("amount_stocks")
    if not isinstance(amt, int) or amt < need: continue
    key = "%s:%d" % (u.get("txid",""), int(u.get("vout",0)))
    if key in used: continue
    with open(used_file, "a") as f: f.write(key + "\n")
    print(u["txid"], int(u["vout"]), amt)
    break
' "$need" "$used_file"; }
# on-chain SOST balance (float) of a wallet
sbalance(){ "$CLI" --wallet "$1" --node "127.0.0.1:$RPC_PORT" listunspent 2>&1 \
  | awk '/On chain:/{for(i=1;i<=NF;i++) if($i=="SOST") print $(i-1)}' | head -1; }
# status field of a lock (status/spent/preimage)
hstatus(){ "$CLI" --node "127.0.0.1:$RPC_PORT" gethtlcstatus "$1" 0 2>&1 \
  | python3 -c "import sys,json
try:
  d=json.load(sys.stdin).get('result',{}); print(d.get('$2',''))
except Exception: print('')"; }
# build+sign+broadcast a SOST HTLC lock funded by a fresh mature coinbase UTXO
sost_lock(){ # sost_lock <lock_label> <refund_height>  -> echoes lock txid or ERR:
  local u; u="$(pick_utxo)"; [ -n "$u" ] || { echo "ERR:no-utxo"; return; }
  local ptx pvout pst; read -r ptx pvout pst <<<"$u"
  # log the exact funding UTXO (to stderr so it is not captured as the txid).
  # The SAME $pst integer amount feeds createhtlclock AND sost-signtx below,
  # so the signer's sighash matches the node's.
  printf '%s[e2e]%s SOST lock #%s funded by UTXO %s:%s amount=%s stocks (refund@%s)\n' \
         "$c_c" "$c_0" "$1" "$ptx" "$pvout" "$pst" "$2" >&2
  local uns sig
  uns="$("$CLI" createhtlclock "$ptx" "$pvout" "$pst" "$APKH" "$HASHLOCK" "$2" \
          "$BPKH" "$APKH" "$LOCK_AMT" "$FEE" 2>>"$WORK/cli.err" \
        | grep -oE '"raw_tx_hex":"[0-9a-f]+"' | sed 's/.*:"//;s/"//')"
  [ -n "$uns" ] || { echo "ERR:build-lock"; return; }
  sig="$("$SIGN" "$uns" "$APRIV" "$pst" 1 0 "$GEN" 2>>"$WORK/sign.err")"   # spent_type 1 = coinbase
  [ -n "$sig" ] || { echo "ERR:sign-lock"; return; }
  srpc sendrawtransaction "[\"$sig\"]" | sendres; }

# ============================================================================
say "workdir: $WORK"
[ -x "$NODE" ] && [ -x "$MINER" ] && [ -x "$CLI" ] || die "missing SOST binaries in $BUILD_DIR"
[ -x "$SIGN" ] || die "missing sost-signtx — build it: cmake --build $BUILD_DIR --target sost-signtx"
command -v anvil >/dev/null && command -v cast >/dev/null && command -v forge >/dev/null \
  || die "foundry (anvil/cast/forge) not found — https://getfoundry.sh"
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null \
  || die "$BUILD_DIR is not a DEVNET_FORKS build (HTLC would never activate)"

# ---- preimage P (32 bytes) and hashlock H = sha256(P) ----------------------
# proper bytes32: 0x + 64 hex both for cast and for the SOST builders.
PRE_HEX="aa$(printf 'aa%.0s' {1..31})"                       # 32 bytes of 0xaa
P_EVM="0x$PRE_HEX"                                            # cast bytes32 preimage
HASHLOCK="$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('$PRE_HEX')).hexdigest())")"
H_EVM="0x$HASHLOCK"
WRONG_HEX="bb$(printf 'bb%.0s' {1..31})"
WP_EVM="0x$WRONG_HEX"
say "preimage P = $P_EVM"
say "hashlock H = sha256(P) = $H_EVM   (identical on both legs)"

# ---------------------------------------------------------------------------
# PHASE A — bring up Anvil + deploy AtomicSwapHTLCv2
# ---------------------------------------------------------------------------
say "PHASE A — Anvil + AtomicSwapHTLCv2"
anvil --port "$ANVIL_PORT" --silent >"$WORK/anvil.log" 2>&1 & ANVIL_PID=$!
for _ in $(seq 1 40); do cast block-number --rpc-url "$ANVIL_RPC" >/dev/null 2>&1 && break; sleep 0.3; done
cast block-number --rpc-url "$ANVIL_RPC" >/dev/null 2>&1 || die "anvil did not come up"
chk "anvil up (chainId 31337)" test "$(cast chain-id --rpc-url "$ANVIL_RPC")" = "31337"
HTLC="$(cd "$SWAP_SRC" && forge create src/AtomicSwapHTLCv2.sol:AtomicSwapHTLCv2 \
        --rpc-url "$ANVIL_RPC" --private-key "$PK0" --broadcast 2>"$WORK/deploy.err" \
        | awk '/Deployed to:/{print $3}')"
if [ -n "$HTLC" ] && [ "$(cast code "$HTLC" --rpc-url "$ANVIL_RPC" | wc -c)" -gt 10 ]; then
  pass "AtomicSwapHTLCv2 deployed @ $HTLC"; else fail "HTLC v2 deploy"; cat "$WORK/deploy.err"; fi

# ---------------------------------------------------------------------------
# PHASE B — bring up SOST devnet node + miner, cross the HTLC activation height
# ---------------------------------------------------------------------------
say "PHASE B — SOST devnet node + miner (HTLC activates at height 11)"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 \
  >"$WORK/node.log" 2>&1 & NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [ -n "$(height)" ] && break; done
[ -n "$(height)" ] || die "SOST node did not answer RPC"
GEN="$(srpc getblockhash '[0]' | res)"
chk "SOST node up (genesis $GEN)" test -n "$GEN"
ALICE="$("$CLI" --wallet "$WORK/alice.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
BOB="$("$CLI"   --wallet "$WORK/bob.json"   newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
APKH="${ALICE:5}"; BPKH="${BOB:5}"
mine "$ALICE" "$WORK/alice.json" 18            # 18 blocks: past HTLC height 11, plenty of mature coinbase
H_NOW="$(height)"
chk "chain past HTLC activation height 11 (now $H_NOW)" test "$H_NOW" -ge 12
APRIV="$("$CLI" --wallet "$WORK/alice.json" dumpprivkey "$ALICE" | head -1 | tr -d '[:space:]')"
BPRIV="$("$CLI" --wallet "$WORK/bob.json"   dumpprivkey "$BOB"   | head -1 | tr -d '[:space:]')"
say "Alice(SOST holder)=$ALICE   Bob(claims SOST)=$BOB"
say "Anvil: Bob(ETH)=$A0  Alice(claims ETH)=$A1"

# ===========================================================================
# PHASE C — HAPPY PATH
#   Alice has SOST & wants ETH; Bob has ETH & wants SOST. Alice chose P.
#   1. Alice locks SOST (claim->Bob, refund->Alice).
#   2. Bob   locks ETH  (claim->Alice, refund->Bob).
#   3. Alice reveals P claiming the ETH leg.
#   4. Bob reuses the SAME P to claim the SOST leg.
# ===========================================================================
say "PHASE C — HAPPY PATH"
RT_SOST=$(( $(height) + 500 ))                 # SOST refund height, far away
LOCK_TXID="$(sost_lock 1 "$RT_SOST")"
case "$LOCK_TXID" in ERR:*) fail "SOST lock (createhtlclock+sign+broadcast): $LOCK_TXID";; *)
  mine "$ALICE" "$WORK/alice.json" 1
  chk "SOST HTLC locked (status=locked, hashlock matches)" bash -c \
    "[ \"\$('$CLI' --node 127.0.0.1:$RPC_PORT gethtlcstatus $LOCK_TXID 0 | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"][\"status\"])')\" = locked ]"
  ;; esac

SID_ETH="$(cast keccak "happy-eth-$(date +%s%N)")"
RT_ETH=$(( $(cast block-number --rpc-url "$ANVIL_RPC") + 200 ))
if cast send "$HTLC" "lockNative(bytes32,bytes32,uint256,address,address)" \
     "$SID_ETH" "$H_EVM" "$RT_ETH" "$A1" "$A0" --value 1ether \
     --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>"$WORK/evm.err"; then
  st="$(cast call "$HTLC" "swaps(bytes32)(uint8,address,uint256,uint256,bytes32,uint256,address,address)" "$SID_ETH" --rpc-url "$ANVIL_RPC" | head -1)"
  chk "EVM HTLC locked (getSwap state=LOCKED)" test "$st" = "1"
else fail "EVM lockNative"; cat "$WORK/evm.err"; fi

# 3. Alice reveals P to claim the ETH leg
A1_BEFORE="$(cast balance "$A1" --rpc-url "$ANVIL_RPC")"
if cast send "$HTLC" "claimNative(bytes32,bytes32)" "$SID_ETH" "$P_EVM" \
     --rpc-url "$ANVIL_RPC" --private-key "$PK1" >/dev/null 2>"$WORK/evm.err"; then
  st="$(cast call "$HTLC" "swaps(bytes32)(uint8,address,uint256,uint256,bytes32,uint256,address,address)" "$SID_ETH" --rpc-url "$ANVIL_RPC" | head -1)"
  A1_AFTER="$(cast balance "$A1" --rpc-url "$ANVIL_RPC")"
  chk "EVM leg CLAIMED by Alice (state=CLAIMED)" test "$st" = "2"
  chk "EVM claim moved ETH to Alice (balance up)" python3 -c "import sys;sys.exit(0 if int('$A1_AFTER')>int('$A1_BEFORE') else 1)"
  REVEALED="$(cast logs --rpc-url "$ANVIL_RPC" --address "$HTLC" 'Claimed(bytes32,bytes32,address,uint256)' 2>/dev/null | awk '/data:/{print $2; exit}')"
  chk "EVM Claimed event reveals preimage P" test "${REVEALED:0:66}" = "$P_EVM"
else fail "EVM claimNative"; cat "$WORK/evm.err"; fi

# 4. Bob reuses the SAME P to claim the SOST leg
if [ -n "$LOCK_TXID" ] && [ "${LOCK_TXID:0:4}" != "ERR:" ]; then
  B_BEFORE="$(sbalance "$WORK/bob.json")"; B_BEFORE="${B_BEFORE:-0}"
  CU="$("$CLI" claimhtlc "$LOCK_TXID" 0 "$LOCK_AMT" "$PRE_HEX" "$BPKH" "$MARKER" "$FEE" 2>>"$WORK/cli.err" | grep -oE '"raw_tx_hex":"[0-9a-f]+"' | sed 's/.*:"//;s/"//')"
  CS="$("$SIGN" "$CU" "$BPRIV" "$LOCK_AMT" 18 0 "$GEN" 2>>"$WORK/sign.err")"   # spent_type 18 = HTLC_LOCK
  CRES="$(srpc sendrawtransaction "[\"$CS\"]" | sendres)"
  case "$CRES" in ERR:*) fail "SOST leg claim broadcast: $CRES";; *)
    mine "$ALICE" "$WORK/alice.json" 1
    chk "SOST leg CLAIMED with same P (status=claimed, spent)" bash -c \
      "[ \"\$('$CLI' --node 127.0.0.1:$RPC_PORT gethtlcstatus $LOCK_TXID 0 | python3 -c 'import sys,json;d=json.load(sys.stdin)[\"result\"];print(d[\"status\"]+\",\"+str(d[\"spent\"]))')\" = claimed,True ]"
    REV="$("$CLI" --node "127.0.0.1:$RPC_PORT" gethtlcstatus "$LOCK_TXID" 0 2>&1 | grep -oE 'preimage[^,}]*' | grep -oE "$PRE_HEX" | head -1)"
    chk "SOST status reveals the preimage" test "$REV" = "$PRE_HEX"
    B_AFTER="$(sbalance "$WORK/bob.json")"; B_AFTER="${B_AFTER:-0}"
    chk "SOST claim moved SOST to Bob (balance up)" python3 -c "import sys;sys.exit(0 if float('$B_AFTER')>float('$B_BEFORE') else 1)"
    ;; esac
fi

# ===========================================================================
# PHASE D — REFUND PATH (nobody claims; advance past timeout; refund both legs)
# ===========================================================================
say "PHASE D — REFUND PATH"
RT_SOST2=$(( $(height) + 4 ))
LOCK_TXID2="$(sost_lock 2 "$RT_SOST2")"
case "$LOCK_TXID2" in ERR:*) fail "SOST refund-path lock: $LOCK_TXID2";; *)
  mine "$ALICE" "$WORK/alice.json" 1
  # refund BEFORE timeout must be rejected (R24)
  RU="$("$CLI" refundhtlc "$LOCK_TXID2" 0 "$LOCK_AMT" "$APKH" "$FEE" 2>>"$WORK/cli.err" | grep -oE '"raw_tx_hex":"[0-9a-f]+"' | sed 's/.*:"//;s/"//')"
  RS="$("$SIGN" "$RU" "$APRIV" "$LOCK_AMT" 18 0 "$GEN" 2>>"$WORK/sign.err")"
  EARLY="$(srpc sendrawtransaction "[\"$RS\"]" | sendres)"
  chk "SOST refund BEFORE timeout rejected (R24)" bash -c "case '$EARLY' in ERR:*R24*) exit 0;; *) exit 1;; esac"
  mine "$ALICE" "$WORK/alice.json" 5            # advance past RT_SOST2
  RS2="$("$SIGN" "$RU" "$APRIV" "$LOCK_AMT" 18 0 "$GEN" 2>>"$WORK/sign.err")"
  LATE="$(srpc sendrawtransaction "[\"$RS2\"]" | sendres)"
  case "$LATE" in ERR:*) fail "SOST refund AFTER timeout broadcast: $LATE";; *)
    mine "$ALICE" "$WORK/alice.json" 1
    chk "SOST leg REFUNDED after timeout (status=refunded)" test "$(hstatus "$LOCK_TXID2" status)" = "refunded"
    ;; esac
  ;; esac

SID_ETH2="$(cast keccak "refund-eth-$(date +%s%N)")"
RT_ETH2=$(( $(cast block-number --rpc-url "$ANVIL_RPC") + 5 ))
if cast send "$HTLC" "lockNative(bytes32,bytes32,uint256,address,address)" \
     "$SID_ETH2" "$H_EVM" "$RT_ETH2" "$A1" "$A0" --value 1ether \
     --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>"$WORK/evm.err"; then
  EARLYE="$(cast send "$HTLC" "refundNative(bytes32)" "$SID_ETH2" --rpc-url "$ANVIL_RPC" --private-key "$PK0" 2>&1)"
  chk "EVM refund BEFORE timeout rejected (NOT_YET)" bash -c "echo '$EARLYE' | grep -qiE 'NOT_YET|revert'"
  cast rpc anvil_mine 0x8 --rpc-url "$ANVIL_RPC" >/dev/null 2>&1    # advance past RT_ETH2
  if cast send "$HTLC" "refundNative(bytes32)" "$SID_ETH2" --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>"$WORK/evm.err"; then
    st="$(cast call "$HTLC" "swaps(bytes32)(uint8,address,uint256,uint256,bytes32,uint256,address,address)" "$SID_ETH2" --rpc-url "$ANVIL_RPC" | head -1)"
    chk "EVM leg REFUNDED after timeout (state=REFUNDED)" test "$st" = "3"
  else fail "EVM refundNative after timeout"; cat "$WORK/evm.err"; fi
else fail "EVM refund-path lockNative"; fi

# ===========================================================================
# PHASE E — NEGATIVE (wrong-secret claim rejected on BOTH legs)
# ===========================================================================
say "PHASE E — NEGATIVE: wrong-secret claim"
# EVM: lock then claim with WRONG preimage -> BAD_PREIMAGE
SID_ETH3="$(cast keccak "wrong-eth-$(date +%s%N)")"
RT_ETH3=$(( $(cast block-number --rpc-url "$ANVIL_RPC") + 200 ))
cast send "$HTLC" "lockNative(bytes32,bytes32,uint256,address,address)" \
   "$SID_ETH3" "$H_EVM" "$RT_ETH3" "$A1" "$A0" --value 1ether \
   --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>"$WORK/evm.err"
WRES="$(cast send "$HTLC" "claimNative(bytes32,bytes32)" "$SID_ETH3" "$WP_EVM" --rpc-url "$ANVIL_RPC" --private-key "$PK1" 2>&1)"
chk "EVM wrong-secret claim rejected (BAD_PREIMAGE)" bash -c "echo '$WRES' | grep -qi 'BAD_PREIMAGE'"

# SOST: lock then claim with WRONG preimage -> R21
RT_SOST3=$(( $(height) + 500 ))
LOCK_TXID3="$(sost_lock 3 "$RT_SOST3")"
case "$LOCK_TXID3" in ERR:*) fail "SOST negative-path lock: $LOCK_TXID3";; *)
  mine "$ALICE" "$WORK/alice.json" 1
  CUW="$("$CLI" claimhtlc "$LOCK_TXID3" 0 "$LOCK_AMT" "$WRONG_HEX" "$BPKH" "$MARKER" "$FEE" 2>>"$WORK/cli.err" | grep -oE '"raw_tx_hex":"[0-9a-f]+"' | sed 's/.*:"//;s/"//')"
  CSW="$("$SIGN" "$CUW" "$BPRIV" "$LOCK_AMT" 18 0 "$GEN" 2>>"$WORK/sign.err")"
  WSRES="$(srpc sendrawtransaction "[\"$CSW\"]" | sendres)"
  chk "SOST wrong-secret claim rejected (R21)" bash -c "case '$WSRES' in ERR:*R21*) exit 0;; *) exit 1;; esac"
  ;; esac

# ===========================================================================
# PHASE F — SOST/USDC leg: MINIMAL mock ERC20 (NOT USDT/PAXG/XAUT)
#   mint -> approve -> lockERC20 -> claimERC20(minReceive) -> balance delta.
# ===========================================================================
say "PHASE F — SOST/USDC mock-ERC20 leg"
TOKEN="$(cd "$SWAP_SRC" && forge create test/mocks/MockERC20.sol:MockERC20 \
         --rpc-url "$ANVIL_RPC" --private-key "$PK0" --broadcast \
         --constructor-args "USD Coin (mock devnet)" "USDC" 2>"$WORK/token.err" \
         | awk '/Deployed to:/{print $3}')"
if [ -n "$TOKEN" ] && [ "$(cast code "$TOKEN" --rpc-url "$ANVIL_RPC" | wc -c)" -gt 10 ]; then
  pass "mock USDC ERC20 deployed @ $TOKEN"
  MINT=1000000000000000000000   # 1000 USDC (18 dec)
  LOCKU=500000000000000000000   # 500  USDC
  cast send "$TOKEN" "mint(address,uint256)"    "$A0" "$MINT"  --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>&1
  cast send "$TOKEN" "approve(address,uint256)" "$HTLC" "$MINT" --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>&1
  chk "mock USDC minted to Bob + HTLC approved" test "$(cast call "$TOKEN" "allowance(address,address)(uint256)" "$A0" "$HTLC" --rpc-url "$ANVIL_RPC" | awk '{print $1}')" = "$MINT"
  SID_USDC="$(cast keccak "usdc-happy-$(date +%s%N)")"
  RT_USDC=$(( $(cast block-number --rpc-url "$ANVIL_RPC") + 200 ))
  if cast send "$HTLC" "lockERC20(bytes32,address,uint256,bytes32,uint256,address,address)" \
       "$SID_USDC" "$TOKEN" "$LOCKU" "$H_EVM" "$RT_USDC" "$A1" "$A0" \
       --rpc-url "$ANVIL_RPC" --private-key "$PK0" >/dev/null 2>"$WORK/evm.err"; then
    st="$(cast call "$HTLC" "swaps(bytes32)(uint8,address,uint256,uint256,bytes32,uint256,address,address)" "$SID_USDC" --rpc-url "$ANVIL_RPC" | head -1)"
    chk "lockERC20 (500 mock-USDC) state=LOCKED" test "$st" = "1"
    UB="$(cast call "$TOKEN" "balanceOf(address)(uint256)" "$A1" --rpc-url "$ANVIL_RPC" | awk '{print $1}')"
    cast send "$HTLC" "claimERC20(bytes32,bytes32,uint256)" "$SID_USDC" "$P_EVM" "$LOCKU" \
      --rpc-url "$ANVIL_RPC" --private-key "$PK1" >/dev/null 2>"$WORK/evm.err"
    UA="$(cast call "$TOKEN" "balanceOf(address)(uint256)" "$A1" --rpc-url "$ANVIL_RPC" | awk '{print $1}')"
    st="$(cast call "$HTLC" "swaps(bytes32)(uint8,address,uint256,uint256,bytes32,uint256,address,address)" "$SID_USDC" --rpc-url "$ANVIL_RPC" | head -1)"
    chk "claimERC20(minReceive=500) state=CLAIMED" test "$st" = "2"
    chk "mock-USDC balance delta == 500e18 to Alice" python3 -c "import sys;sys.exit(0 if int('$UA')-int('$UB')==$LOCKU else 1)"
  else fail "lockERC20"; cat "$WORK/evm.err"; fi
else fail "mock USDC deploy"; cat "$WORK/token.err"; fi

# ---------------------------------------------------------------------------
echo
say "================= SUMMARY ================="
say "PASS: $PASS    FAIL: $FAIL"
say "SOST node RPC http://127.0.0.1:$RPC_PORT (dev, HTLC@11)  ·  Anvil $ANVIL_RPC (chainId 31337)"
say "HTLC v2 $HTLC  ·  mock USDC $TOKEN"
say "NO custody · NO server keys · NO mainnet · NO real funds · NO public trading."
if [ "$FAIL" -eq 0 ]; then
  printf '%s[e2e] RESULT: PASS%s — SOST<->ETH + SOST/USDC atomic swap verified end-to-end headless.\n' "$c_g" "$c_0"
  exit 0
else
  printf '%s[e2e] RESULT: FAIL%s — %d step(s) failed (logs in %s).\n' "$c_r" "$c_0" "$FAIL" "$WORK"; KEEP=1
  exit 1
fi
