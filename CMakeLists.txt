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
# DEFAULT IS ON. The Phase 2 SbPoW Schnorr verification code path is
# REQUIRED for any binary that participates in SOST mainnet consensus.
# Phase 2 has been active since block 7100 and every accepted block
# since then carries a Schnorr signature that the validator MUST be
# able to verify. A binary compiled with SOST_ENABLE_PHASE2_SBPOW=OFF
# is NOT consensus-capable on mainnet: it will reject every Phase 2
# block with the validator-side error
#     "SbPoW: BIP-340 Schnorr signature verification failed for the
#      recomputed message"
# and silently fork itself off the network. The default was flipped
# from OFF to ON in response to the 2026-05-24 seed-node stall
# (post-mortem: BitcoinTalk "SOST Protocol -- Post-Mortem: Block 10109
# Stall"). Verify any locally compiled binary has the code path via:
#
#     strings build/sost-node  | grep -c 'POW-SIG/v11'   # must be > 0
#     strings build/sost-miner | grep -c 'POW-SIG/v11'   # must be > 0
#
# With SOST_ENABLE_PHASE2_SBPOW=ON (default -- REQUIRED for mainnet):
#   - configure asserts the schnorrsig header AND the verify symbol;
#     missing either fails configure with a clear FATAL_ERROR. No
#     silent ECDSA fallback under any circumstances.
#   - sost-core compiles sbpow.cpp with the full Schnorr code path.
#   - The three Schnorr-only test binaries (test-sbpow-signing,
#     test-sbpow-validation, test-sbpow-adversarial) ARE built and
#     registered with CTest.
#
# With SOST_ENABLE_PHASE2_SBPOW=OFF (opt-out, for niche tooling
# builds that do NOT need to validate or produce mainnet blocks):
#   - configure does NOT probe for secp256k1_schnorrsig.h.
#   - sost-core compiles sbpow.cpp with Schnorr-dependent code
#     stubbed out via the SOST_HAVE_SCHNORRSIG macro (signing /
#     verification return false; non-Schnorr helpers like
#     build_sbpow_message, derive_pkh_from_pubkey, secure_memzero
#     stay live).
#   - The three Schnorr-only test binaries (test-sbpow-signing,
#     test-sbpow-validation, test-sbpow-adversarial) are NOT built
#     or registered with CTest.
#   - The remaining V11-Phase-2 tests that don't need Schnorr
#     (test-sbpow-header-v2, test-miner-key-selection) are built
#     unconditionally.
#   - THE RESULTING BINARY IS NOT CONSENSUS-CAPABLE ON MAINNET.
option(SOST_ENABLE_PHASE2_SBPOW
    "Phase 2 SbPoW Schnorr code path -- REQUIRED for mainnet consensus (default ON; OFF only for niche tooling)"
    ON)

# Private-testnet fork heights. When ON, V14 (and future forks) activate at a low
# block so the fork can be dry-run end-to-end on a throwaway chain. NEVER enable
# for a mainnet binary -- it changes V14_HEIGHT. Default OFF => mainnet untouched.
option(SOST_TESTNET_FORKS
    "Lower fork heights for a private testnet dry-run (NEVER for mainnet)"
    OFF)
if(SOST_TESTNET_FORKS)
    add_compile_definitions(SOST_TESTNET_FORKS)
    message(WARNING "SOST_TESTNET_FORKS=ON -- V14 activates at block 200. TESTNET ONLY, do not deploy to mainnet.")
