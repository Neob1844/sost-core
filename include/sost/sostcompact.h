#pragma once
#include "types.h"
#include "params.h"
#include <cstdint>
namespace sost {
Bytes32 target_from_bitsQ(uint32_t bitsQ);
bool pow_meets_target(const Bytes32& commit, uint32_t bitsQ);
inline bool valid_bitsQ(uint32_t b) { return b >= MIN_BITSQ && b <= MAX_BITSQ; }
double bitsQ_to_double(uint32_t bitsQ);

// =========================================================================
// Chainwork computation — best chain = highest cumulative valid work
//
// block_work = approximate 2^(bitsQ / 65536) expected hashes.
// Stored as a 256-bit big-endian integer for lossless accumulation.
// cumulative_work = parent.cumulative_work + block_work
// =========================================================================

// Compute the work represented by a block at difficulty bitsQ.
// Returns a 256-bit big-endian value proportional to expected hashes.
// Formula: work ≈ 2^256 / (target + 1), where target = target_from_bitsQ(bitsQ).
// This is the standard approach used by Bitcoin-family chains.
Bytes32 compute_block_work(uint32_t bitsQ);

// Add two 256-bit big-endian values: result = a + b
Bytes32 add_be256(const Bytes32& a, const Bytes32& b);

// Compare two 256-bit big-endian values.
// Returns <0 if a<b, 0 if equal, >0 if a>b.
// (Uses cmp_be from types.h but exposed here for clarity)
inline int compare_chainwork(const Bytes32& a, const Bytes32& b) {
    return cmp_be(a, b);
}

} // namespace sost
