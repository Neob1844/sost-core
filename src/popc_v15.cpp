// popc_v15.cpp — V15 PoPC Model A/B: attestation crypto (P1, pure base).
// ECDSA verification of a self/supervisor-signed attestation + pubkey→pkh.
// No chain state, no enforcement. See include/sost/popc_v15.h.
#include "sost/popc_v15.h"
#include <secp256k1.h>
#include <openssl/sha.h>
#include <openssl/ripemd.h>

namespace sost {

PubKeyHash popc_v15_pubkey_pkh(const std::vector<uint8_t>& pubkey) {
    PubKeyHash pkh{};
    if (pubkey.empty()) return pkh;
    unsigned char sha[SHA256_DIGEST_LENGTH];
    SHA256(pubkey.data(), pubkey.size(), sha);
    unsigned char rip[RIPEMD160_DIGEST_LENGTH];
    RIPEMD160(sha, SHA256_DIGEST_LENGTH, rip);
    for (int i = 0; i < 20; ++i) pkh[i] = rip[i];
    return pkh;
}

bool popc_v15_pubkey_is_owner(const std::vector<uint8_t>& pubkey, const PubKeyHash& owner_pkh) {
    return popc_v15_pubkey_pkh(pubkey) == owner_pkh;
}

static secp256k1_context* pv_ctx() {
    static secp256k1_context* c = secp256k1_context_create(SECP256K1_CONTEXT_VERIFY);
    return c;
}

bool popc_v15_verify_attestation(const Bytes32& commitment_id, int64_t balance_mg, int64_t attest_height,
                                 const std::vector<uint8_t>& pubkey, const std::vector<uint8_t>& sig_compact) {
    if (sig_compact.size() != 64) return false;
    if (pubkey.size() != 33 && pubkey.size() != 65) return false;
    secp256k1_context* ctx = pv_ctx();
    if (!ctx) return false;
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &pk, pubkey.data(), pubkey.size())) return false;
    secp256k1_ecdsa_signature sig;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sig, sig_compact.data())) return false;
    secp256k1_ecdsa_signature_normalize(ctx, &sig, &sig);   // accept either S form
    Bytes32 digest = popc_v15_attest_digest(commitment_id, balance_mg, attest_height);
    return secp256k1_ecdsa_verify(ctx, &sig, digest.data(), &pk) == 1;
}

bool popc_v15_verify_event_auth(PopcEventType type, const Bytes32& commitment_id, const PubKeyHash& owner,
                                uint8_t model, int64_t end_height,
                                const std::vector<uint8_t>& pubkey, const std::vector<uint8_t>& sig_compact) {
    // The signing key must be the owner's (no third party can authorize events on
    // a commitment they do not own).
    if (!popc_v15_pubkey_is_owner(pubkey, owner)) return false;
    if (sig_compact.size() != 64) return false;
    if (pubkey.size() != 33 && pubkey.size() != 65) return false;
    secp256k1_context* ctx = pv_ctx();
    if (!ctx) return false;
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &pk, pubkey.data(), pubkey.size())) return false;
    secp256k1_ecdsa_signature sig;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sig, sig_compact.data())) return false;
    secp256k1_ecdsa_signature_normalize(ctx, &sig, &sig);
    Bytes32 digest = popc_v15_event_digest(type, commitment_id, owner, model, end_height);
    return secp256k1_ecdsa_verify(ctx, &sig, digest.data(), &pk) == 1;
}

} // namespace sost