endif()

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
    # Phase 3.6: sealed envelope (Fase Sealed-1.A — single-recipient ECIES)
    src/sealed_envelope.cpp
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
    # V13 Gold Vault Slice 1 — G1+G2+G3a wiring (sentinel-disabled by default
    # via GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX in
    # include/sost/gold_vault_slice1.h). See
    # docs/V13_POPC_GOLDVAULT_IMPLEMENTATION_PLAN.md for the operator-decision
    # blockers (whitelist values, cap basis points, rate-limit blocks) that
    # must be filled BEFORE activation makes any consensus difference.
    src/gold_vault_slice1.cpp
    src/gv_g5.cpp
    src/popc_v15.cpp
    # OTC-0.5 — atomic-swap groundwork (dormant; gate at INT64_MAX, mainnet no-op).
    # Pure modules only: BTC P2WSH redeem-script builder, BTC signing (stubs while
    # SOST_BTC_HTLC_SIGNING=OFF), and the local swap coordinator state machine.
    # The consensus HTLC types (OUT_HTLC_LOCK/CLAIM/REFUND) + helpers land in OTC-1.
    src/atomic_swap_btc.cpp
    src/atomic_swap_btc_signing.cpp
    src/atomic_swap_coordinator.cpp
    src/atomic_swap_helpers.cpp   # OTC-1 — HTLC build/RPC helpers (gated; mainnet no-op)
    src/atomic_swap_orderbook.cpp # OTC-2 — off-chain maker/taker order board (pure)
    src/atomic_swap_watcher.cpp   # OTC-2 — local non-custodial watcher / auto-pilot (pure)
    src/atomic_swap_session.cpp   # OTC-4 — end-to-end swap session coordinator (pure)
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

    # DTD lottery emergency pause/resume — signed control state machine.
    # Pure reference functions (parse / nonce supersede / reorg undo / the
    # is_dtd_lottery_active_at chokepoint). Consensus-DEFERRED: the gate
    # DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE (params.h) ships false, so this
    # changes nothing on real chain heights. See
    # docs/DTD_EMERGENCY_PAUSE_RESUME_DESIGN.md.
    src/dtd_control.cpp

    # V13 — Beacon Phase II-A. Local signed-notice display path. Pure
    # informational; no consensus, no P2P, no HTTP. See
    # include/sost/beacon.h for the hard invariants and
    # docs/V13_SPEC.md for the operator runbook.
    src/beacon.cpp

    # V13 — Beacon Phase III P2P scaffold. DORMANT, gated at INT64_MAX.
    # Single-switch design: a future fork commit lowers the gate; this
    # commit ships the inert handler and limits so that future enabling
    # commit cannot relax the constraints by accident.
    src/beacon_p2p.cpp
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

add_executable(test-v14-h3-h4 tests/test_v14_h3_h4.cpp)
target_link_libraries(test-v14-h3-h4 PRIVATE sost-core)
add_test(NAME v14-h3-h4 COMMAND test-v14-h3-h4)

add_executable(test-v14-fork-gates tests/test_v14_fork_gates.cpp)
target_link_libraries(test-v14-fork-gates PRIVATE sost-core)
add_test(NAME v14-fork-gates COMMAND test-v14-fork-gates)

add_executable(test-gv-slice1-activation tests/test_gv_slice1_activation.cpp)
target_link_libraries(test-gv-slice1-activation PRIVATE sost-core)
add_test(NAME gv-slice1-activation COMMAND test-gv-slice1-activation)

add_executable(test-gv-g4 tests/test_gv_g4.cpp)
target_link_libraries(test-gv-g4 PRIVATE sost-core)
add_test(NAME gv-g4 COMMAND test-gv-g4)

# W1: Gold Vault Slice 1 composite block-spend check (shared by process_block + orphan)
add_executable(test-gv-slice1-block tests/test_gv_slice1_block_enforcement.cpp)
target_link_libraries(test-gv-slice1-block PRIVATE sost-core)
add_test(NAME gv-slice1-block COMMAND test-gv-slice1-block)

# W2: G4 coinbase approval marker — gated CB11/CB7 relaxation
add_executable(test-gv-g4-coinbase tests/test_gv_g4_coinbase.cpp)
target_link_libraries(test-gv-g4-coinbase PRIVATE sost-core)
add_test(NAME gv-g4-coinbase COMMAND test-gv-g4-coinbase)

# W4: G5 transitional Guardian veto (gated, ECDSA-signed, auto-disconnect @100k)
add_executable(test-gv-g5 tests/test_gv_g5.cpp)
target_link_libraries(test-gv-g5 PRIVATE sost-core secp256k1)
add_test(NAME gv-g5 COMMAND test-gv-g5)

