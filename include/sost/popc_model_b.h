// popc_model_b.h — PoPC Model B (Escrow-Based)
// No consensus changes — application layer only.
// ESCROW_LOCK (0x11) is active at height 10000 (V6 hard fork).
#pragma once
#include "sost/transaction.h"
#include "sost/popc.h"
#include <string>
#include <vector>
#include <cstdint>

namespace sost {

enum class EscrowStatus : uint8_t {
    ACTIVE    = 0,
    COMPLETED = 1,
    FAILED    = 2,
};

struct EscrowCommitment {
    Hash256     escrow_id;          // SHA256 of canonical terms
    PubKeyHash  user_pkh;           // SOST address
    std::string eth_escrow_address; // Ethereum escrow contract
    std::string gold_token;         // "XAUT" or "PAXG"
    int64_t     gold_amount_mg;     // milligrams deposited
    int64_t     reward_stocks;      // SOST reward (paid immediately)
    uint16_t    duration_months;    // 1, 3, 6, 9, or 12
    int64_t     start_height;
    int64_t     end_height;
    EscrowStatus status;
};

class EscrowRegistry {
public:
    bool register_escrow(const EscrowCommitment& e, std::string* err = nullptr);
    const EscrowCommitment* find(const Hash256& escrow_id) const;
    std::vector<EscrowCommitment> list_active() const;
    bool complete(const Hash256& escrow_id, std::string* err = nullptr);
    bool mark_failed(const Hash256& escrow_id, const std::string& reason, std::string* err = nullptr);
    size_t active_count() const;
    bool save(const std::string& path, std::string* err = nullptr) const;
    bool load(const std::string& path, std::string* err = nullptr);
private:
    std::vector<EscrowCommitment> escrows_;
};

// Calculate immediate reward for Model B
// Same rates as Model A but paid upfront
int64_t calculate_escrow_reward(int64_t gold_value_stocks, uint16_t duration_months);

} // namespace sost
