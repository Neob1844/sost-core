#include "sost/pow/casert.h"
#include <algorithm>
namespace sost {
CasertDecision casert_mode_from_chain(const std::vector<BlockMeta>& chain, int64_t next_height) {
    if (next_height < 2 || chain.size() < 2) return {CasertMode::WARMUP, 0, 0};
    std::vector<int32_t> deltas;
    size_t start = (chain.size() > (size_t)(CASERT_MAX_INTERVALS+1))
                 ? chain.size() - CASERT_MAX_INTERVALS - 1 : 0;
    for (size_t i = start+1; i < chain.size(); ++i) {
        int64_t dt = chain[i].time - chain[i-1].time;
        if (dt < 1) dt = 1;
        deltas.push_back((int32_t)dt);
    }
    if (deltas.empty()) return {CasertMode::WARMUP, 0, 0};
    int64_t score = 0;
    for (int32_t dt : deltas) {
        int32_t err = dt - (int32_t)TARGET_SPACING;
        if (err > CASERT_E_CAP) err = CASERT_E_CAP;
        if (err < -CASERT_E_CAP) err = -CASERT_E_CAP;
        score += err;
    }
    int32_t n = (int32_t)deltas.size();
    int32_t signal = (int32_t)(score / (int64_t)n);
    CasertMode mode;
    if (signal > CASERT_OPEN_TH) mode = CasertMode::OPEN;
    else if (signal > CASERT_DEGRADED_TH) mode = CasertMode::DEGRADED;
    else mode = CasertMode::NORMAL;
    return {mode, signal, n};
}
ConsensusParams casert_apply_overlay(const ConsensusParams& base, const CasertDecision& dec) {
    ConsensusParams out = base;
    // Level 1-3: fixed thresholds. Level 4+: rises every 200 signal points.
    int32_t level;
    if      (dec.signal_s > 200)   level = 1;  // chain very slow
    else if (dec.signal_s > 0)     level = 2;  // chain slow
    else if (dec.signal_s > -200)  level = 3;  // normal range
    else level = 3 + (-dec.signal_s - 200) / 200;  // progressive hardening

    // Scale and steps rise with level. k stays fixed.
    out.stab_scale  = level;
    out.stab_k      = 3;
    out.stab_steps  = 3;
    out.stab_margin = CX_STB_MARGIN;
    return out;
}
} // namespace sost
