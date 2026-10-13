// =============================================================================
// full_verify_history.h — `--full-verify` on the transcript-less early mainnet
// window (heights 1..3300). Verification tooling only: nothing here is reached
// by the default sync path, and no consensus rule for any height changes.
//
// Background (docs/verification/FULL_VERIFY_EARLY_CHAIN.md): before commit
// 07e49b16, save_chain_internal() dropped checkpoint_leaves, segment_proofs,
// round_witnesses and profile_index, so no node holds the Transcript V2 data
// of mainnet blocks 1..3300. What survives is enough to re-check the commit
// binding, the stability basin and the metric (verify_cx_proof phases 1, 4,
// 5, 9, 10) once the profile is derived from the stored stab_* parameters.
// The sequential-work evidence (phases 2, 3, 6, 7, 8) cannot be re-checked
// without the transcript; only a full ConvergenceX recompute (cx-reverify,
// ~8.4 GB per block) can stand in for it.
// =============================================================================
#pragma once

#include "sost/params.h"
#include "sost/types.h"
#include <cstddef>
#include <cstdint>
#include <string>

namespace sost {

// Last mainnet height whose Transcript V2 data was never persisted. Every
// mainnet block 1..3300 lacks it; every block from 3301 on carries it.
inline constexpr int64_t FULL_VERIFY_TRANSCRIPTLESS_LAST_HEIGHT = 3300;

// How `--full-verify` accounted for a block's ConvergenceX proof.
enum class FullVerifyClass : uint8_t {
    // verify_cx_proof() passed on the block's own Transcript V2 data.
    VERIFIED = 0,
    // Transcript V2 data absent, mainnet height <= 3300, every check that can
    // run without the transcript passed, and the block is accepted only
    // because `--full-verify-anchored-history` was given. Its identity is
    // pinned by the hash chain to the compiled-in hard checkpoints (the last
    // one in the window is 3300). The sequential work was NOT re-checked.
    ASSUMED_FROM_HISTORICAL_RULE = 1,
    // Transcript V2 data absent and the block is not covered by an opt-in
    // historical rule: plain `--full-verify` rejects it.
    UNVERIFIABLE_MISSING_HISTORICAL_DATA = 2,
};

const char* full_verify_class_name(FullVerifyClass c);

// Profile index whose cASERT table row (the table casert_apply_profile uses
// at `height`) equals the stored (scale, steps, k, margin). INT32_MIN when no
// row, or more than one row, matches. Deterministic, pure.
int32_t derive_profile_from_stab_params(int64_t height,
                                        int32_t scale, int32_t steps,
                                        int32_t k, int32_t margin);

// Short name of a profile index: E4..E1, B0, H1..H35 (E7..E5 from V8 on).
std::string profile_name(int32_t profile_index);

// The ConvergenceX checks that need no transcript, exactly as verify_cx_proof
// runs them: phase 1 (x_bytes length), 4 (seed), 5 (commit binding, which
// includes the profile byte), 9 (stability basin) and 10 (metric). `params`
// must already carry the block's profile (casert_apply_profile). Returns true
// when all pass; otherwise false and `fail_reason` names the first failure.
bool verify_cx_without_transcript(const uint8_t* header_core, // 72 bytes
                                  uint32_t nonce, uint32_t extra_nonce,
                                  const Bytes32& commit,
                                  const Bytes32& checkpoints_root,
                                  const Bytes32& segments_root,
                                  const Bytes32& final_state,
                                  const uint8_t* x_bytes, size_t x_bytes_len,
                                  uint64_t stability_metric,
                                  const ConsensusParams& params,
                                  std::string* fail_reason);

// Whether a transcript-less block at `height` may be classified
// ASSUMED_FROM_HISTORICAL_RULE: mainnet, 1 <= height <= 3300 and the
// operator opted in. Anything else without a transcript is
// UNVERIFIABLE_MISSING_HISTORICAL_DATA (and rejected).
inline bool full_verify_historical_rule_applies(Profile profile, int64_t height,
                                                bool anchored_history_opt_in) {
    return anchored_history_opt_in && profile == Profile::MAINNET
        && height >= 1 && height <= FULL_VERIFY_TRANSCRIPTLESS_LAST_HEIGHT;
}

} // namespace sost