add_executable(test-gv-governance-audit tests/test_gv_governance_audit.cpp)
target_link_libraries(test-gv-governance-audit PRIVATE sost-core secp256k1)
add_test(NAME gv-governance-audit COMMAND test-gv-governance-audit)

# G3b: rate-limit (timelock) + cumulative-outflow cap (wired but inert, sentinels 0)
add_executable(test-gv-g3b tests/test_gv_g3b.cpp)
target_link_libraries(test-gv-g3b PRIVATE sost-core secp256k1)
add_test(NAME gv-g3b COMMAND test-gv-g3b)

# B3: cross-validator / determinism of the composed Gold Vault governance verdict
add_executable(test-gv-governance-determinism tests/test_gv_governance_determinism.cpp)
target_link_libraries(test-gv-governance-determinism PRIVATE sost-core secp256k1)
add_test(NAME gv-governance-determinism COMMAND test-gv-governance-determinism)

# V15 PoPC Model A/B — pure base (P1): commitment/lifecycle/attestation primitives
add_executable(test-popc-v15 tests/test_popc_v15.cpp)
target_link_libraries(test-popc-v15 PRIVATE sost-core secp256k1)
add_test(NAME popc-v15 COMMAND test-popc-v15)

# V15 PoPC P2 — chain_active_popc_set pure recompute (no crypto)
add_executable(test-popc-v15-set tests/test_popc_v15_set.cpp)
target_link_libraries(test-popc-v15-set PRIVATE sost-core)
add_test(NAME popc-v15-set COMMAND test-popc-v15-set)

# V15 PoPC P3 — on-chain carriers + decoder
add_executable(test-popc-v15-carrier tests/test_popc_v15_carrier.cpp)
target_link_libraries(test-popc-v15-carrier PRIVATE sost-core secp256k1)
add_test(NAME popc-v15-carrier COMMAND test-popc-v15-carrier)

# V15 PoPC P4a — consensus eligibility hook (set_popc_event_source / has_active_canonical_popc)
add_executable(test-popc-v15-eligibility tests/test_popc_v15_eligibility.cpp)
target_link_libraries(test-popc-v15-eligibility PRIVATE sost-core)
add_test(NAME popc-v15-eligibility COMMAND test-popc-v15-eligibility)

# V15 PoPC P4b — deterministic auto-slash + auto-settle (chain_popc_recompute)
add_executable(test-popc-v15-lifecycle tests/test_popc_v15_lifecycle.cpp)
target_link_libraries(test-popc-v15-lifecycle PRIVATE sost-core)
add_test(NAME popc-v15-lifecycle COMMAND test-popc-v15-lifecycle)

# V15 PoPC P4c — carrier authorization (Register=Pending, owner-signed carriers)
add_executable(test-popc-v15-authz tests/test_popc_v15_authz.cpp)
target_link_libraries(test-popc-v15-authz PRIVATE sost-core secp256k1)
add_test(NAME popc-v15-authz COMMAND test-popc-v15-authz)

add_executable(test-popc-v15-carrier-e2e tests/test_popc_v15_carrier_e2e.cpp)
target_link_libraries(test-popc-v15-carrier-e2e PRIVATE sost-core secp256k1)
add_test(NAME popc-v15-carrier-e2e COMMAND test-popc-v15-carrier-e2e)

# V15 PoPC P5 — staged-activation soak (deterministic) + replay byte-identity
add_executable(test-popc-v15-soak tests/test_popc_v15_soak.cpp)
target_link_libraries(test-popc-v15-soak PRIVATE sost-core)
add_test(NAME popc-v15-soak COMMAND test-popc-v15-soak)

# Testnet PoPC soak tooling — carrier-payload generator (not a test)
add_executable(popc15-carrier tools/popc15_carrier.cpp)
target_link_libraries(popc15-carrier PRIVATE sost-core secp256k1)

# OTC-4 — end-to-end swap session driver (operator tool, non-custodial)
add_executable(otc-coordinator tools/otc_swap_coordinator.cpp)
target_link_libraries(otc-coordinator PRIVATE sost-core)

