// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// See include/sost/atomic_swap_btc.h for the API contract and the hard
// invariants (no signing, no addresses, no keys, no I/O, no network).

#include "sost/atomic_swap_btc.h"
#include "sost/crypto.h"
#include <climits>

namespace sost {
namespace atomic_swap {
namespace btc {

// ---------------------------------------------------------------------------
// ScriptNum minimal encoding (positive integers only).
// ---------------------------------------------------------------------------
//
// Bitcoin ScriptNum rules:
//   * value 0          -> empty vector (OP_0 = 0x00 push)
//   * otherwise little-endian bytes, minimal length (no trailing zeros)
//   * if the high bit of the most-significant byte is set, append a
//     sign-extension byte (0x00 for positive values).
//
// The HTLC refund_height is always non-negative (it is a future block
// height) so we never produce a value with the negative sign bit
// (0x80) on the top byte.

std::vector<uint8_t> EncodeScriptNumMinimal(int64_t value) {
    std::vector<uint8_t> out;
    if (value == 0) {
        return out;  // OP_0; emitted by the caller as a 0x00 push count
    }
    if (value < 0) {
        // Negative values are not used by the HTLC builder but kept defined
        // for completeness of the canonical encoding. The negative sign
        // bit (0x80) is appended to the high byte.
        uint64_t mag = static_cast<uint64_t>(-value);
        while (mag) {
            out.push_back(static_cast<uint8_t>(mag & 0xFF));
            mag >>= 8;
        }
        if (out.back() & 0x80) out.push_back(0x80);
        else                    out.back() |= 0x80;
        return out;
    }
    uint64_t mag = static_cast<uint64_t>(value);
    while (mag) {
        out.push_back(static_cast<uint8_t>(mag & 0xFF));
        mag >>= 8;
    }
    // If the high bit of the top byte is set, append a zero byte so the
    // value is unambiguously positive.
    if (out.back() & 0x80) out.push_back(0x00);
    return out;
}

// ---------------------------------------------------------------------------
// Pushdata encoding (general).
// ---------------------------------------------------------------------------

std::vector<uint8_t> EncodePushdata(const uint8_t* data, size_t len) {
    std::vector<uint8_t> out;
    if (len <= 75) {
        out.reserve(1 + len);
        out.push_back(static_cast<uint8_t>(len));
    } else if (len <= 0xFF) {
        out.reserve(2 + len);
        out.push_back(OP_PUSHDATA1);
        out.push_back(static_cast<uint8_t>(len));
    } else if (len <= 0xFFFF) {
        out.reserve(3 + len);
        out.push_back(0x4d);  // OP_PUSHDATA2
        out.push_back(static_cast<uint8_t>(len & 0xFF));
        out.push_back(static_cast<uint8_t>((len >> 8) & 0xFF));
    } else {
        out.reserve(5 + len);
        out.push_back(0x4e);  // OP_PUSHDATA4
        out.push_back(static_cast<uint8_t>(len & 0xFF));
        out.push_back(static_cast<uint8_t>((len >> 8) & 0xFF));
        out.push_back(static_cast<uint8_t>((len >> 16) & 0xFF));
        out.push_back(static_cast<uint8_t>((len >> 24) & 0xFF));
    }
    out.insert(out.end(), data, data + len);
    return out;
}

std::vector<uint8_t> EncodePushdata(const std::vector<uint8_t>& data) {
    return EncodePushdata(data.data(), data.size());
}

// ---------------------------------------------------------------------------
// Build the BIP-199-style HTLC redeem script.
// ---------------------------------------------------------------------------

std::vector<uint8_t> BuildBtcHtlcRedeemScript(
    const std::array<uint8_t, 32>& hashlock,
    int64_t refund_height,
    const std::array<uint8_t, 33>& claim_pubkey,
    const std::array<uint8_t, 33>& refund_pubkey)
{
    std::vector<uint8_t> s;
    s.reserve(120);

    // -- claim branch --
    s.push_back(OP_IF);
    s.push_back(OP_SHA256);
    auto pl_hashlock = EncodePushdata(hashlock.data(), hashlock.size());
    s.insert(s.end(), pl_hashlock.begin(), pl_hashlock.end());
    s.push_back(OP_EQUALVERIFY);
    auto pl_claim = EncodePushdata(claim_pubkey.data(), claim_pubkey.size());
    s.insert(s.end(), pl_claim.begin(), pl_claim.end());
    s.push_back(OP_CHECKSIG);

    // -- refund branch --
    s.push_back(OP_ELSE);
    auto sn = EncodeScriptNumMinimal(refund_height);
    auto pl_height = EncodePushdata(sn.data(), sn.size());
    s.insert(s.end(), pl_height.begin(), pl_height.end());
    s.push_back(OP_CHECKLOCKTIMEVERIFY);
    s.push_back(OP_DROP);
    auto pl_refund = EncodePushdata(refund_pubkey.data(), refund_pubkey.size());
    s.insert(s.end(), pl_refund.begin(), pl_refund.end());
    s.push_back(OP_CHECKSIG);

    s.push_back(OP_ENDIF);
    return s;
}

// ---------------------------------------------------------------------------
// SHA-256 of the redeem script (= future P2WSH witness program).
// ---------------------------------------------------------------------------

Bytes32 BtcHtlcWitnessProgram(const std::vector<uint8_t>& redeem_script) {
    return sha256(redeem_script.data(), redeem_script.size());
}

} // namespace btc
} // namespace atomic_swap
} // namespace sost
