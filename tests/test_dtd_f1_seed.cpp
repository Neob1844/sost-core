// ============================================================================
// test_dtd_f1_seed — V17 (block #40,000) DTD-F1: the normal DTD draw and the
// Historical Jackpot V2 draw are seeded from the PoW commit of [h-16, h-1]
// instead of the block_id, so re-signing a block (BIP-340 aux_rand, same PoW)
// can no longer change who wins.
//
//   pre-V17 : DTD     sha256("SOST_LOTTERY_V11"      || block_id[h-16..h-1] || u64le(h))
//             Jackpot sha256("SOST_HIST_JACKPOT"     || block_id[h-16..h-1] || u64le(h))
//   V17+    : DTD     sha256("SOST_DTD_V17"          || commit[h-16..h-1]   || u64le(h))
//             Jackpot sha256("SOST_HIST_JACKPOT_V17" || commit[h-16..h-1]   || u64le(h))
//
// Sections:
//   1. domain constants, preimage layout, height dispatch (both rules, boundary)
//   2. pre-V17 byte identity: the legacy preimage is reproduced exactly and the
//      new pow_commit field is never read below DTD_F1_HEIGHT
//   3. re-signing with the REAL consensus code: one PoW solution (one commit),
//      N fresh BIP-340 signatures, every one accepted by validate_sbpow_for_block,
//      every one a distinct block_id. Pre-V17 the DTD/Jackpot seeds move with the
//      signature; from V17 they are bit-identical for all N variants.
//   4. frozen normative vectors (docs/v40000/DTD_F1_SEED_POW_COMMIT.md,
//      tests/vectors/dtd_f1_v17.json): known seeds and winners (mainnet params).
//
// Usage: test-dtd-f1-seed            (ctest; N = 2000 re-signatures)
//        test-dtd-f1-seed --resign N (large run, e.g. N = 100000)
//        test-dtd-f1-seed --emit     (print the frozen vector JSON)
// ============================================================================
#include "sost/lottery.h"
#include "sost/jackpot_v2.h"
#include "sost/params.h"
#include "sost/sbpow.h"
#include "sost/crypto.h"
#include "sost/serialize.h"
#include "sost/pow/convergencex.h"

#include <secp256k1.h>
#include <secp256k1_extrakeys.h>
#include <secp256k1_schnorrsig.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <set>
#include <map>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::lottery;
namespace jv2 = sost::jackpot_v2;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { ++g_pass; std::printf("  PASS: %s\n", msg); } \
    else      { ++g_fail; std::printf("  FAIL: %s\n", msg); } \
} while (0)

static std::string hex(const uint8_t* p, size_t n) {
    static const char* d = "0123456789abcdef"; std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s.push_back(d[p[i] >> 4]); s.push_back(d[p[i] & 15]); }
    return s;
}
template <size_t N> static std::string hex(const std::array<uint8_t, N>& a) { return hex(a.data(), N); }
static Bytes32 tagged(const char* tag, int64_t x) {
    std::vector<uint8_t> b(tag, tag + std::strlen(tag)); append_u64_le(b, (uint64_t)x); return sha256(b);
}
static Bytes32 unhex32(const char* s) { Bytes32 b{}; for (int i = 0; i < 32; ++i) { unsigned v; std::sscanf(s + 2 * i, "%2x", &v); b[i] = (uint8_t)v; } return b; }

// Synthetic miner identities (raw pkh; sorted order = byte order).
static PubKeyHash P(int i) { PubKeyHash p{}; p[0] = (uint8_t)(0x10 + i * 7); p[1] = (uint8_t)i; p[19] = 0xA5; return p; }

// Full v2 header bytes, byte-identical to sost-node.cpp build_full_header_bytes():
//   magic || "HDR2" || hc72(prev, merkle, ts, bits) || checkpoints_root || nonce || extra
//   || version || miner_pubkey || miner_signature
struct Hdr {
    Bytes32 prev{}, mrkl{}, croot{}; uint32_t ts{0}, bits{0}, nonce{0}, extra{0}, ver{2};
    sbpow::MinerPubkey pk{}; sbpow::MinerSignature sig{};
};
static Bytes32 block_id_of(const Hdr& h, const Bytes32& commit) {
    std::vector<uint8_t> b; append_magic(b); append(b, "HDR2", 4);
    append(b, h.prev); append(b, h.mrkl); append_u32_le(b, h.ts); append_u32_le(b, h.bits);
    append(b, h.croot); append_u32_le(b, h.nonce); append_u32_le(b, h.extra); append_u32_le(b, h.ver);
    b.insert(b.end(), h.pk.begin(), h.pk.end()); b.insert(b.end(), h.sig.begin(), h.sig.end());
    return compute_block_id(b.data(), b.size(), commit);
}

