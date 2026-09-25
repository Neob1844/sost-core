// libFuzzer harness for the P2P frame state machine — now driving the REAL
// production parser (sost/p2p_frame.h, sost_p2p::try_parse_frame), the exact
// function the node's connection handler calls, instead of a copy of its logic.
//
// Property under test: for ANY byte stream delivered in ANY chunking, the
// extractor (a) never reads out of bounds, (b) always makes progress or stops
// (no infinite loop), (c) computes frame_size without overflow. A sanitiser
// finding or a non-terminating loop is a bug.
//
// Build:  clang++ -std=c++17 -O1 -g -fsanitize=fuzzer,address,undefined \
//                 -I include tests/fuzz/fuzz_p2p_frame.cpp -o fuzz_p2pframe
#include "sost/p2p_frame.h"
#include <vector>
#include <cstdint>
#include <cstring>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    // Byte 0 selects the chunk size AND whether we drive the encrypted branch,
    // so the fuzzer explores boundary/incremental parsing on both paths.
    size_t chunk = size ? (1 + (data[0] % 64)) : 1;
    bool encrypted = size ? (data[0] & 0x80) != 0 : false;
    uint64_t recv_nonce = 0;

    // ENCR decrypt stub: the fuzzer cannot forge a valid Poly1305 tag, so this
    // returns false — exercising the "undecryptable frame is skipped" path. The
    // framing/bounds arithmetic under test is identical on both branches.
    auto decrypt = [](const uint8_t*, uint32_t, const uint8_t*,
                      uint8_t*, uint64_t) -> bool { return false; };

    std::vector<uint8_t> recv_buf;
    recv_buf.reserve(4096);
    std::vector<uint8_t> payload;

    size_t fed = 0;
    size_t guard = size * 4 + 64; // the TEST must terminate even if the code would not
    while (fed < size || !recv_buf.empty()) {
        if (fed < size) {
            size_t n = chunk; if (fed + n > size) n = size - fed;
            recv_buf.insert(recv_buf.end(), data + fed, data + fed + n);
            fed += n;
        }
        for (;;) {
            size_t before = recv_buf.size();
            sost_p2p::ParsedFrame pf; pf.payload = &payload;
            bool got = sost_p2p::try_parse_frame(recv_buf, encrypted, recv_nonce, pf, decrypt);
            if (!got) {
                if (recv_buf.size() == before) break;      // incomplete: wait for feed
                // else: shrank (junk dropped) — keep draining
            }
            if (guard-- == 0) { if (recv_buf.size() >= before) __builtin_trap(); return 0; }
        }
        if (fed >= size) break;
    }
    return 0;
}
