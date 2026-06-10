#!/usr/bin/env bash
# =============================================================================
# OTC-5 — EVM (Anvil) live rehearsal for the SOST<->EVM atomic-swap leg.
#
# Runs the AtomicSwapHTLC.sol counterparty leg: deploy, lock (native + ERC20),
# claim (revealing the preimage in the Claimed event), and refund. TESTNET /
# LOCAL ONLY — no mainnet, no broadcast to a public network, no real keys.
#
# Two modes:
#   (A) LIVE anvil + cast  — when an `anvil` RPC is reachable (operator machine).
#   (B) FALLBACK forge test — always works (in-process EVM, real opcodes/events);
#       this is what runs in CI / a restricted sandbox where anvil can't bind.
#
# Prerequisites: foundry (forge, cast, anvil). Install: https://getfoundry.sh
#   cd contracts/atomic-swap && forge install foundry-rs/forge-std --no-commit
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/../contracts/atomic-swap"

RPC="${RPC:-http://127.0.0.1:8545}"
# anvil deterministic account 0 (well-known TEST key; never a real funded key).
PK="${PK:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"

# Shared swap secret -> hashlock = sha256(secret), identical on every leg.
SECRET="0x000000000000000000000000000000000000000000000000000000000000c0ffee"
HASHLOCK="$(cast keccak 0x || true)"   # placeholder; computed below per-leg

echo "== OTC-5 EVM rehearsal =="
[ -f lib/forge-std/src/Test.sol ] || forge install foundry-rs/forge-std --no-commit
forge build >/dev/null

if cast block-number --rpc-url "$RPC" >/dev/null 2>&1; then
  echo "[mode A] LIVE anvil at $RPC"
  HTLC=$(forge create src/AtomicSwapHTLC.sol:AtomicSwapHTLC --rpc-url "$RPC" --private-key "$PK" --broadcast \
         | grep -i "Deployed to:" | awk '{print $3}')
  echo "HTLC deployed: $HTLC"
  # hashlock = sha256(secret). cast supports sha256 via `cast hash`? use python if needed.
  HL=$(python3 -c "import hashlib;print('0x'+hashlib.sha256(bytes.fromhex('${SECRET#0x}')).hexdigest())")
  SWAP=$(cast keccak "rehearse-native")
  RT=$(( $(cast block-number --rpc-url "$RPC") + 100 ))
  ADDR=$(cast wallet address --private-key "$PK")
  echo "-- lockNative 0.01 ETH (refundTime=$RT) --"
  cast send "$HTLC" "lockNative(bytes32,bytes32,uint256,address,address)" \
       "$SWAP" "$HL" "$RT" "$ADDR" "$ADDR" --value 0.01ether --rpc-url "$RPC" --private-key "$PK" >/dev/null
  echo "-- claim (reveals preimage) --"
  cast send "$HTLC" "claim(bytes32,bytes32)" "$SWAP" "$SECRET" --rpc-url "$RPC" --private-key "$PK" >/dev/null
  echo "-- preimage from Claimed event --"
  cast logs --rpc-url "$RPC" --address "$HTLC" "Claimed(bytes32,bytes32,address)" | cat
  echo "[mode A] done"
else
  echo "[mode B] no anvil RPC reachable -> in-process forge test rehearsal"
  forge test --match-contract OtcRehearsal -vv
fi
echo "== EVM rehearsal complete =="
