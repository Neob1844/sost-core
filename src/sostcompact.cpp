// sostcompact.cpp - Q16.16 difficulty to target (consensus-critical)
// LUT[i] = floor(2^256 * 2^(-i/256)) — fractional LUT, Python-compatible
#include "sost/sostcompact.h"
#include "sost/serialize.h"
#include <cstring>
#include <cmath>
namespace sost {

// ---- Fractional LUT (256 entries, Python-compatible) ----
#include "sostcompact_lut.inc"

// ---- 256-bit big-endian arithmetic helpers ----

// Right-shift a big-endian Bytes32 by s bits
static Bytes32 shr_be(const Bytes32& v, unsigned s) {
    if (s == 0) return v;
    if (s >= 256) return ZERO_HASH();
    Bytes32 r{}; r.fill(0);
    unsigned byS = s / 8, biS = s % 8;
    for (int i = 31; i >= 0; --i) {
        int src = i - (int)byS;
        if (src >= 0 && src < 32) {
            r[i] = v[src] >> biS;
            if (biS > 0 && src > 0)
                r[i] |= v[src - 1] << (8 - biS);
        }
    }
    return r;
}

// Subtract two big-endian Bytes32: a - b (assumes a >= b)
static Bytes32 sub_be(const Bytes32& a, const Bytes32& b) {
    Bytes32 r{}; int borrow = 0;
    for (int i = 31; i >= 0; --i) {
        int diff = (int)a[i] - (int)b[i] - borrow;
        if (diff < 0) { diff += 256; borrow = 1; } else { borrow = 0; }
        r[i] = (uint8_t)diff;
    }
    return r;
}

// Multiply big-endian Bytes32 by uint8 fraction: floor(v * w / 256)
// w is in range [0, 255]
static Bytes32 mul_frac256_be(const Bytes32& v, uint32_t w) {
    if (w == 0) return ZERO_HASH();
    // Compute v * w (result fits in 33 bytes), then divide by 256 (shift right 8)
    uint32_t carry = 0;
    uint8_t tmp[32];
    for (int i = 31; i >= 0; --i) {
        uint32_t prod = (uint32_t)v[i] * w + carry;
        tmp[i] = (uint8_t)(prod & 0xFF);
        carry = prod >> 8;
    }
    // carry has the overflow byte. Now shift right by 8 bits (divide by 256):
    // result[i] = tmp[i-1] for i=1..31, result[0] = carry
    Bytes32 r{};
    r[0] = (uint8_t)(carry & 0xFF);
    for (int i = 1; i < 32; ++i)
        r[i] = tmp[i - 1];
    return r;
}

// ---- target_from_bitsQ (Python-compatible algorithm) ----
// Python logic:
//   e    = bitsQ >> 16          (integer part, 0..255)
//   f    = bitsQ & 0xFFFF       (fractional part, 0..65535)
//   idx0 = f >> 8               (LUT index, 0..255)
//   idx1 = min(idx0 + 1, 255)
//   w    = f & 0xFF             (interpolation weight, 0..255)
//   interp = LUT[idx0] - (LUT[idx0] - LUT[idx1]) * w / 256
//   target = interp >> e

Bytes32 target_from_bitsQ(uint32_t bitsQ) {
    if (bitsQ <= MIN_BITSQ) {
        Bytes32 max_t{}; max_t.fill(0xFF); return max_t;
    }
    if (bitsQ >= MAX_BITSQ) return ZERO_HASH();

    uint32_t e = bitsQ >> 16;           // integer part (0..255)
    uint32_t f = bitsQ & 0xFFFF;        // fractional part (0..65535)

    if (e >= 256) return ZERO_HASH();

    uint32_t idx0 = f >> 8;             // 0..255
    uint32_t idx1 = (idx0 < 255) ? idx0 + 1 : 255;
    uint32_t w    = f & 0xFF;           // interpolation weight (0..255)

    const Bytes32& v0 = LUT[idx0];
    const Bytes32& v1 = LUT[idx1];

    Bytes32 interp;
    if (w == 0) {
        interp = v0;
    } else {
        // interp = v0 - floor((v0 - v1) * w / 256)
        // v0 >= v1 guaranteed (LUT is strictly decreasing)
        Bytes32 delta = sub_be(v0, v1);
        Bytes32 adj = mul_frac256_be(delta, w);
        interp = sub_be(v0, adj);
    }

    // Shift right by integer exponent
    if (e == 0) return interp;
    return shr_be(interp, e);
}

bool pow_meets_target(const Bytes32& commit, uint32_t bitsQ) {
    Bytes32 target = target_from_bitsQ(bitsQ);
    return cmp_be(commit, target) <= 0;
}

double bitsQ_to_double(uint32_t bitsQ) {
    return (double)bitsQ / 65536.0;
}

} // namespace sost
