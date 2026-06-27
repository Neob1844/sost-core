// =============================================================================
// cx_reverify.cpp — INDEPENDENT ConvergenceX PoW re-verifier (forensic tool).
//
// For each block (read from stdin, one per line), this recomputes the FULL CX
// proof from scratch — 4GB dataset + 4GB scratchpad + 100k sequential rounds via
// convergencex_attempt() (the PROVER, not the node's 12-round verifier spot-check)
// — and compares the recomputed commit / roots / final_state / stability_metric
// against the values the block claims. If a block's claimed commit can be
// reproduced by actually doing the work, the work was genuinely done (the commit
// cryptographically binds all 100k rounds). If a miner submitted a valid-looking
// transcript WITHOUT doing the work, the recomputed commit will NOT match.
//
// This is independent of the node's block-ACCEPTANCE path (no verify_cx_proof,
// no chain state) — it re-derives the answer by brute computation. It cannot, by
// design, detect a flaw in the ConvergenceX math shared by prover+verifier (that
// is a separate cryptanalysis question); it conclusively tests the "claimed work
// not actually done" exploit class.
//
// Read-only. Touches no chain, no consensus, no funds.
//
// stdin line (whitespace-separated):
//   label height prev_hash merkle_root timestamp bits_q nonce extra_nonce \
//   profile_index stab_scale stab_k stab_margin stab_steps stab_lr_shift \
//   exp_commit exp_checkpoints_root exp_segments_root exp_final_state exp_stability_metric
// =============================================================================
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/emission.h"
#include "sost/crypto.h"
#include "sost/types.h"
#include "sost/params.h"
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <string>
#include <sstream>
#include <iostream>

using namespace sost;

static Bytes32 hex32(const std::string& h) {
    Bytes32 b{};
    for (int i = 0; i < 32 && (size_t)(i*2+1) < h.size(); ++i)
        b[i] = (uint8_t)std::stoul(h.substr(i*2, 2), nullptr, 16);
    return b;
}
static std::string tohex(const Bytes32& b) {
    static const char* hx = "0123456789abcdef";
    std::string s; s.reserve(64);
    for (uint8_t c : b) { s += hx[c>>4]; s += hx[c&15]; }
    return s;
}

int main() {
    // Scratchpad for epoch 0 (all current mainnet blocks: height < BLOCKS_PER_EPOCH).
    // Built once and reused across all blocks (epoch_scratch_key(0) is constant).
    //
    // ORDER IS CONSENSUS-CRITICAL: get_consensus_params() sets the global
    // ACTIVE_PROFILE, which selects the per-network MAGIC bytes used by
    // append_magic() inside epoch_scratch_key()/compute_single_scratch_block().
    // ACTIVE_PROFILE defaults to Profile::DEV, so deriving the scratch key
    // BEFORE this call would build the scratchpad with the DEV magic and
    // produce a different (wrong) scratchpad than the MAINNET miner used,
    // corrupting m0..m3 mixing and hence final_state/commit. The miner calls
    // get_consensus_params() (line ~1189) before epoch_scratch_key() (~1235);
    // we must mirror that ordering.
    ConsensusParams base = get_consensus_params(Profile::MAINNET, 0);
    Bytes32 skey0 = epoch_scratch_key(0, nullptr);
    fprintf(stderr, "[cx_reverify] epoch-0 scratch_key = %s\n", tohex(skey0).c_str());
    fprintf(stderr, "[cx_reverify] core params: cx_n=%d cx_rounds=%d cx_scratch_mb=%d cx_lr_shift=%d cx_lam=%d cx_cp=%d\n",
            base.cx_n, base.cx_rounds, base.cx_scratch_mb, base.cx_lr_shift, base.cx_lam, base.cx_checkpoint_interval);
    fprintf(stderr, "[cx_reverify] building epoch-0 scratchpad (%d MB)...\n", base.cx_scratch_mb);
    std::vector<uint8_t> scratch = build_scratchpad(skey0, base.cx_scratch_mb);
    fprintf(stderr, "[cx_reverify] scratchpad ready (%zu bytes). reading blocks from stdin...\n", scratch.size());

    int total = 0, match = 0, mismatch = 0;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        std::istringstream is(line);
        std::string label, prev_s, merk_s, exp_commit, exp_cp, exp_seg, exp_fs;
        long long height; long long ts, bq; unsigned long long nonce, extra, metric;
        int pi, ss, sk, sm, sst, slr;
        if (!(is >> label >> height >> prev_s >> merk_s >> ts >> bq >> nonce >> extra
                 >> pi >> ss >> sk >> sm >> sst >> slr
                 >> exp_commit >> exp_cp >> exp_seg >> exp_fs >> metric)) {
            fprintf(stderr, "[cx_reverify] skip malformed line\n"); continue;
        }
        int32_t epoch = (int32_t)((long long)height / BLOCKS_PER_EPOCH);
        if (epoch != 0) { fprintf(stderr, "[cx_reverify] WARN h=%lld epoch=%d != 0 (scratch may differ)\n", height, epoch); }

        uint8_t hc[HEADER_CORE_LEN] = {0};
        Bytes32 prev = hex32(prev_s), merk = hex32(merk_s);
        std::memcpy(hc,      prev.data(), 32);
        std::memcpy(hc + 32, merk.data(), 32);
        uint32_t ts32 = (uint32_t)ts, bq32 = (uint32_t)bq;
        hc[64]=(uint8_t)ts32; hc[65]=(uint8_t)(ts32>>8); hc[66]=(uint8_t)(ts32>>16); hc[67]=(uint8_t)(ts32>>24);
        hc[68]=(uint8_t)bq32; hc[69]=(uint8_t)(bq32>>8); hc[70]=(uint8_t)(bq32>>16); hc[71]=(uint8_t)(bq32>>24);

        Bytes32 bk = compute_block_key(prev);
        ConsensusParams p = base;
        p.stab_scale = ss; p.stab_k = sk; p.stab_margin = sm; p.stab_steps = sst; p.stab_lr_shift = slr;
        p.stab_profile_index = pi;

        CXAttemptResult r = convergencex_attempt(scratch.data(), scratch.size(), bk,
                                                 (uint32_t)nonce, (uint32_t)extra, p, hc, epoch, (int64_t)height);
        std::string got = tohex(r.commit);
        bool ok = (got == exp_commit);
        bool cp_ok  = (tohex(r.checkpoints_root) == exp_cp);
        bool seg_ok = (tohex(r.segments_root)    == exp_seg);
        bool fs_ok  = (tohex(r.final_state)      == exp_fs);
        bool mt_ok  = (r.stability_metric == metric);
        ++total; if (ok) ++match; else ++mismatch;
        printf("%-6s h=%-6lld  commit %s  (cp:%s seg:%s final:%s metric:%s)  pi=%d\n",
               label.c_str(), height, ok?"MATCH ✓":"MISMATCH ✗",
               cp_ok?"ok":"X", seg_ok?"ok":"X", fs_ok?"ok":"X", mt_ok?"ok":"X", pi);
        if (!ok) printf("        expected %s\n        recompute %s\n", exp_commit.c_str(), got.c_str());
        fflush(stdout);
    }
    printf("\n=== cx_reverify: %d blocks, %d MATCH, %d MISMATCH ===\n", total, match, mismatch);
    return mismatch ? 2 : 0;
}
