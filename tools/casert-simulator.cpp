// casert-simulator — cASERT control system simulation
// Phase C: Validate cASERT behavior under various hashpower scenarios
#include "sost/pow/casert.h"
#include "sost/sostcompact.h"
#include "sost/params.h"
#include "sost/types.h"
#include "sost/crypto.h"
#include <cstdio>
#include <cmath>
#include <vector>
#include <algorithm>
#include <numeric>
#include <random>
#include <cstring>
#include <functional>

using namespace sost;

// Simulate mining: given hashpower (attempts/sec) and current bitsQ,
// return a random block time in seconds
static double sim_block_time(double hashpower, uint32_t bits_q,
                             double stability_rate, std::mt19937_64& rng) {
    double b = (double)bits_q / 65536.0;
    double prob_target = std::pow(2.0, -b);
    double prob_solve = stability_rate * prob_target;
    double rate = hashpower * prob_solve;
    if (rate <= 0) return 86400.0; // 1 day cap
    // Exponential distribution (memoryless Poisson process)
    std::exponential_distribution<double> dist(rate);
    double t = dist(rng);
    if (t > 86400.0) t = 86400.0;
    if (t < 1.0) t = 1.0;
    return t;
}

struct SimStats {
    const char* scenario;
    int blocks;
    double mean_bt;
    double median_bt;
    double p5_bt;
    double p95_bt;
    double min_bt;
    double max_bt;
    double stddev_bt;
    double mean_bitsq;
    double final_bitsq;
    double stall_recovery_time;
    int profile_counts[10]; // E3..H6
    double schedule_lag_drift;
};

static SimStats compute_stats(const char* name, const std::vector<double>& block_times,
                              const std::vector<uint32_t>& bitsq_hist,
                              const std::vector<int32_t>& profile_hist,
                              const std::vector<int32_t>& lag_hist) {
    SimStats s{};
    s.scenario = name;
    s.blocks = (int)block_times.size();
    std::memset(s.profile_counts, 0, sizeof(s.profile_counts));

    auto sorted = block_times;
    std::sort(sorted.begin(), sorted.end());
    double sum = std::accumulate(sorted.begin(), sorted.end(), 0.0);
    s.mean_bt = sum / sorted.size();
    s.median_bt = sorted[sorted.size() / 2];
    s.p5_bt = sorted[(size_t)(sorted.size() * 0.05)];
    s.p95_bt = sorted[(size_t)(sorted.size() * 0.95)];
    s.min_bt = sorted.front();
    s.max_bt = sorted.back();

    double var = 0;
    for (auto t : sorted) var += (t - s.mean_bt) * (t - s.mean_bt);
    s.stddev_bt = std::sqrt(var / sorted.size());

    double bq_sum = 0;
    for (auto bq : bitsq_hist) bq_sum += bq;
    s.mean_bitsq = bq_sum / bitsq_hist.size();
    s.final_bitsq = bitsq_hist.back();

    for (auto pi : profile_hist) {
        int idx = pi + 3;
        if (idx >= 0 && idx < 10) s.profile_counts[idx]++;
    }

    s.schedule_lag_drift = lag_hist.empty() ? 0 : lag_hist.back();

    // Stall recovery: find longest gap > 1800s and measure time to return to <900s
    s.stall_recovery_time = 0;
    for (size_t i = 0; i < block_times.size(); ++i) {
        if (block_times[i] > 1800.0) {
            for (size_t j = i + 1; j < block_times.size(); ++j) {
                if (block_times[j] < 900.0) {
                    double recovery = 0;
                    for (size_t k = i; k <= j; ++k) recovery += block_times[k];
                    if (recovery > s.stall_recovery_time)
                        s.stall_recovery_time = recovery;
                    break;
                }
            }
        }
    }
    return s;
}