// --------------------------------------------------------------------------
// Fixture: a chain of `n` synthetic blocks ending at tip T, 13 miners in rotation
// (each ~7.6% of any 288 window: under the 10% gate, gate armed at >= 11 miners),
// block_id = H("blockid"||x), commit = H("commit"||x). Block T is a REAL v2 SbPoW
// block signed by a secp256k1 test key (its pkh is the coinbase miner of T).
// --------------------------------------------------------------------------
struct Fixture {
    int64_t T{0};
    std::vector<LotteryMinedBlockView> hist;    // heights [T-n+1, T]
    Hdr hdrT; Bytes32 commitT{}; Bytes32 genesis{};
    sbpow::MinerPrivkey sk{}; PubKeyHash miner_pkh{};
    secp256k1_context* ctx{nullptr}; secp256k1_keypair kp{};
    Bytes32 msgT{};
};
static Fixture make_fixture(int64_t T, int64_t n) {
    Fixture f; f.T = T;
    for (int64_t x = T - n + 1; x <= T; ++x) {
        LotteryMinedBlockView v; v.height = x; v.miner_pkh = P(1 + (int)(x % 13));
        v.block_hash = tagged("blockid", x); v.pow_commit = tagged("commit", x);
        f.hist.push_back(v);
    }
    for (int i = 0; i < 32; ++i) f.sk[i] = (uint8_t)(i + 1);              // test key 0x0102..20
    f.ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    if (!secp256k1_keypair_create(f.ctx, &f.kp, f.sk.data())) std::abort();
    sbpow::derive_compressed_pubkey_from_privkey(f.sk, f.hdrT.pk);
    f.miner_pkh = sbpow::derive_pkh_from_pubkey(f.hdrT.pk);
    f.genesis = unhex32("6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");   // mainnet genesis
    f.hdrT.prev = tagged("blockid", T - 1); f.hdrT.mrkl = tagged("merkle", T); f.hdrT.croot = tagged("croot", T);
    f.hdrT.ts = 1800000000u; f.hdrT.bits = 229824u; f.hdrT.nonce = 3366u; f.hdrT.extra = 0u; f.hdrT.ver = 2u;
    f.commitT = tagged("commit", T);
    f.msgT = sbpow::build_sbpow_message_v13(f.genesis, f.hdrT.prev, T, f.hdrT.ts, f.hdrT.bits, f.commitT,
                                            f.hdrT.mrkl, f.hdrT.nonce, f.hdrT.extra, f.hdrT.pk);
    // block T: real SbPoW miner, block_id over the deterministic (stock miner) signature
    if (!sbpow::sign_sbpow_commitment(f.sk, f.msgT, f.hdrT.sig)) std::abort();
    f.hist.back().miner_pkh = f.miner_pkh;
    f.hist.back().pow_commit = f.commitT;
    f.hist.back().block_hash = block_id_of(f.hdrT, f.commitT);
    return f;
}

// Re-sign block T with aux_rand derived from i (i == 0: the stock deterministic signature).
// Returns false if the consensus SbPoW gate does not accept the variant.
static bool resign(Fixture& f, uint64_t i, sbpow::MinerSignature& sig) {
    if (i == 0) { if (!sbpow::sign_sbpow_commitment(f.sk, f.msgT, sig)) return false; }
    else {
        uint8_t aux[32] = {0}; for (int k = 0; k < 8; ++k) aux[k] = (uint8_t)(i >> (8 * k)); aux[31] = 0x5A;
        if (!secp256k1_schnorrsig_sign(f.ctx, sig.data(), f.msgT.data(), &f.kp, aux)) return false;
    }
    sbpow::ValidationInputs vi;
    vi.header_version = 2; vi.prev_hash = f.hdrT.prev; vi.height = f.T; vi.commit = f.commitT;
    vi.nonce = f.hdrT.nonce; vi.extra_nonce = f.hdrT.extra; vi.miner_pubkey = f.hdrT.pk; vi.miner_signature = sig;
    vi.coinbase_miner_pkh = f.miner_pkh; vi.phase2_height = V11_PHASE2_HEIGHT; vi.v13_height = V13_HEIGHT;
    vi.timestamp = f.hdrT.ts; vi.bits_q = f.hdrT.bits; vi.merkle_root = f.hdrT.mrkl; vi.genesis_hash = f.genesis;
    return sbpow::validate_sbpow_for_block(vi) == sbpow::ValidationResult::OK;
}

