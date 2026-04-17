#!/bin/bash
# Verify SOSTEscrow source code on Etherscan
# Usage: bash contracts/script/VerifyEtherscan.sh <network> <contract_address>
# Example: bash contracts/script/VerifyEtherscan.sh sepolia 0x1234...

set -e
NETWORK="${1:-sepolia}"
CONTRACT="${2:?Usage: $0 <network> <contract_address>}"

cd "$(dirname "$0")/.."

if [ "$NETWORK" = "mainnet" ]; then
    XAUT="0x68749665FF8D2d112Fa859AA293F07a622782F38"
    PAXG="0x45804880De22913dAFE09f4980848ECE6EcbAf78"
else
    echo "For testnet, use the mock addresses from your deployment log."
    echo "Pass them as: XAUT=0x... PAXG=0x... $0 $NETWORK $CONTRACT"
    XAUT="${XAUT:?Set XAUT address}"
    PAXG="${PAXG:?Set PAXG address}"
fi

ARGS=$(cast abi-encode "constructor(address,address)" "$XAUT" "$PAXG")

forge verify-contract "$CONTRACT" SOSTEscrow \
    --chain "$NETWORK" \
    --constructor-args "$ARGS" \
    --etherscan-api-key "$ETHERSCAN_API_KEY" \
    --watch
