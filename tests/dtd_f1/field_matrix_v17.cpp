// DTD-F1 per-field grinding matrix from a REAL mainnet state, pre-V17 rule vs V17 rule,
// against the linked consensus library (libsost-core of this branch).
//
// Usage: field_matrix_v17 <hdr_30428.txt> <hdr_30428_cx.txt> <blocks.csv>... --ctx D --n N
//   hdr files: real block #30428 header + CX transcript summary (dtd-audit/data)
//   blocks.csv: dtd-audit column layout with a trailing `commit` column (real commits)
//
// Block #30428 plays "block h-1". For every miner-controllable field N variants are built;
// each variant's commit is recomputed with the verify_cx_proof phase 4/5 formula
// (convergencex.cpp, Phase 4 seed + Phase 5 commit) and its block_id with the header layout of
// sost-node.cpp build_full_header_bytes + compute_block_id. The variant (id, commit) is then
// substituted for block D-1 in the real context of draw D:
//   V11 rule: the real draw at D (pre-V17) with the real eligible set (D = 30712: E = 69)
//   V17 rule: the same history relabelled by +OFFSET so the draw is at D+OFFSET >= V17_HEIGHT;
//             the eligible set is recomputed by the library at the relabelled height.
// Columns:
//   COMMIT_CHG   commit differs from the real PoW commit -> the old PoW no longer applies; a
//                new full ConvergenceX solution meeting the target is required (REQUIRES_NEW_POW)
//   SIG_OK       the original SbPoW signature still verifies (v13 message) / for the signature
//                row: validate_sbpow_for_block accepts the re-signed header
//   ID_CHG       block_id differs
//   V11_SEED/V11_WIN  pre-V17 DTD seed / winner at D changed
//   V17_SEED/V17_WIN  V17 DTD seed / winner at D+OFFSET changed
//   V17_JP       V17 Jackpot seed at D+OFFSET changed
#include "sost/lottery.h"
#include "sost/jackpot_v2.h"
#include "sost/sbpow.h"
#include "sost/sostcompact.h"
#include "sost/pow/convergencex.h"
#include "sost/serialize.h"
#include "sost/crypto.h"
#include "sost/params.h"
#include <secp256k1.h>
#include <secp256k1_extrakeys.h>
#include <secp256k1_schnorrsig.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace sost;
static std::vector<uint8_t> unhex(const std::string& s) { std::vector<uint8_t> o(s.size() / 2); for (size_t i = 0; i < o.size(); ++i) o[i] = (uint8_t)std::stoi(s.substr(2 * i, 2), nullptr, 16); return o; }
static Bytes32 b32(const std::string& s) { Bytes32 b{}; auto v = unhex(s); std::memcpy(b.data(), v.data(), 32); return b; }

struct Hdr { Bytes32 prev, mrkl, croot; uint32_t ts, bits, nonce, extra, ver; int8_t pi; sbpow::MinerPubkey pk; sbpow::MinerSignature sig; };
static std::vector<uint8_t> fstate, xbytes; static Bytes32 sroot; static uint64_t stb;
static void hc72_of(const Hdr& h, uint8_t out[72]) { std::memcpy(out, h.prev.data(), 32); std::memcpy(out + 32, h.mrkl.data(), 32); write_u32_le(out + 64, h.ts); write_u32_le(out + 68, h.bits); }
static Bytes32 commit_of(const Hdr& h) {
    uint8_t hc[72]; hc72_of(h, hc);
    std::vector<uint8_t> s; append_magic(s); append(s, "SEED", 4); append(s, hc, 72); append(s, compute_block_key(h.prev));
    append_u32_le(s, h.nonce); append_u32_le(s, h.extra); Bytes32 seed = sha256(s);
    std::vector<uint8_t> c; append_magic(c); append(c, "COMMIT", 6); append(c, hc, 72); append(c, seed);
    c.insert(c.end(), fstate.begin(), fstate.end()); c.insert(c.end(), xbytes.begin(), xbytes.end());
    append(c, h.croot); append(c, sroot); append_u64_le(c, stb); c.push_back((uint8_t)h.pi);
    return sha256(c);
}
static Bytes32 id_of(const Hdr& h, const Bytes32& commit) {
    uint8_t hc[72]; hc72_of(h, hc);
    std::vector<uint8_t> b; append_magic(b); append(b, "HDR2", 4); append(b, hc, 72); append(b, h.croot);
    append_u32_le(b, h.nonce); append_u32_le(b, h.extra); append_u32_le(b, h.ver);
    b.insert(b.end(), h.pk.begin(), h.pk.end()); b.insert(b.end(), h.sig.begin(), h.sig.end());
    return compute_block_id(b.data(), b.size(), commit);
}