// Jackpot V2 weighted set for draw height H from the history (every window miner
// node-bound with the required heartbeats: the seed, not eligibility, is under test).
static std::vector<jv2::JackpotV2Weighted> jackpot_set(const std::vector<LotteryMinedBlockView>& hist, int64_t H) {
    const int64_t A = HIST_JACKPOT_V2_HEIGHT, L = NODE_EPOCH_LENGTH;
    std::map<PubKeyHash, int64_t> powc;
    for (const auto& v : hist) if (v.height >= H - JACKPOT_V2_POW_WINDOW && v.height <= H - 1) powc[v.miner_pkh]++;
    std::vector<jv2::JackpotV2Candidate> cs;
    for (const auto& kv : powc) {
        jv2::JackpotV2Candidate c; c.mining_pkh = kv.first; c.sbpow_valid = true; c.pow_blocks = kv.second;
        c.node_bound = true; c.heartbeats_in_window = jv2::jv2_heartbeat_required(jv2::jv2_completed_epochs_before(A, L, H));
        cs.push_back(c);
    }
    return jv2::jv2_build_weighted_set(cs, A, L, H);
}
// Jackpot seed exactly as sost-node.cpp compute_v2_jackpot_winner builds it.
static Bytes32 jackpot_seed(const std::vector<LotteryMinedBlockView>& hist, int64_t H) {
    std::vector<Bytes32> ids, commits;
    for (const auto& v : hist) if (v.height >= H - LOTTERY_RNG_HISTORY_BLOCKS && v.height <= H - 1) {
        ids.push_back(v.block_hash); commits.push_back(v.pow_commit);
    }
    return jv2::jv2_seed_at(ids, commits, H);
}
static std::vector<LotteryMinedBlockView> below(const std::vector<LotteryMinedBlockView>& h, int64_t H) {
    std::vector<LotteryMinedBlockView> o; for (const auto& v : h) if (v.height < H) o.push_back(v); return o;
}