# ---------------------------------------------------------------------------
# OTC-0.5 — atomic-swap dormant groundwork (gate at INT64_MAX; mainnet no-op).
# BTC HTLC signing stays a compile-time-disabled stub set unless the operator
# explicitly builds with -DSOST_BTC_HTLC_SIGNING=ON (a future OTC-3 step). The
# default OFF build compiles the module with inert stubs that return ok=false.
# ---------------------------------------------------------------------------
option(SOST_BTC_HTLC_SIGNING "Enable the real BTC HTLC signing backend (OTC-3a; requires vendored libwally-core; default OFF stubs)" OFF)
if (SOST_BTC_HTLC_SIGNING)
    # OTC-3a — build & link the vendored libwally-core and switch the BTC HTLC
    # signing backend from inert stubs to the real libwally implementation.
    #
    # libwally is built in ISOLATION via ExternalProject so its bundled
    # secp256k1-zkp never collides with SOST's own system `secp256k1` target
    # (used for consensus SbPoW). The default OFF build links NONE of this and
    # is byte-identical — every change here is inside this `if` block.
    #
    # This is a regtest/review-only build. It does NOT activate mainnet, does
    # NOT change ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT, and does NOT broadcast.
    set(_wally_src "${CMAKE_CURRENT_SOURCE_DIR}/vendor/libwally-core")
    # The vendor ceremony disables libwally's own CMake build by prefixing its
    # build files with "_" (so the pristine tree never auto-builds). Restore
    # them here, idempotently, only when this flag is ON — this is the explicit
    # opt-in that enables the build. (No effect on the default OFF build.)
    foreach(_wf "" "src/")
        if (NOT EXISTS "${_wally_src}/${_wf}CMakeLists.txt"
            AND EXISTS "${_wally_src}/${_wf}_CMakeLists.txt")
            file(RENAME "${_wally_src}/${_wf}_CMakeLists.txt"
                        "${_wally_src}/${_wf}CMakeLists.txt")
        endif()
    endforeach()
    if (NOT EXISTS "${_wally_src}/cmake" AND EXISTS "${_wally_src}/_cmake")
        file(RENAME "${_wally_src}/_cmake" "${_wally_src}/cmake")
    endif()
    if (NOT EXISTS "${_wally_src}/CMakeLists.txt")
        message(FATAL_ERROR
            "SOST_BTC_HTLC_SIGNING=ON but vendored libwally-core is missing at "
            "${_wally_src}. See docs/V15_OTC_BTC_REGTEST_GUIDE.md to vendor "
            "libwally-core (release_1.5.3, GPG-verified per the ceremony doc) "
            "before turning this flag ON.")
    endif()
    include(ExternalProject)
    set(_wally_build "${CMAKE_CURRENT_BINARY_DIR}/libwally-build")
    set(_wally_lib  "${_wally_build}/src/libwallycore.a")
    set(_wally_secp "${_wally_build}/src/secp256k1/src/libsecp256k1.a")
    ExternalProject_Add(libwally_ext
        SOURCE_DIR        "${_wally_src}"
        BINARY_DIR        "${_wally_build}"
        CMAKE_ARGS
            -DCMAKE_BUILD_TYPE=Release
            -DBUILD_SHARED_LIBS=OFF
            -DWALLYCORE_ENABLE_TESTS=OFF
            -DWALLYCORE_BUILD_ELEMENTS=OFF
            -DWALLYCORE_INSTALL=OFF
        BUILD_BYPRODUCTS  "${_wally_lib}" "${_wally_secp}"
        INSTALL_COMMAND   ""
        LOG_CONFIGURE     ON
        LOG_BUILD         ON)
    add_library(sost_wally_core STATIC IMPORTED GLOBAL)
    set_target_properties(sost_wally_core PROPERTIES IMPORTED_LOCATION "${_wally_lib}")
    add_dependencies(sost_wally_core libwally_ext)
    add_library(sost_wally_secp STATIC IMPORTED GLOBAL)
    set_target_properties(sost_wally_secp PROPERTIES IMPORTED_LOCATION "${_wally_secp}")
    add_dependencies(sost_wally_secp libwally_ext)

    # ENABLED gates the API surface; HAS_LIBWALLY gates the real backend bodies.
    # PUBLIC so the test targets that link sost-core see ON-mode too.
    target_compile_definitions(sost-core PUBLIC
        SOST_BTC_HTLC_SIGNING_ENABLED=1
        SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY=1)
    # PUBLIC so test TUs that include <wally_*.h> under HAS_LIBWALLY resolve them.
    target_include_directories(sost-core PUBLIC "${_wally_src}/include")
    # System secp256k1 (consensus SbPoW) already links earlier and stays first;
    # libwally's own secp256k1 is appended only for the wallycore symbols.
    target_link_libraries(sost-core PUBLIC sost_wally_core sost_wally_secp)
    message(WARNING "SOST_BTC_HTLC_SIGNING=ON — building & linking vendored libwally-core (OTC-3a; regtest/review-only).")
