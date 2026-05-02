// lottery.cpp — V11 Phase 2 component D: Proof-of-Participation lottery
//
// Spec: docs/V11_SPEC.md §4 + §10.5
// Status: SKELETON — every entry point aborts when invoked. The real
// implementation lands together with the activation of
// V11_PHASE2_HEIGHT, after gates G4.1-G4.4 in V11_SPEC.md §6.
#include "sost/lottery.h"

#include <cstdio>
#include <cstdlib>

namespace sost::lottery {

namespace {
[[noreturn]] void phase2_not_implemented(const char* fn) {
    std::fprintf(stderr,
        "FATAL: sost::lottery::%s called before V11 Phase 2 implementation. "
        "This is a skeleton — wire the real code before activating "
        "V11_PHASE2_HEIGHT.\n", fn);
    std::abort();
}
} // namespace

bool is_triggered(int64_t /*height*/,
                  int64_t /*v11_phase2_height*/,
                  int64_t /*high_freq_window*/)
{
    phase2_not_implemented("is_triggered");
}

std::vector<PubKeyHash> eligibility_set(
    int64_t /*height*/,
    const std::vector<PubKeyHash>& /*addrs_with_block_since_genesis*/,
    const std::vector<PubKeyHash>& /*recent_block_winners*/,
    const PubKeyHash& /*current_block_miner*/,
    int32_t /*exclusion_window*/)
{
    phase2_not_implemented("eligibility_set");
}

std::optional<PubKeyHash> pick_winner(const Bytes32& /*prev_block_hash*/,
                                   int64_t /*height*/,
                                   const std::vector<PubKeyHash>& /*eligibility_sorted*/)
{
    phase2_not_implemented("pick_winner");
}

void apply_block(RolloverState& /*state*/,
                 const TransitionInputs& /*in*/,
                 TransitionOutputs& /*out*/)
{
    phase2_not_implemented("apply_block");
}

void undo_block(RolloverState& /*state*/, uint64_t /*pending_before_block*/) {
    phase2_not_implemented("undo_block");
}

} // namespace sost::lottery
