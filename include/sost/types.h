#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include <cstddef>
#include <string>
#include <vector>
namespace sost {
using Bytes32 = std::array<uint8_t, 32>;
inline Bytes32 ZERO_HASH() { Bytes32 z{}; z.fill(0); return z; }
inline bool is_zero(const Bytes32& h) { for(auto b:h) if(b) return false; return true; }
inline std::string hex(const Bytes32& h) {
    static const char* d="0123456789abcdef";
    std::string s; s.reserve(64);
    for(auto b:h){s.push_back(d[b>>4]);s.push_back(d[b&0xf]);}
    return s;
}
inline Bytes32 from_hex(const std::string& s) {
    Bytes32 out{}; size_t off=(s.size()>=2&&s[0]=='0'&&(s[1]=='x'||s[1]=='X'))?2:0;
    auto hx=[](char c)->uint8_t{
        if(c>='0'&&c<='9')return c-'0'; if(c>='a'&&c<='f')return 10+c-'a';
        if(c>='A'&&c<='F')return 10+c-'A'; return 0; };
    for(size_t i=0;i<32&&(off+i*2+1)<s.size();++i)
        out[i]=(hx(s[off+i*2])<<4)|hx(s[off+i*2+1]);
    return out;
}
inline int cmp_be(const Bytes32& a, const Bytes32& b) { return std::memcmp(a.data(),b.data(),32); }

struct ConsensusParams {
    int32_t cx_n, cx_rounds, cx_scratch_mb, cx_lr_shift, cx_lam, cx_checkpoint_interval;
    int32_t stab_scale, stab_k, stab_margin, stab_steps, stab_lr_shift;
    int32_t stab_profile_index{0}; // committed to block hash — prevents profile downgrade attacks
    bool verbose{false};           // print CX-VERIFY debug output
};
struct CoinbaseSplit { int64_t miner, gold_vault, popc_pool, total; };
// cASERT unified block-rate control decision
struct CasertDecision {
    uint32_t bitsq;           // primary hardness (Q16.16)
    int32_t  profile_index;   // equalizer profile (-3=E3 .. 0=B0 .. 6=H6)
    int32_t  lag;             // schedule lag (positive=ahead, negative=behind)
    int32_t  r_q16;           // instantaneous log-ratio (Q16.16)
    int32_t  ewma_short;      // short EWMA (Q16.16)
    int32_t  ewma_long;       // long EWMA (Q16.16)
    int32_t  burst_score;     // burst score (Q16.16)
    int32_t  volatility;      // volatility (Q16.16)
    int64_t  integrator;      // integrator (Q16.16)
};

inline const char* casert_profile_name(int32_t idx) {
    static const char* names[] = {"E4","E3","E2","E1","B0","H1","H2","H3","H4","H5","H6","H7","H8","H9","H10","H11","H12"};
    int32_t ai = idx + 4; // offset by -CASERT_H_MIN (4)
    if (ai < 0 || ai >= 17) return "?";
    return names[ai];
}
struct BlockMeta { Bytes32 block_id; int64_t height, time; uint32_t powDiffQ; int32_t profile_index{0}; };
// --- Transcript V2 structures ---
struct SegmentLeaf {
    uint32_t segment_index;
    uint32_t round_start, round_end;
    Bytes32 state_start, state_end;
    Bytes32 x_start_hash, x_end_hash;
    uint64_t residual_start, residual_end;
};
struct SegmentProof {
    SegmentLeaf leaf;
    std::vector<Bytes32> merkle_path;
};
struct RoundWitness {
    uint32_t round_index;
    std::array<int32_t, 32> x_before, x_after;
    Bytes32 state_before, state_after;
    std::array<int32_t, 4> scratch_values;
    std::array<uint32_t, 4> scratch_indices;
    uint64_t dataset_value;
    uint64_t program_output;
};

struct CXAttemptResult {
    Bytes32 commit, checkpoints_root, segments_root, final_state;
    uint64_t stability_metric; bool is_stable;
    std::vector<uint8_t> x_bytes;
    std::vector<Bytes32> checkpoint_leaves;
    std::vector<SegmentLeaf> segment_leaves;
    // Populated after challenge derivation (only for winning attempt):
    std::vector<SegmentProof> segment_proofs;
    std::vector<RoundWitness> round_witnesses;
};
struct Checkpoint { Bytes32 state_hash, x_hash; uint32_t round; uint64_t residual; };
} // namespace sost
