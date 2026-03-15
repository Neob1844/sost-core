cmake_minimum_required(VERSION 3.16)
project(sost-core LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

# Core library — Phase 0 (consensus base) + Phase 1-6
add_library(sost-core STATIC
    # Phase 0: consensus base
    src/crypto.cpp src/subsidy.cpp src/emission.cpp src/pow/casert.cpp
    src/sostcompact.cpp src/pow/convergencex.cpp src/pow/scratchpad.cpp
    
    # Phase 1: transaction serialization
    src/transaction.cpp
    # Phase 2: tx signer
    src/tx_signer.cpp
    # Phase 3: tx validation
    src/tx_validation.cpp
    # Phase 3.5: capsule
    src/capsule.cpp
    # Phase 4: UTXO set
    src/utxo_set.cpp
    # Phase 5: block + merkle
    src/block.cpp src/merkle.cpp
    # Phase 6: mempool
    src/mempool.cpp
    src/address.cpp
    src/wallet.cpp
    # Phase 5.5: block validation
    src/block_validation.cpp
)
# EXCLUDED (use old Block API, will be updated later):
#   src/node.cpp src/miner.cpp src/wallet.cpp

target_include_directories(sost-core PUBLIC include)
target_link_libraries(sost-core PUBLIC OpenSSL::Crypto Threads::Threads secp256k1)

# Binaries — DISABLED until node/miner/wallet updated to new Block API
# add_executable(sost-node src/main_node.cpp)
# target_link_libraries(sost-node PRIVATE sost-core)
# add_executable(sost-miner src/main_miner.cpp)
# target_link_libraries(sost-miner PRIVATE sost-core)
# add_executable(sost-wallet src/main_wallet.cpp)
# target_link_libraries(sost-wallet PRIVATE sost-core)

# Tests
enable_testing()

# Legacy chunk tests
add_executable(test-chunk1 tests/test_chunk1.cpp)
target_link_libraries(test-chunk1 PRIVATE sost-core)
add_test(NAME chunk1 COMMAND test-chunk1)

add_executable(test-chunk2 tests/test_chunk2.cpp)
target_link_libraries(test-chunk2 PRIVATE sost-core)
add_test(NAME chunk2 COMMAND test-chunk2)

#add_executable(test-chunk4 tests/test_chunk4.cpp)
#target_link_libraries(test-chunk4 PRIVATE sost-core)
#add_test(NAME chunk4 COMMAND test-chunk4)

#add_executable(test-chunk6 tests/test_chunk6.cpp)
#target_link_libraries(test-chunk6 PRIVATE sost-core)
#add_test(NAME chunk6 COMMAND test-chunk6)

#add_executable(test-chunk7 tests/test_chunk7.cpp)
#target_link_libraries(test-chunk7 PRIVATE sost-core)
#add_test(NAME chunk7 COMMAND test-chunk7)

# Phase 1-6 tests
add_executable(test-transaction tests/test_transaction.cpp)
target_link_libraries(test-transaction PRIVATE sost-core)
add_test(NAME transaction COMMAND test-transaction)

add_executable(test-tx-signer tests/test_tx_signer.cpp)
target_link_libraries(test-tx-signer PRIVATE sost-core)
add_test(NAME tx-signer COMMAND test-tx-signer)

add_executable(test-tx-validation tests/test_tx_validation.cpp)
target_link_libraries(test-tx-validation PRIVATE sost-core)
add_test(NAME tx-validation COMMAND test-tx-validation)

add_executable(test-capsule tests/test_capsule_codec.cpp)
target_link_libraries(test-capsule PRIVATE sost-core)
add_test(NAME capsule COMMAND test-capsule)

add_executable(test-utxo-set tests/test_utxo_set.cpp)
target_link_libraries(test-utxo-set PRIVATE sost-core)
add_test(NAME utxo-set COMMAND test-utxo-set)

add_executable(test-merkle-block tests/test_merkle_block.cpp)
target_link_libraries(test-merkle-block PRIVATE sost-core)
add_test(NAME merkle-block COMMAND test-merkle-block)

add_executable(test-mempool tests/test_mempool.cpp)
target_link_libraries(test-mempool PRIVATE sost-core)
add_test(NAME mempool COMMAND test-mempool)

add_executable(test-bond-lock tests/test_bond_lock.cpp)
target_link_libraries(test-bond-lock PRIVATE sost-core)
add_test(NAME bond-lock COMMAND test-bond-lock)

add_executable(test-casert tests/test_casert.cpp)
target_link_libraries(test-casert PRIVATE sost-core)
add_test(NAME casert COMMAND test-casert)

add_executable(test-checkpoints tests/test_checkpoints.cpp)
target_link_libraries(test-checkpoints PRIVATE sost-core)
add_test(NAME checkpoints COMMAND test-checkpoints)

add_executable(test-transcript-v2 tests/test_transcript_v2.cpp)
target_link_libraries(test-transcript-v2 PRIVATE sost-core)
add_test(NAME transcript-v2 COMMAND test-transcript-v2)

add_executable(sost-genesis src/genesis.cpp)
target_link_libraries(sost-genesis PRIVATE sost-core)

add_executable(sost-cli src/sost-cli.cpp)
target_link_libraries(sost-cli PRIVATE sost-core)

add_executable(sost-rpc src/sost-rpc.cpp)
target_link_libraries(sost-rpc PRIVATE sost-core)
add_executable(sost-miner src/sost-miner.cpp)
target_link_libraries(sost-miner PRIVATE sost-core)
add_executable(sost-node src/sost-node.cpp)
target_link_libraries(sost-node PRIVATE sost-core)

# Calibration tools
add_executable(cx-benchmark tools/cx-benchmark.cpp)
target_link_libraries(cx-benchmark PRIVATE sost-core)

add_executable(casert-simulator tools/casert-simulator.cpp)
target_link_libraries(casert-simulator PRIVATE sost-core)

add_executable(cx-variance tools/cx-variance.cpp)
target_link_libraries(cx-variance PRIVATE sost-core)

add_executable(eq-benchmark tools/eq-benchmark.cpp)
target_link_libraries(eq-benchmark PRIVATE sost-core)
