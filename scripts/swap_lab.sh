#!/usr/bin/env bash
# Reproducible atomic-swap lab orchestrator. LAB ONLY (SOST devnet + BTC regtest + Anvil).
# Never touches mainnet / real funds. Subcommands: start | stop | run | versions
set -u
ulimit -f unlimited
export PATH="$HOME/.foundry/bin:$PATH"
S="${SWAP_LAB_SCRATCH:-$(cd "$(dirname "$0")/.." && pwd)/.swaplab}"
mkdir -p "$S"
BTC_DD="$S/btcregtest"; BTC="bitcoin-cli -regtest -datadir=$BTC_DD -rpcuser=rt -rpcpassword=rt -rpcport=18443"
DRV_BTC="$S/btc_htlc_driver"; DRV_SOST="$S/sost_htlc_driver"

start_btc(){ $BTC getblockcount >/dev/null 2>&1 && { echo "  bitcoind already up"; return; }
  bitcoind -regtest -datadir="$BTC_DD" -rpcuser=rt -rpcpassword=rt -rpcport=18443 -fallbackfee=0.0001 -txindex=1 -daemon >/dev/null 2>&1
  for _ in $(seq 1 15); do sleep 1; $BTC getblockcount >/dev/null 2>&1 && break; done
  $BTC createwallet w >/dev/null 2>&1 || $BTC loadwallet w >/dev/null 2>&1 || true
  local A=$($BTC -rpcwallet=w getnewaddress 2>/dev/null); [ -n "$A" ] && $BTC -rpcwallet=w generatetoaddress 101 "$A" >/dev/null 2>&1
  echo "  bitcoind regtest up (h=$($BTC getblockcount))"; }
start_anvil(){ pgrep -f 'anvil --port 8545' >/dev/null && { echo "  anvil already up"; return; }
  setsid anvil --port 8545 >"$S/anvil.log" 2>&1 & sleep 3
  ETH_RPC_URL=http://127.0.0.1:8545 cast block-number >/dev/null 2>&1 && echo "  anvil up" || echo "  anvil FAILED"; }
stop_all(){
  $BTC stop >/dev/null 2>&1 || true
  for pid in $(pgrep -f 'anvil --port 8545' 2>/dev/null); do kill -9 "$pid" 2>/dev/null; done
  # kill ONLY lab SOST nodes/miners (devnet ports 1829x/2029x) — NEVER mainnet
  for pid in $(ps -eo pid,args 2>/dev/null | grep -E 'sost-node|sost-miner' | grep -E 'rpc-port 1829|127.0.0.1:1829|port 2029|profile dev' | grep -v grep | awk '{print $1}'); do kill -9 "$pid" 2>/dev/null; done
  echo "  lab stopped (bitcoind, anvil, devnet sost nodes/miners). Mainnet untouched."; }

case "${1:-}" in
  start) echo "[swap-lab] start"; start_btc; start_anvil ;;
  stop)  echo "[swap-lab] stop"; stop_all ;;
  versions)
    echo "[swap-lab] tool versions"
    echo "  bitcoind: $(bitcoind --version 2>/dev/null | head -1)"
    echo "  anvil:    $(anvil --version 2>/dev/null | head -1)"
    echo "  forge:    $(forge --version 2>/dev/null | head -1)"
    echo "  sost-node build: $S/build-sostswap (SOST_DEVNET_FORKS=ON, V14_5=11)" ;;
  run)
    echo "[swap-lab] run all scenarios (results -> $S/RESULTS.txt)"
    : > "$S/RESULTS.txt"
    for sc in "xswap_sost_btc.sh|SOST<->BTC" "xswap_sost_evm.sh native|SOST<->EVM-native" "xswap_sost_evm.sh erc20|SOST<->EVM-erc20"; do
      script="${sc%%|*}"; name="${sc##*|}"; args="${script#* }"; base="${script%% *}"
      echo "  running $name ..."
      out=$(ulimit -f unlimited; timeout 200 bash "$S/${base}" ${args:+$args} 2>&1 | grep -vE 'SIGHASH-DEBUG')
      if echo "$out" | grep -q 'RESULT: ✅✅'; then res=PASS; else res=FAIL; fi
      echo "  $name = $res" | tee -a "$S/RESULTS.txt"
      echo "$out" | grep -E 'received|RESULT|Bob SOST|Alice' >> "$S/RESULTS.txt"
    done
    echo "[swap-lab] done. Summary:"; grep -E '= (PASS|FAIL)' "$S/RESULTS.txt" | sed 's/^/    /' ;;
  *) echo "usage: swap_lab.sh {start|stop|run|versions}"; exit 2 ;;
esac
