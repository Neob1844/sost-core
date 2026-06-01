// test_dtd_control.cpp — DTD lottery emergency pause/resume control.
//
// Exercises the pure reference state machine in src/dtd_control.cpp:
//   - valid PAUSE / RESUME accepted; pause takes effect at effective_height
//   - DTD chokepoint falls back to normal split while paused (effect layer)
//   - invalid signature rejected, state unchanged
//   - replay protection (equal / lower nonce rejected, higher accepted)
//   - wrong chain tag rejected
//   - below-minimum effective height rejected
//   - expiry rejected
//   - pre-effective-height: signal accepted but pause not yet in force
//   - reorg: undo_dtd_control restores prior state
//   - consensus-deferred no-op: with the shipped flag false,
//     is_dtd_emergency_paused_at == false and is_dtd_lottery_active_at ==
//     sost::lottery::is_lottery_block (replay-identical)
//
// Pure; no Schnorr / secp dependency; built unconditionally.

#include "sost/dtd_control.h"
#include "sost/params.h"
#include "sost/lottery.h"

#include <cstdio>
#include <string>

using namespace sost;
using namespace sost::dtd_control;

static int g_pass = 0, g_fail = 0;
static void check(bool c, const char* what) {
    if (c) { ++g_pass; }
    else   { ++g_fail; printf("  FAIL: %s\n", what); }
}

// A non-zero chain tag standing in for sha256(MAGIC_MAINNET) in these pure
// tests. The state machine only needs equality against expected_chain_tag.
static Bytes32 chain_tag(uint8_t b) { Bytes32 t{}; t.fill(b); return t; }

static DTDControlMessage make_msg(DTDAction action,
                                  uint64_t nonce,
                                  int64_t effective_height,
                                  const Bytes32& tag) {
    DTDControlMessage m;
    m.version          = DTD_CONTROL_VERSION;
    m.chain_tag        = tag;
    m.action           = action;
    m.effective_height = effective_height;
    m.nonce            = nonce;
    m.reason_hash      = chain_tag(0xAB);
    m.created_at_height= effective_height - 10;
    m.expiry_height    = 0;          // no expiry by default
    m.key_id           = 0;
    return m;
}

static const Bytes32 TAG = chain_tag(0x11);
static const int64_t EFF = DTD_EMERGENCY_CONTROL_MIN_HEIGHT + 100;  // valid height

// ---------------------------------------------------------------------------
static void test_valid_pause_then_resume() {
    DTDControlState st;
    auto pause = make_msg(DTDAction::PAUSE_DTD, 1, EFF, TAG);
    auto rp = apply_dtd_control(st, pause, /*sig*/true, TAG, /*tip*/EFF);
    check(rp.code == DTDApplyCode::ACCEPTED_PAUSE, "pause accepted");
    check(rp.state_changed, "pause changed state");
    check(st.paused, "state paused after pause");
    check(st.last_nonce == 1, "nonce recorded = 1");
    // core effect: paused from EFF onward, not before
    check(!is_dtd_emergency_paused_core(st, EFF - 1), "not paused below effective_height");
    check(is_dtd_emergency_paused_core(st, EFF),       "paused at effective_height");
    check(is_dtd_emergency_paused_core(st, EFF + 50),  "paused above effective_height");

    auto resume = make_msg(DTDAction::RESUME_DTD, 2, EFF + 200, TAG);
    auto rr = apply_dtd_control(st, resume, true, TAG, EFF + 200);
    check(rr.code == DTDApplyCode::ACCEPTED_RESUME, "resume accepted");
    check(!st.paused, "state not paused after resume");
    check(st.last_nonce == 2, "nonce advanced to 2");
    check(!is_dtd_emergency_paused_core(st, EFF + 1000), "not paused after resume");
}

// ---------------------------------------------------------------------------
static void test_invalid_signature_rejected() {
    DTDControlState st;
    auto pause = make_msg(DTDAction::PAUSE_DTD, 5, EFF, TAG);
    auto r = apply_dtd_control(st, pause, /*sig*/false, TAG, EFF);
    check(r.code == DTDApplyCode::REJECTED_BAD_SIG, "bad sig rejected");
    check(!r.state_changed, "bad sig did not change state");
    check(!st.paused && st.last_nonce == 0, "state untouched after bad sig");
}

// ---------------------------------------------------------------------------
static void test_replay_protection() {
    DTDControlState st;
    auto m1 = make_msg(DTDAction::PAUSE_DTD, 10, EFF, TAG);
    check(apply_dtd_control(st, m1, true, TAG, EFF).accepted(), "nonce 10 accepted");

    auto same = make_msg(DTDAction::RESUME_DTD, 10, EFF, TAG);
    auto rs = apply_dtd_control(st, same, true, TAG, EFF);
    check(rs.code == DTDApplyCode::REJECTED_REPLAY_NONCE, "equal nonce rejected");
    check(st.paused, "state unchanged on equal-nonce replay");

    auto lower = make_msg(DTDAction::RESUME_DTD, 9, EFF, TAG);
    check(apply_dtd_control(st, lower, true, TAG, EFF).code ==
          DTDApplyCode::REJECTED_REPLAY_NONCE, "lower nonce rejected");

    auto higher = make_msg(DTDAction::RESUME_DTD, 11, EFF, TAG);
    check(apply_dtd_control(st, higher, true, TAG, EFF).accepted(), "higher nonce accepted");
    check(st.last_nonce == 11, "nonce advanced to 11");
}