// --------------------------------------------------------------------------
static void test_constants_and_dispatch() {
    std::printf("\n=== 1. domains, preimage layout, height dispatch ===\n");
    TEST("pre-V17 DTD domain unchanged = SOST_LOTTERY_V11", std::string(LOTTERY_RNG_DOMAIN) == "SOST_LOTTERY_V11");
    TEST("V17 DTD domain = SOST_DTD_V17", std::string(LOTTERY_RNG_DOMAIN_V17) == "SOST_DTD_V17");
    TEST("pre-V17 jackpot domain unchanged = SOST_HIST_JACKPOT", std::string(jv2::JACKPOT_V2_DOMAIN) == "SOST_HIST_JACKPOT");
    TEST("V17 jackpot domain = SOST_HIST_JACKPOT_V17", std::string(jv2::JACKPOT_V2_DOMAIN_V17) == "SOST_HIST_JACKPOT_V17");
    std::set<std::string> doms = {LOTTERY_RNG_DOMAIN, LOTTERY_RNG_DOMAIN_V17, jv2::JACKPOT_V2_DOMAIN, jv2::JACKPOT_V2_DOMAIN_V17};
    TEST("four distinct domain tags", doms.size() == 4);
    // No preimage of one rule can equal a preimage of another: with a full 16-entry window
    // every rule hashes tag || 16*32 bytes || 8 bytes, and the four tag lengths differ, so the
    // four preimage lengths (536 / 532 / 537 / 541) are pairwise distinct. ("SOST_HIST_JACKPOT"
    // is a prefix of "SOST_HIST_JACKPOT_V17", which is harmless for that reason; the two
    // jackpot rules also never apply at the same height.)
    std::set<size_t> lens;
    for (auto& d : doms) lens.insert(d.size() + 16 * 32 + 8);
    TEST("full-window preimage lengths pairwise distinct across the 4 rules", lens.size() == 4);
    TEST("DTD_F1_HEIGHT == V17_HEIGHT in the V17 package (no new height)", DTD_F1_HEIGHT == V17_HEIGHT);
    TEST("activation is DTD_F1_HEIGHT exactly",
         !lottery_seed_uses_pow_commit(DTD_F1_HEIGHT - 1) == (DTD_F1_HEIGHT != INT64_MAX) &&
         lottery_seed_uses_pow_commit(DTD_F1_HEIGHT) == dtd_f1_active_at(DTD_F1_HEIGHT));
#if !defined(SOST_TESTNET_FORKS) && !defined(SOST_DEVNET_FORKS)
    TEST("mainnet V17_HEIGHT == 40000", V17_HEIGHT == 40000);
#endif
    if (DTD_F1_HEIGHT == INT64_MAX) return;

    // V17 preimage layout = tag || 16 commits || u64le(h), built by hand
    const int64_t H = DTD_F1_HEIGHT + 100;
    std::vector<LotteryMinedBlockView> hist;
    for (int64_t x = H - 40; x < H; ++x) { LotteryMinedBlockView v; v.height = x; v.miner_pkh = P(1);
        v.block_hash = tagged("blockid", x); v.pow_commit = tagged("commit", x); hist.push_back(v); }
    std::vector<uint8_t> exp(LOTTERY_RNG_DOMAIN_V17, LOTTERY_RNG_DOMAIN_V17 + LOTTERY_RNG_DOMAIN_V17_LEN);
    for (int64_t x = H - 16; x < H; ++x) append(exp, tagged("commit", x));
    append_u64_le(exp, (uint64_t)H);
    TEST("V17 seed input == 'SOST_DTD_V17' || commit[h-16..h-1] || u64le(h)",
         lottery_seed_input_from_history(hist, H) == exp);
    TEST("V17 seed input length == 12 + 16*32 + 8", lottery_seed_input_from_history(hist, H).size() == 12 + 512 + 8);
    // order independence of the caller's vector (window is sorted by height)
    auto rev = hist; std::reverse(rev.begin(), rev.end());
    TEST("V17 seed independent of history vector order", lottery_seed_from_history(rev, H) == lottery_seed_from_history(hist, H));
    // block_hash is never read from V17
    auto mut = hist; for (auto& v : mut) v.block_hash = tagged("other-id", v.height);
    TEST("V17 DTD seed ignores block_id", lottery_seed_from_history(mut, H) == lottery_seed_from_history(hist, H));
    TEST("V17 jackpot seed ignores block_id", jackpot_seed(mut, H) == jackpot_seed(hist, H));
    // every commit in the window matters, outside it none does
    bool each = true;
    for (int64_t x = H - 16; x < H; ++x) { auto m = hist; for (auto& v : m) if (v.height == x) v.pow_commit[5] ^= 1;
        if (lottery_seed_from_history(m, H) == lottery_seed_from_history(hist, H) || jackpot_seed(m, H) == jackpot_seed(hist, H)) each = false; }
    TEST("each of the 16 window commits changes both V17 seeds", each);
    { auto m = hist; for (auto& v : m) if (v.height == H - 17) v.pow_commit[0] ^= 1;
      TEST("commit of h-17 (outside the window) changes nothing", lottery_seed_from_history(m, H) == lottery_seed_from_history(hist, H)); }
    // V17 jackpot preimage layout
    std::vector<Bytes32> cm; for (int64_t x = H - 16; x < H; ++x) cm.push_back(tagged("commit", x));
    std::vector<uint8_t> je(jv2::JACKPOT_V2_DOMAIN_V17, jv2::JACKPOT_V2_DOMAIN_V17 + 21);
    for (auto& c : cm) append(je, c); append_u64_le(je, (uint64_t)H);
    TEST("V17 jackpot seed == sha256('SOST_HIST_JACKPOT_V17' || commits || u64le(h))", jv2::jv2_seed_v17(cm, H) == sha256(je));
    TEST("V17 DTD seed != V17 jackpot seed (same commits, domain-separated)",
         lottery_seed_from_history(hist, H) != jv2::jv2_seed_v17(cm, H));
    TEST("V17 jackpot seed != legacy jackpot seed over the same bytes", jv2::jv2_seed_v17(cm, H) != jv2::jv2_seed(cm, H));
}

