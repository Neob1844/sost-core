#pragma once
#include "types.h"
#include "params.h"
#include <cstdint>
#include <vector>
namespace sost {
inline void write_u32_le(uint8_t* p, uint32_t v) {
    p[0]=(uint8_t)(v);p[1]=(uint8_t)(v>>8);p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24);
}
inline void write_i32_le(uint8_t* p, int32_t v) { write_u32_le(p,(uint32_t)v); }
inline void write_u64_le(uint8_t* p, uint64_t v) { for(int i=0;i<8;++i)p[i]=(uint8_t)(v>>(8*i)); }
inline uint32_t read_u32_le(const uint8_t* p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
inline int32_t read_i32_le(const uint8_t* p) { return (int32_t)read_u32_le(p); }
inline uint64_t read_u64_le(const uint8_t* p) {
    uint64_t v=0; for(int i=0;i<8;++i) v|=((uint64_t)p[i])<<(8*i); return v;
}
// Consensus-safe arithmetic right shift (C++ leaves signed >> impl-defined)
inline int32_t asr_i32(int32_t x, int32_t s) {
    if(s<=0)return x; if(s>=31)return(x<0)?-1:0;
    uint32_t ux=(uint32_t)x; uint32_t shifted=ux>>s;
    if(x<0){uint32_t mask=0xFFFFFFFFu<<(32-s);shifted|=mask;}
    return(int32_t)shifted;
}
inline int32_t clamp_i32(int64_t v) {
    if(v<INT32_MIN)return INT32_MIN; if(v>INT32_MAX)return INT32_MAX; return(int32_t)v;
}
inline uint32_t u32(uint64_t x){return(uint32_t)(x&0xFFFFFFFFu);}
inline uint64_t u64(uint64_t x){return x;}
constexpr uint64_t U64_MAX_VAL = UINT64_MAX;
inline uint64_t sat_u64_add(uint64_t a, uint64_t b) {
    if(a==U64_MAX_VAL||b==U64_MAX_VAL)return U64_MAX_VAL;
    uint64_t c=a+b; return(c<a)?U64_MAX_VAL:c;
}
inline uint64_t sat_u64_from_nonneg(int64_t x) {
    if(x<=0)return 0; if((uint64_t)x>U64_MAX_VAL)return U64_MAX_VAL; return(uint64_t)x;
}
// header_core: prev(32)||mrkl(32)||ts(u32le)||powDiffQ(u32le) = 72 bytes
inline constexpr int HEADER_CORE_LEN = 72;
inline std::array<uint8_t,72> build_header_core(
    const Bytes32& prev, const Bytes32& mrkl, uint32_t ts, uint32_t powDiffQ) {
    std::array<uint8_t,72> hc{};
    std::memcpy(hc.data(),prev.data(),32);
    std::memcpy(hc.data()+32,mrkl.data(),32);
    write_u32_le(hc.data()+64,ts); write_u32_le(hc.data()+68,powDiffQ);
    return hc;
}
inline void append(std::vector<uint8_t>& b, const uint8_t* d, size_t n){b.insert(b.end(),d,d+n);}
inline void append(std::vector<uint8_t>& b, const Bytes32& h){b.insert(b.end(),h.begin(),h.end());}
inline void append(std::vector<uint8_t>& b, const char* s, size_t n){b.insert(b.end(),s,s+n);}
inline void append_u32_le(std::vector<uint8_t>& b, uint32_t v){uint8_t t[4];write_u32_le(t,v);b.insert(b.end(),t,t+4);}
inline void append_u64_le(std::vector<uint8_t>& b, uint64_t v){uint8_t t[8];write_u64_le(t,v);b.insert(b.end(),t,t+8);}
inline void append_magic(std::vector<uint8_t>& b){append(b,MAGIC_STR_BYTES(),MAGIC_LEN);}
} // namespace sost
