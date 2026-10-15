// Bounded-complexity subsidy / cumulative emission: equality with the original algorithm.
//
// The block subsidy schedule is consensus. src/subsidy.cpp stops iterating epochs once the
// per-epoch subsidy is provably zero (pow_q(e) == 0 for every e >= 256). This test keeps a
// verbatim copy of the ORIGINAL (pre-hotfix) algorithm as the reference and checks that the
// shipped functions return exactly the same stocks:
//   * every height 0..400,000 (genesis through the first epoch transition and beyond);
//   * +-128 heights around EVERY epoch boundary 0..300 (all 82 paying epochs, the zero tail);
//   * 20,000 seeded random heights in [0, 300 epochs] and 300 log-uniform heights up to 1e9;
//   (SOST_SUBSIDY_LONG=1: +-512, 200,000 and 3,000, and the reference at 1e12 / 3e12 too)
//   * hostile heights 1e11, 1e12, 3e12, INT64_MAX: bounded time, same value as the zero tail
//     (the reference is evaluated at 1e11 here; at 1e12/3e12 only with SOST_SUBSIDY_LONG=1,
//     it takes seconds/minutes there — that is the defect being fixed).
// Plus the supply identity cum(h) == cum(h-1) + subsidy(h) on every checked height.
// V17 (#40,000) inputs: on every height checked against the reference, the 80/15/5 subsidy
// split, the V17 coinbase amounts (with fees) and the J accumulator transition computed from
// the shipped subsidy are identical to those computed from the reference subsidy; the J
// allocation summed over every block from V17_HEIGHT through the end of the emission schedule
// is identical too, and at hostile heights every V17 amount is 0.
#include <sost/subsidy.h>
#include <sost/v17_economics.h>

#include <algorithm>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <random>

namespace ref {  // ---- verbatim copy of the original src/subsidy.cpp algorithm ----
static constexpr int64_t  BLOCKS_PER_EPOCH = 131'553;
static constexpr uint64_t Q_DEN           = 10'000'000'000'000'000ULL;
static constexpr uint64_t Q_NUM           =  7'788'007'830'714'049ULL;
static constexpr int64_t  R0_STOCKS    = 785'100'863LL;
static inline uint64_t mul_q(uint64_t a, uint64_t b) {
    __int128 prod = ( __int128)a * ( __int128)b;
    prod /= ( __int128)Q_DEN;
    if (prod < 0) return 0;
    if (prod > ( __int128)std::numeric_limits<uint64_t>::max())
        return std::numeric_limits<uint64_t>::max();
    return (uint64_t)prod;
}
static inline uint64_t pow_q(uint64_t exp) {
    uint64_t result = Q_DEN;
    uint64_t base   = Q_NUM;
    while (exp > 0) {
        if (exp & 1ULL) result = mul_q(result, base);
        exp >>= 1ULL;
        if (exp) base = mul_q(base, base);
        else break;
    }
    return result;
}
static constexpr int64_t SUPPLY_CAP = 466'920'160'910'299LL;
static int64_t cumulative_emission(int64_t height) {
    if (height < 0) return 0;
    int64_t total = 0;
    int64_t h = 0;
    while (h <= height) {
        uint64_t epoch = (uint64_t)(h / BLOCKS_PER_EPOCH);
        uint64_t qpow = pow_q(epoch);
        __int128 r = (__int128)R0_STOCKS * (__int128)qpow;
        r /= (__int128)Q_DEN;
        int64_t sub = (r < 0) ? 0 : (int64_t)r;
        int64_t epoch_end = (int64_t)((epoch + 1) * BLOCKS_PER_EPOCH - 1);
        int64_t blocks_in_epoch = std::min(epoch_end, height) - h + 1;
        total += sub * blocks_in_epoch;
        if (total >= SUPPLY_CAP) return SUPPLY_CAP;
        h += blocks_in_epoch;
    }
    return total;
}
static int64_t subsidy(int64_t height) {
    if (height < 0) return 0;
    uint64_t epoch = (uint64_t)(height / BLOCKS_PER_EPOCH);
    uint64_t qpow = pow_q(epoch);
    __int128 r = ( __int128)R0_STOCKS * ( __int128)qpow;
    r /= ( __int128)Q_DEN;
    if (r < 0) return 0;
    if (r > ( __int128)std::numeric_limits<int64_t>::max())
        return std::numeric_limits<int64_t>::max();
    int64_t base_subsidy = (int64_t)r;
    int64_t emitted_before = cumulative_emission(height - 1);
    if (emitted_before >= SUPPLY_CAP) return 0;
    int64_t remaining = SUPPLY_CAP - emitted_before;
    if (base_subsidy > remaining) return remaining;
    return base_subsidy;
}
}  // namespace ref

static int g_fail = 0;
static uint64_t g_checked = 0;
static uint64_t g_v17_checked = 0;

