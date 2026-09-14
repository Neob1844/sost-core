// ============================================================================
// test_node_participation — V16 NODE_BIND / NODE_HEARTBEAT tx layer.
// Byte-exact serialization + round-trip, REAL Schnorr sign+verify, activation
// guard (#29,999 reject / #30,000 accept), heartbeat epoch/tip_ref rules,
// reorg-safe NodeState apply/undo (== fresh recompute), bind_acceptable state
// rules, and the FINAL-eligibility metric (PoW-eligible vs after node gate).
// ============================================================================
#include "sost/node_participation.h"
#include "sost/jackpot_v2.h"
#include "sost/jackpot.h"
#include "sost/sbpow.h"
#include "sost/params.h"

#include <cstdio>
#include <vector>
#include <functional>

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

static PubKeyHash pkh(uint8_t b) { PubKeyHash p{}; p.fill(b); return p; }
static JackpotV2Candidate cand(uint8_t b, int64_t pow, bool bound, int64_t hb, bool sbpow = true) {
    JackpotV2Candidate c;
    c.mining_pkh = pkh(b); c.sbpow_valid = sbpow; c.pow_blocks = pow;
    c.node_bound = bound; c.heartbeats_in_window = hb;
    return c;
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
// Block-level processing: two-phase, order-independent, same-block caps, reorg.
static Bytes32 TIP0() { Bytes32 t{}; t.fill(0x77); return t; }
// canonical block hash lookup for the tests: epoch 0 tip_ref (#29,999) = TIP0.
static bool block_hash_at(int64_t h, Bytes32& out) {
    if (h == 29999) { out = TIP0(); return true; }
    Bytes32 t{}; t.fill((uint8_t)(h & 0xff)); out = t; return true;
}

static void test_block_processing() {
    NodeState s;
    // pre-block: m1 (seed2) binds n1 (seed3) at #30,010 -> active from #30,011
    {
        BlockNodeTxs b; b.binds.push_back(make_bind(2, 3, 1));
        auto r = connect_block_node_txs(s, b, 30010, A, L, block_hash_at);
        TEST("pre-block bind connects", r.ok && r.binds_applied == 1);
    }
    const int64_t H = 30060;                 // epoch 0
    Bytes32 tip = TIP0();

    // (a) heartbeat by the OLD active key n1 -> valid (order independent)
    {
        BlockNodeTxs b; b.heartbeats.push_back(make_hb(3, 0, tip));
        NodeState t = s;                     // copy
        auto r = connect_block_node_txs(t, b, H, A, L, block_hash_at);
        TEST("heartbeat by pre-block active key accepted", r.ok && r.hbs_applied == 1);
    }
    // (b) same-block bind(new key n2) + heartbeat signed by the NEW key -> INVALID,
    //     regardless of tx order.
    {
        BlockNodeTxs b1; b1.binds.push_back(make_bind(2, 4, 2)); b1.heartbeats.push_back(make_hb(4, 0, tip));
        NodeState t1 = s; auto r1 = connect_block_node_txs(t1, b1, H, A, L, block_hash_at);
        BlockNodeTxs b2; b2.heartbeats.push_back(make_hb(4, 0, tip)); b2.binds.push_back(make_bind(2, 4, 2));
        NodeState t2 = s; auto r2 = connect_block_node_txs(t2, b2, H, A, L, block_hash_at);
        TEST("same-block new-key heartbeat INVALID (bind-first order)",
             !r1.ok && std::string(r1.reason) == "heartbeat_node_not_active_preblock");
        TEST("same-block new-key heartbeat INVALID (heartbeat-first order)",
             !r2.ok && std::string(r2.reason) == "heartbeat_node_not_active_preblock");
    }
    // (c) same-block double bind for one miner -> INVALID
    {
        BlockNodeTxs b; b.binds.push_back(make_bind(2, 4, 2)); b.binds.push_back(make_bind(2, 8, 3));
        NodeState t = s; auto r = connect_block_node_txs(t, b, H, A, L, block_hash_at);
        TEST("same-block double bind for one miner INVALID",
             !r.ok && std::string(r.reason) == "double_bind_same_block");
    }
    // (d) same-block duplicate heartbeat (same miner/epoch) -> INVALID
    {
        BlockNodeTxs b; b.heartbeats.push_back(make_hb(3, 0, tip)); b.heartbeats.push_back(make_hb(3, 0, tip));
        NodeState t = s; auto r = connect_block_node_txs(t, b, H, A, L, block_hash_at);
        TEST("same-block duplicate heartbeat INVALID",
             !r.ok && std::string(r.reason) == "dup_heartbeat_same_block");
    }
    // (e) activation guard at block level
    {
        BlockNodeTxs b; b.binds.push_back(make_bind(2, 4, 2));
        NodeState t = s; auto r = connect_block_node_txs(t, b, 29999, A, L, block_hash_at);
        TEST("node tx in block #29,999 -> INVALID", !r.ok && std::string(r.reason) == "node_tx_before_activation");
    }
    // (f) reorg round-trip: connect a heartbeat block then disconnect -> restored
    {
        NodeState t = s;
        size_t hb_before = t.heartbeats().size();
        BlockNodeTxs b; b.heartbeats.push_back(make_hb(3, 0, tip));
        auto r = connect_block_node_txs(t, b, H, A, L, block_hash_at);
        TEST("reorg: heartbeat block connects", r.ok && t.heartbeats().size() == hb_before + 1);
        disconnect_block_node_txs(t, r);
        TEST("reorg: disconnect restores heartbeat count", t.heartbeats().size() == hb_before);
    }
    // (g) canonical chain dedup: a heartbeat for (miner,epoch) already on chain -> INVALID
    {
        NodeState t = s;
        BlockNodeTxs b; b.heartbeats.push_back(make_hb(3, 0, tip));
        auto r1 = connect_block_node_txs(t, b, H, A, L, block_hash_at); (void)r1;
        // a later block re-submits the same (miner,epoch)
        BlockNodeTxs b2; b2.heartbeats.push_back(make_hb(3, 0, tip));
        auto r2 = connect_block_node_txs(t, b2, H, A, L, block_hash_at);
        TEST("heartbeat already on chain -> INVALID",
             !r2.ok && std::string(r2.reason) == "heartbeat_already_on_chain");
    }
}

static void test_reindex_parity() {
    // Build a sequence of blocks; connect into A incrementally; connect same into B;
    // then A: disconnect all + reconnect. All three must be identical.
    auto build = [](NodeState& st) {
        std::vector<ConnectResult> undo;
        BlockNodeTxs b1; b1.binds.push_back(make_bind(2, 3, 1));
        undo.push_back(connect_block_node_txs(st, b1, 30010, A, L, block_hash_at));
        BlockNodeTxs b2; b2.binds.push_back(make_bind(5, 6, 1));
        undo.push_back(connect_block_node_txs(st, b2, 30020, A, L, block_hash_at));
        BlockNodeTxs b3; b3.heartbeats.push_back(make_hb(3, 0, TIP0())); b3.heartbeats.push_back(make_hb(6, 0, TIP0()));
        undo.push_back(connect_block_node_txs(st, b3, 30060, A, L, block_hash_at));
        return undo;
    };
    NodeState a, b;
    build(a); build(b);
    bool same_ab = (a.binds().size() == b.binds().size()) && (a.heartbeats().size() == b.heartbeats().size());
    TEST("reindex parity: two independent replays identical", same_ab);

    // disconnect+reconnect round trip
    NodeState c; auto u = build(c);
    size_t nb = c.binds().size(), nh = c.heartbeats().size();
    for (auto it = u.rbegin(); it != u.rend(); ++it) disconnect_block_node_txs(c, *it);
    TEST("reindex parity: full disconnect empties state", c.binds().empty() && c.heartbeats().empty());
    build(c);
    TEST("reindex parity: reconnect restores identical sizes",
         c.binds().size() == nb && c.heartbeats().size() == nh);
}

static void test_payout_integration() {
    using namespace sost::jackpot;
    // At #30,186 build eligible set + winner + amount via the V15 payout core.
    std::vector<JackpotV2Candidate> cs = { cand(1, 5, true, 0), cand(2, 12, true, 0), cand(3, 3, true, 0) };
    auto w = jv2_build_weighted_set(cs, A, L, 30186);
    std::vector<Bytes32> ent(2); ent[0].fill(0x31); ent[1].fill(0x32);
    Bytes32 seed = jv2_seed(ent, 30186);
    int64_t widx = jv2_select_winner_index(w, seed);
    bool winner_exists = (widx >= 0);
    // reserve big, no rollover -> pays base 100 SOST
    JackpotResult jr = hist_jackpot_apply(30186, winner_exists, /*reserve*/ 1000 * STOCKS_PER_SOST, /*rollover*/ 0);
    TEST("V2 winner selected + base payout 100 SOST",
         winner_exists && jr.paid && jr.payout == 100 * STOCKS_PER_SOST);
    // 0 eligible -> no winner -> rollover (no payout), reserve untouched
    auto w0 = jv2_build_weighted_set({ cand(1, 2, true, 0) }, A, L, 30186); // pow<3
    JackpotResult jr0 = hist_jackpot_apply(30186, jv2_select_winner_index(w0, seed) >= 0,
                                           1000 * STOCKS_PER_SOST, 0);
    TEST("0 eligible -> rollover, no payout, reserve intact",
         !jr0.paid && jr0.payout == 0 && jr0.reserve_after == 1000 * STOCKS_PER_SOST);
}

// ---------------------------------------------------------------------------
// Transaction transport: single 0-value OUT_NODE_PROTOCOL output, non-spendable.
static void test_tx_encoding() {
    NodeBindTx b = make_bind(2, 3, 7);
    Transaction tx = build_node_bind_tx(b);
    TEST("bind tx: tx_type NODE_BIND", tx.tx_type == TX_TYPE_NODE_BIND);
    TEST("bind tx: no inputs", tx.inputs.empty());
    TEST("bind tx: exactly 1 output", tx.outputs.size() == 1);
    TEST("bind tx: output OUT_NODE_PROTOCOL, amount 0",
         tx.outputs[0].type == OUT_NODE_PROTOCOL && tx.outputs[0].amount == 0);
    TEST("classify -> Bind", classify_node_tx(tx) == NodeTxKind::Bind);
    NodeBindTx got; const char* rs = nullptr;
    TEST("extract_bind round-trips", extract_bind(tx, got, &rs)
         && got.mining_pubkey == b.mining_pubkey && got.bind_seq == b.bind_seq && got.mining_sig == b.mining_sig);

    // full serialized tx bytes
    std::vector<uint8_t> wire; std::string e;
    bool sok = tx.Serialize(wire, &e);
    Transaction hbtx = build_node_heartbeat_tx(make_hb(3, 1, TIP0()));
    std::vector<uint8_t> hwire; hbtx.Serialize(hwire, &e);
    printf("  [MEASURED] FULL NODE_BIND TX = %zuB   FULL NODE_HEARTBEAT TX = %zuB\n", wire.size(), hwire.size());
    TEST("full node txs serialize", sok && wire.size() > NODE_BIND_WIRE_BYTES);

    // full serialize -> deserialize -> extract round trip + txid stable
    { Transaction back; std::string de;
      bool dok = Transaction::Deserialize(wire, back, &de);
      NodeBindTx rb; const char* rr = nullptr;
      Hash256 id1{}, id2{}; std::string ie;
      TEST("full node tx serialize->deserialize->extract round-trips",
           dok && back.tx_type == TX_TYPE_NODE_BIND && extract_bind(back, rb, &rr)
           && rb.mining_pubkey == b.mining_pubkey && rb.bind_seq == b.bind_seq);
      TEST("node tx has a stable txid (0-input path works)",
           tx.ComputeTxId(id1, &ie) && back.ComputeTxId(id2, &ie) && id1 == id2);
    }

    // non-spendable predicate
    TEST("OUT_NODE_PROTOCOL is non-spendable", !output_is_spendable(OUT_NODE_PROTOCOL));
    TEST("OUT_TRANSFER is spendable", output_is_spendable(OUT_TRANSFER));

    // ---- malformed cases (all must FAIL extraction) ----
    const char* r = nullptr;
    NodeBindTx tmp;
    { Transaction t = tx; t.outputs.clear(); TEST("0 outputs -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; t.outputs.push_back(t.outputs[0]); TEST("2 outputs -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; t.outputs[0].amount = 1; TEST("amount != 0 -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; t.outputs[0].payload.pop_back(); TEST("truncated payload -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; t.outputs[0].payload.push_back(0); TEST("extra byte -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; t.outputs[0].type = OUT_TRANSFER; TEST("wrong output type -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; TxInput in{}; t.inputs.push_back(in); TEST("node tx with inputs -> FAIL", !extract_bind(t, tmp, &r)); }
    { Transaction t = tx; t.tx_type = TX_TYPE_STANDARD; TEST("wrong tx_type -> FAIL", !extract_bind(t, tmp, &r)); }
    // heartbeat extraction on a bind tx must fail (tx_type disambiguation)
    { NodeHeartbeatTx h; TEST("extract_heartbeat on bind tx -> FAIL", !extract_heartbeat(tx, h, &r)); }
}

// ---------------------------------------------------------------------------
int main() {
    printf("== test_node_participation (V16 NODE_BIND/HEARTBEAT tx layer) ==\n");
    test_serialization();
    test_bind_validation_and_activation_guard();
    test_heartbeat_validation();
    test_state_reorg_and_rules();
    test_final_eligibility_metric();
    test_block_processing();
    test_reindex_parity();
    test_payout_integration();
    test_tx_encoding();
    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
