// cx-benchmark — ConvergenceX real hardware benchmark
// Phase A: Measure actual per-attempt time across profiles
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/pow/casert.h"
#include "sost/sostcompact.h"
#include "sost/emission.h"
#include "sost/crypto.h"
#include <cstdio>
#include <chrono>
#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>

using namespace sost;
using clk = std::chrono::steady_clock;

struct BenchResult {
    const char* label;
    int attempts;
    int stable_count;
    int meets_target_count;
    double avg_ms;
    double min_ms;
    double max_ms;
    double median_ms;
    double p95_ms;
    double stddev_ms;
    double stability_rate;
};

static BenchResult run_bench(const char* label, ConsensusParams params,
                             const uint8_t* scratch, size_t scratch_len,
                             const Bytes32& block_key, const uint8_t* hc72,
                             int32_t epoch, uint32_t bits_q, int attempts)
{
    std::vector<double> times;
    times.reserve(attempts);
    int stable = 0;
    int meets = 0;

    printf("  Running %s (%d attempts)...\n", label, attempts);
    fflush(stdout);

    for (int i = 0; i < attempts; ++i) {
        uint32_t nonce = (uint32_t)i;
        auto t0 = clk::now();
        auto res = convergencex_attempt(
            scratch, scratch_len, block_key, nonce, 0, params, hc72, epoch);
        auto t1 = clk::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        times.push_back(ms);
        if (res.is_stable) {
            stable++;
            if (pow_meets_target(res.commit, bits_q)) meets++;
        }

        if ((i+1) % 10 == 0) {
            printf("\r    %d/%d (avg %.1fms, stable %d/%d)", i+1, attempts,
                   std::accumulate(times.begin(), times.end(), 0.0) / times.size(),
                   stable, i+1);
            fflush(stdout);
        }
    }
    printf("\r    done.                                        \n");

    std::sort(times.begin(), times.end());
    double sum = std::accumulate(times.begin(), times.end(), 0.0);
    double avg = sum / times.size();
    double var = 0;
    for (auto t : times) var += (t - avg) * (t - avg);
    var /= times.size();

    BenchResult r;
    r.label = label;
    r.attempts = attempts;
    r.stable_count = stable;
    r.meets_target_count = meets;
    r.avg_ms = avg;
    r.min_ms = times.front();
    r.max_ms = times.back();
    r.median_ms = times[times.size() / 2];
    r.p95_ms = times[(size_t)(times.size() * 0.95)];
    r.stddev_ms = std::sqrt(var);
    r.stability_rate = (double)stable / attempts;
    return r;
}

static void print_result(const BenchResult& r) {
    printf("\n  === %s ===\n", r.label);
    printf("  Attempts:       %d\n", r.attempts);
    printf("  Stable:         %d (%.1f%%)\n", r.stable_count, r.stability_rate * 100);
    printf("  Meets target:   %d\n", r.meets_target_count);
    printf("  Avg time:       %.1f ms\n", r.avg_ms);
    printf("  Median time:    %.1f ms\n", r.median_ms);
    printf("  Min time:       %.1f ms\n", r.min_ms);
    printf("  Max time:       %.1f ms\n", r.max_ms);
    printf("  P95 time:       %.1f ms\n", r.p95_ms);
    printf("  Stddev:         %.1f ms\n", r.stddev_ms);
    printf("  Attempts/sec:   %.2f\n", 1000.0 / r.avg_ms);
}

static void estimate_block_time(const BenchResult& r, uint32_t bits_q, int miners) {
    // Probability of meeting target at this bitsQ
    // target_from_bitsQ gives a 256-bit threshold
    // Probability ≈ target / 2^256
    // But we measure empirically: if N attempts produce M target-meets,
    // probability ≈ M/N. If M=0 from small sample, use stability_rate * target_fraction.

    double prob_stable = r.stability_rate;

    // Estimate target fraction from bitsQ
    // bitsQ is Q16.16: integer part = leading zero bits in target
    // For bitsQ = b, target ≈ 2^(256 - b) where b = bitsQ / 65536
    double b = (double)bits_q / 65536.0;
    double log2_target = 256.0 - b;
    double log2_prob_target = log2_target - 256.0; // = -b
    double prob_target = std::pow(2.0, log2_prob_target);

    double prob_solve = prob_stable * prob_target;
    double attempts_per_sec = 1000.0 / r.avg_ms;
    double total_attempts_per_sec = attempts_per_sec * miners;
    double expected_seconds = 1.0 / (total_attempts_per_sec * prob_solve);

    printf("  Block time estimate at bitsQ=%u (%.4f):\n", bits_q, b);
    printf("    P(stable) = %.4f\n", prob_stable);
    printf("    P(commit < target) = %.2e\n", prob_target);
    printf("    P(solve) = %.2e\n", prob_solve);
    printf("    Attempts/sec (%d miner%s) = %.2f\n",
           miners, miners > 1 ? "s" : "", total_attempts_per_sec);
    printf("    Expected block time = %.1f seconds (%.1f min)\n",
           expected_seconds, expected_seconds / 60.0);
}