static void test_pre_v17_identity() {
    std::printf("\n=== 2. pre-V17 byte identity ===\n");
    // Heights below DTD_F1_HEIGHT on every network. On mainnet they are real history heights.
    const int64_t top = (DTD_F1_HEIGHT == INT64_MAX) ? 30712 : DTD_F1_HEIGHT - 1;
    std::vector<LotteryMinedBlockView> hist;
    for (int64_t x = top - 40; x <= top; ++x) { LotteryMinedBlockView v; v.height = x; v.miner_pkh = P(2);
        v.block_hash = tagged("blockid", x); v.pow_commit = tagged("commit", x); hist.push_back(v); }
    bool all = true, ignore_commit = true;
    for (int64_t H = top - 20; H <= top; ++H) {
        std::vector<uint8_t> exp(LOTTERY_RNG_DOMAIN, LOTTERY_RNG_DOMAIN + LOTTERY_RNG_DOMAIN_LEN);
        for (int64_t x = H - 16; x < H; ++x) append(exp, tagged("blockid", x));
        append_u64_le(exp, (uint64_t)H);
        if (lottery_seed_input_from_history(hist, H) != exp) all = false;
        auto m = hist; for (auto& v : m) v.pow_commit = tagged("garbage", v.height);
        if (lottery_seed_from_history(m, H) != lottery_seed_from_history(hist, H) || jackpot_seed(m, H) != jackpot_seed(hist, H))
            ignore_commit = false;
        std::vector<Bytes32> ids; for (int64_t x = H - 16; x < H; ++x) ids.push_back(tagged("blockid", x));
        if (jackpot_seed(hist, H) != jv2::jv2_seed(ids, H)) all = false;
    }
    TEST("pre-V17 DTD preimage == 'SOST_LOTTERY_V11' || block_id[h-16..h-1] || u64le(h) (21 heights)", all);
    TEST("pre-V17 seeds never read pow_commit (garbage commits: identical seeds)", ignore_commit);
    // Frozen pre-V17 value over 16 synthetic ids, cross-checked by an independent Python
    // implementation (tests/vectors/dtd_f1_v17.json "pre_v17_control").
    std::vector<LotteryMinedBlockView> one;
    for (int64_t x = 30696; x <= 30711; ++x) { LotteryMinedBlockView v; v.height = x; v.block_hash = tagged("mainnet-shape", x); one.push_back(v); }
    if (!dtd_f1_active_at(30712)) {
        TEST("pre-V17 frozen seed (h=30712, ids=H('mainnet-shape'||x))",
             hex(lottery_seed_from_history(one, 30712)) == "6afa7625033cbfc0e55de4f01fffb1ff4814ff58171b269e0be9643e520e2434");
    }
}

// Section 3: N re-signatures of one PoW solution.
struct ResignStats { uint64_t n{0}, sbpow_ok{0}; size_t ids{0}, pre_dtd_seeds{0}, pre_dtd_winners{0}, pre_jp_seeds{0}, pre_jp_winners{0};
                     size_t post_dtd_seeds{0}, post_dtd_winners{0}, post_jp_seeds{0}, post_jp_winners{0}; size_t E_pre{0}, E_post{0}, J_pre{0}, J_post{0}; };
