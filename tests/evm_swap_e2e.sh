#!/usr/bin/env bash
# SOST EVM atomic-swap HTLC — live E2E on local anvil. Native + ERC-20 claim/refund
# + negative cases. Real deploy + real txs. No mainnet, no real funds.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
CD=/home/sost/SOST/sostcore/sost-core/contracts/atomic-swap
export PATH=/home/sost/.foundry/bin:$PATH
RPC=http://127.0.0.1:8545
K0=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80  # Alice (locker)
K1=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d  # Bob (claimer)
A0=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
A1=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
sw(){ ( sleep "$1" ) & wait $!; }
cd "$CD"
# preimage (32 bytes) + sha256 hashlock
PRE=0x0000000000000000000000000000000000000000000000000000000000000001
HL=$(python3 -c "import hashlib,binascii;print('0x'+hashlib.sha256(binascii.unhexlify('${PRE#0x}')).hexdigest())")
WRONGPRE=0x0000000000000000000000000000000000000000000000000000000000000002
echo "preimage=$PRE  hashlock(sha256)=$HL"
anvil --silent --port 8545 >/dev/null 2>&1 & AV=$!
for i in $(seq 1 30); do cast block-number --rpc-url $RPC >/dev/null 2>&1 && break; sw 0.3; done
echo "anvil up (pid $AV), block=$(cast block-number --rpc-url $RPC)"
HTLC=$(forge create src/AtomicSwapHTLC.sol:AtomicSwapHTLC --private-key $K0 --rpc-url $RPC --broadcast 2>/dev/null | grep -oE 'Deployed to: 0x[0-9a-fA-F]+' | grep -oE '0x[0-9a-fA-F]+')
TOK=$(forge create test/mocks/MockERC20.sol:MockERC20 --private-key $K0 --rpc-url $RPC --broadcast --constructor-args USDC USDC 2>/dev/null | grep -oE 'Deployed to: 0x[0-9a-fA-F]+' | grep -oE '0x[0-9a-fA-F]+')
echo "HTLC=$HTLC  TOKEN=$TOK"
[ -z "$HTLC" ] && { echo "DEPLOY FAILED"; kill -9 $AV; exit 1; }
pass=0; fail=0
chk(){ if [ "$1" = "$2" ]; then echo "  ✅ $3"; pass=$((pass+1)); else echo "  ❌ $3 (got $1 want $2)"; fail=$((fail+1)); fi; }

echo "== TEST 1: NATIVE claim (lock 1 ETH -> claim by preimage) =="
SID=0x1111111111111111111111111111111111111111111111111111111111111111
BN=$(cast block-number --rpc-url $RPC); RT=$((BN+500))
cast send $HTLC "lockNative(bytes32,bytes32,uint256,address,address)" $SID $HL $RT $A1 $A0 --value 1ether --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
BAL_BEFORE=$(cast balance $A1 --rpc-url $RPC)
cast send $HTLC "claim(bytes32,bytes32)" $SID $PRE --private-key $K1 --rpc-url $RPC >/dev/null 2>&1
BAL_AFTER=$(cast balance $A1 --rpc-url $RPC)
ST=$(cast call $HTLC "swaps(bytes32)(uint8,address,uint256,bytes32,uint256,address,address)" $SID --rpc-url $RPC 2>/dev/null | head -1)
# claimer balance should rise ~1 ETH (minus gas on the claim tx bob paid)
python3 -c "print('  claimer +%.4f ETH'%(($BAL_AFTER-$BAL_BEFORE)/1e18))"
chk "$ST" "2" "native swap state=CLAIMED(2)"

echo "== TEST 2: NATIVE wrong preimage rejected =="
SID2=0x2222222222222222222222222222222222222222222222222222222222222222
BN=$(cast block-number --rpc-url $RPC); RT=$((BN+500))
cast send $HTLC "lockNative(bytes32,bytes32,uint256,address,address)" $SID2 $HL $RT $A1 $A0 --value 1ether --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
if cast send $HTLC "claim(bytes32,bytes32)" $SID2 $WRONGPRE --private-key $K1 --rpc-url $RPC >/dev/null 2>&1; then chk 1 0 "wrong preimage should revert"; else echo "  ✅ wrong preimage reverted"; pass=$((pass+1)); fi

echo "== TEST 3: NATIVE refund after timeout (block-height) =="
SID3=0x3333333333333333333333333333333333333333333333333333333333333333
BN=$(cast block-number --rpc-url $RPC); RT=$((BN+3))
cast send $HTLC "lockNative(bytes32,bytes32,uint256,address,address)" $SID3 $HL $RT $A1 $A0 --value 1ether --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
# early refund must revert
if cast send $HTLC "refund(bytes32)" $SID3 --private-key $K0 --rpc-url $RPC >/dev/null 2>&1; then chk 1 0 "early refund should revert"; else echo "  ✅ early refund reverted"; pass=$((pass+1)); fi
cast rpc anvil_mine 5 --rpc-url $RPC >/dev/null 2>&1
cast send $HTLC "refund(bytes32)" $SID3 --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
ST3=$(cast call $HTLC "swaps(bytes32)(uint8,address,uint256,bytes32,uint256,address,address)" $SID3 --rpc-url $RPC 2>/dev/null | head -1)
chk "$ST3" "3" "native swap state=REFUNDED(3)"

echo "== TEST 4: ERC-20 claim (mint+approve+lockERC20 -> claim) =="
SID4=0x4444444444444444444444444444444444444444444444444444444444444444
cast send $TOK "mint(address,uint256)" $A0 1000000 --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
cast send $TOK "approve(address,uint256)" $HTLC 1000000 --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
BN=$(cast block-number --rpc-url $RPC); RT=$((BN+500))
cast send $HTLC "lockERC20(bytes32,address,uint256,bytes32,uint256,address,address)" $SID4 $TOK 500000 $HL $RT $A1 $A0 --private-key $K0 --rpc-url $RPC >/dev/null 2>&1
cast send $HTLC "claim(bytes32,bytes32)" $SID4 $PRE --private-key $K1 --rpc-url $RPC >/dev/null 2>&1
TB=$(cast call $TOK "balanceOf(address)(uint256)" $A1 --rpc-url $RPC 2>/dev/null | grep -oE '^[0-9]+')
chk "$TB" "500000" "claimer ERC20 balance=500000"
echo
echo "RESULT: $pass passed / $fail failed"
kill -9 $AV 2>/dev/null
echo DONE
