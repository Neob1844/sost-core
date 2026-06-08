// test_gv_g5.cpp — V15 Gold Vault G5 transitional Guardian veto.
//
// Covers: gating + AUTO-DISCONNECT at block 100,000, grace constant, the
// silence=accept decision, deterministic veto digest, and the ECDSA veto
// verification (sign→verify roundtrip with a generated key, plus every
// rejection: expired, wrong destination, tampered signature, wrong key, and
// auto-disconnected height). Signed-verify SUCCESS needs G5 active, so those
// cases run on the testnet build; the mainnet build checks it stays a no-op.
#include "sost/gv_g5.h"
#include <secp256k1.h>
#include <cstdio>
#include <string>
#include <vector>
using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(name, cond) do { if (cond) { ++g_pass; std::printf("  ok  %s\n", name); } \
    else { ++g_fail; std::printf("  *** FAIL: %s\n", name); } } while (0)

static PubKeyHash pkh(uint8_t b) { PubKeyHash p; p.fill(b); return p; }
static std::string tohex(const unsigned char* p, size_t n) {
    static const char* H = "0123456789abcdef"; std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s.push_back(H[p[i] >> 4]); s.push_back(H[p[i] & 15]); } return s;
}

int main() {
    std::printf("=== Gold Vault G5 — transitional Guardian veto (W4) ===\n");

    // ---- pure constants + decision ----
    CHECK("grace window == 10", GV_G5_GRACE_BLOCKS == 10);
    CHECK("auto-disconnect height == 100000", GV_G5_AUTO_DISCONNECT_HEIGHT == 100000);
    CHECK("silence=accept: active + no veto -> NOT blocked", gv_g5_spend_blocked(true, false) == false);
    CHECK("active + valid veto -> blocked",                  gv_g5_spend_blocked(true, true)  == true);
    CHECK("inactive + veto -> NOT blocked",                  gv_g5_spend_blocked(false, true) == false);

    // ---- digest determinism / binding ----
    {
        auto d1 = gv_g5_veto_digest(pkh(0x05), 12345);
        auto d2 = gv_g5_veto_digest(pkh(0x05), 12345);
        auto d3 = gv_g5_veto_digest(pkh(0x06), 12345);   // different dest
        auto d4 = gv_g5_veto_digest(pkh(0x05), 12346);   // different expiry
        CHECK("digest is deterministic", d1 == d2);
        CHECK("digest binds destination", !(d1 == d3));
        CHECK("digest binds expiry",      !(d1 == d4));
    }

    // ---- activation + AUTO-DISCONNECT ----
#ifdef SOST_TESTNET_FORKS
    CHECK("testnet: active at V15_HEIGHT",       gv_g5_active_at(V15_HEIGHT) == true);
    CHECK("testnet: inactive before V15",        gv_g5_active_at(V15_HEIGHT - 1) == false);
    CHECK("testnet: active at 99,999",           gv_g5_active_at(99999) == true);
    CHECK("testnet: AUTO-DISCONNECT at 100,000", gv_g5_active_at(100000) == false);
    CHECK("testnet: stays off at 100,001",       gv_g5_active_at(100001) == false);
#else
    CHECK("mainnet: deferred at V15 (20000)",    gv_g5_active_at(20000) == false);
    CHECK("mainnet: deferred at 50000",          gv_g5_active_at(50000) == false);
    CHECK("mainnet: off at 100000",              gv_g5_active_at(100000) == false);
#endif

    // ---- ECDSA veto verification (sign -> verify) ----
    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    unsigned char seckey[32]; for (int i = 0; i < 32; ++i) seckey[i] = (unsigned char)(i + 1);
    secp256k1_pubkey pub; secp256k1_ec_pubkey_create(ctx, &pub, seckey);
    unsigned char pub65[65]; size_t publen = 65;
    secp256k1_ec_pubkey_serialize(ctx, pub65, &publen, &pub, SECP256K1_EC_UNCOMPRESSED);
    const std::string TEST_GUARDIAN = tohex(pub65, publen);

    auto make_payload = [&](const PubKeyHash& dest, int64_t expiry) {
        Bytes32 dg = gv_g5_veto_digest(dest, expiry);
        secp256k1_ecdsa_signature sig;
        secp256k1_ecdsa_sign(ctx, &sig, dg.data(), seckey, nullptr, nullptr);
        unsigned char comp[64]; secp256k1_ecdsa_signature_serialize_compact(ctx, comp, &sig);
        std::vector<uint8_t> pl;
        for (int i = 0; i < 8; ++i) pl.push_back((uint8_t)((uint64_t)expiry >> (8 * i)));
        pl.insert(pl.end(), comp, comp + 64);
        return pl;
    };
    const PubKeyHash DEST = pkh(0x05);

#ifdef SOST_TESTNET_FORKS
    const int64_t H = V15_HEIGHT + 50;   // active, well below auto-disconnect
    {   // valid veto (expiry >= H), signed by the test guardian
        auto pl = make_payload(DEST, H + 5);
        CHECK("post-activation: valid signed veto verifies",
              gv_g5_verify_veto_payload(DEST, H, pl, TEST_GUARDIAN) == true);
    }
    {   // expired veto (expiry < H)
        auto pl = make_payload(DEST, H - 1);
        CHECK("expired veto -> rejected",
              gv_g5_verify_veto_payload(DEST, H, pl, TEST_GUARDIAN) == false);
    }
    {   // veto signed for a DIFFERENT destination
        auto pl = make_payload(pkh(0x06), H + 5);
        CHECK("veto for another destination -> rejected",
              gv_g5_verify_veto_payload(DEST, H, pl, TEST_GUARDIAN) == false);
    }
    {   // tampered signature
        auto pl = make_payload(DEST, H + 5);
        pl[20] ^= 0xFF;
        CHECK("tampered signature -> rejected",
              gv_g5_verify_veto_payload(DEST, H, pl, TEST_GUARDIAN) == false);
    }
    {   // valid signature but verified against the WRONG (real Guardian) key
        auto pl = make_payload(DEST, H + 5);
        CHECK("wrong guardian key -> rejected",
              gv_g5_verify_veto_payload(DEST, H, pl) == false);   // default = real Guardian key
    }
    {   // AUTO-DISCONNECT: even a valid veto is ignored at/after block 100,000
        auto pl = make_payload(DEST, 200000);
        CHECK("auto-disconnect: valid veto ignored at 100000",
              gv_g5_verify_veto_payload(DEST, 100000, pl, TEST_GUARDIAN) == false);
    }
#else
    {   // mainnet: G5 deferred -> verify is a no-op (false) even with a valid sig
        auto pl = make_payload(DEST, 60000);
        CHECK("mainnet: veto verify is a no-op (inactive)",
              gv_g5_verify_veto_payload(DEST, 50000, pl, TEST_GUARDIAN) == false);
    }
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
