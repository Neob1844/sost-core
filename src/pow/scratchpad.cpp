#include "sost/scratchpad.h"
#include "sost/serialize.h"
#include <cstring>
namespace sost {

Bytes32 epoch_scratch_key(int32_t epoch) {
    std::vector<uint8_t> buf;
    append_magic(buf); append(buf, "EPOCH", 5);
    append_u32_le(buf, (uint32_t)epoch);
    return sha256(buf);
}

std::vector<uint8_t> build_scratchpad(const Bytes32& seed_key, int32_t scratch_mb) {
    if (scratch_mb <= 0) scratch_mb = 1;
    size_t nbytes = (size_t)scratch_mb * 1024 * 1024;
    if (nbytes < 8) nbytes = 8;
    std::vector<uint8_t> out(nbytes);
    std::vector<uint8_t> hseed;
    append_magic(hseed); append(hseed, "SCR", 3); append(hseed, seed_key);
    Bytes32 h = sha256(hseed);
    uint32_t counter = 0;
    size_t pos = 0;
    while (pos < nbytes) {
        uint8_t tmp[36];
        std::memcpy(tmp, h.data(), 32);
        write_u32_le(tmp + 32, counter);
        h = sha256(tmp, 36);
        size_t take = std::min<size_t>(32, nbytes - pos);
        std::memcpy(out.data() + pos, h.data(), take);
        pos += take;
        counter++;
    }
    return out;
}
} // namespace sost
