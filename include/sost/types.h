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
};
struct CoinbaseSplit { int64_t miner, gold_vault, popc_pool, total; };
enum class CasertMode : uint8_t { WARMUP=0, NORMAL=1, DEGRADED=2, OPEN=3 };
inline const char* casert_mode_str(CasertMode m) {
    switch(m) {
        case CasertMode::WARMUP:   return "warmup";
        case CasertMode::NORMAL:   return "L3";
        case CasertMode::DEGRADED: return "L4";
        case CasertMode::OPEN:     return "L5+";
    }
    return "?";
}
struct CasertDecision { CasertMode mode; int32_t signal_s, samples; };
struct BlockMeta { Bytes32 block_id; int64_t height, time; uint32_t powDiffQ; };
struct CXAttemptResult {
    Bytes32 commit, checkpoints_root;
    uint64_t stability_metric; bool is_stable;
    std::vector<uint8_t> x_bytes;
};
struct Checkpoint { Bytes32 state_hash, x_hash; uint32_t round; uint64_t residual; };
} // namespace sost
