#include "sost/pow/relief_predict.h"

#include <atomic>

namespace sost {

namespace {
// Last height for which RELIEF-PREDICT has already fired. -1 means "never".
std::atomic<int64_t> g_last_marked_height{-1};
} // namespace

bool relief_predict_check_and_mark(int64_t height) {
    int64_t expected = g_last_marked_height.load(std::memory_order_acquire);
    while (expected != height) {
        if (g_last_marked_height.compare_exchange_weak(
                expected, height,
                std::memory_order_release,
                std::memory_order_acquire)) {
            return true;  // we won the CAS — fire
        }
        // expected was reloaded by compare_exchange_weak; loop and recheck.
    }
    return false;  // already marked for this height
}

void relief_predict_reset() {
    g_last_marked_height.store(-1, std::memory_order_release);
}

int64_t relief_predict_last_marked() {
    return g_last_marked_height.load(std::memory_order_acquire);
}

} // namespace sost