static ResignStats run_resign(uint64_t N, bool verbose) {
    ResignStats st; st.n = N;
    if (DTD_F1_HEIGHT == INT64_MAX) return st;
    // Block T = DTD_F1_HEIGHT - 2 is the re-signed block. Pre-V17 draw at T+1 = DTD_F1_HEIGHT-1 (legacy rule,
    // window contains T's block_id). V17 draw at T+2 = DTD_F1_HEIGHT (new rule, window contains T's commit)
    // and the jackpot draw at the first jackpot height >= DTD_F1_HEIGHT whose window contains T is not
    // guaranteed, so the jackpot is also evaluated at T+1 / T+2 directly (the seed is what matters).
    Fixture f = make_fixture(DTD_F1_HEIGHT - 2, 400);
    const int64_t Hpre = f.T + 1, Hpost = f.T + 2;
    // block T+1 (needed for the V17 draw at T+2)
    LotteryMinedBlockView n1; n1.height = f.T + 1; n1.miner_pkh = P(3); n1.block_hash = tagged("blockid", f.T + 1);
    n1.pow_commit = tagged("commit", f.T + 1);
    auto hist_pre = below(f.hist, Hpre);
    auto hist_post = f.hist; hist_post.push_back(n1);
    auto el_pre = compute_lottery_eligibility_set(hist_pre, Hpre, PubKeyHash{}, lottery_exclusion_window_at(Hpre));
    auto el_post = compute_lottery_eligibility_set(hist_post, Hpost, PubKeyHash{}, lottery_exclusion_window_at(Hpost));
    auto js_pre = jackpot_set(hist_pre, Hpre), js_post = jackpot_set(hist_post, Hpost);
    st.E_pre = el_pre.size(); st.E_post = el_post.size(); st.J_pre = js_pre.size(); st.J_post = js_post.size();
    std::set<std::string> ids, pds, pjs, qds, qjs; std::set<int64_t> pdw, pjw, qdw, qjw;
    const size_t idxT_pre = hist_pre.size() - 1, idxT_post = hist_post.size() - 2;
    for (uint64_t i = 0; i < N; ++i) {
        sbpow::MinerSignature sig{};
        if (!resign(f, i, sig)) continue;
        ++st.sbpow_ok;
        Hdr h = f.hdrT; h.sig = sig;
        const Bytes32 id = block_id_of(h, f.commitT);   // the PoW commit is unchanged (no new PoW)
        ids.insert(hex(id));
        hist_pre[idxT_pre].block_hash = id; hist_post[idxT_post].block_hash = id;
        pds.insert(hex(lottery_seed_from_history(hist_pre, Hpre)));
        pdw.insert(select_lottery_winner_index_from_history(el_pre, hist_pre, Hpre));
        const Bytes32 pj = jackpot_seed(hist_pre, Hpre); pjs.insert(hex(pj)); pjw.insert(jv2::jv2_select_winner_index(js_pre, pj));
        qds.insert(hex(lottery_seed_from_history(hist_post, Hpost)));
        qdw.insert(select_lottery_winner_index_from_history(el_post, hist_post, Hpost));
        const Bytes32 qj = jackpot_seed(hist_post, Hpost); qjs.insert(hex(qj)); qjw.insert(jv2::jv2_select_winner_index(js_post, qj));
    }
    st.ids = ids.size(); st.pre_dtd_seeds = pds.size(); st.pre_dtd_winners = pdw.size(); st.pre_jp_seeds = pjs.size(); st.pre_jp_winners = pjw.size();
    st.post_dtd_seeds = qds.size(); st.post_dtd_winners = qdw.size(); st.post_jp_seeds = qjs.size(); st.post_jp_winners = qjw.size();
    if (verbose) {
        std::printf("  re-signed block #%lld (one PoW commit %s)\n", (long long)f.T, hex(f.commitT).substr(0, 16).c_str());
        std::printf("  N=%llu  validate_sbpow_for_block OK=%llu  distinct block_ids=%zu\n",
                    (unsigned long long)N, (unsigned long long)st.sbpow_ok, st.ids);
        std::printf("  pre-V17 draw #%lld (rule %s): DTD E=%zu seeds=%zu winners=%zu | Jackpot set=%zu seeds=%zu winners=%zu\n",
                    (long long)Hpre, lottery_seed_uses_pow_commit(Hpre) ? "V17" : "V11", st.E_pre, st.pre_dtd_seeds, st.pre_dtd_winners,
                    st.J_pre, st.pre_jp_seeds, st.pre_jp_winners);
        std::printf("  V17     draw #%lld (rule %s): DTD E=%zu seeds=%zu winners=%zu | Jackpot set=%zu seeds=%zu winners=%zu\n",
                    (long long)Hpost, lottery_seed_uses_pow_commit(Hpost) ? "V17" : "V11", st.E_post, st.post_dtd_seeds, st.post_dtd_winners,
                    st.J_post, st.post_jp_seeds, st.post_jp_winners);
        if (qds.size() == 1) std::printf("  V17 DTD seed (all variants)     %s\n", qds.begin()->c_str());
        if (qjs.size() == 1) std::printf("  V17 Jackpot seed (all variants) %s\n", qjs.begin()->c_str());
    }
    secp256k1_context_destroy(f.ctx);
    return st;
}

static void test_resign(uint64_t N) {
    std::printf("\n=== 3. re-signing one PoW solution (N=%llu, real validate_sbpow_for_block) ===\n", (unsigned long long)N);
    if (DTD_F1_HEIGHT == INT64_MAX) { std::printf("  (V17 not scheduled on this network: skipped)\n"); return; }
    ResignStats s = run_resign(N, true);
    TEST("every re-signature accepted by validate_sbpow_for_block", s.sbpow_ok == N);
    TEST("every re-signature gives a distinct block_id", s.ids == N);
    TEST("pre-V17: DTD seed changes with the signature (one per variant)", s.pre_dtd_seeds == N);
    TEST("pre-V17: Jackpot seed changes with the signature (one per variant)", s.pre_jp_seeds == N);
    if (s.E_pre >= 2) TEST("pre-V17: re-signing reaches several DTD winners (grinding reproduced)", s.pre_dtd_winners >= 2);
    if (s.J_pre >= 2) TEST("pre-V17: re-signing reaches several Jackpot winners", s.pre_jp_winners >= 2);
    TEST("V17: DTD seed identical for all variants", s.post_dtd_seeds == 1);
    TEST("V17: DTD winner identical for all variants", s.post_dtd_winners == 1);
    TEST("V17: Jackpot seed identical for all variants", s.post_jp_seeds == 1);
    TEST("V17: Jackpot winner identical for all variants", s.post_jp_winners == 1);
    std::printf("PRE_V17_RESIGN_GRINDING_REPRODUCED=%s (%zu DTD winners, %zu jackpot winners over %llu re-signatures)\n",
                (s.pre_dtd_seeds == N && s.pre_dtd_winners >= 2) ? "YES" : "NO", s.pre_dtd_winners, s.pre_jp_winners, (unsigned long long)N);
    std::printf("POST_V17_RESIGN_GRINDING=%llu/%llu_%s\n", (unsigned long long)s.sbpow_ok, (unsigned long long)N,
                (s.post_dtd_seeds == 1 && s.post_dtd_winners == 1 && s.post_jp_seeds == 1 && s.post_jp_winners == 1) ? "NO_EFFECT" : "EFFECT");
}

