// sostcompact.cpp - Q16.16 difficulty to target (consensus-critical)
#include "sost/sostcompact.h"
#include "sost/serialize.h"
#include <cstring>
#include <cmath>
namespace sost {
#include "sostcompact_lut.inc"

static Bytes32 shr_be(const Bytes32& v, unsigned s) {
    if (s == 0) return v;
    if (s >= 256) return ZERO_HASH();
    Bytes32 r{}; r.fill(0);
    unsigned byS = s/8, biS = s%8;
    for (int i = 31; i >= 0; --i) {
        int src = i - (int)byS;
        if (src >= 0 && src < 32) {
            r[i] = v[src] >> biS;
            if (biS > 0 && src > 0)
                r[i] |= v[src-1] << (8-biS);
        }
    }
    return r;
}

static Bytes32 sub_be(const Bytes32& a, const Bytes32& b) {
    Bytes32 r{}; int borrow = 0;
    for (int i = 31; i >= 0; --i) {
        int diff = (int)a[i] - (int)b[i] - borrow;
        if (diff < 0) { diff += 256; borrow = 1; } else { borrow = 0; }
        r[i] = (uint8_t)diff;
    }
    return r;
}

static Bytes32 mul_frac_be(const Bytes32& v, uint32_t frac) {
    if (frac == 0) return ZERO_HASH();
    Bytes32 r{}; r.fill(0);
    uint32_t carry = 0;
    for (int i = 31; i >= 0; --i) {
        uint32_t prod = (uint32_t)v[i] * frac + carry;
        carry = prod >> 8;
        r[i] = (uint8_t)(prod & 0xFF);
    }
    return r;
}

Bytes32 target_from_bitsQ(uint32_t bitsQ) {
    // target = floor(2^(256 - bitsQ/65536))
    // Use LUT[integer_part] with linear interpolation for fractional part
    // LUT[i] = floor(2^(256 - i))
    // We need: floor(2^(256 - whole - frac/256))
    //        = LUT[whole] >> (frac bits via interpolation)

    if (bitsQ <= MIN_BITSQ) {
        // 1.0 bits or less => maximum target
        Bytes32 max_t{}; max_t.fill(0xFF); return max_t;
    }
    if (bitsQ >= MAX_BITSQ) return ZERO_HASH();

    // Split: bitsQ = whole * 65536 + frac16
    // whole = bitsQ >> 16, frac16 = bitsQ & 0xFFFF
    uint32_t whole = bitsQ >> 16;
    uint32_t frac16 = bitsQ & 0xFFFF;

    if (whole >= 255) return ZERO_HASH();

    // frac16 is in [0, 65536). Map to LUT sub-index.
    // LUT has 256 entries at integer points.
    // frac256 = frac16 / 256 (0..255 range for inter-LUT interpolation)
    uint32_t frac256 = frac16 >> 8;  // top 8 bits of fractional part

    // LUT index: whole corresponds to LUT[whole]
    // But LUT[i] = floor(2^(256-i)), so LUT[whole] = 2^(256-whole)
    // We need 2^(256 - whole - frac256/256)
    // = LUT[whole] * 2^(-frac256/256)
    // Approx via linear interpolation between LUT[whole] and LUT[whole+1]

    if (whole + 1 >= 256) return LUT[whole];

    const Bytes32& hi = LUT[whole];      // 2^(256-whole)
    const Bytes32& lo = LUT[whole + 1];  // 2^(256-whole-1)

    if (frac256 == 0) return hi;

    // Linear interpolation: result = hi - (hi - lo) * frac256 / 256
    Bytes32 delta = sub_be(hi, lo);
    Bytes32 adj = mul_frac_be(delta, frac256);
    return sub_be(hi, adj);
}

bool pow_meets_target(const Bytes32& commit, uint32_t bitsQ) {
    Bytes32 target = target_from_bitsQ(bitsQ);
    return cmp_be(commit, target) <= 0;
}

double bitsQ_to_double(uint32_t bitsQ) {
    return (double)bitsQ / 65536.0;
}
} // namespace sost
