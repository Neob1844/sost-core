// SOST Post-Quantum Migration V3 — standalone prototype tests.
//
// STANDALONE. This test is NOT registered in the project's CMake/ctest and is
// NOT part of the node/miner build. It compiles the header-only prototype in
// prototype/pq/ with nothing but the C++17 standard library, so it can never
// affect mainnet consensus. Build & run:
//
//   c++ -std=c++17 -I prototype/pq  tests/pq_vectors/test_pq_witness.cpp -o /tmp/test_pq_witness
//   /tmp/test_pq_witness            # exit 0 = all pass, nonzero = failure
//
// (See tests/pq_vectors/README.md for the one-liner and expected output.)
//
// Author: NeoB.
#include <cstdio>
#include <cstdlib>
#include <vector>
#include "pq_witness.h"
#include "pq_validate.h"

using namespace sost::pq_proto;

static int g_fail = 0;
static int g_pass = 0;

#define CHECK(cond, msg)                                                     \
    do {                                                                     \
        if (cond) { ++g_pass; }                                              \
        else { ++g_fail; std::printf("  FAIL: %s (line %d)\n", msg, __LINE__); } \
    } while (0)

static Bytes filled(size_t n, Byte v) { return Bytes(n, v); }

// Build a well-formed witness for an active alg_id with placeholder bytes.
static PqWitness make_witness(AlgId id) {
    PqWitness w;
    w.alg_id = id;
    switch (id) {
        case AlgId::LEGACY_ECDSA_SECP256K1:
            w.sig = filled(ECDSA_SIZES.sig_len, 0x11);
            w.pubkey = filled(ECDSA_SIZES.pk_len, 0x22);
            break;
        case AlgId::PQ_ML_DSA_44:
            w.sig = filled(ML_DSA_44_SIZES.sig_len, 0x33);
            w.pubkey = filled(ML_DSA_44_SIZES.pk_len, 0x44);
            break;
        case AlgId::HYBRID_ECDSA_ML_DSA_44:
            w.sig = filled(ECDSA_SIZES.sig_len, 0x11);
            w.pubkey = filled(ECDSA_SIZES.pk_len, 0x22);
            w.pq_sig = filled(ML_DSA_44_SIZES.sig_len, 0x33);
            w.pq_pubkey = filled(ML_DSA_44_SIZES.pk_len, 0x44);
            break;
        default: break;
    }
    return w;
}