// --------------------------------------------------------------------------
// 4. Frozen normative vectors (mainnet parameters, heights >= 40000).
// --------------------------------------------------------------------------
struct VecOut { int64_t H{0}; std::vector<PubKeyHash> elig; std::string dtd_seed; int64_t dtd_wi{-1};
                std::vector<jv2::JackpotV2Weighted> jset; std::string jp_seed; int64_t jp_wi{-1};
                std::vector<std::string> sigs, ids; bool resign_identical{false}; };
static VecOut vector_case(Fixture& f) {
    VecOut o; o.H = f.T + 1;
    auto el = compute_lottery_eligibility_set(f.hist, o.H, PubKeyHash{}, lottery_exclusion_window_at(o.H));
    for (auto& e : el) o.elig.push_back(e.pkh);
    o.dtd_seed = hex(lottery_seed_from_history(f.hist, o.H));
    o.dtd_wi = select_lottery_winner_index_from_history(el, f.hist, o.H);
    o.jset = jackpot_set(f.hist, o.H);
    const Bytes32 js = jackpot_seed(f.hist, o.H); o.jp_seed = hex(js); o.jp_wi = jv2::jv2_select_winner_index(o.jset, js);
    bool same = true; auto h2 = f.hist;
    for (uint64_t i = 0; i < 3; ++i) {
        sbpow::MinerSignature sig{}; if (!resign(f, i, sig)) { same = false; continue; }
        Hdr h = f.hdrT; h.sig = sig; const Bytes32 id = block_id_of(h, f.commitT);
        o.sigs.push_back(hex(sig)); o.ids.push_back(hex(id));
        h2.back().block_hash = id;
        if (hex(lottery_seed_from_history(h2, o.H)) != o.dtd_seed || hex(jackpot_seed(h2, o.H)) != o.jp_seed ||
            select_lottery_winner_index_from_history(el, h2, o.H) != o.dtd_wi) same = false;
    }
    o.resign_identical = same && o.ids.size() == 3 && o.ids[0] != o.ids[1] && o.ids[1] != o.ids[2];
    return o;
}

// Frozen expected values (generated once with --emit, cross-checked by an independent Python
// implementation, see tests/vectors/dtd_f1_v17.json). DO NOT EDIT without a consensus change.
static const char* EXP_DTD_SEED_40266 = "e85e76c8546c962346996fdbb0e2bc3c1afb13c5e48aa19a4600f036de796a49";
static const int64_t EXP_DTD_WI_40266 = 0;
static const char* EXP_JP_SEED_40266  = "e6ad90b76d774339e62690337af5354b515bb46831d2801d9498d5b1d23c1dbe";
static const int64_t EXP_JP_WI_40266  = 9;
static const size_t  EXP_E_40266      = 8;

