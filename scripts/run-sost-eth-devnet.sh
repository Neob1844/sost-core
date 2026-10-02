#!/usr/bin/env bash
# =============================================================================
# run-sost-eth-devnet.sh — bring up a FULLY LOCAL SOST<->ETH atomic-swap devnet
# so the ADMIN dashboard can drive a real E2E swap in the browser.
#
#   NO real funds · NO public testnet · NO EVM mainnet · NO public trading.
#   SOST leg  = local SOST devnet node (--profile dev, low HTLC activation)
#   EVM leg   = local Anvil + AtomicSwapHTLCv2 (well-known TEST key only)
#   Frontend  = the protected dashboard served locally
#
# Usage:   bash scripts/run-sost-eth-devnet.sh up      # start everything
#          bash scripts/run-sost-eth-devnet.sh down     # stop everything
#          bash scripts/run-sost-eth-devnet.sh status   # show config/URLs
# =============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.devnet"; mkdir -p "$RUN"
NODE_BIN="${NODE_BIN:-$ROOT/build-devnet-v2e/sost-node}"
MINER_BIN="${MINER_BIN:-$ROOT/build-devnet-v2e/sost-miner}"
CLI_BIN="${CLI_BIN:-$ROOT/build-devnet-v2e/sost-cli}"
# NOTE: deliberately NOT the SOST mainnet defaults (RPC 18232 / P2P 19333) —
# those collide with a live mainnet node/miner on this host. Devnet uses a
# private, non-colliding port block. Override via env if needed.
RPC_PORT="${RPC_PORT:-18252}"; P2P_PORT="${P2P_PORT:-19352}"
ANVIL_PORT="${ANVIL_PORT:-8552}"; WEB_PORT="${WEB_PORT:-8899}"
ANVIL_RPC="http://127.0.0.1:$ANVIL_PORT"
# anvil deterministic account #0 — WELL-KNOWN TEST KEY, never a real funded key
TEST_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

say(){ printf '\033[1;36m[devnet]\033[0m %s\n' "$*"; }

