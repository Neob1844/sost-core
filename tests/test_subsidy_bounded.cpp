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
#include <sost/subsidy.h>

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

static void check_height(int64_t h, bool with_ref = true) {
    const int64_t s = sost::sost_subsidy_stocks(h);
    const int64_t c = sost::sost_cumulative_emission_stocks(h);
    if (with_ref) {
        const int64_t rs = ref::subsidy(h), rc = ref::cumulative_emission(h);
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
    // INT64_MIN must not misbehave either
    if (sost::sost_subsidy_stocks(std::numeric_limits<int64_t>::min()) != 0 ||
        sost::sost_cumulative_emission_stocks(std::numeric_limits<int64_t>::min()) != 0) ++g_fail;

    std::printf("final cumulative supply %" PRId64 " stocks (cap %" PRId64 ")\n", tail_cum, ref::SUPPLY_CAP);
    std::printf("%s%s: %" PRIu64 " heights checked, %d failures\n", g_fail ? "FAIL" : "PASS", long_mode ? " (long)" : "", g_checked, g_fail);
    return g_fail ? 1 : 0;
}