static void emit(const VecOut& o, const Fixture& f) {
    std::printf("{\n  \"name\": \"DTD-F1 V17 normative vector\",\n  \"rule\": \"V17_POW_COMMIT\",\n");
    std::printf("  \"draw_height\": %lld,\n  \"dtd_domain\": \"%s\",\n  \"jackpot_domain\": \"%s\",\n", (long long)o.H,
                LOTTERY_RNG_DOMAIN_V17, jv2::JACKPOT_V2_DOMAIN_V17);
    std::printf("  \"history\": \"heights %lld..%lld; miner(x)=P(1+x%%13) where P(i)=[0x10+7i, i, 0..0, 0xA5] (20 bytes); "
                "block_id(x)=sha256('blockid'||u64le(x)); commit(x)=sha256('commit'||u64le(x)); block %lld: real v2 SbPoW block, key 0x0102..20\",\n",
                (long long)f.hist.front().height, (long long)f.hist.back().height, (long long)f.T);
    std::printf("  \"input_commitments\": [");
    for (int64_t x = o.H - 16; x < o.H; ++x) { for (auto& v : f.hist) if (v.height == x)
        std::printf("%s\n    {\"height\": %lld, \"commit\": \"%s\"}", x == o.H - 16 ? "" : ",", (long long)x, hex(v.pow_commit).c_str()); }
    std::printf("\n  ],\n  \"candidate_identities\": [");
    std::set<PubKeyHash> cand; for (auto& v : f.hist) cand.insert(v.miner_pkh);
    bool first = true; for (auto& c : cand) { std::printf("%s\"%s\"", first ? "" : ", ", hex(c).c_str()); first = false; }
    std::printf("],\n  \"dtd_eligible_set\": [");
    first = true; for (auto& e : o.elig) { std::printf("%s\"%s\"", first ? "" : ", ", hex(e).c_str()); first = false; }
    std::printf("],\n  \"dtd_seed\": \"%s\",\n  \"dtd_winner_index\": %lld,\n  \"dtd_winner\": \"%s\",\n", o.dtd_seed.c_str(),
                (long long)o.dtd_wi, o.dtd_wi >= 0 ? hex(o.elig[(size_t)o.dtd_wi]).c_str() : "");
    std::printf("  \"jackpot_weighted_set\": [");
    first = true; for (auto& w : o.jset) { std::printf("%s{\"pkh\": \"%s\", \"weight\": %lld}", first ? "" : ", ", hex(w.pkh).c_str(), (long long)w.weight); first = false; }
    std::printf("],\n  \"jackpot_seed\": \"%s\",\n  \"jackpot_winner_index\": %lld,\n  \"jackpot_winner\": \"%s\",\n", o.jp_seed.c_str(),
                (long long)o.jp_wi, o.jp_wi >= 0 ? hex(o.jset[(size_t)o.jp_wi].pkh).c_str() : "");
    std::printf("  \"resigned_block\": {\"height\": %lld, \"commit\": \"%s\", \"miner_pubkey\": \"%s\", \"sbpow_message_v13\": \"%s\", \"variants\": [",
                (long long)f.T, hex(f.commitT).c_str(), hex(f.hdrT.pk).c_str(), hex(f.msgT).c_str());
    for (size_t i = 0; i < o.sigs.size(); ++i)
        std::printf("%s\n    {\"aux\": %zu, \"miner_signature\": \"%s\", \"block_id\": \"%s\"}", i ? "," : "", i, o.sigs[i].c_str(), o.ids[i].c_str());
    std::printf("\n  ], \"all_variants_same_dtd_seed_and_winner\": %s, \"all_variants_same_jackpot_seed_and_winner\": %s}\n}\n",
                o.resign_identical ? "true" : "false", o.resign_identical ? "true" : "false");
}

static void test_frozen_vectors() {
    std::printf("\n=== 4. frozen normative vectors (mainnet params) ===\n");
    if (DTD_F1_HEIGHT != 40000) { std::printf("  (not a mainnet build: frozen values skipped)\n"); return; }
    Fixture f = make_fixture(40265, 2400);
    VecOut o = vector_case(f);
    TEST("vector: draw height 40266 is a V17 jackpot height", is_hist_jackpot_v2_height(40266) && dtd_f1_active_at(40266));
    TEST("vector: eligible set size", o.elig.size() == EXP_E_40266);
    TEST("vector: DTD seed", o.dtd_seed == EXP_DTD_SEED_40266);
    TEST("vector: DTD winner index", o.dtd_wi == EXP_DTD_WI_40266);
    TEST("vector: Jackpot seed", o.jp_seed == EXP_JP_SEED_40266);
    TEST("vector: Jackpot winner index", o.jp_wi == EXP_JP_WI_40266);
    TEST("vector: 3 re-signatures, 3 block_ids, identical DTD + Jackpot result", o.resign_identical);
    secp256k1_context_destroy(f.ctx);
}

int main(int argc, char** argv) {
    ACTIVE_PROFILE = Profile::MAINNET;
    if (argc >= 2 && std::string(argv[1]) == "--emit") {
        Fixture f = make_fixture(40265, 2400); VecOut o = vector_case(f); emit(o, f); secp256k1_context_destroy(f.ctx); return 0;
    }
    uint64_t N = 2000;
    if (argc >= 3 && std::string(argv[1]) == "--resign") N = std::strtoull(argv[2], nullptr, 10);
    std::printf("test_dtd_f1_seed  DTD_F1_HEIGHT=%lld\n", (long long)DTD_F1_HEIGHT);
    test_constants_and_dispatch();
    test_pre_v17_identity();
    test_resign(N);
    test_frozen_vectors();
    std::printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
