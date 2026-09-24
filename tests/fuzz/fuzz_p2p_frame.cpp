// libFuzzer harness for the P2P frame state machine (plaintext path).
//
// The node pulls attacker-controlled bytes off a socket into a growing
// recv_buf and repeatedly extracts complete frames from the front. The real
// extractor is a lambda inside the connection handler in sost-node.cpp
// (`try_parse_message`), so it cannot be linked directly; this harness is an
// EXACT MIRROR of its plaintext branch, kept byte-for-byte in step with:
//   src/sost-node.cpp  try_parse_message  (magic/cmd/payload_len/frame_size,
//   bad-magic drop-one-byte, oversize skip-12, incomplete-return).
// If that logic changes, update this mirror.
//
// Property under test: for ANY byte stream delivered in ANY chunking, the
// extractor (a) never reads out of bounds, (b) always makes progress or stops
// (no infinite loop), (c) computes frame_size without overflow. A sanitiser
// finding or a non-terminating loop is a bug.
//
// Build:  clang++ -std=c++17 -O1 -g -fsanitize=fuzzer,address,undefined \
//                 tests/fuzz/fuzz_p2p_frame.cpp -o fuzz_p2pframe
#include <vector>
#include <cstdint>
#include <cstring>
#include <cstddef>

static const uint32_t P2P_MAGIC = 0x534F5354; // "SOST"
static const size_t   MAX_P2P_MSG_SIZE = 4 * 1024 * 1024;

static uint32_t read_u32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

struct Frame { char cmd[5]; std::vector<uint8_t> payload; };

// Exact mirror of the plaintext branch of try_parse_message.
static bool try_parse_frame_plain(std::vector<uint8_t>& recv_buf, Frame& out) {
    if (recv_buf.size() < 12) return false;                 // need header
    uint32_t magic = read_u32(recv_buf.data());
    if (magic != P2P_MAGIC) {                               // bad magic: drop one byte
        recv_buf.erase(recv_buf.begin());
        return false;
    }
    char cmd[5]; memcpy(cmd, recv_buf.data() + 4, 4); cmd[4] = 0;
    uint32_t payload_len = read_u32(recv_buf.data() + 8);
    if (payload_len > MAX_P2P_MSG_SIZE) {                   // corrupt length: skip header
        recv_buf.erase(recv_buf.begin(), recv_buf.begin() + 12);
        return false;
    }
    size_t frame_size = 12 + (size_t)payload_len;
    if (recv_buf.size() < frame_size) return false;         // incomplete
    memcpy(out.cmd, cmd, 5);
    out.payload.assign(recv_buf.begin() + 12, recv_buf.begin() + frame_size);
    recv_buf.erase(recv_buf.begin(), recv_buf.begin() + frame_size);
    return true;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    // Feed the bytes in adversarial chunk splits: the first byte of the input
    // picks a chunk size, so the fuzzer explores boundary/incremental parsing.
    size_t chunk = size ? (1 + (data[0] % 64)) : 1;
    std::vector<uint8_t> recv_buf;
    recv_buf.reserve(4096);

    size_t fed = 0;
    // Bound total extraction work to guarantee the *test* terminates even if the
    // real loop wouldn't; a hit on this bound with a shrinking buffer is normal,
    // a hit with a NON-shrinking buffer is the bug (infinite loop) and we assert.
    size_t guard = size * 4 + 64;
    while (fed < size || !recv_buf.empty()) {
        if (fed < size) {
            size_t n = chunk; if (fed + n > size) n = size - fed;
            recv_buf.insert(recv_buf.end(), data + fed, data + fed + n);
            fed += n;
        }
        // drain everything currently extractable
        for (;;) {
            size_t before = recv_buf.size();
            Frame f;
            bool got = try_parse_frame_plain(recv_buf, f);
            if (!got) {
                // false means either "incomplete" (buffer unchanged, need more
                // bytes) or "skipped junk" (buffer shrank). If unchanged and we
                // have no more bytes to feed, we are done with this buffer.
                if (recv_buf.size() == before) break;         // incomplete: wait for feed
                // else: shrank (junk dropped) — keep draining
            }
            if (guard-- == 0) { if (recv_buf.size() >= before) __builtin_trap(); return 0; }
        }
        if (fed >= size && recv_buf.size() < 12) break;       // no full header possible
        if (fed >= size) {
            // remaining bytes are a partial/incomplete frame; nothing more to do
            break;
        }
    }
    return 0;
}