// V17 inputs derived from the subsidy: split, coinbase amounts, J transition.
static bool v17_equal(int64_t h, int64_t s_new, int64_t s_ref) {
    const auto a = sost::v17::subsidy_split(s_new), b = sost::v17::subsidy_split(s_ref);
    if (a.ok != b.ok || a.subsidy != b.subsidy || a.miner_subsidy != b.miner_subsidy ||
        a.dtd_subsidy != b.dtd_subsidy || a.jackpot_j != b.jackpot_j) return false;
    if (a.ok && a.miner_subsidy + a.dtd_subsidy + a.jackpot_j != a.subsidy) return false;
    const int64_t fees = (h & 0xFFFF) * 1000;
    const auto ca = sost::v17::coinbase_amounts(s_new, fees), cb = sost::v17::coinbase_amounts(s_ref, fees);
    if (ca.ok != cb.ok || ca.miner_total != cb.miner_total || ca.dtd_subsidy != cb.dtd_subsidy ||
        ca.jackpot_j != cb.jackpot_j) return false;
    const int64_t jb = 1'000'000'000LL;
    const auto ta = sost::v17::j_transition(h, jb, s_new, 0), tb = sost::v17::j_transition(h, jb, s_ref, 0);
    if (ta.ok != tb.ok || ta.j_alloc != tb.j_alloc || ta.j_after != tb.j_after) return false;
    ++g_v17_checked;
    return true;
}

static void check_height(int64_t h, bool with_ref = true) {
    const int64_t s = sost::sost_subsidy_stocks(h);
    const int64_t c = sost::sost_cumulative_emission_stocks(h);
    if (with_ref) {
        const int64_t rs = ref::subsidy(h), rc = ref::cumulative_emission(h);
        if (!v17_equal(h, s, rs)) {
            if (g_fail < 20) std::printf("FAIL V17 split/coinbase/J mismatch at h=%" PRId64 "\n", h);
            ++g_fail;
        }
        if (s != rs || c != rc) {
            if (g_fail < 20)
                std::printf("FAIL h=%" PRId64 " subsidy new=%" PRId64 " ref=%" PRId64
                            " cum new=%" PRId64 " ref=%" PRId64 "\n", h, s, rs, c, rc);
            ++g_fail;
        }
    }
    if (h > std::numeric_limits<int64_t>::min()) {
        const int64_t cprev = sost::sost_cumulative_emission_stocks(h - 1);
        if (h >= 0 && c != cprev + s) {
            if (g_fail < 20) std::printf("FAIL supply identity at h=%" PRId64 "\n", h);
            ++g_fail;
        }
    }
    ++g_checked;
}