cfg(){
  cat <<EOF

==================== SOST <-> ETH DEVNET ====================
 SOST node RPC   : http://127.0.0.1:$RPC_PORT   (user devadmin, pass-file $RUN/rpc.pass)
 SOST P2P        : 127.0.0.1:$P2P_PORT
 Anvil (EVM)     : $ANVIL_RPC   chainId 31337   (import TEST_PK into MetaMask)
 HTLC v2 address : $(cat "$RUN/htlc_v2.addr" 2>/dev/null || echo '(deploy pending)')
 Dashboard       : http://127.0.0.1:$WEB_PORT/sost-dex-dashboard.html?devnet=1
 Test EVM key    : $TEST_PK   (anvil #0 — TEST ONLY)
============================================================
EOF
}

up(){
  [ -x "$NODE_BIN" ]  || { echo "missing $NODE_BIN (build the devnet node first)"; exit 1; }
  command -v anvil >/dev/null || { echo "anvil not found (install foundry)"; exit 1; }
  umask 077; [ -f "$RUN/rpc.pass" ] || openssl rand -base64 24 > "$RUN/rpc.pass"

  say "starting anvil on :$ANVIL_PORT"
  anvil --port $ANVIL_PORT --silent > "$RUN/anvil.log" 2>&1 &
  echo $! > "$RUN/anvil.pid"
  for i in $(seq 1 30); do cast block-number --rpc-url $ANVIL_RPC >/dev/null 2>&1 && break; sleep 0.3; done

  say "deploying AtomicSwapHTLCv2 to anvil"
  ( cd "$ROOT/contracts/atomic-swap"
    forge create src/AtomicSwapHTLCv2.sol:AtomicSwapHTLCv2 \
      --rpc-url "$ANVIL_RPC" --private-key "$TEST_PK" --broadcast 2>"$RUN/deploy.err" \
      | awk '/Deployed to:/{print $3}' > "$RUN/htlc_v2.addr" )
  [ -s "$RUN/htlc_v2.addr" ] || { echo "deploy failed:"; cat "$RUN/deploy.err"; exit 1; }
  say "HTLC v2 @ $(cat "$RUN/htlc_v2.addr")"

  say "starting SOST devnet node (--profile dev, HTLC activates at height 11)"
  "$NODE_BIN" --profile dev --genesis "$ROOT/genesis_block.json" \
    --port $P2P_PORT --rpc-port $RPC_PORT \
    --rpc-user devadmin --rpc-pass-file "$RUN/rpc.pass" \
    --chain "$RUN/chain.json" --connect 127.0.0.1:1 > "$RUN/node.log" 2>&1 &
  echo $! > "$RUN/node.pid"

  # authenticated RPC helper for height polling
  PASS="$(cat "$RUN/rpc.pass")"
  srpc(){ curl -s --max-time 15 --user "devadmin:$PASS" -H 'content-type: application/json' \
          --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
  height(){ srpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
  for i in $(seq 1 30); do sleep 1; [ -n "$(height)" ] && break; done
  [ -n "$(height)" ] || { echo "node did not answer RPC"; cat "$RUN/node.log" | tail; exit 1; }

  # -------------------------------------------------------------------------
  # Phase 8 — mine a SOST miner wallet past the HTLC activation height so the
  # chain can accept HTLC LOCK/CLAIM/REFUND txs, then surface the test accounts.
  # -------------------------------------------------------------------------
  say "Phase 8: mining past the HTLC activation height (SOST miner)"
  MINE_ADDR="$("$CLI_BIN" --wallet "$RUN/miner.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
  [ -n "$MINE_ADDR" ] || MINE_ADDR="$("$CLI_BIN" --wallet "$RUN/miner.json" listaddresses 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
  echo "$MINE_ADDR" > "$RUN/miner.addr"
  # 16 blocks: crosses HTLC height 11 and matures early coinbase (maturity 5).
  "$MINER_BIN" --profile dev --rpc "127.0.0.1:$RPC_PORT" \
    --rpc-user devadmin --rpc-pass-file "$RUN/rpc.pass" \
    --address "$MINE_ADDR" --wallet "$RUN/miner.json" --mining-key-label default \
    --blocks 16 --threads 2 --realtime >> "$RUN/miner.log" 2>&1 || true
  say "SOST chain height: $(height)  (HTLC active: $([ "$(height)" -ge 11 ] && echo yes || echo no))"

  # Pre-funded Anvil test accounts (anvil seeds each with 10000 ETH on start).
  say "Anvil pre-funded TEST accounts (import into MetaMask — TEST keys only):"
  for i in 0 1; do
    a="$(cast rpc eth_accounts --rpc-url "$ANVIL_RPC" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)[$i])" 2>/dev/null)"
    [ -n "$a" ] && printf '    #%s %s  balance %s wei\n' "$i" "$a" "$(cast balance "$a" --rpc-url "$ANVIL_RPC" 2>/dev/null)"
  done
  echo "    #0 key $TEST_PK (anvil deterministic #0)"

  # write the devnet config the dashboard reads (?devnet=1 path)
  cat > "$ROOT/website/dex-devnet-config.json" <<EOF
{ "mode":"devnet", "public_trading":false, "admin_only":true,
  "sost_rpc":"http://127.0.0.1:$RPC_PORT", "sost_rpc_user":"devadmin",
  "evm_rpc":"$ANVIL_RPC", "evm_chain_id":31337,
  "htlc_v2":"$(cat "$RUN/htlc_v2.addr")", "pairs":["SOST/ETH","SOST/USDC"] }
EOF
  say "wrote website/dex-devnet-config.json (public_trading=false, admin_only=true)"

  say "serving dashboard on :$WEB_PORT"
  ( cd "$ROOT/website" && python3 -m http.server $WEB_PORT >/dev/null 2>&1 & echo $! > "$RUN/web.pid" )
  cfg
}

down(){ for p in web node anvil; do [ -f "$RUN/$p.pid" ] && kill "$(cat "$RUN/$p.pid")" 2>/dev/null && rm -f "$RUN/$p.pid"; done; pkill -x anvil 2>/dev/null || true; say "stopped"; }

case "${1:-up}" in up) up ;; down) down ;; status) cfg ;; *) echo "usage: $0 up|down|status" ;; esac
