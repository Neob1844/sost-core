#!/usr/bin/env bash
# SACS P1 — prove the --noseed / --disable-dns-seeds isolation flag.
#   FLAG ON : zero DNS queries to the default seed hostnames, zero external
#             auto-connections; only explicit --connect peers are dialed.
#   FLAG OFF: default behaviour — resolves the seed hostnames and dials them.
# Uses strace to classify every connect() the node makes. NON-CONSENSUS flag.
#
# Requires: strace, a devnet-capable build (SOST_DEVNET_FORKS=ON), genesis_block.json.
# Usage: BIN=/path/to/build tests/sacs_p1_isolation.sh
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${BIN:-$REPO/build-sacs}"
G="${GENESIS:-$REPO/genesis_block.json}"
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
command -v strace >/dev/null || { echo "SKIP: strace not installed"; exit 0; }
[ -x "$BIN/sost-node" ] || { echo "FAIL: $BIN/sost-node not found (build with -DSOST_DEVNET_FORKS=ON)"; exit 1; }

softwait(){ ( sleep "$1" ) & wait $!; }
runb(){ local D=$1 EXTRA=$2; mkdir -p "$D"; printf p > "$D/pass"; chmod 600 "$D/pass"
  strace -f -e trace=connect -o "$D/strace.log" \
    "$BIN/sost-node" --profile dev --genesis "$G" --chain "$D/chain.json" --wallet "$D/w.json" \
      --port 0 --rpc-port 0 --rpc-user u --rpc-pass-file "$D/pass" $EXTRA > "$D/node.log" 2>&1 &
  local PID=$!; softwait 4; kill -TERM $PID 2>/dev/null; softwait 1; kill -9 $PID 2>/dev/null; wait $PID 2>/dev/null; }
extcount(){ grep -E 'sa_family=AF_INET,' "$1" 2>/dev/null | grep -oE 'inet_addr\("[0-9.]+"\)' | grep -vcE '127\.'; }

runb "$ROOT/on"  "--noseed --connect 127.0.0.1:9"
runb "$ROOT/off" ""
EXT_ON=$(extcount "$ROOT/on/strace.log");  EXT_OFF=$(extcount "$ROOT/off/strace.log")
ON_LOG=$(grep -c "noseed: DNS seeds and external auto-connect DISABLED" "$ROOT/on/node.log")
ON_SEEDS=$(grep -c "trying .* default seeds" "$ROOT/on/node.log")
OFF_SEEDS=$(grep -c "trying .* default seeds" "$ROOT/off/node.log")
echo "ON  external connects=$EXT_ON (want 0)  isolation-log=$ON_LOG (want>=1)  default-seed-log=$ON_SEEDS (want 0)"
echo "OFF external connects=$EXT_OFF (want>0) default-seed-log=$OFF_SEEDS (want>=1)"
if [ "$EXT_ON" -eq 0 ] && [ "$EXT_OFF" -gt 0 ] && [ "$ON_LOG" -ge 1 ] && [ "$ON_SEEDS" -eq 0 ] && [ "$OFF_SEEDS" -ge 1 ]; then
  echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
