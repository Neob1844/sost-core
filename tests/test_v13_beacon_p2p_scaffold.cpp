// V13 Beacon Phase III P2P scaffold — disabled-by-default tests.
//
// Pins the dormancy invariants. The whole point of this test is that
// the scaffold cannot accidentally come alive without an explicit
// commit that lowers BEACON_P2P_ACTIVATION_HEIGHT below INT64_MAX.

#include "sost/beacon_p2p.h"
#include "sost/params.h"

#include <cstdio>
#include <cstdint>
#include <climits>
#include <string>

using namespace sost;
using namespace sost::beacon::p2p;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Compile-time pins: the gate sentinel is the structural guarantee
// that the scaffold cannot fire. If a future commit lowers the gate,
// these static_asserts force a deliberate edit here as well.
// ---------------------------------------------------------------------------
static_assert(BEACON_P2P_ACTIVATION_HEIGHT == INT64_MAX,
              "Beacon Phase III P2P must remain DISABLED-by-default. "
              "The sentinel INT64_MAX is the single switch keeping the "
              "scaffold from gossiping. Lowering it requires a deliberate "
              "fork plan and updates here.");

static_assert(BEACON_P2P_NOTICE_MAX_BYTES   == 4 * 1024,
              "Phase III on-wire size cap pinned at 4 KiB.");
static_assert(BEACON_P2P_CACHE_MAX_NOTICES  == 32,
              "Phase III in-memory cache cap pinned at 32 notices.");
static_assert(BEACON_P2P_PEER_RATE_PER_MIN  == 8,
              "Phase III per-peer rate cap pinned at 8 new notices / min.");

// ---------------------------------------------------------------------------
// is_p2p_enabled: always false today, at every finite height.
// ---------------------------------------------------------------------------
static void test_is_p2p_enabled_always_false() {
    printf("\n=== is_p2p_enabled — disabled at every finite height ===\n");
    TEST("h=0          → disabled",            !is_p2p_enabled(0));
    TEST("h=11999      → disabled",            !is_p2p_enabled(11999));
    TEST("h=V13_HEIGHT → disabled (Phase II-A is enough; III stays off)",
         !is_p2p_enabled(V13_HEIGHT));
    TEST("h=20000      → disabled",            !is_p2p_enabled(20000));
    TEST("h=2^60       → disabled",            !is_p2p_enabled((int64_t)1 << 60));
    // INT64_MAX itself: cmp is `current_height >= BEACON_P2P_ACTIVATION_HEIGHT`,
    // and since BEACON_P2P_ACTIVATION_HEIGHT == INT64_MAX, the only height
    // that would make this true is INT64_MAX itself. The chain will never
    // reach there, so this is documentation only — but the test pins the
    // semantic so a future change cannot silently flip it.
    TEST("h=INT64_MAX  → enabled (degenerate edge — chain never reaches)",
         is_p2p_enabled(INT64_MAX));
}

// ---------------------------------------------------------------------------
// handle_incoming_notice_message: always DiscardDormant today.
// Exercises the function with a variety of inputs to confirm none can
// reach the live path (no allocation, no parse, no signature work).
// ---------------------------------------------------------------------------
static void test_handler_always_dormant() {
    printf("\n=== handle_incoming_notice_message — always Dormant ===\n");

    const std::string empty_bytes;
    const std::string short_bytes  = "{}";
    const std::string medium_bytes(512, 'x');
    const std::string oversized   (BEACON_P2P_NOTICE_MAX_BYTES + 1, 'x');

    TEST("empty payload @ h=0       → DiscardDormant",
         handle_incoming_notice_message(empty_bytes,  0)
             == IncomingDecision::DiscardDormant);
    TEST("short payload @ h=12000   → DiscardDormant",
         handle_incoming_notice_message(short_bytes,  V13_HEIGHT)
             == IncomingDecision::DiscardDormant);
    TEST("medium payload @ h=20000  → DiscardDormant",
         handle_incoming_notice_message(medium_bytes, 20000)
             == IncomingDecision::DiscardDormant);
    // Oversized: while the gate is closed we MUST NOT even produce
    // DiscardOversized — the dormancy short-circuit precedes the
    // size check. This pins that order: dormant-first, no work after.
    TEST("oversized payload @ h=20000 → DiscardDormant (dormancy precedes size check)",
         handle_incoming_notice_message(oversized,    20000)
             == IncomingDecision::DiscardDormant);
}

// ---------------------------------------------------------------------------
// decision_name covers the full enum (compile-time check via switch
// fall-through, runtime spot check that strings are non-null).
// ---------------------------------------------------------------------------
static void test_decision_name_complete() {
    printf("\n=== decision_name — every enum value mapped ===\n");
    auto check = [](IncomingDecision d, const char* expected) {
        const char* got = decision_name(d);
        bool ok = got && std::string(got) == expected;
        char buf[128];
        std::snprintf(buf, sizeof(buf), "%s → \"%s\"", expected, got ? got : "(null)");
        if (ok) { printf("  PASS: %s\n", buf); g_pass++; }
        else    { printf("  *** FAIL: %s\n", buf); g_fail++; }
    };
    check(IncomingDecision::DiscardDormant,      "DiscardDormant");
    check(IncomingDecision::DiscardOversized,    "DiscardOversized");
    check(IncomingDecision::DiscardMalformed,    "DiscardMalformed");
    check(IncomingDecision::DiscardBadSignature, "DiscardBadSignature");
    check(IncomingDecision::DiscardExpired,      "DiscardExpired");
    check(IncomingDecision::DiscardWrongNetwork, "DiscardWrongNetwork");
    check(IncomingDecision::DiscardDuplicate,    "DiscardDuplicate");
    check(IncomingDecision::DiscardRateLimited,  "DiscardRateLimited");
    check(IncomingDecision::AcceptAndRelay,      "AcceptAndRelay");
}

int main() {
    printf("\n=== V13 Beacon Phase III P2P scaffold — DISABLED tests ===\n");
    printf("BEACON_P2P_ACTIVATION_HEIGHT = %lld  (INT64_MAX = DISABLED)\n",
           (long long)BEACON_P2P_ACTIVATION_HEIGHT);
    printf("BEACON_P2P_NOTICE_MAX_BYTES  = %zu\n", BEACON_P2P_NOTICE_MAX_BYTES);
    printf("BEACON_P2P_CACHE_MAX_NOTICES = %zu\n", BEACON_P2P_CACHE_MAX_NOTICES);
    printf("BEACON_P2P_PEER_RATE_PER_MIN = %d\n",  BEACON_P2P_PEER_RATE_PER_MIN);

    test_is_p2p_enabled_always_false();
    test_handler_always_dormant();
    test_decision_name_complete();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