endif()

# Pure atomic-swap tests (no consensus surface; safe in OTC-0.5).
add_executable(test-atomic-swap-btc-script tests/test_atomic_swap_btc_script.cpp)
target_link_libraries(test-atomic-swap-btc-script PRIVATE sost-core)
add_test(NAME atomic-swap-btc-script COMMAND test-atomic-swap-btc-script)

add_executable(test-atomic-swap-btc-test-vectors tests/test_atomic_swap_btc_test_vectors.cpp)
target_link_libraries(test-atomic-swap-btc-test-vectors PRIVATE sost-core)
add_test(NAME atomic-swap-btc-test-vectors COMMAND test-atomic-swap-btc-test-vectors)

add_executable(test-atomic-swap-btc-signing tests/test_atomic_swap_btc_signing.cpp)
target_link_libraries(test-atomic-swap-btc-signing PRIVATE sost-core)
add_test(NAME atomic-swap-btc-signing COMMAND test-atomic-swap-btc-signing)

add_executable(test-atomic-swap-coordinator tests/test_atomic_swap_coordinator.cpp)
target_link_libraries(test-atomic-swap-coordinator PRIVATE sost-core)
add_test(NAME atomic-swap-coordinator COMMAND test-atomic-swap-coordinator)

add_executable(test-atomic-swap-e2e-sim tests/test_atomic_swap_e2e_sim.cpp)
target_link_libraries(test-atomic-swap-e2e-sim PRIVATE sost-core)
add_test(NAME atomic-swap-e2e-sim COMMAND test-atomic-swap-e2e-sim)

# OTC-1 — SOST-side HTLC consensus (LOCK/CLAIM/REFUND) + helpers + RPC.
# All gated by ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX (mainnet no-op).
add_executable(test-atomic-swap-htlc-lock tests/test_atomic_swap_htlc_lock.cpp)
target_link_libraries(test-atomic-swap-htlc-lock PRIVATE sost-core)
add_test(NAME atomic-swap-htlc-lock COMMAND test-atomic-swap-htlc-lock)

add_executable(test-atomic-swap-htlc-helpers tests/test_atomic_swap_htlc_helpers.cpp)
target_link_libraries(test-atomic-swap-htlc-helpers PRIVATE sost-core)
add_test(NAME atomic-swap-htlc-helpers COMMAND test-atomic-swap-htlc-helpers)

add_executable(test-atomic-swap-htlc-rpc tests/test_atomic_swap_htlc_rpc.cpp)
target_link_libraries(test-atomic-swap-htlc-rpc PRIVATE sost-core)
add_test(NAME atomic-swap-htlc-rpc COMMAND test-atomic-swap-htlc-rpc)

# OTC-2 — wallet/watcher/order-board (pure userspace; no consensus surface).
add_executable(test-atomic-swap-orderbook tests/test_atomic_swap_orderbook.cpp)
target_link_libraries(test-atomic-swap-orderbook PRIVATE sost-core)
add_test(NAME atomic-swap-orderbook COMMAND test-atomic-swap-orderbook)

add_executable(test-atomic-swap-watcher tests/test_atomic_swap_watcher.cpp)
target_link_libraries(test-atomic-swap-watcher PRIVATE sost-core)
add_test(NAME atomic-swap-watcher COMMAND test-atomic-swap-watcher)

