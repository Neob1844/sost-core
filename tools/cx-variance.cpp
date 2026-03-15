// cx-variance — ConvergenceX structural variance measurement
// Phase D: Measure basin variance across random block programs
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/emission.h"
#include "sost/sostcompact.h"
#include "sost/crypto.h"
#include <cstdio>
#include <chrono>
#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <random>

using namespace sost;
using clk = std::chrono::steady_clock;

struct AttemptData {
    uint32_t nonce;
    bool is_stable;
    uint64_t stability_metric;
    double time_ms;
    int64_t residual;  // final residual from checkpoints
};

int main(int argc, char** argv) {
    int num_blocks = 20;    // different block programs to test
    int attempts_per = 30;  // attempts per block program
    if (argc > 1) num_blocks = std::atoi(argv[1]);
    if (argc > 2) attempts_per = std::atoi(argv[2]);

    printf("============================================================\n");
    printf("  ConvergenceX Structural Variance Measurement — Phase D\n");
    printf("============================================================\n");
    printf("  Block programs:      %d\n", num_blocks);
    printf("  Attempts per block:  %d\n", attempts_per);

    ACTIVE_PROFILE = Profile::MAINNET;
    ConsensusParams params = get_consensus_params(Profile::MAINNET, 0);

    // Reduce scratchpad for memory (timing unaffected, see benchmark notes)
    int scratch_mb = params.cx_scratch_mb;
    if (argc > 3) scratch_mb = std::atoi(argv[3]);
    if (scratch_mb > 0 && scratch_mb != params.cx_scratch_mb) {
        printf("  NOTE: scratchpad reduced from %d to %d MB\n", params.cx_scratch_mb, scratch_mb);
        params.cx_scratch_mb = scratch_mb;
    }

    printf("\n--- Building scratchpad (%d MB)...\n", params.cx_scratch_mb);
    Bytes32 epoch_key = epoch_scratch_key(0, nullptr);
    auto scratch = build_scratchpad(epoch_key, params.cx_scratch_mb);
    printf("  Done.\n");

    // Per-block statistics
    std::vector<double> block_stability_rates;
    std::vector<double> block_avg_metrics;
    std::vector<double> block_avg_times;
    std::vector<double> all_metrics;
    std::vector<double> all_times;
    std::vector<int> all_stable;

    std::mt19937_64 rng(12345);

    for (int bi = 0; bi < num_blocks; ++bi) {
        // Generate unique prev_hash for each "block"
        Bytes32 prev_hash{};
        for (int j = 0; j < 32; ++j)
            prev_hash[j] = (uint8_t)(rng() & 0xFF);

        Bytes32 merkle{};
        merkle.fill(0xCC);

        uint8_t hc72[72];
        std::memcpy(hc72, prev_hash.data(), 32);
        std::memcpy(hc72 + 32, merkle.data(), 32);
        write_u32_le(hc72 + 64, (uint32_t)GENESIS_TIME);
        write_u32_le(hc72 + 68, GENESIS_BITSQ);

        Bytes32 bk = compute_block_key(prev_hash);

        // Force dataset regeneration for new prev_hash
        g_cx_dataset.generate(prev_hash);

        int stable_count = 0;
        double metric_sum = 0;
        double time_sum = 0;

        printf("\r  Block %d/%d (prev=%s)...",
               bi + 1, num_blocks, hex(prev_hash).substr(0, 8).c_str());
        fflush(stdout);

        for (int ai = 0; ai < attempts_per; ++ai) {
            uint32_t nonce = (uint32_t)ai;
            auto t0 = clk::now();
            auto res = convergencex_attempt(
                scratch.data(), scratch.size(), bk, nonce, 0, params, hc72, 0);
            auto t1 = clk::now();
            double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

            all_times.push_back(ms);
            all_metrics.push_back((double)res.stability_metric);
            all_stable.push_back(res.is_stable ? 1 : 0);

            if (res.is_stable) {
                stable_count++;
                metric_sum += res.stability_metric;
            }
            time_sum += ms;
        }

        double sr = (double)stable_count / attempts_per;
        double avg_m = stable_count > 0 ? metric_sum / stable_count : 0;
        double avg_t = time_sum / attempts_per;

        block_stability_rates.push_back(sr);
        block_avg_metrics.push_back(avg_m);
        block_avg_times.push_back(avg_t);
    }

    printf("\r  Done.                                                \n");

    // Compute variance statistics
    printf("\n============================================================\n");
    printf("  PER-BLOCK STABILITY RATE DISTRIBUTION\n");
    printf("============================================================\n");

    auto sorted_sr = block_stability_rates;
    std::sort(sorted_sr.begin(), sorted_sr.end());
    double sr_mean = std::accumulate(sorted_sr.begin(), sorted_sr.end(), 0.0) / sorted_sr.size();
    double sr_var = 0;
    for (auto v : sorted_sr) sr_var += (v - sr_mean) * (v - sr_mean);
    sr_var /= sorted_sr.size();

    printf("  Blocks tested: %d\n", num_blocks);
    printf("  Mean stability rate: %.4f (%.1f%%)\n", sr_mean, sr_mean * 100);
    printf("  Min:  %.4f\n", sorted_sr.front());
    printf("  Max:  %.4f\n", sorted_sr.back());
    printf("  P10:  %.4f\n", sorted_sr[(size_t)(sorted_sr.size() * 0.1)]);
    printf("  P90:  %.4f\n", sorted_sr[(size_t)(sorted_sr.size() * 0.9)]);
    printf("  Stddev: %.4f\n", std::sqrt(sr_var));
    printf("  CoV:    %.4f\n", sr_mean > 0 ? std::sqrt(sr_var) / sr_mean : 0);

    // Histogram
    printf("\n  Stability rate histogram:\n");
    int buckets[11] = {};
    for (auto v : block_stability_rates) {
        int b = (int)(v * 10);
        if (b < 0) b = 0;
        if (b > 10) b = 10;
        buckets[b]++;
    }
    for (int i = 0; i <= 10; ++i) {
        printf("    [%.0f%%-%.0f%%): %d ", i * 10.0, (i + 1) * 10.0, buckets[i]);
        for (int j = 0; j < buckets[i]; ++j) printf("#");
        printf("\n");
    }

    printf("\n============================================================\n");
    printf("  STABILITY METRIC DISTRIBUTION (stable attempts only)\n");
    printf("============================================================\n");

    std::vector<double> stable_metrics;
    for (size_t i = 0; i < all_metrics.size(); ++i) {
        if (all_stable[i]) stable_metrics.push_back(all_metrics[i]);
    }

    if (!stable_metrics.empty()) {
        std::sort(stable_metrics.begin(), stable_metrics.end());
        double m_mean = std::accumulate(stable_metrics.begin(), stable_metrics.end(), 0.0) / stable_metrics.size();
        double m_var = 0;
        for (auto v : stable_metrics) m_var += (v - m_mean) * (v - m_mean);
        m_var /= stable_metrics.size();

        printf("  Stable attempts: %zu / %zu (%.1f%%)\n",
               stable_metrics.size(), all_metrics.size(),
               100.0 * stable_metrics.size() / all_metrics.size());
        printf("  Mean metric:   %.1f\n", m_mean);
        printf("  Median metric: %.1f\n", stable_metrics[stable_metrics.size() / 2]);
        printf("  Min/Max:       %.1f / %.1f\n", stable_metrics.front(), stable_metrics.back());
        printf("  Stddev:        %.1f\n", std::sqrt(m_var));
        printf("  CoV:           %.4f\n", m_mean > 0 ? std::sqrt(m_var) / m_mean : 0);
    }

    printf("\n============================================================\n");
    printf("  PER-ATTEMPT TIME DISTRIBUTION\n");
    printf("============================================================\n");

    auto sorted_t = all_times;
    std::sort(sorted_t.begin(), sorted_t.end());
    double t_mean = std::accumulate(sorted_t.begin(), sorted_t.end(), 0.0) / sorted_t.size();
    double t_var = 0;
    for (auto v : sorted_t) t_var += (v - t_mean) * (v - t_mean);
    t_var /= sorted_t.size();

    printf("  Total attempts: %zu\n", sorted_t.size());
    printf("  Mean time:   %.1f ms\n", t_mean);
    printf("  Median time: %.1f ms\n", sorted_t[sorted_t.size() / 2]);
    printf("  Min/Max:     %.1f / %.1f ms\n", sorted_t.front(), sorted_t.back());
    printf("  P5/P95:      %.1f / %.1f ms\n",
           sorted_t[(size_t)(sorted_t.size() * 0.05)],
           sorted_t[(size_t)(sorted_t.size() * 0.95)]);
    printf("  Stddev:      %.1f ms\n", std::sqrt(t_var));
    printf("  CoV:         %.4f\n", t_mean > 0 ? std::sqrt(t_var) / t_mean : 0);

    printf("\n============================================================\n");
    printf("  VARIANCE ASSESSMENT\n");
    printf("============================================================\n");

    double cov_sr = sr_mean > 0 ? std::sqrt(sr_var) / sr_mean : 999;
    const char* assessment;
    if (cov_sr < 0.15) assessment = "NEGLIGIBLE — block programs are structurally uniform";
    else if (cov_sr < 0.35) assessment = "MODERATE — some blocks are easier/harder, but within tolerance";
    else assessment = "SEVERE — significant structural bias between block programs";

    printf("  Stability rate CoV: %.4f\n", cov_sr);
    printf("  Assessment: %s\n", assessment);
    printf("\n  NOTE: This measures whether certain block programs produce\n"
           "  systematically easier or harder stability basins. If SEVERE,\n"
           "  a normalization layer may be needed in the future.\n");

    printf("\n============================================================\n");
    printf("  VARIANCE MEASUREMENT COMPLETE\n");
    printf("============================================================\n");
    return 0;
}
