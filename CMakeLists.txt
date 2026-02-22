cmake_minimum_required(VERSION 3.16)
project(sost-core LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

# Core library
add_library(sost-core STATIC
    src/crypto.cpp src/emission.cpp src/asert.cpp src/casert.cpp
    src/sostcompact.cpp src/convergencex.cpp src/scratchpad.cpp
    src/block.cpp src/wallet.cpp src/miner.cpp src/node.cpp)
target_include_directories(sost-core PUBLIC include)
target_link_libraries(sost-core PUBLIC OpenSSL::Crypto Threads::Threads)

# Binaries
add_executable(sost-node src/main_node.cpp)
target_link_libraries(sost-node PRIVATE sost-core)

add_executable(sost-miner src/main_miner.cpp)
target_link_libraries(sost-miner PRIVATE sost-core)

add_executable(sost-wallet src/main_wallet.cpp)
target_link_libraries(sost-wallet PRIVATE sost-core)

# Tests
enable_testing()
add_executable(test-chunk1 tests/test_chunk1.cpp)
target_link_libraries(test-chunk1 PRIVATE sost-core)
add_test(NAME chunk1 COMMAND test-chunk1)

add_executable(test-chunk2 tests/test_chunk2.cpp)
target_link_libraries(test-chunk2 PRIVATE sost-core)
add_test(NAME chunk2 COMMAND test-chunk2)

add_executable(test-chunk4 tests/test_chunk4.cpp)
target_link_libraries(test-chunk4 PRIVATE sost-core)
add_test(NAME chunk4 COMMAND test-chunk4)

add_executable(test-chunk6 tests/test_chunk6.cpp)
target_link_libraries(test-chunk6 PRIVATE sost-core)
add_test(NAME chunk6 COMMAND test-chunk6)

add_executable(test-chunk7 tests/test_chunk7.cpp)
target_link_libraries(test-chunk7 PRIVATE sost-core)
add_test(NAME chunk7 COMMAND test-chunk7)
