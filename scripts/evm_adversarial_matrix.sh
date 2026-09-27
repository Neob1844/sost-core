#!/usr/bin/env bash
# EVM adversarial matrix against a deployed AtomicSwapHTLC on anvil. LAB ONLY.
# Env: ETH_RPC_URL, CONTRACT. Uses anvil deterministic accts 1 (Bob) & 2 (Alice).
set -u; export PATH="$HOME/.foundry/bin:$PATH"
C="${CONTRACT:?set CONTRACT}"; export ETH_RPC_URL="${ETH_RPC_URL:-http://127.0.0.1:8545}"
BOB_PK=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
ALICE_PK=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
BOB=$(cast wallet address $BOB_PK); ALICE=$(cast wallet address $ALICE_PK)
PRE=1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
H=$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('$PRE')).hexdigest())")
WRONG=0000000000000000000000000000000000000000000000000000000000000001
mk(){ python3 -c "import hashlib,sys;print('0x'+hashlib.sha256(sys.argv[1].encode()).hexdigest())" "$1"; }
P=0; F=0; chk(){ echo "$2"|grep -qiE "$3" && { echo "  PASS $1"; P=$((P+1)); } || { echo "  FAIL $1 :: $(echo "$2"|head -c 80)"; F=$((F+1)); }; }
SW=$(mk A$RANDOM); RT=$(( $(cast block-number)+1000 ))
cast send "$C" "lockNative(bytes32,bytes32,uint256,address,address)" "$SW" "0x$H" "$RT" "$ALICE" "$BOB" --value 0.1ether --private-key $BOB_PK >/dev/null 2>&1
chk "wrong-preimage rejected"    "$(cast send "$C" "claim(bytes32,bytes32)" "$SW" "0x$WRONG" --private-key $ALICE_PK 2>&1)" "WRONG_PREIMAGE"
cast send "$C" "claim(bytes32,bytes32)" "$SW" "0x$PRE" --private-key $ALICE_PK >/dev/null 2>&1
chk "double-claim rejected"      "$(cast send "$C" "claim(bytes32,bytes32)" "$SW" "0x$PRE" --private-key $ALICE_PK 2>&1)" "NOT_LOCKED"
SW=$(mk B$RANDOM); RT=$(( $(cast block-number)+1000 ))
cast send "$C" "lockNative(bytes32,bytes32,uint256,address,address)" "$SW" "0x$H" "$RT" "$ALICE" "$BOB" --value 0.1ether --private-key $BOB_PK >/dev/null 2>&1
chk "premature-refund rejected"  "$(cast send "$C" "refund(bytes32)" "$SW" --private-key $BOB_PK 2>&1)" "revert|NOT_|EARLY"
SW=$(mk C$RANDOM); RT=$(( $(cast block-number)+3 ))
cast send "$C" "lockNative(bytes32,bytes32,uint256,address,address)" "$SW" "0x$H" "$RT" "$ALICE" "$BOB" --value 0.1ether --private-key $BOB_PK >/dev/null 2>&1
cast rpc anvil_mine 5 >/dev/null 2>&1
chk "claim-after-timeout reject" "$(cast send "$C" "claim(bytes32,bytes32)" "$SW" "0x$PRE" --private-key $ALICE_PK 2>&1)" "TIMEOUT_PASSED"
chk "post-timeout refund OK"     "$(cast send "$C" "refund(bytes32)" "$SW" --private-key $BOB_PK --json 2>&1)" '"status":"0x1"'
echo "EVM ADVERSARIAL: PASS=$P FAIL=$F"
