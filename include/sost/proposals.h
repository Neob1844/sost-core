// proposals.h — Version-bit signaling for consensus upgrades (BIP9-style)
// Block header version field (32 bits):
//   Bits 0-7:   Protocol version (currently 1)
//   Bits 8-28:  Available for proposal signaling (21 concurrent proposals)
//   Bits 29-31: Reserved
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace sost {

// Signaling parameters
inline constexpr int32_t  SIGNALING_THRESHOLD_PCT  = 75;    // 75% of blocks must signal
inline constexpr int32_t  SIGNALING_WINDOW         = 288;   // ~48 hours at 10min/block
inline constexpr int32_t  FOUNDATION_WEIGHT_BLOCKS = 29;    // ~10% of 288 window

// Proposal status
enum class ProposalStatus : uint8_t {
    DEFINED    = 0,  // Proposal exists, not yet signaling
    STARTED    = 1,  // Signaling period active
    LOCKED_IN  = 2,  // Threshold reached, waiting for activation
    ACTIVE     = 3,  // Activated
    FAILED     = 4,  // Signaling period expired without reaching threshold
    VETOED     = 5,  // Foundation veto applied
};

struct Proposal {
    uint8_t     bit;          // Which bit (8-28) in the version field
    std::string name;
    std::string description;
    int64_t     start_height; // When signaling begins
    int64_t     timeout_height; // When signaling expires if not reached
    int64_t     activation_height; // Set when LOCKED_IN (start + SIGNALING_WINDOW)
    ProposalStatus status;
    bool        foundation_veto;
    bool        foundation_support;
};

// Get all defined proposals (currently empty — no active proposals)
inline std::vector<Proposal> get_proposals() {
    // Placeholder: Post-Quantum Migration (not active, just reserved)
    return {
        {8, "post_quantum", "Post-Quantum Signature Migration (SPHINCS+/Dilithium)",
         -1, -1, -1, ProposalStatus::DEFINED, false, false}
    };
}

// Check if a specific bit is set in a block version
inline bool version_has_signal(uint32_t version, uint8_t bit) {
    if (bit < 8 || bit > 28) return false;
    return (version >> bit) & 1;
}

// Count how many blocks in a window signal for a given bit
// chain = vector of block versions (most recent last)
// Returns count of blocks with the bit set
inline int32_t count_version_signals(const std::vector<uint32_t>& versions, uint8_t bit, int32_t window = SIGNALING_WINDOW) {
    int32_t count = 0;
    int32_t start = (int32_t)versions.size() - window;
    if (start < 0) start = 0;
    for (int32_t i = start; i < (int32_t)versions.size(); ++i) {
        if (version_has_signal(versions[i], bit)) ++count;
    }
    return count;
}

// Check if activation threshold is met
// foundation_support adds FOUNDATION_WEIGHT_BLOCKS equivalent signals
// foundation_veto blocks activation regardless
inline bool check_activation(const std::vector<uint32_t>& versions, uint8_t bit,
                              bool foundation_support = false, bool foundation_veto = false) {
    if (foundation_veto) return false;
    int32_t window = std::min((int32_t)versions.size(), SIGNALING_WINDOW);
    if (window == 0) return false;
    int32_t count = count_version_signals(versions, bit, window);
    if (foundation_support) count += FOUNDATION_WEIGHT_BLOCKS;
    int32_t threshold = (window * SIGNALING_THRESHOLD_PCT) / 100;
    return count >= threshold;
}

// Foundation quality vote expiration:
// The Foundation retains the quality vote until it voluntarily relinquishes it.
// However, the quality vote expires AUTOMATICALLY and IRREVOCABLY at the end of
// Epoch 2 (block 263,106 = 2 × 131,553). This is hard-coded — no governance vote,
// no extension, no override. The Foundation may remove it earlier at its sole
// discretion, but cannot extend it beyond Epoch 2 under any circumstance.
// Approximately 5 years post-genesis.
inline constexpr int64_t FOUNDATION_VETO_EXPIRY_BLOCKS = 263'106; // End of Epoch 2 (~5 years)

inline bool foundation_veto_active(int64_t current_height) {
    if (current_height >= FOUNDATION_VETO_EXPIRY_BLOCKS) return false;
    return true;
}

} // namespace sost