int main() {
    std::printf("== SOST PQ V3 prototype witness tests ==\n");

    // ---- VALID round-trips: serialize -> parse -> OK, fields preserved ----
    for (AlgId id : { AlgId::LEGACY_ECDSA_SECP256K1,
                      AlgId::PQ_ML_DSA_44,
                      AlgId::HYBRID_ECDSA_ML_DSA_44 }) {
        Bytes wire = serialize_witness(make_witness(id));
        PqWitness parsed;
        PqParseCode rc = parse_witness(wire, parsed);
        CHECK(rc == PqParseCode::OK, "valid witness must parse OK");
        CHECK(parsed.alg_id == id, "alg_id preserved");
    }

    // ---- INVALID: empty ----
    {
        PqWitness p; Bytes empty;
        CHECK(parse_witness(empty, p) == PqParseCode::ERR_EMPTY, "empty rejected");
    }

    // ---- INVALID: unknown alg_id (0x7E) ----
    {
        Bytes wire = { 0x7E }; PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_UNKNOWN_ALGID, "unknown id rejected");
    }

    // ---- INVALID: reserved alg_ids rejected distinctly ----
    for (Byte id : { (Byte)0x03, (Byte)0x04, (Byte)0x10 }) {
        Bytes wire = { id }; PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_RESERVED_ALGID, "reserved id rejected");
    }

    // ---- INVALID: 0xFF sentinel ----
    {
        Bytes wire = { 0xFF }; PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_INVALID_ALGID, "0xFF rejected");
    }

    // ---- INVALID: truncated (id + partial length prefix) ----
    {
        Bytes wire = { 0x00, 0x00 }; PqWitness p;  // only 1 of 2 len bytes
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_TRUNCATED, "truncated prefix rejected");
    }

    // ---- INVALID: wrong component length (declared 63 not 64) ----
    {
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        // wire[1..2] is the big-endian length of the sig (0x0040 = 64). Corrupt to 63.
        wire[1] = 0x00; wire[2] = 0x3F;
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "wrong declared length rejected");
    }

    // ---- INVALID: oversized declared length (0xFFFF) with too few bytes ----
    {
        Bytes wire = serialize_witness(make_witness(AlgId::PQ_ML_DSA_44));
        wire[1] = 0xFF; wire[2] = 0xFF;  // claim 65535-byte sig
        PqWitness p;
        // 65535 != 2420 expected -> WRONG_COMPONENT_LEN (rejected before allocation)
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "oversized declared length rejected");
    }

    // ---- INVALID: trailing bytes after a complete witness ----
    {
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        wire.push_back(0xAB);  // one extra byte
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_TRAILING_BYTES, "trailing byte rejected");
    }

    // ---- INVALID: hybrid halves mis-ordered (ML-DSA sig where ECDSA sig expected) ----
    {
        // Build a hybrid but swap the two signature sizes: the first declared
        // length becomes 2420 where 64 is required -> WRONG_COMPONENT_LEN.
        PqWitness w = make_witness(AlgId::HYBRID_ECDSA_ML_DSA_44);
        std::swap(w.sig, w.pq_sig);      // now sig is 2420 bytes in the ECDSA slot
        std::swap(w.pubkey, w.pq_pubkey);
        Bytes wire = serialize_witness(w);
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "mis-ordered hybrid halves rejected");
    }

    // ---- BE16-ONLY: accidental little-endian length (bytes swapped) ----
    {
        // sig length 64 is big-endian 0x00 0x40; a little-endian encoder would emit
        // 0x40 0x00 = 0x4000 = 16384 under BE decoding -> WRONG_COMPONENT_LEN.
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        std::swap(wire[1], wire[2]);
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "little-endian length rejected (BE16 only)");
    }

    // ---- BE16-ONLY: one-byte length prefix (high byte dropped) ----
    {
        // Drop the high 0x00 byte so only one length byte precedes the data. The
        // parser still reads TWO bytes; it sees 0x40,0x11 = 0x4011 -> WRONG_COMPONENT_LEN.
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        wire.erase(wire.begin() + 1);  // remove the 0x00 high length byte
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "one-byte length prefix rejected (exactly two bytes required)");
    }

    // ---- BE16-ONLY: three-byte CompactSize-style prefix (0xFD||uint16_le) ----
    {
        // CompactSize(2420) = FD 74 09. Under BE16 the first two bytes are
        // 0xFD74 = 64884 != 2420 expected -> WRONG_COMPONENT_LEN. CompactSize is not
        // a recognised encoding; 0xFD is just a high length byte here.
        Bytes wire = { 0x01, 0xFD, 0x74, 0x09 };  // ML-DSA-44 alg + CompactSize sig len
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "three-byte CompactSize prefix rejected");
    }

    // ---- BE16-ONLY: 0xFD lead is NOT a varint marker ----
    {
        Bytes wire = { 0x00, 0xFD, 0x00 };  // BE16 = 0xFD00 = 64768 != 64
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "0xFD lead treated as high length byte, not varint");
    }

    // ---- INVALID: correct declared length but truncated component data ----
    {
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        wire.resize(1 + 2 + 30);  // alg + len(=64) + only 30 of 64 sig bytes
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_TRUNCATED,
              "correct length but truncated data rejected");
    }

    // ---- INVALID: wrong declared length (65) with more than enough bytes ----
    {
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        wire[1] = 0x00; wire[2] = 0x41;  // declare 65, buffer still holds 64+ bytes
        PqWitness p;
        CHECK(parse_witness(wire, p) == PqParseCode::ERR_WRONG_COMPONENT_LEN,
              "wrong length with enough data rejected before reading");
    }

    // ---- CANONICAL: serialize(parse(x)) is byte-identical for every active alg ----
    for (AlgId id : { AlgId::LEGACY_ECDSA_SECP256K1,
                      AlgId::PQ_ML_DSA_44,
                      AlgId::HYBRID_ECDSA_ML_DSA_44 }) {
        Bytes wire = serialize_witness(make_witness(id));
        PqWitness parsed;
        CHECK(parse_witness(wire, parsed) == PqParseCode::OK, "round-trip parse OK");
        Bytes reser = serialize_witness(parsed);
        CHECK(reser == wire, "canonical round-trip is byte-identical");
    }

    // ---- VERIFY: LEGACY OK when ECDSA hook returns true ----
    {
        Verifiers v;
        v.ecdsa_verify   = [](const Bytes&, const Bytes&, const Bytes&) { return true; };
        v.ml_dsa_verify  = [](const Bytes&, const Bytes&, const Bytes&) { return true; };
        Bytes wire = serialize_witness(make_witness(AlgId::LEGACY_ECDSA_SECP256K1));
        Sighash32 sh{}; sh.fill(0xAA);
        CHECK(parse_and_verify(wire, sh, v) == PqVerifyCode::OK, "legacy verify OK");
    }

    // ---- VERIFY: HYBRID is AND — fails if ML-DSA half fails even when ECDSA passes ----
    {
        Verifiers v;
        v.ecdsa_verify  = [](const Bytes&, const Bytes&, const Bytes&) { return true; };
        v.ml_dsa_verify = [](const Bytes&, const Bytes&, const Bytes&) { return false; };
        Bytes wire = serialize_witness(make_witness(AlgId::HYBRID_ECDSA_ML_DSA_44));
        Sighash32 sh{}; sh.fill(0xCC);
        CHECK(parse_and_verify(wire, sh, v) == PqVerifyCode::ERR_ML_DSA_FAIL,
              "hybrid rejects when ML-DSA half fails (AND, not OR)");
    }

    // ---- VERIFY: HYBRID fails if ECDSA half fails even when ML-DSA passes ----
    {
        Verifiers v;
        v.ecdsa_verify  = [](const Bytes&, const Bytes&, const Bytes&) { return false; };
        v.ml_dsa_verify = [](const Bytes&, const Bytes&, const Bytes&) { return true; };
        Bytes wire = serialize_witness(make_witness(AlgId::HYBRID_ECDSA_ML_DSA_44));
        Sighash32 sh{}; sh.fill(0xDD);
        CHECK(parse_and_verify(wire, sh, v) == PqVerifyCode::ERR_ECDSA_FAIL,
              "hybrid rejects when ECDSA half fails (AND, not OR)");
    }

    // ---- VERIFY: domain separation differs per scheme ----
    {
        Sighash32 sh{}; sh.fill(0x01);
        Bytes a = domain_message(DOMAIN_TAG_LEGACY, sh);
        Bytes b = domain_message(DOMAIN_TAG_ML_DSA, sh);
        Bytes c = domain_message(DOMAIN_TAG_HYBRID, sh);
        CHECK(a != b && b != c && a != c, "distinct domain tags per scheme");
    }

    std::printf("== pass=%d fail=%d ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