int main() {
    const int64_t E = ref::BLOCKS_PER_EPOCH;
    const bool long_mode = std::getenv("SOST_SUBSIDY_LONG") != nullptr;
    const int64_t W = long_mode ? 512 : 128;          // window around each epoch boundary
    const int n_rand = long_mode ? 200000 : 20000;    // uniform samples in [0, 300 epochs]
    const int n_log  = long_mode ? 3000 : 300;        // log-uniform samples up to 1e9

    // 0. structural premise of the bound: q^256 truncates to zero (so does every q^e, e >= 256)
    if (ref::pow_q(256) != 0) { std::printf("FAIL pow_q(256) != 0\n"); ++g_fail; }
    int last_paying = -1;
    for (uint64_t e = 0; e < 512; ++e)
        if (((__int128)ref::R0_STOCKS * ref::pow_q(e)) / ref::Q_DEN > 0) last_paying = (int)e;
    std::printf("last paying epoch = %d (expected 81)\n", last_paying);
    if (last_paying != 81) ++g_fail;

    // 1. every height 0..400,000
    for (int64_t h = -3; h <= 400000; ++h) check_height(h);
    std::printf("exhaustive 0..400000: done (%" PRIu64 " heights)\n", g_checked);

    // 2. +-512 around every epoch boundary 0..300
    for (int64_t e = 0; e <= 300; ++e)
        for (int64_t h = e * E - W; h <= e * E + W; ++h) check_height(h);
    std::printf("epoch transitions 0..300 +-W: done (%" PRIu64 " heights)\n", g_checked);

    // 3. seeded random samples
    std::mt19937_64 rng(0x5057ULL);
    std::uniform_int_distribution<int64_t> u(0, 300 * E);
    for (int i = 0; i < n_rand; ++i) check_height(u(rng));
    std::uniform_real_distribution<double> lg(0.0, 9.0);
    for (int i = 0; i < n_log; ++i) check_height((int64_t)std::pow(10.0, lg(rng)));
    std::printf("random samples: done (%" PRIu64 " heights)\n", g_checked);

    // 4. hostile heights: bounded time, equal to the tail
    const int64_t tail_cum = ref::cumulative_emission(300 * E);
    const int64_t hostile[] = {100000000000LL, 1000000000000LL, 3000000000000LL,
                               std::numeric_limits<int64_t>::max() - 1,
                               std::numeric_limits<int64_t>::max()};
    for (int64_t h : hostile) {
        auto t0 = std::chrono::steady_clock::now();
        const int64_t s = sost::sost_subsidy_stocks(h);
        const int64_t c = sost::sost_cumulative_emission_stocks(h);
        const double ms = std::chrono::duration<double, std::milli>(
                              std::chrono::steady_clock::now() - t0).count();
        bool ok = (s == 0 && c == tail_cum && ms < 50.0);
        if (h == 100000000000LL || (long_mode && h <= 3000000000000LL)) {
            ok = ok && ref::subsidy(h) == s && ref::cumulative_emission(h) == c;
        }
        std::printf("%s hostile h=%" PRId64 ": subsidy=%" PRId64 " cum=%" PRId64 " in %.3f ms%s\n",
                    ok ? "PASS" : "FAIL", h, s, c, ms,
                    (h == 100000000000LL || (long_mode && h <= 3000000000000LL)) ? " (== reference)" : "");
        if (!ok) ++g_fail;
    }
    // 4b. V17 at hostile heights: every V17 amount derived from the subsidy is 0
    for (int64_t h : hostile) {
        const int64_t s = sost::sost_subsidy_stocks(h);
        const auto sp = sost::v17::subsidy_split(s);
        const auto jt = sost::v17::j_transition(h, 5, s, 0);
        if (!sp.ok || sp.miner_subsidy || sp.dtd_subsidy || sp.jackpot_j || !jt.ok || jt.j_alloc || jt.j_after != 5) {
            std::printf("FAIL V17 hostile h=%" PRId64 "\n", h); ++g_fail;
        }
    }

    // 4c. V17 J accumulator over the whole remaining schedule: per-epoch sums of jackpot_j
    // from V17_HEIGHT (mainnet 40,000) to the end of epoch 300, new vs reference subsidy.
    if (sost::V17_HEIGHT != std::numeric_limits<int64_t>::max()) {
        __int128 j_new = 0, j_ref = 0, d_new = 0, d_ref = 0, m_new = 0, m_ref = 0;
        for (int64_t e = 0; e <= 300; ++e) {
            const int64_t lo = std::max<int64_t>(sost::V17_HEIGHT, e * E), hi = (e + 1) * E - 1;
            if (hi < lo) continue;
            // the subsidy is constant inside an epoch except where the cap clamps it:
            // evaluate the first, last and (when they differ) every block of the epoch
            const int64_t sf = sost::sost_subsidy_stocks(lo), sl = sost::sost_subsidy_stocks(hi);
            if (sf == sl && sf == ref::subsidy(lo) && sl == ref::subsidy(hi)) {
                const auto sp = sost::v17::subsidy_split(sf);
                const __int128 n = hi - lo + 1;
                j_new += n * sp.jackpot_j; d_new += n * sp.dtd_subsidy; m_new += n * sp.miner_subsidy;
                j_ref += n * sp.jackpot_j; d_ref += n * sp.dtd_subsidy; m_ref += n * sp.miner_subsidy;
            } else {
                for (int64_t h = lo; h <= hi; ++h) {
                    const auto a = sost::v17::subsidy_split(sost::sost_subsidy_stocks(h));
                    const auto b = sost::v17::subsidy_split(ref::subsidy(h));
                    j_new += a.jackpot_j; d_new += a.dtd_subsidy; m_new += a.miner_subsidy;
                    j_ref += b.jackpot_j; d_ref += b.dtd_subsidy; m_ref += b.miner_subsidy;
                }
            }
        }
        const bool ok = (j_new == j_ref && d_new == d_ref && m_new == m_ref);
        std::printf("%s V17 schedule from h=%" PRId64 ": J total=%" PRId64 " DTD total=%" PRId64
                    " miner-subsidy total=%" PRId64 " (new == reference)\n", ok ? "PASS" : "FAIL",
                    sost::V17_HEIGHT, (int64_t)j_new, (int64_t)d_new, (int64_t)m_new);
        if (!ok) ++g_fail;
    }

    // INT64_MIN must not misbehave either
    if (sost::sost_subsidy_stocks(std::numeric_limits<int64_t>::min()) != 0 ||
        sost::sost_cumulative_emission_stocks(std::numeric_limits<int64_t>::min()) != 0) ++g_fail;

    std::printf("final cumulative supply %" PRId64 " stocks (cap %" PRId64 ")\n", tail_cum, ref::SUPPLY_CAP);
    std::printf("%s%s: %" PRIu64 " heights checked (%" PRIu64 " with V17 split/coinbase/J), %d failures\n",
                g_fail ? "FAIL" : "PASS", long_mode ? " (long)" : "", g_checked, g_v17_checked, g_fail);
    return g_fail ? 1 : 0;
}
