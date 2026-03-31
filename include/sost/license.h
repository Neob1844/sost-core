// license.h — ConvergenceX License System (Deposit-Based)
//
// Licenses are JSON documents signed by the Foundation's ECDSA key.
// Verification is trustless: anyone can verify on-chain without contacting
// the Foundation.
//
// A license is required for commercial deployment of ConvergenceX.
// No license is needed for: code study, research, private testing, contributions.
#pragma once

#include "sost/transaction.h"
#include <cstdint>
#include <string>

namespace sost {

// License constants
inline constexpr int64_t LICENSE_LOCK_BLOCKS    = 52560;   // ~1 year at 10min/block
inline constexpr int64_t LICENSE_GRACE_BLOCKS   = 4320;    // ~30 days grace period for auto-renewal
inline constexpr int64_t LICENSE_MIN_USD        = 1000;    // $1000 USD equiv minimum deposit
inline constexpr const char* LICENSE_TYPE_CX    = "convergencex_operational";

// Auto-renewal: if deposit is not withdrawn within GRACE_BLOCKS after expiry,
// the license auto-renews for another LICENSE_LOCK_BLOCKS period.
// Timeline: lock → 52,560 blocks → grace (4,320) → auto-renew or expire

struct SOSTLicense {
    Hash256     license_id;          // SHA256(txid + address + timestamp)
    std::string licensee_address;    // SOST address of licensee
    std::string deposit_txid;        // TXID of ESCROW_LOCK deposit
    int64_t     deposit_stocks;      // SOST amount locked (in stocks)
    int64_t     deposit_usd_micro;   // USD equivalent at lock time (micro-USD)
    int64_t     lock_height;         // Block where deposit was locked
    int64_t     unlock_height;       // lock_height + LICENSE_LOCK_BLOCKS
    std::string license_type;        // "convergencex_operational"
    std::string scope;               // What the license permits
    std::string issued_at;           // ISO 8601 timestamp
    std::string status;              // "ACTIVE", "EXPIRED", "REVOKED"
    std::vector<uint8_t> signature;  // ECDSA signature by Foundation
};

// Verify that a license signature is valid
bool verify_license_signature(const SOSTLicense& lic, const PubKey& foundation_pubkey);

// Check if a deposit meets the minimum USD requirement
// sost_price_usd = current PoPC reference price
bool deposit_meets_minimum(int64_t deposit_stocks, double sost_price_usd);

} // namespace sost
