#include "sost/emission.h"
#include <stdexcept>
namespace sost {
static inline int64_t qmul_floor(int64_t a, int64_t b) {
    __int128 prod = (__int128)a * (__int128)b;
    return (int64_t)(prod / (__int128)EMISSION_Q_DEN);
}
static int64_t qpow_floor(int64_t base, int64_t exp) {
    if (exp < 0) throw std::runtime_error("qpow: neg exp");
    int64_t result = EMISSION_Q_DEN;
    int64_t x = base; int64_t e = exp;
    while (e > 0) {
        if (e & 1) result = qmul_floor(result, x);
        x = qmul_floor(x, x); e >>= 1;
    }
    return result;
}
int64_t sost_subsidy_stocks(int64_t height) {
    if (height < 0) return 0;
    int64_t epoch = height / BLOCKS_PER_EPOCH;
    int64_t qpow = qpow_floor(EMISSION_Q_NUM, epoch);
    __int128 prod = (__int128)R0_STOCKSHIS * (__int128)qpow;
    return (int64_t)(prod / (__int128)EMISSION_Q_DEN);
}
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
        p.stab_steps = 1; p.stab_lr_shift = CX_LR_SHIFT + 2; break;
    case Profile::TESTNET:
        p.cx_rounds = CX_ROUNDS_T; p.cx_scratch_mb = CX_SCRATCH_T;
        p.cx_checkpoint_interval = CX_CP_T;
        p.stab_scale = 1; p.stab_k = 1; p.stab_margin = 1536;
        p.stab_steps = 1; p.stab_lr_shift = CX_LR_SHIFT + 2; break;
    case Profile::MAINNET: default:
        p.cx_rounds = CX_ROUNDS_M; p.cx_scratch_mb = CX_SCRATCH_M;
        p.cx_checkpoint_interval = CX_CP_M;
        p.stab_scale = CX_STB_SCALE; p.stab_k = CX_STB_K;
        p.stab_margin = CX_STB_MARGIN; p.stab_steps = CX_STB_STEPS;
        p.stab_lr_shift = CX_STB_LR; break;
    }
    return p;
}
} // namespace sost
