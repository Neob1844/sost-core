// Regression: devnet stalled at h=513 with "bits_q mismatch (got=69632
// expected=65536)". getinfo/getblocktemplate computed next bitsQ from a
// 512-block window, but the pre-V6++ anchor rule needs the chain from genesis.
#include "sost/pow/casert.h"
#include "sost/casert_meta_window.h"
#include <cstdio>
#include <vector>

using namespace sost;

static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { printf("FAIL: " __VA_ARGS__); printf("\n"); ++fails; } } while (0)

// Synthetic chain: fast blocks (devnet-like, ~2 s apart) so bitsQ moves.
static std::vector<BlockMeta> make_chain(size_t n, int64_t spacing) {
    std::vector<BlockMeta> c;
    uint32_t bq = GENESIS_BITSQ;
    for (size_t i = 0; i < n; ++i) {
        BlockMeta m{}; m.height = (int64_t)i; m.time = 1773597600 + (int64_t)i * spacing; m.powDiffQ = bq;
        c.push_back(m);
        bq = casert_next_bitsq(c, (int64_t)i + 1, 0);   // full-chain rule, as validation does
    }
    return c;
}

static uint32_t windowed(const std::vector<BlockMeta>& full, size_t start, int64_t next_h, int64_t now) {
    std::vector<BlockMeta> w(full.begin() + start, full.end());
    return casert_next_bitsq(w, next_h, now);
}

int main() {
    // 1. pre-V6++ heights 500..700: new window == full chain (validation), every height.
    auto chain = make_chain(700, 2);
    int old_mismatch = 0;
    for (size_t end = 500; end <= 700; ++end) {
        std::vector<BlockMeta> prefix(chain.begin(), chain.begin() + end);
        uint32_t full = casert_next_bitsq(prefix, (int64_t)end, 0);
        uint32_t fixed = windowed(prefix, casert_meta_window_start(end), (int64_t)end, 1773597600 + (int64_t)end * 2 + 5);
        size_t old_start = end > CASERT_META_WINDOW ? end - CASERT_META_WINDOW : 0;
        uint32_t old = windowed(prefix, old_start, (int64_t)end, 1773597600 + (int64_t)end * 2 + 5);
        CHECK(fixed == full, "h=%zu fixed=%u full=%u", end, fixed, full);
        if (old != full) ++old_mismatch;
        if (end == 513) printf("h=513: full(validation)=%u old_window=%u fixed_window=%u\n", full, old, fixed);
    }
    // the old 512-window is wrong past 512 blocks on the pre-V6++ rule (the bug)
    CHECK(old_mismatch > 0, "old window never diverged — test does not reproduce the bug");
    printf("pre-V6++ 500..700: old window wrong at %d heights, fixed window wrong at 0\n", old_mismatch);

    // 2. mainnet-like heights >= V6++: helper returns exactly the old window (no behaviour change).
    for (size_t end : {(size_t)CASERT_V6PP_HEIGHT, (size_t)CASERT_V6PP_HEIGHT + 1, (size_t)20000, (size_t)30500, (size_t)40000})
        CHECK(casert_meta_window_start(end) == end - CASERT_META_WINDOW, "end=%zu start changed", end);
    // and below V6++ it is the full chain
    for (size_t end : {(size_t)0, (size_t)1, (size_t)512, (size_t)513, (size_t)5174})
        CHECK(casert_meta_window_start(end) == 0, "end=%zu not full chain", end);

    // 3. V6++ heights on a real-length chain: window == full (the original 5e3a3cfa claim still holds).
    auto longc = make_chain(5600, 600);
    for (size_t end = (size_t)CASERT_V6PP_HEIGHT; end <= 5600; end += 37) {
        std::vector<BlockMeta> prefix(longc.begin(), longc.begin() + end);
        int64_t now = prefix.back().time + 700;
        uint32_t full = casert_next_bitsq(prefix, (int64_t)end, now);
        uint32_t fixed = windowed(prefix, casert_meta_window_start(end), (int64_t)end, now);
        CHECK(fixed == full, "V6++ h=%zu fixed=%u full=%u", end, fixed, full);
    }

    printf(fails ? "FAILED %d\n" : "ALL PASS\n", fails);
    return fails ? 1 : 0;
}
