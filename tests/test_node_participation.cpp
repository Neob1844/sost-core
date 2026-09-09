// ============================================================================
// test_node_participation — V16 NODE_BIND / NODE_HEARTBEAT tx layer.
// Byte-exact serialization + round-trip, REAL Schnorr sign+verify, activation
// guard (#29,999 reject / #30,000 accept), heartbeat epoch/tip_ref rules,
// reorg-safe NodeState apply/undo (== fresh recompute), bind_acceptable state
// rules, and the FINAL-eligibility metric (PoW-eligible vs after node gate).
// ============================================================================
#include "sost/node_participation.h"
#include "sost/jackpot_v2.h"
#include "sost/sbpow.h"
#include "sost/params.h"

#include <cstdio>
#include <vector>

using namespace sost;
using namespace sost::node_participation;
using namespace sost::jackpot_v2;
using namespace sost::sbpow;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { ++g_pass; printf("  PASS: %s\n", msg); } \
    else      { ++g_fail; printf("  FAIL: %s\n", msg); } \
} while (0)

static const int64_t A = 30000, L = 288;

// Deterministic keypair from a seed byte (a filled 32-byte scalar is a valid key).
static bool make_key(uint8_t seed, MinerPrivkey& sk, MinerPubkey& pk) {
    sk.fill(seed ? seed : 1);
    return derive_compressed_pubkey_from_privkey(sk, pk);
}

static NodeBindTx make_bind(uint8_t mseed, uint8_t nseed, uint64_t seq) {
    NodeBindTx t;
    MinerPrivkey msk, nsk; MinerPubkey mpk, npk;
    make_key(mseed, msk, mpk); make_key(nseed, nsk, npk);
    t.mining_pubkey = mpk; t.node_pubkey = npk; t.bind_seq = seq;
    PubKeyHash pkh = derive_pkh_from_pubkey(mpk);
    Bytes32 msg = bind_message(pkh, npk, seq);
    sign_sbpow_commitment(msk, msg, t.mining_sig);
    return t;
}

static NodeHeartbeatTx make_hb(uint8_t nseed, uint64_t epoch, const Bytes32& tipref) {
    NodeHeartbeatTx t;
    MinerPrivkey nsk; MinerPubkey npk; make_key(nseed, nsk, npk);
    t.node_pubkey = npk; t.epoch_idx = epoch; t.tip_ref_hash = tipref;
    Bytes32 msg = heartbeat_message(npk, epoch, tipref);
    sign_sbpow_commitment(nsk, msg, t.node_sig);
    return t;
}

// ---------------------------------------------------------------------------
static void test_serialization() {
    NodeBindTx b = make_bind(2, 3, 7);
    auto sb = serialize_bind(b);
    TEST("NODE_BIND serialized == 138 bytes", sb.size() == NODE_BIND_WIRE_BYTES && sb.size() == 138);
    NodeBindTx b2;
    TEST("NODE_BIND round-trips", deserialize_bind(sb, b2)
         && b2.mining_pubkey == b.mining_pubkey && b2.node_pubkey == b.node_pubkey
         && b2.bind_seq == b.bind_seq && b2.mining_sig == b.mining_sig);

    Bytes32 tip{}; tip.fill(0x5a);
    NodeHeartbeatTx h = make_hb(3, 4, tip);
    auto sh = serialize_heartbeat(h);
    TEST("NODE_HEARTBEAT serialized == 137 bytes", sh.size() == NODE_HEARTBEAT_WIRE_BYTES && sh.size() == 137);
    NodeHeartbeatTx h2;
    TEST("NODE_HEARTBEAT round-trips", deserialize_heartbeat(sh, h2)
         && h2.node_pubkey == h.node_pubkey && h2.epoch_idx == h.epoch_idx
         && h2.tip_ref_hash == h.tip_ref_hash && h2.node_sig == h.node_sig);
    printf("  [MEASURED] NODE_BIND=%zuB  NODE_HEARTBEAT=%zuB\n", sb.size(), sh.size());
}

