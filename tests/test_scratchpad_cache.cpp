// Tests for the scratchpad cache (sost/pow/scratchpad_cache.h).
//
// Covers the 8-point check requested for the public commit:
//   1. First lookup of skey_A: miss -> store
//   2. Second lookup of skey_A: hit
//   3. First lookup of skey_B (different epoch): miss -> store
//   4. cache_size() == 2
//   5. Third lookup of skey_C (third epoch): miss -> evict_lru(skey_A) -> store
//   6. cache_size() == 2 still
//   7. Re-lookup of skey_A (was evicted): miss -> rebuild
//   8. Exactly one [PRECOMP] cache_evict line emitted across the run
//
// The test redirects stdout to a buffer so we can count [PRECOMP] lines.
// Scratchpads are built with scratch_mb=1 (1 MB) for speed.

#include "sost/pow/scratchpad.h"
#include "sost/pow/scratchpad_cache.h"
#include "sost/types.h"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include <unistd.h>
#include <fcntl.h>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  EXPECT failed: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while(0)

// Small helper: build a scratchpad and stash it in the cache. Mirrors the
// pattern used by mine_one_block(): cache_get → on miss, build, cache_put.
static std::shared_ptr<std::vector<uint8_t>>
fetch_or_build(const Bytes32& skey, int32_t scratch_mb) {
    auto p = scratch_cache_get(skey);
    if (p) return p;
    auto data = std::make_shared<std::vector<uint8_t>>(
        build_scratchpad(skey, scratch_mb));
    scratch_cache_put(skey, data, scratch_mb, /*build_took_ms=*/0);
    return data;
}

// Distinct skeys (32-byte tags). We do not use the real epoch_scratch_key()
// because we want full control over which key is which. The cache only
// cares about the bytes.
static Bytes32 mk_skey(uint8_t tag) {
    Bytes32 b{};
    b.fill(0);
    b[0] = tag;
    return b;
}

// Count occurrences of needle in haystack.
static size_t count_occurrences(const std::string& haystack, const std::string& needle) {
    size_t n = 0, pos = 0;
    while ((pos = haystack.find(needle, pos)) != std::string::npos) {
        n++;
        pos += needle.size();
    }
    return n;
}

int main() {
    printf("[scratchpad_cache] start\n");

    // Reset cache so the test is independent of any other test that linked it.
    scratch_cache_clear();
    TEST("cache empty at start", scratch_cache_size() == 0);

    // Redirect stdout to a temp file so we can scan emitted [PRECOMP] lines.
    // Save the original stdout fd via dup() so we can restore it cleanly
    // afterwards (preserves the test's own pipe to ctest / `tee` etc.).
    const char* tmp = "/tmp/test_scratchpad_cache_stdout.log";
    std::remove(tmp);
    fflush(stdout);
    int saved_stdout = dup(STDOUT_FILENO);
    assert(saved_stdout >= 0);
    int tmp_fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    assert(tmp_fd >= 0);
    dup2(tmp_fd, STDOUT_FILENO);
    close(tmp_fd);

    Bytes32 skey_A = mk_skey(0xAA);
    Bytes32 skey_B = mk_skey(0xBB);
    Bytes32 skey_C = mk_skey(0xCC);
    const int32_t scratch_mb = 1;

    // 1. First lookup of skey_A: miss -> store
    auto a1 = fetch_or_build(skey_A, scratch_mb);
    bool size_eq_1 = (scratch_cache_size() == 1);

    // 2. Second lookup of skey_A: hit (no new build)
    auto a2 = scratch_cache_get(skey_A);
    bool a2_hit = (a2 != nullptr);
    bool a2_same_buffer = (a2.get() == a1.get());

    // 3. First lookup of skey_B: miss -> store
    auto b1 = fetch_or_build(skey_B, scratch_mb);

    // 4. cache_size() == 2
    bool size_eq_2_after_B = (scratch_cache_size() == 2);

    // Bump skey_B's last_access so eviction picks skey_A (LRU). A second
    // lookup of B updates its last_access_ts to "now", making A oldest.
    (void)scratch_cache_get(skey_B);

    // 5. Third lookup of skey_C: miss -> evict_lru(skey_A) -> store
    auto c1 = fetch_or_build(skey_C, scratch_mb);

    // 6. cache_size() == 2 still
    bool size_eq_2_after_C = (scratch_cache_size() == 2);

    // 7. Re-lookup of skey_A (was evicted): miss -> rebuild
    auto a3 = scratch_cache_get(skey_A);
    bool a3_was_evicted = (a3 == nullptr);

    // Restore stdout, read captured log.
    fflush(stdout);
    dup2(saved_stdout, STDOUT_FILENO);
    close(saved_stdout);
    std::ifstream in(tmp);
    std::stringstream ss;
    ss << in.rdbuf();
    std::string captured = ss.str();
    std::remove(tmp);

    // 8. Exactly one cache_evict line.
    size_t n_evict = count_occurrences(captured, "[PRECOMP] cache_evict");
    size_t n_lookup_hit_1 = count_occurrences(captured, "hit=1");
    size_t n_lookup_hit_0 = count_occurrences(captured, "hit=0");
    size_t n_store        = count_occurrences(captured, "[PRECOMP] cache_store");

    // Expected event counts:
    //   misses: A(1), B(3), C(5), A-after-evict(7) = 4 → hit=0
    //   hits:   A(2), B(extra-bump)                 = 2 → hit=1
    //   stores: 3 (A, B, C; A-after-evict is just a get, not put)
    //   evicts: 1 (A LRU when C arrives)

    TEST("size==1 after first store",                    size_eq_1);
    TEST("second lookup of A is a hit",                  a2_hit);
    TEST("second lookup returns the same buffer",        a2_same_buffer);
    TEST("size==2 after storing B",                      size_eq_2_after_B);
    TEST("size==2 after storing C (cap respected)",      size_eq_2_after_C);
    TEST("A was evicted on C arrival (LRU)",             a3_was_evicted);
    TEST("exactly 1 [PRECOMP] cache_evict line emitted", n_evict == 1);
    TEST("exactly 4 hit=0 (miss) lines emitted",         n_lookup_hit_0 == 4);
    TEST("exactly 2 hit=1 (hit) lines emitted",          n_lookup_hit_1 == 2);
    TEST("exactly 3 [PRECOMP] cache_store lines",        n_store == 3);

    // Cleanup leaves the cache empty for any other test.
    scratch_cache_clear();
    TEST("cache empty after clear", scratch_cache_size() == 0);

    printf("[scratchpad_cache] %d pass, %d fail\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