int main(int argc, char** argv) {
    ACTIVE_PROFILE = Profile::MAINNET;
    std::map<std::string, std::string> H; std::vector<std::string> csvs; int64_t D = 30712; int N = 2000;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--ctx") D = std::stoll(argv[++i]); else if (a == "--n") N = std::stoi(argv[++i]);
        else if (a.find("hdr_") != std::string::npos) { std::ifstream in(a); std::string k, v; while (in >> k >> v) H[k] = v; }
        else csvs.push_back(a);
    }
    Hdr h0{}; h0.prev = b32(H["prev_hash"]); h0.mrkl = b32(H["merkle_root"]); h0.croot = b32(H["checkpoints_root"]);
    h0.ts = std::stoul(H["timestamp"]); h0.bits = std::stoul(H["bits_q"]); h0.nonce = std::stoul(H["nonce"]); h0.extra = std::stoul(H["extra_nonce"]);
    h0.ver = std::stoul(H["version"]); h0.pi = (int8_t)std::stoi(H["profile_index"]);
    { auto v = unhex(H["miner_pubkey"]); std::memcpy(h0.pk.data(), v.data(), 33); }
    { auto v = unhex(H["miner_signature"]); std::memcpy(h0.sig.data(), v.data(), 64); }
    fstate = unhex(H["final_state"]); xbytes = unhex(H["x_bytes"]); sroot = b32(H["segments_root"]); stb = std::stoull(H["stability_metric"]);
    const Bytes32 genesis = b32(H["genesis"]), real_commit = b32(H["commit"]), real_id = b32(H["block_id"]);
    const int64_t HB = std::stoll(H["height"]);
    const Bytes32 c0 = commit_of(h0);
    std::printf("fidelity: block #%lld commit recomputed %s on-chain, block_id recomputed %s on-chain, pow_meets_target(real)=%d\n",
                (long long)HB, c0 == real_commit ? "==" : "!=", id_of(h0, c0) == real_id ? "==" : "!=", (int)pow_meets_target(real_commit, h0.bits));

    // history < D with real ids + commits
    std::map<int64_t, lottery::LotteryMinedBlockView> rows; size_t with_commit = 0;
    for (auto& f : csvs) {
        std::ifstream in(f); std::string line; std::getline(in, line); if (!line.empty() && line.back() == '\r') line.pop_back();
        int ci = -1; { std::stringstream ss(line); std::string c; int k = 0; while (std::getline(ss, c, ',')) { if (c == "commit") ci = k; ++k; } }
        while (std::getline(in, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            std::vector<std::string> c; std::stringstream ss(line); std::string x; while (std::getline(ss, x, ',')) c.push_back(x);
            int64_t hh = std::stoll(c[0]); if (hh >= D || rows.count(hh) || c[3].size() != 40) continue;
            lottery::LotteryMinedBlockView v; v.height = hh; auto p = unhex(c[3]); std::memcpy(v.miner_pkh.data(), p.data(), 20);
            v.block_hash = b32(c[1]);
            if (ci >= 0 && (int)c.size() > ci && c[(size_t)ci].size() == 64) { v.pow_commit = b32(c[(size_t)ci]); if (hh >= D - 16) ++with_commit; }
            rows[hh] = v;
        }
    }
    std::vector<lottery::LotteryMinedBlockView> ctx; for (auto& kv : rows) ctx.push_back(kv.second);
    const int64_t OFF = (V17_HEIGHT + 1000) - D + 0;   // relabel so the draw is well inside V17
    std::vector<lottery::LotteryMinedBlockView> ctx17 = ctx; for (auto& v : ctx17) v.height += OFF;
    const int64_t D17 = D + OFF;
    std::printf("context: draw #%lld (V11 rule) and relabelled #%lld (rule %s); window commits present %zu/16\n",
                (long long)D, (long long)D17, lottery::lottery_seed_uses_pow_commit(D17) ? "V17" : "V11", with_commit);
    if (with_commit != 16) { std::printf("missing real commits for the window\n"); return 2; }
    size_t last = ctx.size() - 1;
    auto el = lottery::compute_lottery_eligibility_set(ctx, D, PubKeyHash{}, lottery_exclusion_window_at(D));
    auto el17 = lottery::compute_lottery_eligibility_set(ctx17, D17, PubKeyHash{}, lottery_exclusion_window_at(D17));
    const int64_t w0 = lottery::select_lottery_winner_index_from_history(el, ctx, D);
    const int64_t w17 = lottery::select_lottery_winner_index_from_history(el17, ctx17, D17);
    auto jseed17 = [&](const std::vector<lottery::LotteryMinedBlockView>& hv) {
        std::vector<Bytes32> ids, cm; for (auto& v : hv) if (v.height >= D17 - 16) { ids.push_back(v.block_hash); cm.push_back(v.pow_commit); }
        return jackpot_v2::jv2_seed_at(ids, cm, D17); };
    std::printf("eligible: V11 E=%zu winner_idx=%lld | V17 E=%zu winner_idx=%lld\n\n", el.size(), (long long)w0, el17.size(), (long long)w17);

    secp256k1_context* sctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    sbpow::MinerPrivkey sk{}; for (int i = 0; i < 32; ++i) sk[i] = (uint8_t)(0x21 + i);
    secp256k1_keypair kp; if (!secp256k1_keypair_create(sctx, &kp, sk.data())) return 2;
    sbpow::MinerPubkey apk{}; sbpow::derive_compressed_pubkey_from_privkey(sk, apk);
    const PubKeyHash apkh = sbpow::derive_pkh_from_pubkey(apk);
    // The signature row needs a key we hold: the identity of h-1 is the test key (pkh bound to the
    // coinbase), the PoW commit c0 is the real one. The block_id baseline is that signed block.
    Hdr hs = h0; hs.pk = apk;
    const Bytes32 smsg = sbpow::build_sbpow_message_v13(genesis, hs.prev, HB, hs.ts, hs.bits, c0, hs.mrkl, hs.nonce, hs.extra, apk);
    sbpow::sign_sbpow_commitment(sk, smsg, hs.sig);

    struct Row { const char* field; std::function<Hdr(int)> mk; int kind; };   // kind 1 = re-sign
    std::vector<Row> rowsv = {
        {"nonce",              [&](int i){ Hdr x = h0; x.nonce += i + 1; return x; }, 0},
        {"extra_nonce",        [&](int i){ Hdr x = h0; x.extra += i + 1; return x; }, 0},
        {"timestamp",          [&](int i){ Hdr x = h0; x.ts += i + 1; return x; }, 0},
        {"tx order",           [&](int i){ Hdr x = h0; x.mrkl[(i * 7) % 32] ^= (uint8_t)(1 + i / 32); return x; }, 0},
        {"tx inclusion",       [&](int i){ Hdr x = h0; x.mrkl[(i * 11 + 3) % 32] ^= (uint8_t)(1 + i / 32); return x; }, 0},
        {"coinbase",           [&](int i){ Hdr x = h0; x.mrkl[(i * 13 + 5) % 32] ^= (uint8_t)(1 + i / 32); return x; }, 0},
        {"miner identity",     [&](int i){ Hdr x = h0; x.pk = apk; x.mrkl[i % 32] ^= (uint8_t)(1 + i / 32); return x; }, 0},
        {"NODE_BIND tx",       [&](int i){ Hdr x = h0; x.mrkl[(i * 17 + 9) % 32] ^= (uint8_t)(1 + i / 32); return x; }, 0},
        {"HEARTBEAT tx",       [&](int i){ Hdr x = h0; x.mrkl[(i * 19 + 1) % 32] ^= (uint8_t)(1 + i / 32); return x; }, 0},
        {"profile_index",      [&](int i){ Hdr x = h0; x.pi = (int8_t)(h0.pi - 1 - (i % 3)); return x; }, 0},
        {"signature (re-sign)",[&](int){ return hs; }, 1},
    };
    std::printf("%-20s %8s %8s %8s %9s %8s %9s %8s %8s | CHANGES_SEED REQUIRES_NEW_POW CAN_GRIND_FOR_FREE\n",
                "FIELD", "COMMIT", "SIG_OK", "ID_CHG", "V11_SEED", "V11_WIN", "V17_SEED", "V17_WIN", "V17_JP");
    for (auto& r : rowsv) {
        int cc = 0, sig_ok = 0, idc = 0, v11s = 0, v11w = 0, v17s = 0, v17w = 0, v17j = 0;
        const Bytes32 base_id = (r.kind == 1) ? id_of(hs, c0) : id_of(h0, c0);
        // Baseline of this row: the UNMODIFIED block h-1 (id base_id, real PoW commit c0) placed at D-1.
        auto a0 = ctx; a0[last].block_hash = base_id; a0[last].pow_commit = c0;
        auto b0 = ctx17; b0[last].block_hash = base_id; b0[last].pow_commit = c0;
        const Bytes32 bs0 = lottery::lottery_seed_from_history(a0, D), bs17 = lottery::lottery_seed_from_history(b0, D17), bj17 = jseed17(b0);
        const int64_t bw0 = lottery::select_lottery_winner_index_from_history(el, a0, D);
        const int64_t bw17 = lottery::select_lottery_winner_index_from_history(el17, b0, D17);
        for (int i = 0; i < N; ++i) {
            Hdr x = r.mk(i); Bytes32 c = commit_of(x);
            if (r.kind == 1) {
                uint8_t aux[32] = {0}; write_u32_le(aux, (uint32_t)i + 1); aux[31] = 0x77;
                secp256k1_schnorrsig_sign(sctx, x.sig.data(), smsg.data(), &kp, aux);
                sbpow::ValidationInputs vi; vi.header_version = 2; vi.prev_hash = x.prev; vi.height = HB; vi.commit = c;
                vi.nonce = x.nonce; vi.extra_nonce = x.extra; vi.miner_pubkey = x.pk; vi.miner_signature = x.sig; vi.coinbase_miner_pkh = apkh;
                vi.phase2_height = V11_PHASE2_HEIGHT; vi.v13_height = V13_HEIGHT; vi.timestamp = x.ts; vi.bits_q = x.bits;
                vi.merkle_root = x.mrkl; vi.genesis_hash = genesis;
                if (sbpow::validate_sbpow_for_block(vi) == sbpow::ValidationResult::OK) ++sig_ok;
            } else {
                Bytes32 m = sbpow::build_sbpow_message_v13(genesis, x.prev, HB, x.ts, x.bits, c, x.mrkl, x.nonce, x.extra, x.pk);
                if (sbpow::verify_sbpow_signature(x.pk, m, x.sig)) ++sig_ok;
            }
            if (c != c0) ++cc;
            const Bytes32 id = id_of(x, c); if (id != base_id) ++idc;
            auto a = ctx; a[last].block_hash = id; a[last].pow_commit = c;
            auto b = ctx17; b[last].block_hash = id; b[last].pow_commit = c;
            if (lottery::lottery_seed_from_history(a, D) != bs0) ++v11s;
            if (lottery::select_lottery_winner_index_from_history(el, a, D) != bw0) ++v11w;
            if (lottery::lottery_seed_from_history(b, D17) != bs17) ++v17s;
            if (lottery::select_lottery_winner_index_from_history(el17, b, D17) != bw17) ++v17w;
            if (jseed17(b) != bj17) ++v17j;
        }
        const bool seed = v17s > 0, pow = cc > 0;
        std::printf("%-20s %8d %8d %8d %9d %8d %9d %8d %8d | %-12s %-16s %s\n", r.field, cc, sig_ok, idc, v11s, v11w, v17s, v17w, v17j,
                    seed ? "YES" : "NO", pow ? "YES" : "NO", r.kind == 1 ? (seed ? "YES" : "NO_EFFECT") : "NO");
    }
    std::printf("\n(N=%d per row. Without a new PoW a changed commit fails pow/verify_cx_proof: the CX transcript seed binds\n"
                " hc72||nonce||extra and the challenges derive from the commit. SIG_OK=0 on the other rows: the v13 SbPoW\n"
                " message commits ts/bits/merkle/nonce/extra/commit/pubkey. Signature row: validate_sbpow_for_block OK count.)\n", N);
    secp256k1_context_destroy(sctx);
    return 0;
}
