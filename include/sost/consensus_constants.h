// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once
#include <cstdint>
#include <cstddef>

namespace sost {

// Monetary unit
inline constexpr int64_t STOCKS_PER_SOST   = 100'000'000LL;              // 1e-8 SOST
inline constexpr int64_t SUPPLY_MAX_STOCKS = 466'920'160'910'299LL;      // ~4.669M SOST

// Consensus limits
inline constexpr int64_t  COINBASE_MATURITY         = 1000;
inline constexpr int32_t  MAX_TX_BYTES_CONSENSUS    = 100'000;
inline constexpr int32_t  MAX_BLOCK_BYTES_CONSENSUS = 1'000'000;
inline constexpr uint16_t MAX_INPUTS_CONSENSUS      = 256;
inline constexpr uint16_t MAX_OUTPUTS_CONSENSUS     = 256;

// Bond/Escrow activation — BOND_LOCK (0x10) and ESCROW_LOCK (0x11) become valid
// output types after this height. Before activation, R11 rejects them.
inline constexpr int64_t  BOND_ACTIVATION_HEIGHT_MAINNET = 10000;
inline constexpr int64_t  BOND_ACTIVATION_HEIGHT_TESTNET = 100;
inline constexpr int64_t  BOND_ACTIVATION_HEIGHT_DEV     = 1;

// Payload sizes for lock outputs
inline constexpr uint16_t BOND_LOCK_PAYLOAD_LEN   = 8;   // lock_until (uint64 LE)
inline constexpr uint16_t ESCROW_LOCK_PAYLOAD_LEN = 28;  // lock_until (8) + beneficiary_pkh (20)

// =========================================================================
// Gold Vault Governance — Consensus-level spending rules
// Activates at BOND_ACTIVATION_HEIGHT (10000). Before that, no restriction.
// =========================================================================

// Activation (same height as Bond/Escrow/Capsule)
inline constexpr int64_t  GV_GOVERNANCE_ACTIVATION = 10000;

// Signaling thresholds for large Gold Vault spends
inline constexpr int32_t  GV_THRESHOLD_EPOCH01  = 95;   // 95% in Epoch 0-1 (V6: raised from 75% — see BTCTalk ANN post #89)
inline constexpr int32_t  GV_THRESHOLD_EPOCH2   = 95;   // 95% in Epoch 2+ (blocks 263106+)
inline constexpr int32_t  GV_APPROVAL_WINDOW    = 288;  // ~48h voting window

// Foundation quality vote (expires at Epoch 2)
inline constexpr int32_t  GV_FOUNDATION_VOTE_PCT = 10;  // +10% equivalent signaling
// Foundation veto expires at FOUNDATION_VETO_EXPIRY_BLOCKS (263106) from proposals.h

// Monthly operational limit (no voting required below this)
inline constexpr int32_t  GV_MONTHLY_LIMIT_PCT  = 10;   // 10% of vault balance
inline constexpr int64_t  GV_MONTHLY_WINDOW     = 4320; // ~30 days at 10min/block

// Gold purchase payload marker
inline constexpr uint8_t  GV_PAYLOAD_GOLD_PURCHASE = 0x47; // 'G' — marks TX as gold purchase

// =========================================================================
// V13 Gold Vault Slice 1 — MIRROR whitelist (G2 dual-source-of-truth)
// =========================================================================
//
// This is the SECOND of the two independent whitelists required by G2 of
// docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md. The PRIMARY whitelist lives in
// include/sost/gold_vault_slice1.h (GV_SLICE1_WHITELIST_PRIMARY).
//
// The validator (via gv_slice1_whitelists_agree() in
// src/gold_vault_slice1.cpp) compares PRIMARY and MIRROR element-by-element
// and fails closed on any mismatch. This catches operator misconfiguration
// where one constant table is edited but the other is forgotten — that
// failure mode would otherwise become a silent consensus split.
//
// Default: empty. With GV_SLICE1_ACTIVATION_HEIGHT also at INT64_MAX in
// the PRIMARY header, the rule is fully sentinel-disabled and the
// validator wiring is a no-op for every block.
//
// To activate the rule in a future commit, the operator MUST:
//   1. Set GV_SLICE1_ACTIVATION_HEIGHT = V13_HEIGHT in gold_vault_slice1.h
//   2. Populate GV_SLICE1_WHITELIST_PRIMARY with the agreed PubKeyHashes
//   3. Populate GV_SLICE1_WHITELIST_MIRROR_DATA below with the same set in
//      the same order, AND set GV_SLICE1_WHITELIST_MIRROR_LEN accordingly
//   4. Set GV_SLICE1_PER_SPEND_CAP_BPS in gold_vault_slice1.h
//   5. Set GV_SLICE1_RATE_LIMIT_BLOCKS in gold_vault_slice1.h
//      (rate-limit wiring needs a separate StoredBlock field extension)
//
// All five steps land in a single small reviewable commit.
//
inline constexpr std::size_t GV_SLICE1_WHITELIST_MIRROR_LEN = 0;
// PubKeyHash is defined in include/sost/tx_signer.h; we only need the size
// (20 bytes) here for the array declaration. To avoid a heavy include
// chain in this header, the actual array is forward-declared as 20-byte
// raw entries — the .cpp that calls gv_slice1_whitelists_agree() will
// convert / compare via the PubKeyHash type from tx_signer.h.
inline constexpr std::size_t GV_SLICE1_PKH_LEN = 20;
// Empty array literal — zero rows, each row 20 bytes.
extern const unsigned char GV_SLICE1_WHITELIST_MIRROR_DATA[][20];

} // namespace sost
