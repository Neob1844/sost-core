// gold_vault_governance.h — Consensus-level Gold Vault spending rules
//
// Activates at block 5000 (same as Bond/Escrow/Capsule).
// Before block 5000: no spending restrictions on Gold Vault.
//
// 4 rules:
//   GV1: Gold purchase (marked payload) → no vote needed
//   GV2: ≤10% monthly operational → no vote needed
//   GV3: >10% or non-standard → requires 75%/95% miner vote
//   GV4: No rule matched → REJECTED
//
// Foundation quality vote (+10%) expires at Epoch 2 (block 263106).
// After Epoch 2: threshold rises to 95%, no foundation vote.
#pragma once

#include "sost/consensus_constants.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include <cstdint>
#include <string>
#include <vector>

namespace sost {

// =========================================================================
// Gold Vault spend classification
// =========================================================================
enum class GVSpendType : uint8_t {
    GOLD_PURCHASE      = 0,  // GV1: constitutional purpose, no vote
    OPERATIONAL_SMALL  = 1,  // GV2: ≤10% monthly, no vote
    REQUIRES_APPROVAL  = 2,  // GV3: needs miner signaling
    REJECTED           = 3,  // GV4: no rule matches
};

// =========================================================================
// Approval token — embedded in TX payload to prove miner approval
// =========================================================================
struct GVApprovalToken {
    Hash256  proposal_id;       // SHA256 of proposal
    int64_t  approved_height;   // block where threshold was met
    int32_t  signal_pct;        // percentage achieved
    int32_t  threshold_required; // 75 or 95
    bool     foundation_supported;
};

// =========================================================================
// Proposal for Gold Vault spending
// =========================================================================
struct GVProposal {
    Hash256     id;
    int64_t     amount_stocks;
    PubKeyHash  destination;
    std::string reason;          // max 256 chars
    int64_t     start_height;
    int64_t     end_height;      // start + GV_APPROVAL_WINDOW
    uint8_t     proposal_type;   // 0=general, 1=gold_purchase
    bool        foundation_vetoed;
    bool        foundation_supported;
    bool        executed;
    int32_t     signal_count;    // blocks signaling
    int32_t     window_size;     // total blocks in window
};

// =========================================================================
// Gold Vault spending tracker (monthly limit)
// =========================================================================
struct GVMonthlyTracker {
    int64_t  window_start_height{0};
    int64_t  spent_stocks{0};

    void reset(int64_t height) {
        window_start_height = height;
        spent_stocks = 0;
    }

    bool is_within_window(int64_t current_height) const {
        return (current_height - window_start_height) < GV_MONTHLY_WINDOW;
    }

    int64_t remaining_allowance(int64_t vault_balance) const {
        int64_t limit = (vault_balance * GV_MONTHLY_LIMIT_PCT) / 100;
        return (limit > spent_stocks) ? (limit - spent_stocks) : 0;
    }
};

// =========================================================================
// Core validation function — called from tx_validation for Gold Vault spends
// =========================================================================

// Classify a Gold Vault spend and determine if it's allowed.
// vault_balance = current SOST balance of Gold Vault address (stocks)
// spend_amount = total amount being spent from Gold Vault in this TX (stocks)
// has_gold_purchase_marker = true if TX payload contains GV_PAYLOAD_GOLD_PURCHASE
// approval_token = non-null if TX includes a valid approval token
// monthly_tracker = tracks spending over the last 4320 blocks
// current_height = block height for threshold selection
inline GVSpendType classify_gv_spend(
    int64_t vault_balance,
    int64_t spend_amount,
    bool has_gold_purchase_marker,
    const GVApprovalToken* approval_token,
    const GVMonthlyTracker& monthly_tracker,
    int64_t current_height)
{
    // Before activation: all spends allowed (no governance)
    if (current_height < GV_GOVERNANCE_ACTIVATION) {
        return GVSpendType::GOLD_PURCHASE; // treat as allowed
    }

    // GV1: Gold purchase with marker → allowed without vote
    if (has_gold_purchase_marker) {
        return GVSpendType::GOLD_PURCHASE;
    }

    // GV2: Small operational spend ≤ monthly limit → allowed without vote
    if (monthly_tracker.is_within_window(current_height)) {
        if (spend_amount <= monthly_tracker.remaining_allowance(vault_balance)) {
            return GVSpendType::OPERATIONAL_SMALL;
        }
    } else {
        // Window expired — fresh allowance
        int64_t fresh_limit = (vault_balance * GV_MONTHLY_LIMIT_PCT) / 100;
        if (spend_amount <= fresh_limit) {
            return GVSpendType::OPERATIONAL_SMALL;
        }
    }

    // GV3: Requires approval token with sufficient signaling
    if (approval_token) {
        int32_t required = (current_height >= 263106) ? GV_THRESHOLD_EPOCH2 : GV_THRESHOLD_EPOCH01;
        int32_t effective_pct = approval_token->signal_pct;
        // Add foundation bonus in Epoch 0-1 only
        if (current_height < 263106 && approval_token->foundation_supported) {
            effective_pct += GV_FOUNDATION_VOTE_PCT;
        }
        if (effective_pct >= required && approval_token->threshold_required == required) {
            return GVSpendType::REQUIRES_APPROVAL; // approved via vote
        }
    }

    // GV4: No rule matched → REJECTED
    return GVSpendType::REJECTED;
}

// Check if a specific Gold Vault proposal passes the threshold
inline bool gv_proposal_passes(int32_t signal_count, int32_t window_size,
                                bool foundation_supported, int64_t current_height) {
    if (window_size <= 0) return false;
    int32_t pct = (signal_count * 100) / window_size;
    if (current_height < 263106 && foundation_supported) {
        pct += GV_FOUNDATION_VOTE_PCT;
    }
    int32_t required = (current_height >= 263106) ? GV_THRESHOLD_EPOCH2 : GV_THRESHOLD_EPOCH01;
    return pct >= required;
}

} // namespace sost
