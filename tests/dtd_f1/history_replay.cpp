// DTD-F1 history replay: recompute every historical normal-DTD draw and every historical
// jackpot draw from a read-only chain extract with the LINKED lottery library, and compare
// the winner with the on-chain payout.
//
// Built twice and diffed (docs/v40000/DTD_F1_SEED_POW_COMMIT.md, "History"):
//   * against the PRODUCTION library (origin/main headers + libsost-core.a), -DDTD_F1_LEGACY_LIB
//   * against the V17 DTD-F1 library (this branch). Here every block also carries its REAL
//     PoW commit (pow_commit) when the extract has it, so the replay proves that no draw below
//     V17_HEIGHT reads it.
// The seed printed per draw is sha256 of the preimage the library hashes: from
// lottery_seed_from_history() for the new library, from the legacy formula for the old one
// (the old library does not expose it); the winners come from the library in both builds.
//
// Input: CSV files with the dtd-audit columns (height,block_id,prev,miner_pkh,lottery_pkh,
// lottery_amount,jackpot_pkh,jackpot_amount,...[,commit]); later files only add heights not
// already present and must agree (block_id) on overlaps.
// Output: one line per draw: "D h E seed winner onchain OK|MISMATCH", "J15 ...", "J2 ...".
#include "sost/lottery.h"
#include "sost/jackpot_v2.h"
#include "sost/params.h"
#include "sost/crypto.h"
#include "sost/serialize.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::lottery;

static std::vector<uint8_t> unhex(const std::string& s) { std::vector<uint8_t> o(s.size() / 2); for (size_t i = 0; i < o.size(); ++i) o[i] = (uint8_t)std::stoi(s.substr(2 * i, 2), nullptr, 16); return o; }
static std::string hx(const uint8_t* p, size_t n) { static const char* d = "0123456789abcdef"; std::string s; for (size_t i = 0; i < n; ++i) { s += d[p[i] >> 4]; s += d[p[i] & 15]; } return s; }

struct Row { int64_t h; std::string id, miner, lot, jp, commit; };

