cmake_minimum_required(VERSION 3.16)
project(sost-core LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Always include debug symbols for crash diagnostics (core dumps)
add_compile_options(-g)

# === Security hardening flags ===
if(NOT MSVC)
  add_compile_options(-fstack-protector-strong)   # Stack buffer overflow detection
  add_compile_options(-fstack-clash-protection)   # Stack clash attack prevention
  add_compile_options(-fPIE)                       # Position-independent executables (ASLR)
  add_compile_options(-Wformat -Wformat-security)  # Format string protection
  add_link_options(-pie)                           # ASLR for linked executables
  add_link_options(-Wl,-z,relro,-z,now)            # Read-only relocations (RELRO)
  if(CMAKE_BUILD_TYPE STREQUAL "Release")
    add_compile_options(-D_FORTIFY_SOURCE=2)       # Runtime buffer overflow detection
  endif()
endif()

find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

# =============================================================================
# V11 Phase 2 (SbPoW) — libsecp256k1 schnorrsig build gate (CONDITIONAL)
# =============================================================================
# Phase 2 SbPoW uses the BIP-340 Schnorr module of libsecp256k1. The
# module is only required when the operator opts in to the Phase 2
# code paths via:
#
#     cmake .. -DSOST_ENABLE_PHASE2_SBPOW=ON
#
# Default is OFF: a normal pre-Phase-2 build does NOT need the
# schnorrsig module. With SOST_ENABLE_PHASE2_SBPOW=OFF:
#   - configure does NOT probe for secp256k1_schnorrsig.h.
#   - sost-core compiles sbpow.cpp with Schnorr-dependent code stubbed
#     out via the SOST_HAVE_SCHNORRSIG macro (signing/verification
#     return false; non-Schnorr helpers like build_sbpow_message,
#     derive_pkh_from_pubkey, secure_memzero stay live).
#   - The three Schnorr-only test binaries (test-sbpow-signing,
#     test-sbpow-validation, test-sbpow-adversarial) are NOT built or
#     registered with CTest.
#   - The remaining V11-Phase-2 tests that don't need Schnorr
#     (test-sbpow-header-v2, test-miner-key-selection) are built
#     unconditionally.
#
# With SOST_ENABLE_PHASE2_SBPOW=ON the configure asserts the schnorrsig
# header AND the verify symbol; missing either fails configure with a
# clear FATAL_ERROR. No silent ECDSA fallback under any circumstances.
option(SOST_ENABLE_PHASE2_SBPOW
    "Build Phase 2 SbPoW Schnorr tests/tools (requires libsecp256k1 with schnorrsig module)"
    OFF)

if(SOST_ENABLE_PHASE2_SBPOW)
    include(CheckIncludeFiles)
    include(CheckSymbolExists)

    # Check the schnorrsig header alongside secp256k1.h, since the former
    # depends on type declarations from the latter and won't compile alone.
    check_include_files("secp256k1.h;secp256k1_schnorrsig.h"
        SOST_HAVE_SCHNORRSIG_HEADER)
    if(NOT SOST_HAVE_SCHNORRSIG_HEADER)
        message(FATAL_ERROR
            "SbPoW requires libsecp256k1 with schnorrsig module enabled "
            "(missing header: secp256k1_schnorrsig.h). Rebuild libsecp256k1 "
            "with --enable-module-schnorrsig, upgrade the system package, "
            "or build with -DSOST_ENABLE_PHASE2_SBPOW=OFF (default).")
    endif()

    set(CMAKE_REQUIRED_LIBRARIES secp256k1)
    check_symbol_exists(secp256k1_schnorrsig_verify
        "secp256k1.h;secp256k1_schnorrsig.h"
        SOST_HAVE_SCHNORRSIG_VERIFY)
    unset(CMAKE_REQUIRED_LIBRARIES)
    if(NOT SOST_HAVE_SCHNORRSIG_VERIFY)
        message(FATAL_ERROR
            "SbPoW requires libsecp256k1 with schnorrsig module enabled "
            "(missing symbol: secp256k1_schnorrsig_verify). Rebuild "
            "libsecp256k1 with --enable-module-schnorrsig, or build "
            "with -DSOST_ENABLE_PHASE2_SBPOW=OFF (default).")
    endif()
    message(STATUS "V11 Phase 2 SbPoW: ENABLED (Schnorr tests will be built)")
else()
    message(STATUS "V11 Phase 2 SbPoW: DISABLED "
                   "(use -DSOST_ENABLE_PHASE2_SBPOW=ON to build Schnorr tests)")
endif()

# Core library — Phase 0 (consensus base) + Phase 1-6
add_library(sost-core STATIC
    # Phase 0: consensus base
    src/crypto.cpp src/subsidy.cpp src/emission.cpp src/pow/casert.cpp
    src/sostcompact.cpp src/pow/convergencex.cpp src/pow/scratchpad.cpp
    src/pow/scratchpad_cache.cpp
    src/pow/relief_predict.cpp

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
    src/spam_guard.cpp
    src/address.cpp
    src/wallet.cpp
    # Phase 5.5: block validation
    src/block_validation.cpp
    # Phase 7: wallet security layer (no consensus)
    src/addressbook.cpp
    src/wallet_policy.cpp
    src/hd_wallet.cpp
    src/psbt.cpp
    src/script.cpp
    # Phase 8: PoPC application layer (no consensus)
    src/popc.cpp
    src/popc_tx_builder.cpp
    src/popc_model_b.cpp

    # V11 Phase 2 — SbPoW (Schnorr-bound PoW). Real implementation as of
    # Commit 3 (signing + key derivation + secure_memzero). Consensus
    # validation in src/sbpow.cpp::validate() still aborts and is wired
    # into block_validation in Commit 4.
    src/sbpow.cpp

    # V11 Phase 2 — PoP lottery (component D). Real eligibility + winner
    # selection helpers as of Commit 6. The remaining lottery functions
    # (apply_block / undo_block — rollover state machinery) stay
    # abort-on-call until C7. Phase 2 stays dormant via
    # V11_PHASE2_HEIGHT == INT64_MAX in params.h; nothing in this file
    # is reached on real chain heights yet.
    src/lottery.cpp
)
# EXCLUDED (use old Block API, will be updated later):
#   src/node.cpp src/miner.cpp src/wallet.cpp

target_include_directories(sost-core PUBLIC include)
target_link_libraries(sost-core PUBLIC OpenSSL::Crypto Threads::Threads secp256k1)

# Phase 2 SbPoW build flag — propagated to sbpow.cpp via #ifdef.
# When OFF (default), sbpow.cpp's Schnorr-dependent code is stubbed.
if(SOST_ENABLE_PHASE2_SBPOW)
    target_compile_definitions(sost-core PUBLIC SOST_HAVE_SCHNORRSIG=1)
endif()

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

# V11 Phase 1 — component A (extended cASERT cascade)
add_executable(test-casert-v11 tests/test_casert_v11.cpp)
target_link_libraries(test-casert-v11 PRIVATE sost-core)
add_test(NAME casert-v11 COMMAND test-casert-v11)

# V11 Phase 2 — component C (SbPoW): structural header v2 serialization
add_executable(test-sbpow-header-v2 tests/test_sbpow_header_v2.cpp)
target_link_libraries(test-sbpow-header-v2 PRIVATE sost-core)
add_test(NAME sbpow-header-v2 COMMAND test-sbpow-header-v2)

# V11 Phase 2 — component C (SbPoW): miner key selection (CLI flag resolver)
# Always built — does not need the Schnorr module (uses Wallet only).
add_executable(test-miner-key-selection tests/test_miner_key_selection.cpp)
target_link_libraries(test-miner-key-selection PRIVATE sost-core)
add_test(NAME miner-key-selection COMMAND test-miner-key-selection)

# V11 Phase 2 — component D (Lottery): height-only frequency rule.
# Always built — pure function, no Schnorr, no chain state, no consensus
# behaviour change. Verifies the dormant-by-INT64_MAX guarantee.
add_executable(test-lottery-frequency tests/test_lottery_frequency.cpp)
target_link_libraries(test-lottery-frequency PRIVATE sost-core)
add_test(NAME lottery-frequency COMMAND test-lottery-frequency)

# V11 Phase 2 — component D (Lottery): eligibility set + winner pick.
# Always built — pure functions over a chain view, no Schnorr, no
# consensus behaviour change. Includes a synthetic-10k-blocks
# benchmark (target < 50 ms) per the C9 G4.5 gate.
add_executable(test-lottery-eligibility tests/test_lottery_eligibility.cpp)
target_link_libraries(test-lottery-eligibility PRIVATE sost-core)
add_test(NAME lottery-eligibility COMMAND test-lottery-eligibility)

# V11 Phase 2 — component D (Lottery): rollover state machinery.
# Always built — pure functions, no Schnorr, no chain state writes
# (StoredBlock / BlockUndo persistence is C8). Verifies IDLE / UPDATE
# / PAYOUT transitions, undo symmetry, and overflow protection.
add_executable(test-lottery-rollover tests/test_lottery_rollover.cpp)
target_link_libraries(test-lottery-rollover PRIVATE sost-core)
add_test(NAME lottery-rollover COMMAND test-lottery-rollover)

# V11 Phase 2 — coinbase shape + lottery accounting (C8).
# Always built. Exercises ValidateCoinbaseConsensus with the new
# Phase2CoinbaseContext: pre-Phase-2 / non-triggered (3 outputs),
# UPDATE (1 output, lottery share withheld in chain-state pending),
# PAYOUT (2 outputs, MINER + OUT_COINBASE_LOTTERY). Phase 2 stays
# dormant in production (V11_PHASE2_HEIGHT == INT64_MAX); tests
# inject a finite phase2_height to exercise the active path.
add_executable(test-coinbase-phase2 tests/test_coinbase_phase2.cpp)
target_link_libraries(test-coinbase-phase2 PRIVATE sost-core)
add_test(NAME coinbase-phase2 COMMAND test-coinbase-phase2)

# V11 Phase 2 — miner ↔ validator integration (C11).
# Always built. Exercises the full handshake: build coinbase the way the
# production miner would (NORMAL / UPDATE_EMPTY / PAYOUT) and feed it to
# ValidateCoinbaseConsensus with the matching Phase2CoinbaseContext.
# Boundary heights probed against phase2_height = 7050 (proposed C11
# activation) — fixture passes a synthetic phase2_height so the file
# stays valid regardless of the params.h activation value.
add_executable(test-phase2-miner-integration tests/test_phase2_miner_integration.cpp)
target_link_libraries(test-phase2-miner-integration PRIVATE sost-core)
add_test(NAME phase2-miner-integration COMMAND test-phase2-miner-integration)

# V11 Phase 2 — Schnorr-only test binaries. Gated behind
# SOST_ENABLE_PHASE2_SBPOW because they call sign_sbpow_commitment /
# verify_sbpow_signature, which require the libsecp256k1 schnorrsig
# module. With the option OFF (default) these tests are NOT built and
# NOT registered with CTest.
if(SOST_ENABLE_PHASE2_SBPOW)
    # Schnorr signing + message construction
    add_executable(test-sbpow-signing tests/test_sbpow_signing.cpp)
    target_link_libraries(test-sbpow-signing PRIVATE sost-core)
    add_test(NAME sbpow-signing COMMAND test-sbpow-signing)

    # Height-gated consensus-side validation
    add_executable(test-sbpow-validation tests/test_sbpow_validation.cpp)
    target_link_libraries(test-sbpow-validation PRIVATE sost-core)
    add_test(NAME sbpow-validation COMMAND test-sbpow-validation)

    # Adversarial test suite
    add_executable(test-sbpow-adversarial tests/test_sbpow_adversarial.cpp)
    target_link_libraries(test-sbpow-adversarial PRIVATE sost-core)
    add_test(NAME sbpow-adversarial COMMAND test-sbpow-adversarial)

    # V11 Phase 2 (C12) — miner submit-path integration. Exercises the
    # encode → decode → ValidateSbPoW handshake that wires the signed
    # v2 header from the production miner through the submitblock RPC
    # to the node-side validator. Requires SOST_ENABLE_PHASE2_SBPOW
    # because Schnorr signing is invoked directly.
    add_executable(test-sbpow-submit-integration tests/test_sbpow_submit_integration.cpp)
    target_link_libraries(test-sbpow-submit-integration PRIVATE sost-core)
    add_test(NAME phase2-sbpow-submit COMMAND test-sbpow-submit-integration)
endif()

# V11 Phase 1 — component B (state-dependent dataset access)
add_executable(test-convergencex-v11 tests/test_convergencex_v11.cpp)
target_link_libraries(test-convergencex-v11 PRIVATE sost-core)
add_test(NAME convergencex-v11 COMMAND test-convergencex-v11)

add_executable(test-scratchpad-cache tests/test_scratchpad_cache.cpp)
target_link_libraries(test-scratchpad-cache PRIVATE sost-core)
add_test(NAME scratchpad-cache COMMAND test-scratchpad-cache)

add_executable(test-relief-predict tests/test_relief_predict.cpp)
target_link_libraries(test-relief-predict PRIVATE sost-core)
add_test(NAME relief-predict COMMAND test-relief-predict)

add_executable(test-mtp-fork tests/test_mtp_fork.cpp)
target_link_libraries(test-mtp-fork PRIVATE sost-core)
add_test(NAME mtp-fork COMMAND test-mtp-fork)

add_executable(test-checkpoints tests/test_checkpoints.cpp)
target_link_libraries(test-checkpoints PRIVATE sost-core)
add_test(NAME checkpoints COMMAND test-checkpoints)

add_executable(test-transcript-v2 tests/test_transcript_v2.cpp)
target_link_libraries(test-transcript-v2 PRIVATE sost-core)
add_test(NAME transcript-v2 COMMAND test-transcript-v2)

add_executable(test-reorg tests/test_reorg.cpp)
target_link_libraries(test-reorg PRIVATE sost-core)
add_test(NAME reorg COMMAND test-reorg)

add_executable(test-chainwork tests/test_chainwork.cpp)
target_link_libraries(test-chainwork PRIVATE sost-core)
add_test(NAME chainwork COMMAND test-chainwork)

# Phase 7: wallet security + mempool policy tests
add_executable(test-addressbook tests/test_addressbook.cpp)
target_link_libraries(test-addressbook PRIVATE sost-core)
add_test(NAME addressbook COMMAND test-addressbook)

add_executable(test-wallet-policy tests/test_wallet_policy.cpp)
target_link_libraries(test-wallet-policy PRIVATE sost-core)
add_test(NAME wallet-policy COMMAND test-wallet-policy)

add_executable(test-rbf tests/test_rbf.cpp)
target_link_libraries(test-rbf PRIVATE sost-core)
add_test(NAME rbf COMMAND test-rbf)

add_executable(test-cpfp tests/test_cpfp.cpp)
target_link_libraries(test-cpfp PRIVATE sost-core)
add_test(NAME cpfp COMMAND test-cpfp)

add_executable(test-hd-wallet tests/test_hd_wallet.cpp)
target_link_libraries(test-hd-wallet PRIVATE sost-core)
add_test(NAME hd-wallet COMMAND test-hd-wallet)

add_executable(test-psbt tests/test_psbt.cpp)
target_link_libraries(test-psbt PRIVATE sost-core)
add_test(NAME psbt COMMAND test-psbt)

add_executable(test-multisig tests/test_multisig.cpp)
target_link_libraries(test-multisig PRIVATE sost-core)
add_test(NAME multisig COMMAND test-multisig)

add_executable(test-popc tests/test_popc.cpp)
target_link_libraries(test-popc PRIVATE sost-core)
add_test(NAME popc COMMAND test-popc)

add_executable(test-popc-tx tests/test_popc_tx.cpp)
target_link_libraries(test-popc-tx PRIVATE sost-core)
add_test(NAME popc-tx COMMAND test-popc-tx)

add_executable(test-escrow tests/test_escrow.cpp)
target_link_libraries(test-escrow PRIVATE sost-core)
add_test(NAME escrow COMMAND test-escrow)

add_executable(test-proposals tests/test_proposals.cpp)
target_link_libraries(test-proposals PRIVATE sost-core)
add_test(NAME proposals COMMAND test-proposals)

add_executable(test-dynamic-rewards tests/test_dynamic_rewards.cpp)
target_link_libraries(test-dynamic-rewards PRIVATE sost-core)
add_test(NAME dynamic-rewards COMMAND test-dynamic-rewards)

add_executable(test-gold-vault tests/test_gold_vault.cpp)
target_link_libraries(test-gold-vault PRIVATE sost-core)
add_test(NAME gold-vault COMMAND test-gold-vault)

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
add_executable(tx_send src/tx_send.cpp)
target_link_libraries(tx_send PRIVATE sost-core)

# Calibration tools
add_executable(cx-benchmark tools/cx-benchmark.cpp)
target_link_libraries(cx-benchmark PRIVATE sost-core)

add_executable(casert-simulator tools/casert-simulator.cpp)
target_link_libraries(casert-simulator PRIVATE sost-core)

add_executable(cx-variance tools/cx-variance.cpp)
target_link_libraries(cx-variance PRIVATE sost-core)

add_executable(eq-benchmark tools/eq-benchmark.cpp)
target_link_libraries(eq-benchmark PRIVATE sost-core)