# OTC-2.5 — HTLC read-only status classifier + node-status->watcher pipeline.
add_executable(test-atomic-swap-status tests/test_atomic_swap_status.cpp)
target_link_libraries(test-atomic-swap-status PRIVATE sost-core)
add_test(NAME atomic-swap-status COMMAND test-atomic-swap-status)

# OTC-4 — end-to-end swap session coordinator (pure full-flow + adversarial).
add_executable(test-atomic-swap-session tests/test_atomic_swap_session.cpp)
target_link_libraries(test-atomic-swap-session PRIVATE sost-core)
add_test(NAME atomic-swap-session COMMAND test-atomic-swap-session)

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

# V11 Phase 3 — Slingshot single-shot bitsQ relief
add_executable(test-slingshot tests/test_slingshot.cpp)
target_link_libraries(test-slingshot PRIVATE sost-core)
add_test(NAME slingshot COMMAND test-slingshot)

# V11 Phase 3 — Slingshot miner-side rebuild predicate. Verifies the
# miner aborts the in-flight candidate the instant gate 2 crosses
# during nonce search, so the next mine_one_block iteration can
# recompute bits_q and avoid the consensus divergence between
# miner-committed bits_q and validator-expected bits_q.
add_executable(test-slingshot-miner-rebuild tests/test_slingshot_miner_rebuild.cpp)
target_link_libraries(test-slingshot-miner-rebuild PRIVATE sost-core)
add_test(NAME slingshot-miner-rebuild COMMAND test-slingshot-miner-rebuild)

# V12 hard fork — cASERT profile ceiling H13→H20 + 7-step triangular cascade
add_executable(test-casert-v12-ceiling tests/test_casert_v12_ceiling.cpp)
target_link_libraries(test-casert-v12-ceiling PRIVATE sost-core)
add_test(NAME casert-v12-ceiling COMMAND test-casert-v12-ceiling)

# V13 hard fork — cASERT profile ceiling H20→H35 (full 43-profile range)
add_executable(test-casert-v13-ceiling tests/test_casert_v13_ceiling.cpp)
target_link_libraries(test-casert-v13-ceiling PRIVATE sost-core)
add_test(NAME casert-v13-ceiling COMMAND test-casert-v13-ceiling)

# V12 hard fork — same-block 4-tier Slingshot ladder (current_elapsed only)
add_executable(test-slingshot-v12-tier tests/test_slingshot_v12_tier.cpp)
target_link_libraries(test-slingshot-v12-tier PRIVATE sost-core)
add_test(NAME slingshot-v12-tier COMMAND test-slingshot-v12-tier)

# V12 hard fork — capsule activation height moved 10000 → 7350
add_executable(test-capsule-v12-activation tests/test_capsule_v12_activation.cpp)
target_link_libraries(test-capsule-v12-activation PRIVATE sost-core)
add_test(NAME capsule-v12-activation COMMAND test-capsule-v12-activation)

# V12 hard fork — timestamp manipulation safety audit. Pins drift cap,
# tier spacings, and MTP/min_delta heights so any future change to these
# constants surfaces as a test failure forcing re-audit.
add_executable(test-slingshot-v12-timestamp-safety tests/test_slingshot_v12_timestamp_safety.cpp)
target_link_libraries(test-slingshot-v12-timestamp-safety PRIVATE sost-core)
add_test(NAME slingshot-v12-timestamp-safety COMMAND test-slingshot-v12-timestamp-safety)

# V13 hard fork @ block 12000 — height-gated helpers boundary test.
# Pins V13_HEIGHT, the lottery exclusion window helper (5 → 6), the
# future-drift cap helper (60s → 10s), and the Beacon Phase II-A / P2P
# activation gates. NO consensus call sites are exercised here — wire-up
# commits ship their own end-to-end boundary tests.
add_executable(test-v13-helpers tests/test_v13_helpers.cpp)
target_link_libraries(test-v13-helpers PRIVATE sost-core)
add_test(NAME v13-helpers COMMAND test-v13-helpers)