static void print_stats(const SimStats& s) {
    printf("\n  === %s ===\n", s.scenario);
    printf("  Blocks:         %d\n", s.blocks);
    printf("  Mean BT:        %.1f sec (target: 600)\n", s.mean_bt);
    printf("  Median BT:      %.1f sec\n", s.median_bt);
    printf("  P5/P95:         %.1f / %.1f sec\n", s.p5_bt, s.p95_bt);
    printf("  Min/Max:        %.1f / %.1f sec\n", s.min_bt, s.max_bt);
    printf("  Stddev:         %.1f sec\n", s.stddev_bt);
    printf("  Mean bitsQ:     %.1f (%.4f)\n", s.mean_bitsq, s.mean_bitsq / 65536.0);
    printf("  Final bitsQ:    %u (%.4f)\n", (uint32_t)s.final_bitsq, s.final_bitsq / 65536.0);
    printf("  Schedule lag:   %d blocks\n", (int)s.schedule_lag_drift);
    printf("  Stall recovery: %.1f sec\n", s.stall_recovery_time);

    const char* pnames[] = {"E3","E2","E1","B0","H1","H2","H3","H4","H5","H6"};
    printf("  Profile dist:   ");
    for (int i = 0; i < 10; ++i) {
        if (s.profile_counts[i] > 0)
            printf("%s=%d ", pnames[i], s.profile_counts[i]);
    }
    printf("\n");
}

// Run a scenario
static SimStats run_scenario(const char* name, int blocks,
                             uint32_t start_bitsq,
                             // hashpower_fn: given block index, return attempts/sec
                             std::function<double(int)> hashpower_fn,
                             double stability_rate,
                             // timestamp_noise_fn: add noise to block time
                             std::function<double(int, double)> noise_fn,
                             std::mt19937_64& rng) {
    printf("\n  Running: %s (%d blocks)...\n", name, blocks);

    std::vector<BlockMeta> chain;
    std::vector<double> block_times;
    std::vector<uint32_t> bitsq_hist;
    std::vector<int32_t> profile_hist;
    std::vector<int32_t> lag_hist;

    // Genesis block
    chain.push_back({ZERO_HASH(), 0, GENESIS_TIME, start_bitsq});
    bitsq_hist.push_back(start_bitsq);

    for (int i = 1; i <= blocks; ++i) {
        uint32_t bits_q = casert_next_bitsq(chain, i);
        auto dec = casert_compute(chain, i, 0);

        double hp = hashpower_fn(i);
        double bt = sim_block_time(hp, bits_q, stability_rate, rng);

        // Apply noise
        bt = noise_fn(i, bt);
        if (bt < 1.0) bt = 1.0;

        int64_t block_time = chain.back().time + (int64_t)bt;

        Bytes32 id{};
        id[0] = (uint8_t)(i & 0xFF);
        id[1] = (uint8_t)((i >> 8) & 0xFF);

        chain.push_back({id, (int64_t)i, block_time, bits_q});
        block_times.push_back(bt);
        bitsq_hist.push_back(bits_q);
        profile_hist.push_back(dec.profile_index);
        lag_hist.push_back(dec.lag);

        if (i % 100 == 0) {
            printf("\r    block %d/%d bitsQ=%.4f profile=%d lag=%d bt=%.0fs",
                   i, blocks, (double)bits_q / 65536.0, dec.profile_index, dec.lag, bt);
            fflush(stdout);
        }
    }
    printf("\r    done.                                                          \n");

    return compute_stats(name, block_times, bitsq_hist, profile_hist, lag_hist);
}