// ---------------------------------------------------------------------------
static void test_bind_validation_and_activation_guard() {
    NodeBindTx b = make_bind(2, 3, 1);
    // activation guard
    TEST("#29,999 NODE_BIND rejected (before_activation)",
         !check_bind(b, 29999).ok && std::string(check_bind(b, 29999).reason) == "before_activation");
    auto ok = check_bind(b, 30000);
    TEST("#30,000 NODE_BIND accepted (valid sig)", ok.ok);
    TEST("mining_pkh derived matches", ok.mining_pkh == derive_pkh_from_pubkey(b.mining_pubkey));
    // tamper signature
    NodeBindTx bad = b; bad.mining_sig[0] ^= 0xFF;
    TEST("tampered NODE_BIND sig rejected",
         !check_bind(bad, 30000).ok && std::string(check_bind(bad, 30000).reason) == "bad_signature");
    // wrong bind_seq in message (re-sign for seq 1 but present seq 2) -> sig fails
    NodeBindTx mism = b; mism.bind_seq = 999;
    TEST("NODE_BIND seq mismatch vs signed message rejected", !check_bind(mism, 30000).ok);
}

// ---------------------------------------------------------------------------
static void test_heartbeat_validation() {
    Bytes32 tipref{}; tipref.fill(0x11);
    // epoch of inclusion #30,290 with A=30000,L=288 -> (290)/288 = 1
    int64_t incl = 30290;
    int64_t e = jv2_epoch_of_height(A, L, incl);
    NodeHeartbeatTx h = make_hb(3, (uint64_t)e, tipref);
    TEST("valid heartbeat accepted", check_heartbeat(h, incl, A, L, tipref).ok);
    // wrong epoch (future/late)
    NodeHeartbeatTx hf = make_hb(3, (uint64_t)e + 1, tipref);
    TEST("wrong-epoch heartbeat rejected",
         std::string(check_heartbeat(hf, incl, A, L, tipref).reason) == "wrong_epoch");
    // bad tip_ref
    Bytes32 other{}; other.fill(0x22);
    TEST("bad tip_ref rejected",
         std::string(check_heartbeat(h, incl, A, L, other).reason) == "bad_tip_ref");
    // before activation
    TEST("#29,999 heartbeat rejected",
         std::string(check_heartbeat(h, 29999, A, L, tipref).reason) == "before_activation");
    // tampered node sig
    NodeHeartbeatTx ht = h; ht.node_sig[10] ^= 0xFF;
    TEST("tampered heartbeat sig rejected",
         std::string(check_heartbeat(ht, incl, A, L, tipref).reason) == "bad_signature");
}

// ---------------------------------------------------------------------------
static NodePubKey npk_of(uint8_t nseed) { MinerPrivkey sk; MinerPubkey pk; make_key(nseed, sk, pk); return pk; }
static PubKeyHash mpkh_of(uint8_t mseed) { MinerPrivkey sk; MinerPubkey pk; make_key(mseed, sk, pk); return derive_pkh_from_pubkey(pk); }