# V13 hard fork @ block 12000 — lottery cooldown wire-up boundary.
# Exercises the FULL eligibility computation path
# (compute_lottery_eligibility_set + lottery_exclusion_window_at) to
# verify the cooldown reaches one block further from V13_HEIGHT and that
# the helper produces a byte-identical eligibility set vs. literal-window
# calls (pre-fork = 5 literal, post-fork = 6 literal).
add_executable(test-v13-lottery-cooldown-fork tests/test_v13_lottery_cooldown_fork.cpp)
target_link_libraries(test-v13-lottery-cooldown-fork PRIVATE sost-core)
add_test(NAME v13-lottery-cooldown-fork COMMAND test-v13-lottery-cooldown-fork)

# V13 hard fork @ block 12000 — future-drift cap wire-up boundary.
# Pins the validator inequality (block_ts > now + max_future_drift_at(h))
# at every regime boundary: V13 (10 s), staged-relief (60 s) and the
# legacy genesis-region (600 s). Confirms strict greater-than semantics
# at ±1 s and that pre-V13 caps are byte-identical to the historical
# branches the helper subsumes.
add_executable(test-v13-drift-fork tests/test_v13_drift_fork.cpp)
target_link_libraries(test-v13-drift-fork PRIVATE sost-core)
add_test(NAME v13-drift-fork COMMAND test-v13-drift-fork)

# V13 Beacon Phase II-A — local notice load/verify/filter tests.
# Exercises load_active_notices end-to-end: dormancy gate, valid signed
# notice, tampered signature, expired, wrong network, non-empty commands
# (Phase II-A invariant), malformed JSON, missing/oversized file, and
# the fail-closed default-pubkey placeholder. Generates a real keypair
# via libsecp256k1 directly so the verify path is exercised under a
# known-good key.
add_executable(test-v13-beacon-phase2a tests/test_v13_beacon_phase2a.cpp)
target_link_libraries(test-v13-beacon-phase2a PRIVATE sost-core secp256k1)
add_test(NAME v13-beacon-phase2a COMMAND test-v13-beacon-phase2a)

# V13 Beacon Phase II-B regression tests — threshold (3-of-5) + revocation
# + mirror metadata. See docs/V13_BEACON_PHASE_II_B.md.
add_executable(test-v13-beacon-phase2b tests/test_v13_beacon_phase2b.cpp)
target_link_libraries(test-v13-beacon-phase2b PRIVATE sost-core secp256k1)
add_test(NAME v13-beacon-phase2b COMMAND test-v13-beacon-phase2b)

# V13 Beacon Phase III P2P gossip — Commit A tests. Pipeline (size cap,
# parse, sig verify, network, expiry, dedup LRU 32, per-peer rate-limit
# 8/min) is exercised via gate_height_override; production gate stays at
# BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX so V13 nodes remain dormant.
# See docs/V13_BEACON_PHASE_III.md.
add_executable(test-v13-beacon-phase3-p2p tests/test_v13_beacon_phase3_p2p.cpp)
target_link_libraries(test-v13-beacon-phase3-p2p PRIVATE sost-core secp256k1)
add_test(NAME v13-beacon-phase3-p2p COMMAND test-v13-beacon-phase3-p2p)

# V13 Beacon Phase III P2P scaffold — DISABLED-by-default tests.
# Pins the gate sentinel (INT64_MAX), the four hard limits, and the
# always-DiscardDormant behaviour for every input. A future commit that
# lowers the gate or relaxes a limit fails the static_asserts here at
# build time, forcing a deliberate update.
add_executable(test-v13-beacon-p2p-scaffold tests/test_v13_beacon_p2p_scaffold.cpp)
target_link_libraries(test-v13-beacon-p2p-scaffold PRIVATE sost-core)
add_test(NAME v13-beacon-p2p-scaffold COMMAND test-v13-beacon-p2p-scaffold)

# Capsule build helpers — public modes.
# Round-trip + reject coverage for the four public capsule builders
# (Open Note, Doc Ref, Template Fields, Cert Instruction). Pins the
# encode/decode contract before sost-cli starts producing capsules.
add_executable(test-capsule-build-public tests/test_capsule_build_public.cpp)
target_link_libraries(test-capsule-build-public PRIVATE sost-core)
add_test(NAME capsule-build-public COMMAND test-capsule-build-public)

