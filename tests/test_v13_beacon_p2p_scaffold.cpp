// V13 Beacon Phase III P2P scaffold tests — gate semantics under
// V13 activation.
//
// Pins the gate invariants. Pre-V13: dormant. From V13_HEIGHT onwards:
// active (the production pipeline runs in BeaconP2PState::process_incoming
// from the dispatcher; see test_v13_beacon_phase3_p2p.cpp for the
// active-path regression suite).

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
// Compile-time pins.
// ---------------------------------------------------------------------------
static_assert(BEACON_P2P_ACTIVATION_HEIGHT == V13_HEIGHT,
              "Beacon Phase III P2P is gated at V13_HEIGHT. "
              "If a follow-up commit changes the gate, update this "
              "static_assert deliberately.");

static_assert(BEACON_P2P_NOTICE_MAX_BYTES   == 4 * 1024,
              "Phase III on-wire size cap pinned at 4 KiB.");
static_assert(BEACON_P2P_CACHE_MAX_NOTICES  == 32,
              "Phase III in-memory cache cap pinned at 32 notices.");
static_assert(BEACON_P2P_PEER_RATE_PER_MIN  == 8,
              "Phase III per-peer rate cap pinned at 8 new notices / min.");

// ---------------------------------------------------------------------------
// is_p2p_enabled: dormant below V13_HEIGHT, active at and above.
// ---------------------------------------------------------------------------
static void test_is_p2p_enabled_gate_at_v13() {
    printf("\n=== is_p2p_enabled - gated at V13_HEIGHT (active at V13) ===\n");
    // Pre-V13: disabled.
    TEST("h=0          -> disabled (pre-V13)",       !is_p2p_enabled(0));
    TEST("h=11999      -> disabled (pre-V13)",       !is_p2p_enabled(11999));
    // At and after V13_HEIGHT: enabled.
    TEST("h=V13_HEIGHT -> enabled (gate inclusive)", is_p2p_enabled(V13_HEIGHT));
    TEST("h=V13_HEIGHT+1 -> enabled",                is_p2p_enabled(V13_HEIGHT + 1));
    TEST("h=20000      -> enabled",                  is_p2p_enabled(20000));
    TEST("h=2^60       -> enabled",                  is_p2p_enabled((int64_t)1 << 60));
    TEST("h=INT64_MAX  -> enabled (comparison branch)",
         is_p2p_enabled(INT64_MAX));
}

// ---------------------------------------------------------------------------
// handle_incoming_notice_message: dormant for h < V13_HEIGHT.
// The legacy entry point (kept for backwards-compat with this scaffold)
// returns DiscardDormant before allocation when the gate is closed.
// ---------------------------------------------------------------------------
static void test_handler_dormant_below_gate() {
    printf("\n=== handle_incoming_notice_message - dormant for h < V13_HEIGHT ===\n");
    TEST("empty payload @ h=0           -> DiscardDormant",
         handle_incoming_notice_message(std::string(), 0)
             == IncomingDecision::DiscardDormant);
    TEST("short payload @ h=11999       -> DiscardDormant",
         handle_incoming_notice_message("abc", 11999)
             == IncomingDecision::DiscardDormant);
    TEST("medium payload @ h=11000      -> DiscardDormant",
         handle_incoming_notice_message(std::string(512, 'a'), 11000)
             == IncomingDecision::DiscardDormant);
    TEST("oversized payload @ h=11500   -> DiscardDormant (gate before size check)",
         handle_incoming_notice_message(
             std::string(BEACON_P2P_NOTICE_MAX_BYTES + 1, 'X'), 11500)
             == IncomingDecision::DiscardDormant);
}

// ---------------------------------------------------------------------------
// decision_name covers every enum value.
// ---------------------------------------------------------------------------
static void test_decision_name_complete() {
    printf("\n=== decision_name - every enum value mapped ===\n");
    auto check = [](IncomingDecision d, const char* expected) {
        const char* got = decision_name(d);
        bool ok = got && std::string(got) == expected;
        char buf[128];
        std::snprintf(buf, sizeof(buf), "%s -> \"%s\"", expected, got ? got : "(null)");
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
    printf("\n=== V13 Beacon Phase III P2P scaffold tests ===\n");
    printf("BEACON_P2P_ACTIVATION_HEIGHT = %lld  (V13_HEIGHT = active at V13)\n",
           (long long)BEACON_P2P_ACTIVATION_HEIGHT);
    printf("BEACON_P2P_NOTICE_MAX_BYTES  = %zu\n", BEACON_P2P_NOTICE_MAX_BYTES);
    printf("BEACON_P2P_CACHE_MAX_NOTICES = %zu\n", BEACON_P2P_CACHE_MAX_NOTICES);
    printf("BEACON_P2P_PEER_RATE_PER_MIN = %d\n",  BEACON_P2P_PEER_RATE_PER_MIN);

    test_is_p2p_enabled_gate_at_v13();
    test_handler_dormant_below_gate();
    test_decision_name_complete();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
