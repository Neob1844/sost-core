// gv_g5.cpp — V15 Gold Vault G5 Guardian: ECDSA verification of a veto payload.
//
// The Guardian key is the same single developer/genesis operator key used by
// Beacon II-A. G5 is TRANSITIONAL: gv_g5_active_at() forces it off forever at
// block GV_G5_AUTO_DISCONNECT_HEIGHT (100,000), so this veto power cannot become
// a permanent control door. See include/sost/gv_g5.h.
#include "sost/gv_g5.h"
#include <secp256k1.h>

namespace sost {

// Guardian pubkey = Beacon II-A operator key (uncompressed, 65 bytes hex).
// Fingerprint bbb560e3…; one custodian, transitional, auto-disconnected @100,000.
const char* GV_G5_GUARDIAN_PUBKEY =
    "04"
    "7ef6e1495c4834fcf753aba1b5bf60aee300a318cc70e79c6b56a8e5fc543073"
    "11c53d6464a1a1d052f452374e92610a051cb1f4543349b8b6c54485991866e4";

static secp256k1_context* g5_ctx() {
    static secp256k1_context* c = secp256k1_context_create(SECP256K1_CONTEXT_VERIFY);
    return c;
}

static bool hexdec(const std::string& h, std::vector<uint8_t>& out) {
    if (h.size() % 2) return false;
    out.clear(); out.reserve(h.size() / 2);
    auto nyb = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < h.size(); i += 2) {
        int hi = nyb(h[i]), lo = nyb(h[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back((uint8_t)((hi << 4) | lo));
    }
    return true;
}

bool gv_g5_verify_veto_payload(const PubKeyHash& dest_pkh,
                               int64_t spend_height,
                               const std::vector<uint8_t>& payload,
                               const std::string& guardian_pubkey_hex) {
    if (!gv_g5_active_at(spend_height)) return false;   // inactive or auto-disconnected
    if (payload.size() < 8 + 64) return false;          // expiry(8 LE) + compact sig(64)

    int64_t expiry = 0;
    for (int i = 0; i < 8; ++i) expiry |= (int64_t)payload[(size_t)i] << (8 * i);
    if (expiry < spend_height) return false;            // veto expired

    const Bytes32 digest = gv_g5_veto_digest(dest_pkh, expiry);

    secp256k1_context* ctx = g5_ctx();
    if (!ctx) return false;
    std::vector<uint8_t> pub;
    if (!hexdec(guardian_pubkey_hex, pub)) return false;
    if (pub.size() != 33 && pub.size() != 65) return false;
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &pk, pub.data(), pub.size())) return false;

    secp256k1_ecdsa_signature sig;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sig, payload.data() + 8)) return false;
    secp256k1_ecdsa_signature_normalize(ctx, &sig, &sig);   // accept either S form
    return secp256k1_ecdsa_verify(ctx, &sig, digest.data(), &pk) == 1;
}

bool gv_g5_verify_veto_payload(const PubKeyHash& dest_pkh,
                               int64_t spend_height,
                               const std::vector<uint8_t>& payload) {
    return gv_g5_verify_veto_payload(dest_pkh, spend_height, payload, GV_G5_GUARDIAN_PUBKEY);
}

} // namespace sost
