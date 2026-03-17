#include "sost/emission.h"
#include <stdexcept>
namespace sost {
// sost_subsidy_stocks() removed — single definition lives in subsidy.cpp
// qmul_floor / qpow_floor removed — only used by the deleted function above
CoinbaseSplit coinbase_split(int64_t reward) {
    int64_t q = reward / 4;
    return { reward - q - q, q, q, reward };
}
ConsensusParams get_consensus_params(Profile profile, int64_t) {
    ACTIVE_PROFILE = profile; // Set global for MAGIC derivation
    ConsensusParams p{};
    p.cx_n = CX_N; p.cx_lr_shift = CX_LR_SHIFT; p.cx_lam = CX_LAM;
    switch (profile) {
    case Profile::DEV:
        p.cx_rounds = CX_ROUNDS_D; p.cx_scratch_mb = CX_SCRATCH_D;
        p.cx_checkpoint_interval = CX_CP_D;
        p.stab_scale = 1; p.stab_k = 1; p.stab_margin = 2048;
        p.stab_steps = 1; p.stab_lr_shift = CX_LR_SHIFT + 2;
        p.stab_profile_index = 0; break;
    case Profile::TESTNET:
        p.cx_rounds = CX_ROUNDS_T; p.cx_scratch_mb = CX_SCRATCH_T;
        p.cx_checkpoint_interval = CX_CP_T;
        p.stab_scale = 1; p.stab_k = 1; p.stab_margin = 1536;
        p.stab_steps = 1; p.stab_lr_shift = CX_LR_SHIFT + 2;
        p.stab_profile_index = 0; break;
    case Profile::MAINNET: default:
        p.cx_rounds = CX_ROUNDS_M; p.cx_scratch_mb = CX_SCRATCH_M;
        p.cx_checkpoint_interval = CX_CP_M;
        p.stab_scale = CX_STB_SCALE; p.stab_k = CX_STB_K;
        p.stab_margin = CX_STB_MARGIN; p.stab_steps = CX_STB_STEPS;
        p.stab_lr_shift = CX_STB_LR;
        p.stab_profile_index = 0; break;
    }
    return p;
}
} // namespace sost
