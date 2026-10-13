// =============================================================================
// test_full_verify_early_chain.cpp — regression for `sost-node --full-verify`
// on the real mainnet chain, early window (heights 1..3300).
//
// Finding (docs/verification/FULL_VERIFY_EARLY_CHAIN.md): before commit
// 07e49b16 (2026-04-08) save_chain_internal() rebuilt each block's JSON field
// by field and dropped checkpoint_leaves, segment_proofs, round_witnesses and
// profile_index. Every block persisted before that fix — mainnet 1..3300 — has
// no Transcript V2 data anywhere on the network. --full-verify sends block 1
// into verify_cx_proof(), which fails at Phase 1 ("checkpoint_leaves empty"),
// so the node rejects block 1. The default path never gets there: the block
// is under the assumevalid anchor (3554) and is a hard-checkpoint ancestor.
//
// What this test pins, with real mainnet blocks (one per profile class used
// in the window, plus the last block of the window):
//   1. verify_cx_proof() rejects each of them — the transcript is missing.
//      This is the exact failure --full-verify hits at block 1.
//   2. What IS still verifiable without the transcript passes: the commit
//      binding (header, seed, final_state, x_bytes, both roots, metric and the
//      profile byte) and the stability basin + metric, using the profile that
//      the block's stored stab_* parameters select in the legacy table.
//   3. The node's current pre-V3 fallback (missing profile_index => B0) is
//      wrong for 4 of the 5 classes: the commit only binds with the profile the
//      miner actually used (E4/E1/H1/H2 here). Any future full-verify path for
//      this window must derive the profile from stab_*, not assume B0.
//
//   4. The node-side fix (src/full_verify_history.cpp, used only under
//      --full-verify): derive_profile_from_stab_params() returns the same
//      profile as the reference derivation here, for every block; and
//      verify_cx_without_transcript() accepts each block with that profile
//      and rejects it with the B0 default whenever the block is not B0.
//   5. The classification rule: only mainnet 1..3300 with the explicit
//      --full-verify-anchored-history opt-in may be ASSUMED_FROM_HISTORICAL_RULE.
//
// Pure, no network, no chain file, no 4 GB allocations. Consensus untouched.
// =============================================================================
#include "sost/full_verify_history.h"
#include "sost/pow/convergencex.h"
#include "sost/pow/casert.h"
#include "sost/emission.h"
#include "sost/params.h"
#include "sost/serialize.h"
#include "sost/crypto.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace sost;

namespace {

struct EarlyBlock {
    int64_t height;
    const char* prev; const char* merkle;
    uint32_t ts, bits_q, nonce, extra;
    const char* commit; const char* cp_root;
    const char* seg_root; const char* final_state;
    const char* x_bytes;
    uint64_t metric;
    int32_t scale, k, margin, steps, lr_shift;   // as stored in chain.json
};

// Real mainnet blocks (copied from the canonical chain, tip 849e95b1… @30428).
const EarlyBlock kBlocks[] = {
#include "fixtures/full_verify_early_chain_blocks.inc"
};

int g_fail = 0, g_checks = 0;
std::map<int32_t, long> g_profile_hist;   // derived profile -> blocks
bool g_quiet = false;   // whole-window mode: print failures only
void check(bool ok, const std::string& what) {
    ++g_checks;
    if (!ok || !g_quiet) std::printf("[%s] %s\n", ok ? "PASS" : "FAIL", what.c_str());
    if (!ok) ++g_fail;
}

uint8_t hexv(char c) {
    return (uint8_t)(c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10);
}
std::vector<uint8_t> unhex(const char* s) {
    std::vector<uint8_t> v; size_t n = std::strlen(s);
    for (size_t i = 0; i + 1 < n; i += 2) v.push_back((uint8_t)(hexv(s[i]) << 4 | hexv(s[i+1])));
    return v;
}
Bytes32 h32(const char* s) {
    Bytes32 b{}; auto v = unhex(s);
    std::memcpy(b.data(), v.data(), 32); return b;
}

// Legacy (pre-V8) profile index whose table row equals the stored params, or
// INT32_MIN if none does.
int32_t legacy_profile_from_params(int32_t scale, int32_t steps, int32_t k, int32_t margin) {
    int32_t found = INT32_MIN, hits = 0;
    for (int32_t i = 0; i < CASERT_PROFILE_COUNT_LEGACY; ++i) {
        const auto& p = CASERT_PROFILES_LEGACY[i];
        if (p.scale == scale && p.steps == steps && p.k == k && p.margin == margin) {
            found = i + CASERT_H_MIN_LEGACY; ++hits;
        }
    }
    return hits == 1 ? found : INT32_MIN;
}

ConsensusParams params_for(int64_t h, int32_t pi) {
    ConsensusParams base = get_consensus_params(Profile::MAINNET, h);
    CasertDecision d; d.profile_index = pi;
    return casert_apply_profile(base, d, h);
}

// Phase 4 + 5 of verify_cx_proof, reproduced: the commit binding needs no
// transcript.
Bytes32 recompute_commit(const EarlyBlock& b, const uint8_t* hc, int32_t pi, Bytes32& seed_out) {
    Bytes32 prev = h32(b.prev);
    Bytes32 bk = compute_block_key(prev);
    std::vector<uint8_t> sbuf; append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, hc, 72); append(sbuf, bk);
    append_u32_le(sbuf, b.nonce); append_u32_le(sbuf, b.extra);
    seed_out = sha256(sbuf);
    auto xb = unhex(b.x_bytes);
    std::vector<uint8_t> cbuf; append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, hc, 72); append(cbuf, seed_out); append(cbuf, h32(b.final_state));
    append(cbuf, xb.data(), xb.size());
    append(cbuf, h32(b.cp_root)); append(cbuf, h32(b.seg_root));
    append_u64_le(cbuf, b.metric);
    cbuf.push_back((uint8_t)(int8_t)pi);
    return sha256(cbuf);
}

} // namespace

