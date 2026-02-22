#pragma once
#include "types.h"
#include "params.h"
namespace sost {
Bytes32 target_from_bitsQ(uint32_t bitsQ);
bool pow_meets_target(const Bytes32& commit, uint32_t bitsQ);
inline bool valid_bitsQ(uint32_t b) { return b >= MIN_BITSQ && b <= MAX_BITSQ; }
double bitsQ_to_double(uint32_t bitsQ);
} // namespace sost
