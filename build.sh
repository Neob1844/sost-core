#!/bin/bash
set -e
echo "=== SOST Core Build ==="
F="-std=c++17 -O2 -Wno-deprecated-declarations -Wno-misleading-indentation -pthread"
INCL="-I include"
# Try system openssl first, fallback to node headers
if [ -d "/usr/include/openssl" ]; then INCL="$INCL"; LINK="-lcrypto"
elif [ -d "/usr/include/node/openssl" ]; then INCL="$INCL -I /usr/include/node"; LINK="/usr/lib/x86_64-linux-gnu/libcrypto.so.3"
else echo "ERROR: No OpenSSL headers found"; exit 1; fi
mkdir -p build
echo "Compiling..."
for f in src/crypto.cpp src/emission.cpp src/asert.cpp src/casert.cpp \
         src/sostcompact.cpp src/convergencex.cpp src/scratchpad.cpp \
         src/block.cpp src/wallet.cpp src/miner.cpp src/node.cpp; do
    obj="build/$(basename ${f%.cpp}.o)"
    g++ $F $INCL -c "$f" -o "$obj"
done
echo "Linking binaries..."
g++ $F $INCL src/main_node.cpp build/*.o $LINK -o build/sost-node
g++ $F $INCL src/main_miner.cpp build/*.o $LINK -o build/sost-miner
g++ $F $INCL src/main_wallet.cpp build/*.o $LINK -o build/sost-wallet
echo "Linking tests..."
for t in tests/test_chunk*.cpp; do
    name="build/$(basename ${t%.cpp})"
    g++ $F $INCL "$t" build/*.o $LINK -o "$name"
done
echo "=== Running all tests ==="
fail=0
for t in build/test_chunk*; do
    echo "--- $t ---"
    if ! "$t"; then fail=1; fi
done
[ $fail -eq 0 ] && echo -e "\n=== ALL TESTS PASSED ===" || echo -e "\n=== SOME TESTS FAILED ==="
exit $fail