int main(int argc, char** argv) {
    if (argc < 2) { std::fprintf(stderr, "usage: history_replay a.csv [b.csv ...]\n"); return 2; }
    ACTIVE_PROFILE = Profile::MAINNET;
    std::map<int64_t, Row> rows;
    for (int f = 1; f < argc; ++f) {
        std::ifstream in(argv[f]); std::string line; std::getline(in, line); if (!line.empty() && line.back() == '\r') line.pop_back();
        std::vector<std::string> hdr; { std::stringstream ss(line); std::string c; while (std::getline(ss, c, ',')) hdr.push_back(c); }
        int ci = -1; for (size_t i = 0; i < hdr.size(); ++i) if (hdr[i] == "commit") ci = (int)i;
        while (std::getline(in, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            std::vector<std::string> c; std::stringstream ss(line); std::string x; while (std::getline(ss, x, ',')) c.push_back(x);
            while (c.size() < hdr.size()) c.push_back("");
            Row r{std::stoll(c[0]), c[1], c[3], c[4], c[6], ci >= 0 ? c[(size_t)ci] : ""};
            auto it = rows.find(r.h);
            if (it != rows.end()) { if (it->second.id != r.id) { std::fprintf(stderr, "overlap mismatch at %lld\n", (long long)r.h); return 3; } continue; }
            rows[r.h] = r;
        }
    }
    const int64_t tip = rows.rbegin()->first;
    for (int64_t h = 0; h <= tip; ++h) if (!rows.count(h)) { std::fprintf(stderr, "gap at %lld\n", (long long)h); return 4; }
    std::vector<LotteryMinedBlockView> hist; hist.reserve((size_t)tip + 1);
    size_t with_commit = 0;
    for (auto& kv : rows) {
        const Row& r = kv.second; if (r.miner.size() != 40) continue;     // node skips blocks without a coinbase pkh
        LotteryMinedBlockView v; v.height = r.h;
        auto p = unhex(r.miner); std::memcpy(v.miner_pkh.data(), p.data(), 20);
        auto b = unhex(r.id); std::memcpy(v.block_hash.data(), b.data(), 32);
#ifndef DTD_F1_LEGACY_LIB
        if (r.commit.size() == 64) { auto c = unhex(r.commit); std::memcpy(v.pow_commit.data(), c.data(), 32); ++with_commit; }
#endif
        hist.push_back(v);
    }
    std::fprintf(stderr, "blocks 0..%lld, %zu with miner pkh, %zu with real pow_commit\n", (long long)tip, hist.size(), with_commit);
    std::vector<LotteryMinedBlockView> view; view.reserve(hist.size());
    size_t hi = 0, draws = 0, ok = 0, bad = 0, j15 = 0, j15ok = 0;
    for (int64_t h = V11_PHASE2_HEIGHT; h <= tip; ++h) {
        while (hi < hist.size() && hist[hi].height < h) view.push_back(hist[hi++]);
        if (!is_lottery_block(h, V11_PHASE2_HEIGHT)) continue;
        auto el = compute_lottery_eligibility_set(view, h, PubKeyHash{}, lottery_exclusion_window_at(h));
        const int64_t wi = select_lottery_winner_index_from_history(el, view, h);
#ifdef DTD_F1_LEGACY_LIB
        std::vector<uint8_t> pre(LOTTERY_RNG_DOMAIN, LOTTERY_RNG_DOMAIN + LOTTERY_RNG_DOMAIN_LEN);
        for (size_t k = view.size() >= 16 ? view.size() - 16 : 0; k < view.size(); ++k) if (view[k].height >= h - 16) append(pre, view[k].block_hash);
        append_u64_le(pre, (uint64_t)h);
        const Bytes32 seed = sha256(pre);
#else
        const Bytes32 seed = lottery_seed_from_history(view, h);
#endif
        const std::string win = wi >= 0 ? hx(el[(size_t)wi].pkh.data(), 20) : "-";
        const std::string got = rows[h].lot.empty() ? "-" : rows[h].lot;
        ++draws; const bool m = (win == got); m ? ++ok : ++bad;
        std::printf("D %lld %zu %s %s %s %s\n", (long long)h, el.size(), hx(seed.data(), 32).c_str(), win.c_str(), got.c_str(), m ? "OK" : "MISMATCH");
        if (is_hist_jackpot_height(h) && h < HIST_JACKPOT_V2_HEIGHT) {   // V15: jackpot winner == DTD winner at the jackpot height
            const std::string jg = rows[h].jp.empty() ? "-" : rows[h].jp; ++j15; if (jg == win) ++j15ok;
            std::printf("J15 %lld %s %s %s\n", (long long)h, win.c_str(), jg.c_str(), jg == win ? "OK" : "MISMATCH");
        }
        if (is_hist_jackpot_v2_height(h)) {   // V2: seed over the same window (eligibility needs node state: payout compared only)
            std::vector<Bytes32> ids, commits;
#ifdef DTD_F1_LEGACY_LIB
            for (const auto& v : view) if (v.height >= h - 16) ids.push_back(v.block_hash);
            const Bytes32 js = jackpot_v2::jv2_seed(ids, h);
#else
            for (const auto& v : view) if (v.height >= h - 16) { ids.push_back(v.block_hash); commits.push_back(v.pow_commit); }
            const Bytes32 js = jackpot_v2::jv2_seed_at(ids, commits, h);
#endif
            std::printf("J2 %lld seed %s onchain_payout %s\n", (long long)h, hx(js.data(), 32).c_str(), rows[h].jp.empty() ? "none" : rows[h].jp.c_str());
        }
    }
    std::fprintf(stderr, "draws=%zu match=%zu mismatch=%zu v15_jackpots=%zu match=%zu\n", draws, ok, bad, j15, j15ok);
    return bad ? 1 : 0;
}
