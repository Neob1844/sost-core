#include "sost/crypto.h"
#include "sost/params.h"
#include "sost/serialize.h"
#include <openssl/sha.h>
#include <cstring>
namespace sost {
Bytes32 sha256(const uint8_t* data, size_t len) {
    Bytes32 out{};
    SHA256_CTX ctx; SHA256_Init(&ctx);
    SHA256_Update(&ctx, data, len);
    SHA256_Final(out.data(), &ctx);
    return out;
}
Bytes32 sha256(const std::vector<uint8_t>& data) {
    return sha256(data.data(), data.size());
}
std::vector<uint8_t> prng_bytes(const Bytes32& seed, size_t n_bytes) {
    std::vector<uint8_t> output; output.reserve(n_bytes + 32);
    uint32_t counter = 0;
    uint8_t buf[36]; std::memcpy(buf, seed.data(), 32);
    while (output.size() < n_bytes) {
        write_u32_le(buf + 32, counter);
        Bytes32 chunk = sha256(buf, 36);
        size_t take = std::min<size_t>(32, n_bytes - output.size());
        output.insert(output.end(), chunk.begin(), chunk.begin() + take);
        counter++;
    }
    return output;
}
std::vector<uint8_t> magic_bytes() {
    auto m = MAGIC_STR_BYTES();
    return std::vector<uint8_t>(m, m + MAGIC_LEN);
}
} // namespace sost
