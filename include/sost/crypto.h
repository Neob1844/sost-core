#pragma once
#include "types.h"
#include <vector>
namespace sost {
Bytes32 sha256(const uint8_t* data, size_t len);
Bytes32 sha256(const std::vector<uint8_t>& data);
std::vector<uint8_t> prng_bytes(const Bytes32& seed, size_t n_bytes);
std::vector<uint8_t> magic_bytes();
} // namespace sost