// ---------------------------------------------------------------------------
static void test_wrong_chain_rejected() {
    DTDControlState st;
    auto m = make_msg(DTDAction::PAUSE_DTD, 1, EFF, chain_tag(0x99));  // wrong tag
    auto r = apply_dtd_control(st, m, true, TAG, EFF);
    check(r.code == DTDApplyCode::REJECTED_WRONG_CHAIN, "wrong chain rejected");
    check(!st.paused, "state untouched on wrong chain");
}

// ---------------------------------------------------------------------------
static void test_below_min_height_rejected() {
    DTDControlState st;
    auto m = make_msg(DTDAction::PAUSE_DTD, 1,
                      DTD_EMERGENCY_CONTROL_MIN_HEIGHT - 1, TAG);
    auto r = apply_dtd_control(st, m, true, TAG, DTD_EMERGENCY_CONTROL_MIN_HEIGHT);
    check(r.code == DTDApplyCode::REJECTED_BELOW_MIN, "below-min effective height rejected");
}

// ---------------------------------------------------------------------------
static void test_expiry_rejected() {
    DTDControlState st;
    auto m = make_msg(DTDAction::PAUSE_DTD, 1, EFF, TAG);
    m.expiry_height = EFF + 100;
    // tip already at/after expiry → rejected
    auto r = apply_dtd_control(st, m, true, TAG, EFF + 100);
    check(r.code == DTDApplyCode::REJECTED_EXPIRED, "expired message rejected");
    // tip before expiry → accepted
    auto r2 = apply_dtd_control(st, m, true, TAG, EFF + 99);
    check(r2.accepted(), "non-expired message accepted");
}

// ---------------------------------------------------------------------------
static void test_pre_effective_height_no_effect() {
    DTDControlState st;
    auto pause = make_msg(DTDAction::PAUSE_DTD, 1, EFF + 500, TAG);
    auto r = apply_dtd_control(st, pause, true, TAG, EFF);  // published early
    check(r.accepted(), "early-published pause accepted into state");
    check(st.paused, "paused flag set");
    // but the EFFECT does not bite until effective_height
    check(!is_dtd_emergency_paused_core(st, EFF + 499), "no effect below effective_height");
    check(is_dtd_emergency_paused_core(st, EFF + 500),  "effect at effective_height");
}

// ---------------------------------------------------------------------------
static void test_reorg_undo() {
    DTDControlState st;
    auto m1 = make_msg(DTDAction::PAUSE_DTD, 7, EFF, TAG);
    apply_dtd_control(st, m1, true, TAG, EFF);

    DTDControlState before = st;
    auto m2 = make_msg(DTDAction::RESUME_DTD, 8, EFF + 10, TAG);
    auto applied = apply_dtd_control(st, m2, true, TAG, EFF + 10);
    check(applied.accepted() && !st.paused, "resume applied");

    undo_dtd_control(st, applied);
    check(st.paused == before.paused, "undo restored paused flag");
    check(st.last_nonce == before.last_nonce, "undo restored nonce");
    check(st.last_action == before.last_action, "undo restored action");

    // undo of a rejected apply is a no-op
    auto rej = apply_dtd_control(st, make_msg(DTDAction::PAUSE_DTD, 1, EFF, TAG),
                                 true, TAG, EFF);  // nonce 1 <= 7 → replay reject
    check(!rej.accepted(), "stale nonce rejected post-undo");
    DTDControlState snap = st;
    undo_dtd_control(st, rej);
    check(st.last_nonce == snap.last_nonce, "undo of rejected apply is a no-op");
}

// ---------------------------------------------------------------------------
static void test_canonical_payload_deterministic() {
    auto m = make_msg(DTDAction::PAUSE_DTD, 42, EFF, TAG);
    std::string a = canonical_payload(m);
    std::string b = canonical_payload(m);
    check(a == b, "canonical payload stable for identical input");
    check(a.find("SOST_DTD_CONTROL_V1") == 0, "payload starts with magic");
    check(a.find("action=PAUSE_DTD") != std::string::npos, "payload carries action text");
    check(a.find("nonce=42") != std::string::npos, "payload carries nonce");
    // any field change perturbs the preimage
    auto m2 = m; m2.nonce = 43;
    check(canonical_payload(m2) != a, "payload changes when a field changes");
}

// ---------------------------------------------------------------------------
// Consensus-deferred no-op: with the shipped flag false, the brake never
// affects consensus and the chokepoint equals is_lottery_block everywhere.
static void test_consensus_deferred_noop() {
    check(DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE == false,
          "control ships consensus-INACTIVE");

    DTDControlState st;
    // Force a 'paused' state that WOULD bite if the flag were on.
    apply_dtd_control(st, make_msg(DTDAction::PAUSE_DTD, 1, EFF, TAG), true, TAG, EFF);
    check(is_dtd_emergency_paused_core(st, EFF + 1), "core says paused");
    check(!is_dtd_emergency_paused_at(st, EFF + 1),
          "consensus-facing pause is false while flag off");

    // is_dtd_lottery_active_at must equal is_lottery_block at every sampled
    // height around the DTD schedule, regardless of the paused state.
    const int64_t H = V11_PHASE2_HEIGHT;
    bool identical = true;
    for (int64_t h = H; h < H + 30; ++h) {
        if (is_dtd_lottery_active_at(h, H, st) != lottery::is_lottery_block(h, H)) {
            identical = false; break;
        }
    }
    check(identical, "chokepoint == is_lottery_block while flag off (replay-identical)");
}

int main() {
    printf("=== DTD emergency pause/resume control ===\n");
    test_valid_pause_then_resume();
    test_invalid_signature_rejected();
    test_replay_protection();
    test_wrong_chain_rejected();
    test_below_min_height_rejected();
    test_expiry_rejected();
    test_pre_effective_height_no_effect();
    test_reorg_undo();
    test_canonical_payload_deterministic();
    test_consensus_deferred_noop();
    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
