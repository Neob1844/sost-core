// Tests for relief_predict_check_and_mark (sost/pow/relief_predict.h).
//
// The function is the gate that prevents the block monitor from re-firing
// the RELIEF-PREDICT path every poll cycle when the monitor thread restarts
// (which happens on every mine_one_block restart, ~ms-cadence with the
// scratchpad cache). It must:
//
//   1. Return true exactly once per mining height.
//   2. Return false on subsequent calls with the same height.
//   3. Return true again when the height changes (new block arrived).
//   4. Reset cleanly to the initial state (-1 sentinel).
//
// Also a basic concurrency test: many threads racing on the same height
// must result in exactly one "fire" winner (CAS semantics).

#include "sost/pow/relief_predict.h"

#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  EXPECT failed: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while(0)

int main() {
    printf("[relief_predict] start\n");

    // 1. Initial state.
    relief_predict_reset();
    TEST("after reset, last_marked == -1", relief_predict_last_marked() == -1);

    // 2. First call for a height fires.
    bool first_call = relief_predict_check_and_mark(100);
    TEST("first check_and_mark(100) returns true", first_call);
    TEST("last_marked == 100 after first call", relief_predict_last_marked() == 100);

    // 3. Repeat call for same height does NOT fire.
    bool second_call = relief_predict_check_and_mark(100);
    TEST("second check_and_mark(100) returns false", !second_call);
    bool third_call = relief_predict_check_and_mark(100);
    TEST("third check_and_mark(100) returns false", !third_call);

    // 4. New height fires.
    bool new_height = relief_predict_check_and_mark(101);
    TEST("check_and_mark(101) returns true", new_height);
    TEST("last_marked == 101 after move", relief_predict_last_marked() == 101);

    // 5. Old height fires (e.g. reorg back to 100). The contract is "different
    //    from current marked" → fire. This is fine because in production the
    //    monitor only uses the current g_monitor_height, never an older one.
    bool rollback = relief_predict_check_and_mark(100);
    TEST("check_and_mark(100) after marking 101 returns true (different)", rollback);
    TEST("last_marked == 100 after rollback call", relief_predict_last_marked() == 100);

    // 6. Reset works.
    relief_predict_reset();
    TEST("after second reset, last_marked == -1", relief_predict_last_marked() == -1);
    TEST("first call after reset fires", relief_predict_check_and_mark(50));

    // 7. Concurrency: 16 threads racing on the same height. Exactly one must
    //    return true; the other 15 must return false.
    relief_predict_reset();
    constexpr int N = 16;
    std::atomic<int> winners{0};
    std::vector<std::thread> threads;
    threads.reserve(N);
    for (int i = 0; i < N; ++i) {
        threads.emplace_back([&winners]() {
            if (relief_predict_check_and_mark(7777)) {
                winners.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    for (auto& t : threads) t.join();
    TEST("under 16-way concurrency, exactly 1 winner", winners.load() == 1);
    TEST("last_marked == 7777 after race", relief_predict_last_marked() == 7777);

    // 8. The exact mainnet loop scenario:
    //    Monitor fires for height H → predict happens.
    //    Monitor restarts (cache fix → restart in <1 ms).
    //    Same height H, elapsed still > threshold → MUST NOT re-fire.
    //    Block arrives, height becomes H+1.
    //    Elapsed for H+1 starts at 0; at some point if elapsed > threshold,
    //      a new fire is allowed.
    relief_predict_reset();
    int fires = 0;
    int64_t simulated_height = 6231;  // taken from real log

    // Several poll cycles at the same height: only the first should fire.
    for (int i = 0; i < 50; ++i) {
        if (relief_predict_check_and_mark(simulated_height)) fires++;
    }
    TEST("50 polls at same height: exactly 1 fire", fires == 1);

    // New block arrives → height bumps.
    simulated_height++;
    for (int i = 0; i < 50; ++i) {
        if (relief_predict_check_and_mark(simulated_height)) fires++;
    }
    TEST("after height bump, 50 more polls: exactly 1 more fire (total 2)", fires == 2);

    // Cleanup.
    relief_predict_reset();

    printf("[relief_predict] %d pass, %d fail\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