namespace {
void check_block(const EarlyBlock& b) {
    const std::string tag = "h=" + std::to_string(b.height) + " ";
    uint8_t hc[72] = {0};
    Bytes32 prev = h32(b.prev), merk = h32(b.merkle);
    std::memcpy(hc, prev.data(), 32); std::memcpy(hc + 32, merk.data(), 32);
    write_u32_le(hc + 64, b.ts); write_u32_le(hc + 68, b.bits_q);

    const int32_t pi = legacy_profile_from_params(b.scale, b.steps, b.k, b.margin);
    check(pi != INT32_MIN, tag + "stored stab_* params select exactly one legacy profile (pi=" + std::to_string(pi) + ")");
    if (pi == INT32_MIN) return;
    ConsensusParams p = params_for(b.height, pi);
    check(p.stab_lr_shift == b.lr_shift, tag + "stab_lr_shift matches the consensus value");

    // (1) The transcript is gone: the full verifier cannot accept this block.
    auto xb = unhex(b.x_bytes);
    bool v = verify_cx_proof(hc, b.nonce, b.extra, h32(b.commit), h32(b.cp_root),
                             h32(b.seg_root), h32(b.final_state), xb.data(), xb.size(),
                             b.metric, /*checkpoint_leaves=*/{}, /*segment_proofs=*/{},
                             /*round_witnesses=*/{}, p, b.height);
    check(!v, tag + "verify_cx_proof rejects the block (no Transcript V2 data persisted) — the --full-verify failure");

    // (2a) Commit binding with the profile the miner used.
    Bytes32 seed{};
    check(recompute_commit(b, hc, pi, seed) == h32(b.commit),
          tag + "commit binds with the profile derived from stab_* (pi=" + std::to_string(pi) + ")");

    // (3) The node's pre-V3 fallback (assume B0) only fits B0 blocks.
    Bytes32 seed_b0{};
    bool b0_binds = recompute_commit(b, hc, 0, seed_b0) == h32(b.commit);
    check(b0_binds == (pi == 0), tag + (pi == 0 ? "B0 fallback binds (block is B0)"
                                                : "B0 fallback does NOT bind (block is not B0)"));

    // (2b) Stability basin + metric (Phases 9-10) need no transcript either.
    int32_t x[32];
    for (int i = 0; i < p.cx_n; ++i) x[i] = read_i32_le(xb.data() + i * 4);
    CXProblem prob = derive_M_and_b(compute_block_key(prev), p.cx_n, p.cx_lam);
    Bytes32 stctx = stability_ctx(hc, seed, h32(b.cp_root));
    uint64_t metric = 0;
    bool basin = verify_stability_basin(x, prob, p.cx_n, p.cx_lr_shift, stctx,
                                        p.stab_scale, p.stab_k, p.stab_margin, p.stab_steps,
                                        p.stab_lr_shift, metric);
    check(basin && metric == b.metric, tag + "stability basin holds and metric matches (" + std::to_string(metric) + ")");

    // (4) The node-side helpers used by --full-verify.
    const int32_t lib_pi = derive_profile_from_stab_params(b.height, b.scale, b.steps, b.k, b.margin);
    check(lib_pi == pi, tag + "derive_profile_from_stab_params = " + profile_name(lib_pi) + " (reference " + profile_name(pi) + ")");
    ++g_profile_hist[lib_pi];
    std::string why;
    bool lib_ok = verify_cx_without_transcript(hc, b.nonce, b.extra, h32(b.commit), h32(b.cp_root),
                                               h32(b.seg_root), h32(b.final_state), xb.data(), xb.size(),
                                               b.metric, p, &why);
    check(lib_ok, tag + "verify_cx_without_transcript passes with the derived profile" + (why.empty() ? "" : " [" + why + "]"));
    if (pi != 0) {
        why.clear();
        bool b0_ok = verify_cx_without_transcript(hc, b.nonce, b.extra, h32(b.commit), h32(b.cp_root),
                                                  h32(b.seg_root), h32(b.final_state), xb.data(), xb.size(),
                                                  b.metric, params_for(b.height, 0), &why);
        check(!b0_ok && why.rfind("phase 5", 0) == 0,
              tag + "verify_cx_without_transcript rejects the old B0 default at phase 5 (" + why + ")");
    }
    // Tampering with any committed field must fail.
    Bytes32 bad_fs = h32(b.final_state); bad_fs[0] ^= 1;
    why.clear();
    bool tampered_ok = verify_cx_without_transcript(hc, b.nonce, b.extra, h32(b.commit), h32(b.cp_root),
                                                    h32(b.seg_root), bad_fs, xb.data(), xb.size(),
                                                    b.metric, p, &why);
    check(!tampered_ok && why.rfind("phase 5", 0) == 0, tag + "tampered final_state is rejected (" + why + ")");
    why.clear();
    bool short_ok = verify_cx_without_transcript(hc, b.nonce, b.extra, h32(b.commit), h32(b.cp_root),
                                                 h32(b.seg_root), h32(b.final_state), xb.data(), xb.size() - 4,
                                                 b.metric, p, &why);
    check(!short_ok && why.rfind("phase 1", 0) == 0, tag + "short x_bytes is rejected at phase 1 (" + why + ")");
}

// Profile derivation on its own: every row of both cASERT tables round-trips
// through casert_apply_profile at a height that uses that table, and
// parameters that match no row fail closed.
void check_derivation_tables() {
    for (int64_t h : {int64_t(1), int64_t(3300), int64_t(CASERT_CEILING_H13_HEIGHT - 1)}) {
        int ok = 0;
        for (int32_t pi = CASERT_H_MIN_LEGACY; pi < CASERT_H_MIN_LEGACY + CASERT_PROFILE_COUNT_LEGACY; ++pi) {
            ConsensusParams p = params_for(h, pi);
            ok += derive_profile_from_stab_params(h, p.stab_scale, p.stab_steps, p.stab_k, p.stab_margin) == pi;
        }
        check(ok == CASERT_PROFILE_COUNT_LEGACY, "legacy table round-trips at h=" + std::to_string(h)
              + " (" + std::to_string(ok) + "/" + std::to_string(CASERT_PROFILE_COUNT_LEGACY) + ")");
    }
    {
        const int64_t h = CASERT_CEILING_H13_HEIGHT;
        int ok = 0;
        for (int32_t pi = CASERT_H_MIN; pi < CASERT_H_MIN + CASERT_PROFILE_COUNT; ++pi) {
            ConsensusParams p = params_for(h, pi);
            ok += derive_profile_from_stab_params(h, p.stab_scale, p.stab_steps, p.stab_k, p.stab_margin) == pi;
        }
        check(ok == CASERT_PROFILE_COUNT, "V8 table round-trips at h=" + std::to_string(h)
              + " (" + std::to_string(ok) + "/" + std::to_string(CASERT_PROFILE_COUNT) + ")");
    }
    check(derive_profile_from_stab_params(1, 1, 4, 4, 186) == INT32_MIN, "no matching row -> INT32_MIN (fail closed)");
    check(derive_profile_from_stab_params(1, 0, 0, 0, 0) == INT32_MIN, "zeroed/absent stab_* -> INT32_MIN (fail closed)");
    check(derive_profile_from_stab_params(1, -1, -1, -1, -1) == INT32_MIN, "jint() missing-field value -1 -> INT32_MIN (fail closed)");
    check(profile_name(-4) == "E4" && profile_name(0) == "B0" && profile_name(2) == "H2", "profile names E4/B0/H2");
}

void check_classification_rule() {
    check(full_verify_historical_rule_applies(Profile::MAINNET, 1, true), "mainnet h=1 + opt-in -> historical rule applies");
    check(full_verify_historical_rule_applies(Profile::MAINNET, 3300, true), "mainnet h=3300 + opt-in -> historical rule applies");
    check(!full_verify_historical_rule_applies(Profile::MAINNET, 3301, true), "mainnet h=3301 -> no historical rule (transcripts exist from here)");
    check(!full_verify_historical_rule_applies(Profile::MAINNET, 1, false), "plain --full-verify -> no historical rule (UNVERIFIABLE)");
    check(!full_verify_historical_rule_applies(Profile::MAINNET, 0, true), "genesis is never covered");
    check(!full_verify_historical_rule_applies(Profile::TESTNET, 1, true), "testnet -> no historical rule");
    check(!full_verify_historical_rule_applies(Profile::DEV, 1, true), "dev -> no historical rule");
    check(std::string(full_verify_class_name(FullVerifyClass::VERIFIED)) == "VERIFIED"
          && std::string(full_verify_class_name(FullVerifyClass::ASSUMED_FROM_HISTORICAL_RULE)) == "ASSUMED_FROM_HISTORICAL_RULE"
          && std::string(full_verify_class_name(FullVerifyClass::UNVERIFIABLE_MISSING_HISTORICAL_DATA)) == "UNVERIFIABLE_MISSING_HISTORICAL_DATA",
          "classification names");
}

void print_profile_hist() {
    std::string s;
    for (const auto& kv : g_profile_hist)
        s += " " + profile_name(kv.first) + "=" + std::to_string(kv.second);
    std::printf("derived profiles:%s\n", s.c_str());
}
} // namespace