// Compute bitsQ that gives ~600s block time for given attempt rate and stability rate
static uint32_t calibrate_bitsq(double attempts_per_sec, double stability_rate, int miners) {
    // We want: 600 = 1 / (total_rate * prob_solve)
    // prob_solve = stability_rate * 2^(-bitsQ/65536)
    // 600 = 1 / (total_rate * stability_rate * 2^(-b))
    // 2^(-b) = 1 / (600 * total_rate * stability_rate)
    // -b = log2(1 / (600 * total_rate * stability_rate))
    // b = log2(600 * total_rate * stability_rate)

    double total_rate = attempts_per_sec * miners;
    double b = std::log2(600.0 * total_rate * stability_rate);
    if (b < 1.0) b = 1.0;
    if (b > 255.0) b = 255.0;
    uint32_t bitsq = (uint32_t)(b * 65536.0);
    if (bitsq < MIN_BITSQ) bitsq = MIN_BITSQ;
    if (bitsq > MAX_BITSQ) bitsq = MAX_BITSQ;
    return bitsq;
}

int main(int argc, char** argv) {
    int num_attempts = 50; // default
    if (argc > 1) num_attempts = std::atoi(argv[1]);
    if (num_attempts < 10) num_attempts = 10;

    printf("============================================================\n");
    printf("  ConvergenceX Hardware Benchmark — Phase A\n");
    printf("============================================================\n");
    printf("  Attempts per profile: %d\n", num_attempts);

    // Set up mainnet profile
    ACTIVE_PROFILE = Profile::MAINNET;
    ConsensusParams base = get_consensus_params(Profile::MAINNET, 0);

    // Memory optimization: reduce scratchpad if system RAM is limited.
    // Per-round compute cost (100K rounds of gradient descent + SHA256) is
    // independent of scratchpad size — scratchpad only provides mixing values.
    // The 4GB dataset is the dominant memory consumer.
    int scratch_mb = base.cx_scratch_mb;
    if (argc > 2) scratch_mb = std::atoi(argv[2]);
    if (scratch_mb <= 0) scratch_mb = base.cx_scratch_mb;
    if (scratch_mb != base.cx_scratch_mb) {
        printf("\n  NOTE: scratchpad reduced from %d to %d MB for memory.\n", base.cx_scratch_mb, scratch_mb);
        printf("  Per-round timing is unaffected (dominated by 100K gradient descent + SHA256).\n");
        base.cx_scratch_mb = scratch_mb;
    }

    printf("\n--- Mainnet baseline params ---\n");
    printf("  n=%d rounds=%d scratch=%dMB lr_shift=%d lam=%d\n",
           base.cx_n, base.cx_rounds, base.cx_scratch_mb, base.cx_lr_shift, base.cx_lam);
    printf("  stab: scale=%d steps=%d k=%d margin=%d\n",
           base.stab_scale, base.stab_steps, base.stab_k, base.stab_margin);

    // Build scratchpad
    printf("\n--- Building scratchpad (%d MB)...\n", base.cx_scratch_mb);
    auto scratch_t0 = clk::now();
    Bytes32 epoch_key = epoch_scratch_key(0, nullptr);
    auto scratch = build_scratchpad(epoch_key, base.cx_scratch_mb);
    auto scratch_t1 = clk::now();
    double scratch_ms = std::chrono::duration<double, std::milli>(scratch_t1 - scratch_t0).count();
    printf("  Scratchpad built: %.1f ms (%.2f sec)\n", scratch_ms, scratch_ms / 1000.0);

    // Build dataset (first attempt will trigger it)
    printf("\n--- Dataset will be generated on first attempt (4GB)...\n");

    // Synthetic header
    Bytes32 prev_hash{}; prev_hash.fill(0xAA);
    Bytes32 merkle{}; merkle.fill(0xBB);
    uint32_t bits_q = GENESIS_BITSQ;
    uint8_t hc72[72];
    std::memcpy(hc72, prev_hash.data(), 32);
    std::memcpy(hc72 + 32, merkle.data(), 32);
    write_u32_le(hc72 + 64, (uint32_t)GENESIS_TIME);
    write_u32_le(hc72 + 68, bits_q);

    Bytes32 bk = compute_block_key(prev_hash);

    // Measure dataset generation time
    auto ds_t0 = clk::now();
    g_cx_dataset.generate(prev_hash);
    auto ds_t1 = clk::now();
    double ds_ms = std::chrono::duration<double, std::milli>(ds_t1 - ds_t0).count();
    printf("  Dataset generated: %.1f ms (%.2f sec)\n", ds_ms, ds_ms / 1000.0);

    // Profile configurations to benchmark
    struct ProfileBench {
        const char* name;
        CasertProfile profile;
    };

    ProfileBench profiles[] = {
        {"B0 (baseline)",  CASERT_PROFILES[3]},  // index 0 → array[3]
        {"H1",             CASERT_PROFILES[4]},
        {"H2",             CASERT_PROFILES[5]},
        {"H3",             CASERT_PROFILES[6]},
    };

    std::vector<BenchResult> results;

    printf("\n============================================================\n");
    printf("  BENCHMARKING PROFILES\n");
    printf("============================================================\n");

    for (auto& pb : profiles) {
        ConsensusParams p = base;
        p.stab_scale = pb.profile.scale;
        p.stab_steps = pb.profile.steps;
        p.stab_k = pb.profile.k;
        p.stab_margin = pb.profile.margin;

        printf("\n  Profile: %s (scale=%d steps=%d k=%d margin=%d)\n",
               pb.name, p.stab_scale, p.stab_steps, p.stab_k, p.stab_margin);

        auto r = run_bench(pb.name, p, scratch.data(), scratch.size(),
                           bk, hc72, 0, bits_q, num_attempts);
        results.push_back(r);
    }

    // Print results table
    printf("\n============================================================\n");
    printf("  RESULTS SUMMARY\n");
    printf("============================================================\n");

    for (auto& r : results) print_result(r);

    // Calibration estimates
    printf("\n============================================================\n");
    printf("  GENESIS_BITSQ CALIBRATION ESTIMATES\n");
    printf("============================================================\n");

    auto& b0 = results[0]; // B0 is the baseline for genesis
    double att_per_sec = 1000.0 / b0.avg_ms;

    printf("\n  Using B0 profile (genesis baseline):\n");
    printf("  Attempts/sec: %.4f\n", att_per_sec);
    printf("  Stability rate: %.4f\n", b0.stability_rate);

    // Candidate bitsQ values
    printf("\n  --- Block time estimates at various bitsQ (1 miner) ---\n");
    uint32_t candidates[] = {
        Q16_ONE,                            // 1.0
        Q16_ONE * 2,                        // 2.0
        Q16_ONE * 3,                        // 3.0
        (uint32_t)(Q16_ONE * 3.5),          // 3.5
        Q16_ONE * 4,                        // 4.0
        (uint32_t)(Q16_ONE * 4.5),          // 4.5
        Q16_ONE * 5,                        // 5.0
        GENESIS_BITSQ,                      // calibrated ~11.684
        Q16_ONE * 6,                        // 6.0
        Q16_ONE * 7,                        // 7.0
        Q16_ONE * 8,                        // 8.0
        Q16_ONE * 10,                       // 10.0
    };
    for (auto bq : candidates) {
        estimate_block_time(b0, bq, 1);
    }

    printf("\n  --- Calibrated GENESIS_BITSQ for target 600s ---\n");
    for (int miners : {1, 2, 5}) {
        uint32_t cal = calibrate_bitsq(att_per_sec, b0.stability_rate, miners);
        printf("  %d miner%s: GENESIS_BITSQ = %u (%.4f)\n",
               miners, miners > 1 ? "s" : "",
               cal, (double)cal / 65536.0);
        estimate_block_time(b0, cal, miners);
    }

    // Empirical target-hit rate from actual benchmark
    if (b0.meets_target_count > 0) {
        printf("\n  --- Empirical data ---\n");
        printf("  %d/%d attempts hit target at bitsQ=%u\n",
               b0.meets_target_count, b0.attempts, bits_q);
        double emp_rate = (double)b0.meets_target_count / b0.attempts;
        double emp_block_time = 1.0 / (att_per_sec * emp_rate);
        printf("  Empirical block time (1 miner): %.1f sec\n", emp_block_time);
    }

    printf("\n============================================================\n");
    printf("  BENCHMARK COMPLETE\n");
    printf("============================================================\n");
    return 0;
}