# Wallet → capsule attachment. End-to-end test that
# Wallet::create_transaction(...) honours the new optional capsule_payload
# parameter: payload reaches output[0], change is left clean, the attached
# bytes still pass ValidateCapsulePolicy, and the no-payload code path is
# bit-identical to pre-change behaviour.
add_executable(test-wallet-capsule-attach tests/test_wallet_capsule_attach.cpp)
target_link_libraries(test-wallet-capsule-attach PRIVATE sost-core)
add_test(NAME wallet-capsule-attach COMMAND test-wallet-capsule-attach)

# Fase Sealed-1.A — single-recipient ECIES envelope. Round-trip,
# wrong-key, tamper-detection, and over-cap rejection on the bare
# crypto motor (no capsule header, no wallet, no mempool).
add_executable(test-sealed-envelope tests/test_sealed_envelope.cpp)
target_link_libraries(test-sealed-envelope PRIVATE sost-core OpenSSL::Crypto secp256k1)
add_test(NAME sealed-envelope COMMAND test-sealed-envelope)

# Fase Sealed-1.B — SCPv1 packaging around the ECIES envelope.
# Builders for sealed-note / sealed-doc-ref / sealed-template plus
# ValidateCapsulePolicy structural checks (no decryption, no ECDH).
add_executable(test-sealed-capsule-packaging tests/test_sealed_capsule_packaging.cpp)
target_link_libraries(test-sealed-capsule-packaging PRIVATE sost-core OpenSSL::Crypto secp256k1)
add_test(NAME sealed-capsule-packaging COMMAND test-sealed-capsule-packaging)

# Fase Sealed-1.C-2 — deterministic vector dumper. Prints fixed-input/
# fixed-output hex for the JS test harness to reproduce. Not a unit test
# in CTest's sense; consumed by tests/sealed_envelope_vectors.mjs.
add_executable(sealed-envelope-fixture tests/sealed_envelope_fixture.cpp)
target_link_libraries(sealed-envelope-fixture PRIVATE sost-core OpenSSL::Crypto secp256k1)

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

add_executable(test-dtd-control tests/test_dtd_control.cpp)
target_link_libraries(test-dtd-control PRIVATE sost-core)
add_test(NAME dtd-control COMMAND test-dtd-control)

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

    # V13 SbPoW hardening regression tests (see docs/V13_SBPOW_HARDENING.md).
    # Covers timestamp / bits_q / merkle_root / genesis_hash binding under
    # the height-gated v13 preimage, plus boundary and backwards-compat.
    add_executable(test-sbpow-v13-hardening tests/test_sbpow_v13_hardening.cpp)
    target_link_libraries(test-sbpow-v13-hardening PRIVATE sost-core)
    add_test(NAME sbpow-v13-hardening COMMAND test-sbpow-v13-hardening)
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

# PoPC single-model redesign (whitepaper §6.0) — DRAFT, consensus-DEFERRED.
# Transition tests: height gate + gold-boost math (pure functions).
add_executable(test-popc-single-model tests/test_popc_single_model.cpp)
target_link_libraries(test-popc-single-model PRIVATE sost-core)
add_test(NAME popc-single-model COMMAND test-popc-single-model)

# Regression: testnet submitblock must validate with the node's runtime profile,
# not a hardcoded MAINNET (which flipped ACTIVE_PROFILE -> wrong block_id magic).
add_executable(test-profile-magic tests/test_profile_magic.cpp)
target_link_libraries(test-profile-magic PRIVATE sost-core)
add_test(NAME profile-magic COMMAND test-profile-magic)

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

# V13 Gold Vault Slice 1 — pure-function tests for helpers
# (gv_slice1_active_at / agree / destination_allowed / amount_within_cap /
#  rate_limit_ok) AND a fail-closed-design regression that asserts the
# default sentinel state leaves consensus behaviour bit-identical.
add_executable(test-v13-gold-vault-slice1 tests/test_v13_gold_vault_slice1.cpp)
target_link_libraries(test-v13-gold-vault-slice1 PRIVATE sost-core)
add_test(NAME v13-gold-vault-slice1 COMMAND test-v13-gold-vault-slice1)

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