static void test_state_reorg_and_rules() {
    NodeState s;
    PubKeyHash m1 = mpkh_of(2), m2 = mpkh_of(5);
    NodePubKey n1 = npk_of(3),  n2 = npk_of(4), n3 = npk_of(6);

    // effective at inclusion+1
    s.apply_bind(m1, n1, /*seq*/1, /*incl*/30100);
    TEST("bind inactive at inclusion height", !s.is_node_bound(m1, 30100));
    TEST("bind active at inclusion+1",         s.is_node_bound(m1, 30101));

    // bind_acceptable rules
    TEST("lower/equal seq not acceptable",  !s.bind_acceptable(m1, n2, 1, 30200));
    TEST("higher seq acceptable",            s.bind_acceptable(m1, n2, 2, 30200));
    TEST("node key owned by m1 not acceptable for m2", !s.bind_acceptable(m2, n1, 1, 30200));

    // rotation
    s.apply_bind(m1, n2, 2, 30120);
    TEST("rotation -> active key n2", s.active_bindings(30200)[m1].node_pubkey == n2);
    TEST("m2 cannot claim rotated-away n1", !s.bind_acceptable(m2, n1, 1, 30200));

    // undo restores exactly (reorg of the rotation)
    s.undo_bind();
    TEST("undo rotation -> active key back to n1", s.active_bindings(30200)[m1].node_pubkey == n1);

    // divergent reapply (reorg to a different branch) -> state == fresh recompute
    s.apply_bind(m2, n3, 1, 30130);
    std::vector<NodeBindRecord> expected = {
        {m1, n1, 1, 30100}, {m2, n3, 1, 30130},
    };
    auto fresh = jv2_active_bindings_at(expected, 30200);
    auto live  = s.active_bindings(30200);
    TEST("incremental state == fresh from-chain recompute (reorg-safe)",
         live.size() == fresh.size()
         && live[m1].node_pubkey == fresh[m1].node_pubkey
         && live[m2].node_pubkey == fresh[m2].node_pubkey);

    // heartbeat apply resolves owner via active binding; dedup + undo
    // at inclusion 30130+ , n3 is active for m2
    bool applied = s.apply_heartbeat(n3, /*epoch*/3, /*incl*/31400);
    TEST("heartbeat by active node key recorded to owner", applied);
    bool unknown = s.apply_heartbeat(npk_of(99), 3, 31400);
    TEST("heartbeat by unbound node key not recorded", !unknown);
    s.undo_heartbeat();  // pop the m2 heartbeat
    TEST("undo heartbeat pops record", s.heartbeats().empty());
}

// ---------------------------------------------------------------------------
// FINAL eligibility metric: PoW-eligible vs after the full node gate.
static void test_final_eligibility_metric() {
    // 6 PoW-eligible miners (mirrors the real replay: >=3 blocks/5000)
    struct P { uint8_t seed; int64_t blocks; };
    std::vector<P> miners = {{10,2542},{11,1365},{12,864},{13,38},{14,12},{15,3}};

    NodeState s;
    // Only miners 10, 11, 12 register a node bind (before the jackpot) and heartbeat.
    // effective at inclusion+1; jackpot height H below is well past.
    int64_t H = 31338;                       // permanent 3/4 window
    for (uint8_t seed : {10, 11, 12}) {
        PubKeyHash m = mpkh_of(seed);
        NodePubKey n = npk_of((uint8_t)(seed + 100));
        s.apply_bind(m, n, 1, 30050);
        // give heartbeats in epochs 0..3 (>= required 3)
        for (int e = 0; e <= 3; ++e) s.apply_heartbeat(n, e, 30060 + e * (int)L);
    }

    int pow_eligible = 0, final_eligible = 0;
    for (auto& p : miners) {
        PubKeyHash m = mpkh_of(p.seed);
        if (p.blocks >= JACKPOT_V2_MIN_BLOCKS) ++pow_eligible;
        JackpotV2Candidate c;
        c.mining_pkh = m; c.sbpow_valid = true; c.pow_blocks = p.blocks;
        c.node_bound = s.is_node_bound(m, H);
        c.heartbeats_in_window = s.heartbeats_in_window(m, A, L, H);
        if (jv2_is_eligible(c, A, L, H)) ++final_eligible;
    }
    printf("  [METRIC] POW_ELIGIBLE=%d  FINAL_ELIGIBLE_AFTER_NODE_GATE=%d\n", pow_eligible, final_eligible);
    TEST("PoW-eligible == 6", pow_eligible == 6);
    TEST("node gate reduces to the 3 that bound + heartbeat", final_eligible == 3);
}

// ---------------------------------------------------------------------------
int main() {
    printf("== test_node_participation (V16 NODE_BIND/HEARTBEAT tx layer) ==\n");
    test_serialization();
    test_bind_validation_and_activation_guard();
    test_heartbeat_validation();
    test_state_reorg_and_rules();
    test_final_eligibility_metric();
    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