// Optional argv[1]: a whitespace-separated dump of the whole window, one block
// per line, same field order as EarlyBlock (scripts/verification/
// full_verify_early_chain.sh writes it from a chain.json copy). Without it the
// embedded real blocks are checked.
int main(int argc, char** argv) {
    // Sets ACTIVE_PROFILE (and therefore the MAINNET magic) before any hashing.
    (void)get_consensus_params(Profile::MAINNET, 1);

    if (argc > 1) {
        g_quiet = true;
        std::ifstream in(argv[1]);
        if (!in) { std::printf("cannot open %s\n", argv[1]); return 2; }
        std::string line; long n = 0;
        while (std::getline(in, line)) {
            std::istringstream is(line);
            EarlyBlock b{}; std::string prev, merk, com, cp, seg, fs, xb;
            if (!(is >> b.height >> prev >> merk >> b.ts >> b.bits_q >> b.nonce >> b.extra
                     >> com >> cp >> seg >> fs >> xb >> b.metric
                     >> b.scale >> b.k >> b.margin >> b.steps >> b.lr_shift)) continue;
            b.prev = prev.c_str(); b.merkle = merk.c_str(); b.commit = com.c_str();
            b.cp_root = cp.c_str(); b.seg_root = seg.c_str(); b.final_state = fs.c_str();
            b.x_bytes = xb.c_str();
            check_block(b); ++n;
        }
        print_profile_hist();
        std::printf("\n=== full-verify early chain (file): %ld blocks, %d checks, %d failure%s ===\n",
                    n, g_checks, g_fail, g_fail == 1 ? "" : "s");
        return (g_fail || n == 0) ? 1 : 0;
    }

    for (const auto& b : kBlocks) check_block(b);
    check_derivation_tables();
    check_classification_rule();
    print_profile_hist();
    {
        // The embedded fixture must cover every profile class used in 1..3300.
        bool all = g_profile_hist.count(0) && g_profile_hist.count(-1) && g_profile_hist.count(1)
                && g_profile_hist.count(2) && g_profile_hist.count(-4);
        check(all, "fixture covers B0, E1, H1, H2 and E4");
    }

    std::printf("\n=== full-verify early chain: %s (%d failure%s) ===\n",
                g_fail ? "FAIL" : "PASS", g_fail, g_fail == 1 ? "" : "s");
    return g_fail ? 1 : 0;
}
