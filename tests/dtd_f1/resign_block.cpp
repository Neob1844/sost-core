// dtd-f1-resign-block — TEST TOOL (devnet E2E only). Re-signs a mined block with a fresh BIP-340
// signature over the SAME SbPoW message (same PoW commit, no new work), exactly what a modified
// miner or a submitblock proxy holding the miner key can do, and prints the resulting block JSON
// (new miner_signature, recomputed block_id; every other byte unchanged).
//
// Usage: dtd-f1-resign-block <block.json> <privkey-file> <genesis-hex> <aux-index> [--profile dev|mainnet]
//   aux-index 0 = the stock deterministic signature (must reproduce the original block_id).
// Exit: 0 ok; 2 usage/parse; 3 original block_id not reproduced; 4 key/pkh mismatch or signing failed.
#include "sost/sbpow.h"
#include "sost/params.h"
#include "sost/serialize.h"
#include "sost/crypto.h"
#include "sost/pow/convergencex.h"
#include <secp256k1.h>
#include <secp256k1_extrakeys.h>
#include <secp256k1_schnorrsig.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

using namespace sost;

static std::string field(const std::string& j, const char* k) {
    const std::string key = std::string("\"") + k + "\"";
    size_t p = j.find(key); if (p == std::string::npos) return "";
    p = j.find(':', p + key.size()); if (p == std::string::npos) return "";
    ++p; while (p < j.size() && (j[p] == ' ' || j[p] == '\t')) ++p;
    if (p < j.size() && j[p] == '"') { size_t e = j.find('"', p + 1); return j.substr(p + 1, e - p - 1); }
    size_t e = p; while (e < j.size() && (std::isdigit((unsigned char)j[e]) || j[e] == '-')) ++e;
    return j.substr(p, e - p);
}
static bool unhex(const std::string& s, uint8_t* out, size_t n) {
    if (s.size() != 2 * n) return false;
    for (size_t i = 0; i < n; ++i) { unsigned v; if (std::sscanf(s.c_str() + 2 * i, "%2x", &v) != 1) return false; out[i] = (uint8_t)v; }
    return true;
}
static std::string hex(const uint8_t* p, size_t n) { static const char* d = "0123456789abcdef"; std::string s; for (size_t i = 0; i < n; ++i) { s += d[p[i] >> 4]; s += d[p[i] & 15]; } return s; }
static void replace_all(std::string& s, const std::string& a, const std::string& b) { size_t p = 0; while ((p = s.find(a, p)) != std::string::npos) { s.replace(p, a.size(), b); p += b.size(); } }

int main(int argc, char** argv) {
    if (argc < 5) { std::fprintf(stderr, "usage: %s block.json privkey-file genesis-hex aux-index [--profile dev|mainnet]\n", argv[0]); return 2; }
    ACTIVE_PROFILE = Profile::DEV;
    if (argc >= 7 && std::string(argv[5]) == "--profile" && std::string(argv[6]) == "mainnet") ACTIVE_PROFILE = Profile::MAINNET;
    std::ifstream in(argv[1]); std::stringstream ss; ss << in.rdbuf(); std::string j = ss.str();
    std::ifstream kf(argv[2]); std::string khex; kf >> khex;
    Bytes32 prev{}, mrkl{}, commit{}, croot{}, genesis{}, bid{}; sbpow::MinerPubkey pk{}; sbpow::MinerSignature sig0{}; sbpow::MinerPrivkey sk{};
    if (!unhex(field(j, "prev_hash"), prev.data(), 32) || !unhex(field(j, "merkle_root"), mrkl.data(), 32) ||
        !unhex(field(j, "commit"), commit.data(), 32) || !unhex(field(j, "checkpoints_root"), croot.data(), 32) ||
        !unhex(field(j, "block_id"), bid.data(), 32) || !unhex(field(j, "miner_pubkey"), pk.data(), 33) ||
        !unhex(field(j, "miner_signature"), sig0.data(), 64) || !unhex(argv[3], genesis.data(), 32) || !unhex(khex, sk.data(), 32)) {
        std::fprintf(stderr, "parse error\n"); return 2;
    }
    const int64_t height = std::stoll(field(j, "height"));
    const uint32_t ts = (uint32_t)std::stoul(field(j, "timestamp")), bits = (uint32_t)std::stoul(field(j, "bits_q"));
    const uint32_t nonce = (uint32_t)std::stoul(field(j, "nonce")), extra = (uint32_t)std::stoul(field(j, "extra_nonce"));
    const uint32_t ver = (uint32_t)std::stoul(field(j, "version"));
    const uint64_t aux_i = std::stoull(argv[4]);
    auto id_with = [&](const sbpow::MinerSignature& sg) {
        std::vector<uint8_t> b; append_magic(b); append(b, "HDR2", 4); append(b, prev); append(b, mrkl);
        append_u32_le(b, ts); append_u32_le(b, bits); append(b, croot); append_u32_le(b, nonce); append_u32_le(b, extra);
        append_u32_le(b, ver); b.insert(b.end(), pk.begin(), pk.end()); b.insert(b.end(), sg.begin(), sg.end());
        return compute_block_id(b.data(), b.size(), commit); };
    if (id_with(sig0) != bid) { std::fprintf(stderr, "original block_id not reproduced\n"); return 3; }
    sbpow::MinerPubkey dpk{};
    if (!sbpow::derive_compressed_pubkey_from_privkey(sk, dpk) || dpk != pk) { std::fprintf(stderr, "key does not match miner_pubkey\n"); return 4; }
    const Bytes32 msg = (height >= V13_HEIGHT)
        ? sbpow::build_sbpow_message_v13(genesis, prev, height, ts, bits, commit, mrkl, nonce, extra, pk)
        : sbpow::build_sbpow_message(prev, height, commit, nonce, extra, pk);
    sbpow::MinerSignature sig{};
    if (aux_i == 0) { if (!sbpow::sign_sbpow_commitment(sk, msg, sig)) return 4; }
    else {
        secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN);
        secp256k1_keypair kp; if (!secp256k1_keypair_create(ctx, &kp, sk.data())) return 4;
        uint8_t aux[32] = {0}; for (int k = 0; k < 8; ++k) aux[k] = (uint8_t)(aux_i >> (8 * k)); aux[31] = 0xA7;
        if (!secp256k1_schnorrsig_sign(ctx, sig.data(), msg.data(), &kp, aux)) return 4;
        secp256k1_context_destroy(ctx);
    }
    if (!sbpow::verify_sbpow_signature(pk, msg, sig)) { std::fprintf(stderr, "signature does not verify\n"); return 4; }
    const Bytes32 nid = id_with(sig);
    replace_all(j, hex(sig0.data(), 64), hex(sig.data(), 64));
    replace_all(j, hex(bid.data(), 32), hex(nid.data(), 32));
    std::fputs(j.c_str(), stdout);
    std::fprintf(stderr, "resigned h=%lld aux=%llu block_id %s -> %s (commit unchanged %s)\n", (long long)height,
                 (unsigned long long)aux_i, hex(bid.data(), 8).c_str(), hex(nid.data(), 8).c_str(), hex(commit.data(), 8).c_str());
    return 0;
}