int main(int argc, char** argv) {
    // Configurable params
    double base_hashpower = 0.5; // attempts/sec (from benchmark)
    double stability_rate = 0.6; // fraction of attempts that pass stability
    uint32_t start_bitsq = GENESIS_BITSQ;
    int sim_blocks = 500;

    if (argc > 1) base_hashpower = std::atof(argv[1]);
    if (argc > 2) stability_rate = std::atof(argv[2]);
    if (argc > 3) start_bitsq = (uint32_t)std::atoi(argv[3]);
    if (argc > 4) sim_blocks = std::atoi(argv[4]);

    printf("============================================================\n");
    printf("  cASERT Control System Simulator — Phase C\n");
    printf("============================================================\n");
    printf("  Base hashpower:   %.4f att/s\n", base_hashpower);
    printf("  Stability rate:   %.2f%%\n", stability_rate * 100);
    printf("  Start bitsQ:      %u (%.4f)\n", start_bitsq, (double)start_bitsq / 65536.0);
    printf("  Blocks/scenario:  %d\n", sim_blocks);
    printf("  BITSQ_HALF_LIFE:  %lld s\n", (long long)BITSQ_HALF_LIFE);
    printf("  Delta cap:        %d/%d (%.2f%%)\n",
           BITSQ_MAX_DELTA_NUM, BITSQ_MAX_DELTA_DEN,
           100.0 * BITSQ_MAX_DELTA_NUM / BITSQ_MAX_DELTA_DEN);

    std::mt19937_64 rng(42);
    auto no_noise = [](int, double bt) { return bt; };

    std::vector<SimStats> all_stats;

    // Scenario 1: Constant hashpower
    all_stats.push_back(run_scenario(
        "1. Constant hashpower (1 miner)", sim_blocks, start_bitsq,
        [&](int) { return base_hashpower; }, stability_rate, no_noise, rng));

    // Scenario 2: +50% hashpower increase at block 100
    all_stats.push_back(run_scenario(
        "2. +50% hashpower at block 100", sim_blocks, start_bitsq,
        [&](int i) { return i < 100 ? base_hashpower : base_hashpower * 1.5; },
        stability_rate, no_noise, rng));

    // Scenario 3: -50% hashpower drop at block 100
    all_stats.push_back(run_scenario(
        "3. -50% hashpower at block 100", sim_blocks, start_bitsq,
        [&](int i) { return i < 100 ? base_hashpower : base_hashpower * 0.5; },
        stability_rate, no_noise, rng));

    // Scenario 4: Short burst (5x for 20 blocks at block 100)
    all_stats.push_back(run_scenario(
        "4. Short burst (5x for 20 blocks)", sim_blocks, start_bitsq,
        [&](int i) { return (i >= 100 && i < 120) ? base_hashpower * 5.0 : base_hashpower; },
        stability_rate, no_noise, rng));

    // Scenario 5: Long stall (0.1x for 50 blocks at block 100)
    all_stats.push_back(run_scenario(
        "5. Long stall (0.1x for 50 blocks)", sim_blocks, start_bitsq,
        [&](int i) { return (i >= 100 && i < 150) ? base_hashpower * 0.1 : base_hashpower; },
        stability_rate, no_noise, rng));

    // Scenario 6: Oscillating miners (toggle 1x/3x every 30 blocks)
    all_stats.push_back(run_scenario(
        "6. Oscillating miners (1x/3x every 30 blocks)", sim_blocks, start_bitsq,
        [&](int i) { return ((i / 30) % 2 == 0) ? base_hashpower : base_hashpower * 3.0; },
        stability_rate, no_noise, rng));

    // Scenario 7: Adversarial timestamp noise (±300s random)
    std::uniform_real_distribution<double> noise_dist(-300.0, 300.0);
    all_stats.push_back(run_scenario(
        "7. Adversarial timestamp noise (±300s)", sim_blocks, start_bitsq,
        [&](int) { return base_hashpower; }, stability_rate,
        [&](int, double bt) { return bt + noise_dist(rng); }, rng));

    // Summary table
    printf("\n============================================================\n");
    printf("  SIMULATION SUMMARY\n");
    printf("============================================================\n");

    for (auto& s : all_stats) print_stats(s);

    printf("\n============================================================\n");
    printf("  PARAMETER SENSITIVITY ASSESSMENT\n");
    printf("============================================================\n");

    bool stable = true;
    for (auto& s : all_stats) {
        bool ok = true;
        if (s.mean_bt < 300 || s.mean_bt > 1200) { ok = false; printf("  WARN: %s mean BT out of range (%.0f)\n", s.scenario, s.mean_bt); }
        if (s.p95_bt > 3600) { ok = false; printf("  WARN: %s P95 > 1h (%.0f)\n", s.scenario, s.p95_bt); }
        if (std::abs(s.schedule_lag_drift) > 100) { ok = false; printf("  WARN: %s lag drift > 100 (%d)\n", s.scenario, (int)s.schedule_lag_drift); }
        if (!ok) stable = false;
    }

    if (stable) {
        printf("  ALL SCENARIOS WITHIN ACCEPTABLE BOUNDS.\n");
        printf("  Parameters validated.\n");
    } else {
        printf("  SOME SCENARIOS SHOW ISSUES — review above.\n");
    }

    printf("\n============================================================\n");
    printf("  SIMULATION COMPLETE\n");
    printf("============================================================\n");
    return 0;
}
