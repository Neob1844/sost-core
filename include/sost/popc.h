// popc.h — Proof of Personal Custody (PoPC) Model A
//
// Design document: docs/POPC_MODEL_A_SPECIFICATION.md
// Whitepaper reference: Section 6
//
// Status: SKELETON — structures defined, functions declared but NOT implemented.
// Implementation requires CTO review and approval.
//
// Key design principle: "No consensus changes. All PoPC logic remains
// operational/application-layer except that the PoPC Pool receives 25%
// coinbase by consensus." — Whitepaper Section 6
#pragma once

#include "sost/transaction.h"
#include "sost/address.h"
#include <string>
#include <vector>
#include <cstdint>

namespace sost {

// =========================================================================
// Constants
// =========================================================================

// Valid commitment durations (months)
static constexpr uint16_t POPC_DURATIONS[] = {1, 3, 6, 9, 12};

// Reward rates (% of bond × 100) — operational, not consensus
static constexpr uint16_t POPC_REWARD_RATES[] = {100, 400, 900, 1500, 2200};

// Protocol fee on rewards (5% × 100 = 500 basis points)
static constexpr uint16_t POPC_PROTOCOL_FEE_BPS = 500;

// Slash distribution: 50% PoPC Pool, 50% Gold Vault
static constexpr uint16_t POPC_SLASH_POOL_PCT = 50;
static constexpr uint16_t POPC_SLASH_VAULT_PCT = 50;

// Reputation tiers
static constexpr uint8_t  POPC_STARS_NEW       = 0;
static constexpr uint8_t  POPC_STARS_ESTAB     = 1;
static constexpr uint8_t  POPC_STARS_TRUSTED   = 3;
static constexpr uint8_t  POPC_STARS_VETERAN   = 5;

// Max gold (milligrams) per reputation tier
static constexpr int64_t  POPC_MAX_MG_NEW      = 15552;   // 0.5 oz
static constexpr int64_t  POPC_MAX_MG_ESTAB    = 31103;   // 1 oz
static constexpr int64_t  POPC_MAX_MG_TRUSTED  = 93310;   // 3 oz
static constexpr int64_t  POPC_MAX_MG_VETERAN  = 311035;  // 10 oz

// Audit probability by reputation (per mille)
static constexpr uint16_t POPC_AUDIT_PROB_NEW     = 300;  // 30%
static constexpr uint16_t POPC_AUDIT_PROB_ESTAB   = 200;  // 20%
static constexpr uint16_t POPC_AUDIT_PROB_TRUSTED = 100;  // 10%
static constexpr uint16_t POPC_AUDIT_PROB_VETERAN = 50;   // 5%

// Grace period for audit response (blocks ≈ 48 hours)
static constexpr int64_t  POPC_AUDIT_GRACE_BLOCKS = 288;  // 48h at 10min/block

// =========================================================================
// Commitment status
// =========================================================================
enum class PoPCStatus : uint8_t {
    ACTIVE    = 0,
    COMPLETED = 1,
    SLASHED   = 2,
    EXPIRED   = 3,
};

// =========================================================================
// Commitment record
// =========================================================================
struct PoPCCommitment {
    Hash256     commitment_id;       // SHA256 of canonical terms
    PubKeyHash  user_pkh;            // SOST address
    std::string eth_wallet;          // Ethereum EOA (0x...)
    std::string gold_token;          // "XAUT" or "PAXG"
    int64_t     gold_amount_mg;      // milligrams (integer)
    int64_t     bond_sost_stocks;    // bond in stocks (integer, no float)
    uint16_t    duration_months;     // 1, 3, 6, 9, or 12
    int64_t     start_height;        // block at registration
    int64_t     end_height;          // block at expiry
    uint16_t    bond_pct_bps;        // bond % × 100
    uint16_t    reward_pct_bps;      // reward % × 100
    PoPCStatus  status;

    // Frozen price reference
    int64_t     sost_price_usd_micro;  // micro-USD (integer)
    int64_t     gold_price_usd_micro;  // micro-USD per oz (integer)
};

// =========================================================================
// Audit record
// =========================================================================
struct PoPCAudit {
    Hash256     commitment_id;
    int64_t     audit_height;
    Hash256     entropy_seed;        // SHA256(block_id || commit || checkpoints_root)
    bool        passed;
    int64_t     balance_observed_mg;
    int64_t     response_height;     // block when user responded
};

// =========================================================================
// Reputation
// =========================================================================
struct PoPCReputation {
    PubKeyHash  user_pkh;
    uint8_t     stars;               // 0, 1, 3, 5
    uint16_t    contracts_completed;
    uint16_t    contracts_slashed;
    bool        blacklisted;
};

// =========================================================================
// Bond sizing (constitutional — from whitepaper Section 6.5)
// =========================================================================

// Returns bond percentage in basis points (e.g., 2500 = 25%)
// ratio_bps = (sost_price / gold_oz_price) × 10000
uint16_t compute_bond_pct(uint64_t ratio_bps);

// Returns reward percentage in basis points
uint16_t compute_reward_pct(uint16_t duration_months);

// Returns max gold (mg) for a reputation level
int64_t max_gold_for_reputation(uint8_t stars);

// Returns audit probability (per mille) for a reputation level
uint16_t audit_probability(uint8_t stars);

// =========================================================================
// Audit entropy (from ConvergenceX — whitepaper Section 6.3)
// =========================================================================

// Derive audit seed from block header
Hash256 compute_audit_seed(const Hash256& block_id,
                            const Hash256& commit,
                            const Hash256& checkpoints_root);

// Check if an audit is triggered for a commitment at a given block
bool is_audit_triggered(const Hash256& audit_seed,
                        const Hash256& commitment_id,
                        uint16_t period_index,
                        uint16_t audit_prob_permille);

// =========================================================================
// Registry (application-layer — NOT consensus)
// =========================================================================
class PoPCRegistry {
public:
    // Register a new commitment
    bool register_commitment(const PoPCCommitment& c, std::string* err = nullptr);

    // Query
    const PoPCCommitment* find(const Hash256& commitment_id) const;
    std::vector<PoPCCommitment> list_active() const;
    std::vector<PoPCCommitment> list_by_user(const PubKeyHash& pkh) const;

    // Lifecycle
    bool complete(const Hash256& commitment_id, std::string* err = nullptr);
    bool slash(const Hash256& commitment_id, const std::string& reason, std::string* err = nullptr);

    // Reputation
    PoPCReputation get_reputation(const PubKeyHash& pkh) const;
    void update_reputation(const PubKeyHash& pkh, bool success);

    // Persistence
    bool save(const std::string& path, std::string* err = nullptr) const;
    bool load(const std::string& path, std::string* err = nullptr);

    // Stats
    size_t active_count() const;
    int64_t total_bonded_stocks() const;

private:
    std::vector<PoPCCommitment> commitments_;
    std::vector<PoPCReputation> reputations_;
};

} // namespace sost
