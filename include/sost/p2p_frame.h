// Shared P2P frame state machine — the EXACT code the node uses to carve one
// message out of a growing receive buffer, extracted so the fuzzer links the
// production parser instead of a hand-kept copy of its logic (V16.3.x hardening,
// NON-CONSENSUS). The framing arithmetic (magic, length cap, frame size, the
// bad-magic drop-one-byte and oversize skip-header behaviour, bounds) lives
// here; the ChaCha20-Poly1305 decrypt for ENCR frames is injected as a callback
// so this header carries no crypto dependency and can be fuzzed standalone.
#pragma once
#include <vector>
#include <cstdint>
#include <cstring>
#include <cstddef>

namespace sost_p2p {

static const uint32_t FRAME_MAGIC        = 0x534F5354; // "SOST"
static const size_t   FRAME_MAX_PAYLOAD  = 4 * 1024 * 1024; // MAX_P2P_MSG_SIZE

inline uint32_t frame_rd_u32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

// Output of one parsed frame: a 4-char command (NUL-terminated) + its payload.
struct ParsedFrame {
    char cmd[5];
    std::vector<uint8_t>* payload; // caller-owned sink, filled on success
};

// Try to extract one complete frame from the front of `buf`.
//   returns true  -> a message was decoded into out.cmd / *out.payload, and the
//                    frame was consumed from the front of buf.
//   returns false -> no usable frame yet: buf was either advanced past junk
//                    (bad magic / oversize / undecryptable / too-short) so the
//                    caller should retry, or left intact awaiting more bytes.
// `encrypted` selects the ENCR path; `decrypt(cipher,clen,tag,plain,nonce)` must
// return true and fill `plain` (clen bytes) on success, and is called with the
// current `recv_nonce`, which is incremented on a successful decrypt — byte-for-
// byte the production behaviour.
template <typename DecryptFn>
inline bool try_parse_frame(std::vector<uint8_t>& buf, bool encrypted,
                            uint64_t& recv_nonce, ParsedFrame& out,
                            DecryptFn decrypt) {
    if (buf.size() < 12) return false; // need header

    uint32_t magic = frame_rd_u32(buf.data());
    if (magic != FRAME_MAGIC) {
        buf.erase(buf.begin());        // bad magic — discard one byte, retry
        return false;
    }

    char cmd[5];
    memcpy(cmd, buf.data() + 4, 4);
    cmd[4] = 0;
    uint32_t payload_len = frame_rd_u32(buf.data() + 8);

    if (payload_len > FRAME_MAX_PAYLOAD) {
        buf.erase(buf.begin(), buf.begin() + 12); // corrupt length — skip header
        return false;
    }

    size_t frame_size = 12 + (size_t)payload_len;
    if (buf.size() < frame_size) return false; // incomplete

    if (encrypted && strcmp(cmd, "ENCR") == 0) {
        if (payload_len < 20) {
            buf.erase(buf.begin(), buf.begin() + frame_size);
            return false;
        }
        uint32_t clen = payload_len - 16;
        const uint8_t* cipher_ptr = buf.data() + 12;
        const uint8_t* tag_ptr    = buf.data() + 12 + clen;

        std::vector<uint8_t> plain(clen);
        uint64_t nonce_val = recv_nonce;
        if (!decrypt(cipher_ptr, clen, tag_ptr, plain.data(), nonce_val)) {
            buf.erase(buf.begin(), buf.begin() + frame_size);
            return false;
        }
        recv_nonce = nonce_val + 1;

        if (clen < 4) {
            buf.erase(buf.begin(), buf.begin() + frame_size);
            return false;
        }
        memcpy(out.cmd, plain.data(), 4);
        out.cmd[4] = 0;
        out.payload->assign(plain.begin() + 4, plain.end());
    } else {
        memcpy(out.cmd, cmd, 5);
        out.payload->assign(buf.begin() + 12, buf.begin() + frame_size);
    }

    buf.erase(buf.begin(), buf.begin() + frame_size);
    return true;
}

} // namespace sost_p2p
