// full_verify_history.cpp — see include/sost/full_verify_history.h.
#include "sost/full_verify_history.h"
#include "sost/pow/convergencex.h"
#include "sost/serialize.h"
#include "sost/crypto.h"
#include <cstring>
#include <vector>

namespace sost {

const char* full_verify_class_name(FullVerifyClass c) {
    switch (c) {
        case FullVerifyClass::VERIFIED: return "VERIFIED";
        case FullVerifyClass::ASSUMED_FROM_HISTORICAL_RULE: return "ASSUMED_FROM_HISTORICAL_RULE";
        case FullVerifyClass::UNVERIFIABLE_MISSING_HISTORICAL_DATA: return "UNVERIFIABLE_MISSING_HISTORICAL_DATA";
    }
    return "UNKNOWN";
}

int32_t derive_profile_from_stab_params(int64_t height,
                                        int32_t scale, int32_t steps,
                                        int32_t k, int32_t margin) {
    // Same table selection as casert_apply_profile(): the 43-row table from
    // V8 (CASERT_CEILING_H13_HEIGHT) on, the 40-row legacy table before.
    const bool v8 = height >= CASERT_CEILING_H13_HEIGHT;
    const CasertProfile* table = v8 ? CASERT_PROFILES : CASERT_PROFILES_LEGACY;
    const int32_t count = v8 ? CASERT_PROFILE_COUNT : CASERT_PROFILE_COUNT_LEGACY;
    const int32_t h_min = v8 ? CASERT_H_MIN : CASERT_H_MIN_LEGACY;
    int32_t found = INT32_MIN, hits = 0;
    for (int32_t i = 0; i < count; ++i) {
        const CasertProfile& p = table[i];
        if (p.scale == scale && p.steps == steps && p.k == k && p.margin == margin) {
            found = i + h_min;
            ++hits;
        }
    }
    return hits == 1 ? found : INT32_MIN;
}

std::string profile_name(int32_t pi) {
    if (pi == INT32_MIN) return "none";
    if (pi < 0) return "E" + std::to_string(-pi);
    if (pi == 0) return "B0";
    return "H" + std::to_string(pi);
}

bool verify_cx_without_transcript(const uint8_t* header_core,
                                  uint32_t nonce, uint32_t extra_nonce,
                                  const Bytes32& commit,
                                  const Bytes32& checkpoints_root,
                                  const Bytes32& segments_root,
                                  const Bytes32& final_state,
                                  const uint8_t* x_bytes, size_t x_bytes_len,
                                  uint64_t stability_metric,
                                  const ConsensusParams& params,
                                  std::string* fail_reason) {
    auto fail = [&](const std::string& why) {
        if (fail_reason) *fail_reason = why;
        return false;
    };
    const int32_t n = params.cx_n;
    if (n <= 0 || n > 32) return fail("cx_n out of range");

    // Phase 1 (the part that needs no transcript): x_bytes length.
    if ((int64_t)x_bytes_len != (int64_t)n * 4) return fail("phase 1: x_bytes length != n*4");

    // Phase 4: seed.
    Bytes32 prev_hash;
    std::memcpy(prev_hash.data(), header_core, 32);
    const Bytes32 block_key = compute_block_key(prev_hash);
    std::vector<uint8_t> sbuf;
    append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, header_core, 72); append(sbuf, block_key);
    append_u32_le(sbuf, nonce); append_u32_le(sbuf, extra_nonce);
    const Bytes32 seed = sha256(sbuf);

    // Phase 5: commit binding (header, seed, final_state, x_bytes, both
    // roots, metric and the profile byte).
    std::vector<uint8_t> cbuf;
    append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, header_core, 72); append(cbuf, seed); append(cbuf, final_state);
    append(cbuf, x_bytes, x_bytes_len);
    append(cbuf, checkpoints_root); append(cbuf, segments_root);
    append_u64_le(cbuf, stability_metric);
    cbuf.push_back((uint8_t)(int8_t)params.stab_profile_index);
    if (sha256(cbuf) != commit) return fail("phase 5: commit binding mismatch");

    // Phase 9: stability basin.
    int32_t x[32];
    for (int i = 0; i < n; ++i) x[i] = read_i32_le(x_bytes + i * 4);
    const CXProblem prob = derive_M_and_b(block_key, n, params.cx_lam);
    const Bytes32 stctx = stability_ctx(header_core, seed, checkpoints_root);
    uint64_t metric_out = 0;
    if (!verify_stability_basin(x, prob, n, params.cx_lr_shift, stctx,
                                params.stab_scale, params.stab_k, params.stab_margin,
                                params.stab_steps, params.stab_lr_shift, metric_out))
        return fail("phase 9: stability basin failed");

    // Phase 10: metric.
    if (metric_out != stability_metric) return fail("phase 10: stability metric mismatch");
    return true;
}

} // namespace sost
