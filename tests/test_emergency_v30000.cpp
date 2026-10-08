// ============================================================================
// test_emergency_v30000 — regression suite for the 2026-10-08 V30000 audit.
//
//   CRITICAL #2  node-tx mempool poisoning (138-byte bad-sig NODE_BIND, stale /
//                future / unbound heartbeat, same-block conflicts) -> chain halt
//   CRITICAL #3  STANDARD tx carrying / spending native-asset state (SOST burn,
//                counterfeit units, S14 + max_supply bypass)
//
// Build-agnostic. Design target (2026-10-08): CONSENSUS-IDENTICAL to v16.3.0 (the
// release the network majority runs) at/after #30,000 on mainnet:
//   * native assets DEFERRED (INT64_MAX) -> asset types rejected exactly as in v16.x;
//   * NODE_BIND / HEARTBEAT / Jackpot V2 eligibility UNCHANGED (already consensus in
//     v16.x) -> their poisoning is fixed NON-consensus: full validation before mempool
//     admission + cumulative template revalidation.
// On devnet/testnet builds the asset layer is live and S15 must reject the same probes.
//
// ============================================================================
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/utxo_set.h"
#include "sost/mempool.h"
#include "sost/native_assets.h"
#include "sost/native_assets_validation.h"
#include "sost/native_assets_index.h"
#include "sost/node_participation.h"
#include "sost/jackpot_v2.h"
#include "sost/jackpot.h"
#include "sost/sbpow.h"
#include "sost/consensus_constants.h"

#include <cstdio>
#include <string>
#include <vector>

using namespace sost;
namespace np = sost::node_participation;
namespace jv2 = sost::jackpot_v2;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { if (cond) { ++g_pass; std::printf("  PASS: %s\n", msg); } \
    else { ++g_fail; std::printf("  *** FAIL: %s [line %d]\n", msg, __LINE__); } } while (0)

#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
static constexpr bool MAINNET_BUILD = false;
#else
static constexpr bool MAINNET_BUILD = true;
#endif

// Heights probed: the real activation when live, else the mainnet V30000 heights.
static const int64_t NODE_A  = HIST_JACKPOT_V2_HEIGHT;           // epoch math anchor
static const int64_t NODE_L  = NODE_EPOCH_LENGTH;
static const int64_t ASSET_H = (NATIVE_ASSETS_ACTIVATION_HEIGHT == INT64_MAX)
                                   ? 30000 : NATIVE_ASSETS_ACTIVATION_HEIGHT + 10;
static const bool NODE_LIVE  = node_participation_active_at(NODE_A);
static const bool ASSET_LIVE = native_assets_active_at(ASSET_H);

// ---------------------------------------------------------------------------
// node-participation helpers (real Schnorr keys)
// ---------------------------------------------------------------------------
static bool mk(uint32_t seed, sbpow::MinerPrivkey& sk, sbpow::MinerPubkey& pk) {
    sk.fill(0x11); sk[0] = seed & 0xff; sk[1] = (seed >> 8) & 0xff; sk[3] = 1;
    return sbpow::derive_compressed_pubkey_from_privkey(sk, pk);
}
static np::NodePubKey npk_of(uint32_t s) {
    sbpow::MinerPrivkey sk; sbpow::MinerPubkey pk; mk(s, sk, pk);
    np::NodePubKey n; std::copy(pk.begin(), pk.end(), n.begin()); return n;
}
static PubKeyHash pkh_of(uint32_t s) {
    sbpow::MinerPrivkey sk; sbpow::MinerPubkey pk; mk(s, sk, pk); return sbpow::derive_pkh_from_pubkey(pk);
}
static np::NodeBindTx bind(uint32_t ms, const np::NodePubKey& n, uint64_t seq) {
    np::NodeBindTx t; sbpow::MinerPrivkey sk; sbpow::MinerPubkey pk; mk(ms, sk, pk);
    t.mining_pubkey = pk; t.node_pubkey = n; t.bind_seq = seq;
    sbpow::sign_sbpow_commitment(sk, np::bind_message(sbpow::derive_pkh_from_pubkey(pk), n, seq), t.mining_sig);
    return t;
}
static np::NodeHeartbeatTx hb(uint32_t ns, uint64_t ep, const Bytes32& tip) {
    np::NodeHeartbeatTx t; sbpow::MinerPrivkey sk; sbpow::MinerPubkey pk; mk(ns, sk, pk);
    std::copy(pk.begin(), pk.end(), t.node_pubkey.begin()); t.epoch_idx = ep; t.tip_ref_hash = tip;
    sbpow::sign_sbpow_commitment(sk, np::heartbeat_message(t.node_pubkey, ep, tip), t.node_sig);
    return t;
}
static Bytes32 tip_for(int64_t h) { Bytes32 t{}; t.fill((uint8_t)(0x40 + (h & 0x3f))); return t; }
static bool hash_at(int64_t h, Bytes32& out) { out = tip_for(h); return true; }

// Authoritative block rule on a scratch copy (set validity).
static bool node_txs_valid(const np::NodeState& live, const std::vector<const Transaction*>& txs,
                           int64_t height, std::string& why) {
    return np::node_txs_valid_for_block(live, txs, height, NODE_A, NODE_L, hash_at, &why);
}
// The REAL per-tx policy the node installs (judge_node_tx over a per-height context).
static bool judge(const np::NodeState& live, const Transaction& tx, int64_t h, std::string& why) {
    auto c = np::make_node_tx_policy_context(live, h, NODE_A, NODE_L, hash_at);
    auto v = np::judge_node_tx(c, live, tx); why = v.reason; return v.ok;
}
static np::NodeTxSelection selectT(const np::NodeState& live, const std::vector<const Transaction*>& v, int64_t h,
                                   size_t cap = np::MAX_NODE_TXS_PER_TEMPLATE) {
    auto c = np::make_node_tx_policy_context(live, h, NODE_A, NODE_L, hash_at);
    return np::select_node_txs_for_template(c, live, v, hash_at, cap);
}

// ---------------------------------------------------------------------------
// asset helpers
// ---------------------------------------------------------------------------
static TxValidationContext ctxAt(int64_t h) {
    TxValidationContext c; c.genesis_hash.fill(0x11); c.spend_height = h;
    c.capsule_activation_height = CAPSULE_ACTIVATION_HEIGHT_MAINNET;
    c.bond_activation_height = BOND_ACTIVATION_HEIGHT_MAINNET;
    return c;   // admin_authority_pkh zero -> baked ADMIN_AUTHORITY_PKH (as the node)
}
static void signAll(Transaction& tx, const UtxoSet& u, const PrivKey& k, const Hash256& g) {
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        auto e = u.GetUTXO(OutPoint{tx.inputs[i].prev_txid, tx.inputs[i].prev_index});
        SpentOutput s; s.amount = e ? e->amount : 0; s.type = e ? e->type : OUT_TRANSFER; std::string err;
        SignTransactionInput(tx, i, s, g, k, &err);
    }
}
static TxOutput out(uint8_t type, int64_t amt, const PubKeyHash& pkh, std::vector<uint8_t> payload = {}) {
    TxOutput o; o.type = type; o.amount = amt; o.pubkey_hash = pkh; o.payload = std::move(payload); return o;
}
static bool rejected(const TxValidationResult& r) { return !r.ok; }

// ===========================================================================
static void test_constants() {
    std::printf("\n-- activation constants (%s build) --\n", MAINNET_BUILD ? "MAINNET" : "devnet/testnet");
    TEST("HIST_JACKPOT_V2_HEIGHT unchanged", MAINNET_BUILD ? HIST_JACKPOT_V2_HEIGHT == 30000 : true);
    if (MAINNET_BUILD) {
        TEST("mainnet NATIVE_ASSETS_ACTIVATION_HEIGHT == INT64_MAX (deferred = v16.x rule set)", NATIVE_ASSETS_ACTIVATION_HEIGHT == INT64_MAX);
        TEST("mainnet assets inactive at 30000 / 30186 / 40000", !native_assets_active_at(30000) && !native_assets_active_at(30186) && !native_assets_active_at(40000));
        TEST("mainnet restricted dev mode never active (assets deferred)", !restricted_dev_mode_active_at(30000) && !restricted_dev_mode_active_at(40000));
        TEST("mainnet node participation UNCHANGED vs v16.x (inactive 29999, live 30000)",
             !node_participation_active_at(29999) && node_participation_active_at(30000));
        TEST("mainnet SACS_V2_ACTIVATION_HEIGHT == INT64_MAX (legacy 500 cap = v16.x)", SACS_V2_ACTIVATION_HEIGHT == INT64_MAX);
        TEST("mainnet V2 jackpot cadence unchanged (first V2 draw #30,186)", is_hist_jackpot_v2_height(30186) && !is_hist_jackpot_v2_height(30000));
    } else {
        TEST("devnet/testnet: assets live (feature testable)", ASSET_LIVE);
        TEST("devnet/testnet: node participation live at V2 height", NODE_LIVE);
    }
}

// ===========================================================================
// B/F/G — node-tx admission (mempool), template selection, post-block eviction.
// Uses the REAL library policy (judge_node_tx / select_node_txs_for_template over
// make_node_tx_policy_context) — the exact functions the node installs.
static Mempool make_pool(const np::NodeState& live) {
    Mempool mp;
    mp.SetNodeTxValidator([&live](const Transaction& tx, int64_t h, std::string& why) {
        return judge(live, tx, h, why);
    });
    return mp;
}

static void test_node_poison() {
    std::printf("\n-- B: node-tx poisoning (CRITICAL #2), A=%lld L=%lld --\n", (long long)NODE_A, (long long)NODE_L);
    np::NodeState live;          // empty chain node state
    Mempool mp = make_pool(live); UtxoSet u;
    auto acc = [&](Mempool& m, const Transaction& tx, int64_t h) {
        TxValidationContext c; c.spend_height = h; return m.AcceptToMempool(tx, u, c, 1000);
    };

    // 138-byte poison: canonical shape, garbage signature (the audit PoC F1)
    {
        np::NodeBindTx b = bind(1, npk_of(2), 1); b.mining_sig.fill(0x00);
        Transaction t = np::build_node_bind_tx(b);
        TEST("PoC payload is exactly 138 bytes", t.outputs.size() == 1 && t.outputs[0].payload.size() == 138);
        auto r = acc(mp, t, NODE_A);
        TEST("138-byte bad-sig NODE_BIND REJECTED by mempool", !r.accepted);
        TEST("  ... reason is the consensus rule (bad_signature)", r.reason.find("bad_signature") != std::string::npos);
        TEST("138-byte poison never reaches the template", mp.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 500 * 1024, NODE_A).txs.empty());
    }
    { np::NodeBindTx b = bind(3, npk_of(4), 1); b.bind_seq = 2;
      TEST("invalid NODE_BIND (seq != signed message) REJECTED", !acc(mp, np::build_node_bind_tx(b), NODE_A).accepted); }
    { np::NodeBindTx b = bind(3, npk_of(4), 1); b.node_pubkey[7] ^= 0x10;   // sig covers node key
      TEST("invalid NODE_BIND (node key swapped after signing) REJECTED", !acc(mp, np::build_node_bind_tx(b), NODE_A).accepted); }
    { Transaction t = np::build_node_bind_tx(bind(3, npk_of(4), 1)); t.outputs[0].amount = 1;
      TEST("NODE_BIND carrying SOST value REJECTED", !acc(mp, t, NODE_A).accepted); }
    TEST("NODE_BIND before activation REJECTED", !acc(mp, np::build_node_bind_tx(bind(3, npk_of(4), 1)), NODE_A - 1).accepted);

    // ---- F: heartbeat rules ----
    std::printf("\n-- F: NODE_HEARTBEAT rules --\n");
    TEST("heartbeat from UNBOUND node key REJECTED",
         !acc(mp, np::build_node_heartbeat_tx(hb(77, 0, tip_for(NODE_A - 1))), NODE_A + 5).accepted);
    live.apply_bind(pkh_of(5), npk_of(6), 1, NODE_A);   // miner 5 -> node 6, effective NODE_A+1
    { np::NodeHeartbeatTx h = hb(6, 0, tip_for(NODE_A - 1)); h.node_sig[5] ^= 0x01;
      TEST("bad-signature heartbeat REJECTED", !acc(mp, np::build_node_heartbeat_tx(h), NODE_A + 5).accepted); }
    { np::NodeHeartbeatTx h = hb(6, 0, tip_for(NODE_A - 1));
      sbpow::MinerPrivkey sk; sbpow::MinerPubkey pk; mk(99, sk, pk);                 // signed by the WRONG key
      sbpow::sign_sbpow_commitment(sk, np::heartbeat_message(h.node_pubkey, 0, h.tip_ref_hash), h.node_sig);
      TEST("heartbeat signed by a key that is not the node key (wrong owner) REJECTED",
           !acc(mp, np::build_node_heartbeat_tx(h), NODE_A + 5).accepted); }
    TEST("future-epoch heartbeat REJECTED",
         !acc(mp, np::build_node_heartbeat_tx(hb(6, 1, tip_for(NODE_A + NODE_L - 1))), NODE_A + 5).accepted);
    TEST("wrong tip_ref heartbeat REJECTED",
         !acc(mp, np::build_node_heartbeat_tx(hb(6, 0, tip_for(12345))), NODE_A + 5).accepted);
    TEST("heartbeat at bind inclusion height (binding not yet effective) REJECTED",
         !acc(mp, np::build_node_heartbeat_tx(hb(6, 0, tip_for(NODE_A - 1))), NODE_A).accepted);

    // epoch transition: last block of epoch 0 / first of epoch 1 / second of epoch 1
    const int64_t last0 = NODE_A + NODE_L - 1, first1 = NODE_A + NODE_L, second1 = NODE_A + NODE_L + 1;
    {
        Transaction e0 = np::build_node_heartbeat_tx(hb(6, 0, tip_for(NODE_A - 1)));
        Transaction e1 = np::build_node_heartbeat_tx(hb(6, 1, tip_for(first1 - 1)));
        std::string w;
        char m[160];
        std::snprintf(m, sizeof m, "epoch-0 heartbeat VALID at #%lld (last block of epoch 0)", (long long)last0);
        TEST(m, node_txs_valid(live, {&e0}, last0, w));
        std::snprintf(m, sizeof m, "epoch-0 heartbeat INVALID at #%lld (first block of epoch 1)", (long long)first1);
        TEST(m, !node_txs_valid(live, {&e0}, first1, w));
        std::snprintf(m, sizeof m, "epoch-0 heartbeat INVALID at #%lld", (long long)second1);
        TEST(m, !node_txs_valid(live, {&e0}, second1, w));
        std::snprintf(m, sizeof m, "epoch-1 heartbeat INVALID at #%lld (future epoch)", (long long)last0);
        TEST(m, !node_txs_valid(live, {&e1}, last0, w));
        std::snprintf(m, sizeof m, "epoch-1 heartbeat VALID at #%lld and #%lld", (long long)first1, (long long)second1);
        TEST(m, node_txs_valid(live, {&e1}, first1, w) && node_txs_valid(live, {&e1}, second1, w));

        // stale-in-pool: admitted while valid, the boundary passes, it is evicted + never templated
        Mempool sp = make_pool(live);
        TEST("epoch-0 heartbeat admitted at the last block of epoch 0", acc(sp, e0, last0).accepted);
        Mempool::BlockTemplate t = sp.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 500 * 1024, first1);
        std::vector<const Transaction*> v; for (auto& x : t.txs) v.push_back(&x);
        auto sel = selectT(live, v, first1);
        TEST("template at the epoch boundary keeps 0 of the stale heartbeat (marked invalid)",
             sel.keep.empty() && sel.invalid.size() == 1);
        TEST("post-block revalidation EVICTS the expired heartbeat", sp.RevalidateNodeTxs(first1) == 1 && sp.Size() == 0);
    }
    // replay / duplicate
    {
        Transaction g = np::build_node_heartbeat_tx(hb(6, 0, tip_for(NODE_A - 1)));
        TEST("valid heartbeat ACCEPTED (positive control)", acc(mp, g, NODE_A + 5).accepted);
        TEST("exact duplicate heartbeat REJECTED (already in pool)", !acc(mp, g, NODE_A + 5).accepted);
        np::NodeState after = live; after.record_heartbeat(pkh_of(5), 0);          // it got mined
        std::string w;
        TEST("replay of a heartbeat already on chain is INVALID", !node_txs_valid(after, {&g}, NODE_A + 5, w) && w == "heartbeat_already_on_chain");
        Mempool rp = make_pool(after);
        TEST("replay REJECTED by mempool", !acc(rp, g, NODE_A + 5).accepted);
        // reorg: the block that carried it is disconnected -> valid again (state is exact on undo)
        np::NodeState reorged = after; reorged.undo_heartbeat();
        TEST("after the carrying block is reorged out the heartbeat is valid again",
             node_txs_valid(reorged, {&g}, NODE_A + 5, w));
        // rotation: miner 5 rotates to node 8 -> node 6's heartbeat no longer counts
        np::NodeState rot = live; rot.apply_bind(pkh_of(5), npk_of(8), 2, NODE_A + 2);
        TEST("heartbeat by a rotated-away node key is INVALID", !node_txs_valid(rot, {&g}, NODE_A + 5, w));
    }

    // same-block conflicts (audit F1c): each valid alone, together an invalid block
    {
        Mempool m2 = make_pool(live);
        Transaction b1 = np::build_node_bind_tx(bind(10, npk_of(50), 1));
        Transaction b2 = np::build_node_bind_tx(bind(11, npk_of(50), 1));
        TEST("F1c: bind(miner10,node50) admitted", acc(m2, b1, NODE_A + 1).accepted);
        TEST("F1c: bind(miner11,node50) admitted (valid alone)", acc(m2, b2, NODE_A + 1).accepted);
        auto t = m2.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 500 * 1024, NODE_A + 1);
        std::vector<const Transaction*> v; for (auto& x : t.txs) v.push_back(&x);
        auto sel = selectT(live, v, NODE_A + 1);
        std::vector<const Transaction*> kept; for (size_t k : sel.keep) kept.push_back(v[k]);
        std::string w;
        TEST("F1c: template keeps exactly ONE of the conflicting binds", sel.keep.size() == 1 && sel.deferred.size() == 1);
        TEST("F1c: the kept set is a VALID block", node_txs_valid(live, kept, NODE_A + 1, w));
        np::NodeState mined = live; np::BlockNodeTxs bnt; np::NodeBindTx bb; np::extract_bind(*kept[0], bb); bnt.binds.push_back(bb);
        np::connect_block_node_txs(mined, bnt, NODE_A + 1, NODE_A, NODE_L, hash_at);
        Mempool m3 = make_pool(mined);
        TEST("F1c: after the first bind is mined the loser is INVALID (bind_not_acceptable)",
             !node_txs_valid(mined, {v[sel.deferred[0]]}, NODE_A + 2, w));
        (void)m3;
    }
    // no validator installed -> fail-closed
    { Mempool raw; TxValidationContext c; c.spend_height = NODE_A + 1;
      TEST("no validator installed -> valid NODE_BIND still REJECTED (fail-closed)",
           !raw.AcceptToMempool(np::build_node_bind_tx(bind(10, npk_of(51), 1)), u, c, 1000).accepted);
      TEST("no validator installed -> RevalidateNodeTxs evicts nothing it cannot judge (pool empty)", raw.RevalidateNodeTxs(NODE_A + 2) == 0); }

    // ---- G: spam / complexity bounds ----
    std::printf("\n-- G: spam / complexity bounds --\n");
    {
        Mempool sp; sp.SetNodeTxValidator([](const Transaction&, int64_t, std::string&) { return true; });
        TxValidationContext c; c.spend_height = NODE_A + 1;
        size_t admitted = 0;
        for (uint32_t i = 0; i < 4096u + 50; ++i) {
            np::NodeBindTx b; b.mining_pubkey.fill(0x02); b.mining_pubkey[1] = i & 0xff; b.mining_pubkey[2] = (i >> 8) & 0xff;
            b.mining_pubkey[3] = (i >> 16) & 0xff; b.node_pubkey.fill(0x03); b.bind_seq = 1;
            if (sp.AcceptToMempool(np::build_node_bind_tx(b), u, c, 1000).accepted) ++admitted;
        }
        TEST("node-tx pool capped at 4096 (Mempool::NODE_TX_MEMPOOL_MAX)", admitted == 4096);
    }
    {
        // template cap: 100 valid, non-conflicting binds -> at most MAX_NODE_TXS_PER_TEMPLATE kept
        std::vector<Transaction> bs;
        for (uint32_t i = 0; i < 100; ++i) bs.push_back(np::build_node_bind_tx(bind(1000 + i, npk_of(5000 + i), 1)));
        std::vector<const Transaction*> v; for (auto& x : bs) v.push_back(&x);
        auto sel = selectT(np::NodeState{}, v, NODE_A + 1);
        TEST("template carries at most MAX_NODE_TXS_PER_TEMPLATE node txs (rest deferred, not evicted)",
             sel.keep.size() == np::MAX_NODE_TXS_PER_TEMPLATE && sel.deferred.size() == 100 - np::MAX_NODE_TXS_PER_TEMPLATE && sel.invalid.empty());
    }
}

// ===========================================================================
// E — NODE_BIND takeover (audit F2). The fix (proof of node-key possession) changes the
// NODE_BIND wire format = CONSENSUS FIX REQUIRED: YES. It is NOT shipped (the v16.x
// majority would split). This test pins the CURRENT v16-compatible behaviour so the
// future fork's regression has a baseline: it is EXPECTED to flip when that fork lands.
static void test_bind_takeover_known() {
    std::printf("\n-- E: NODE_BIND takeover (KNOWN, consensus fix required; EXPECTED under v16 rules) --\n");
    np::NodeState st;
    const np::NodePubKey victim_node = npk_of(50);
    np::BlockNodeTxs b1; b1.binds.push_back(bind(99, victim_node, 1));       // attacker miner 99 claims it first
    auto c1 = np::connect_block_node_txs(st, b1, NODE_A + 1, NODE_A, NODE_L, hash_at);
    np::BlockNodeTxs b2; b2.binds.push_back(bind(10, victim_node, 1));       // the real owner tries later
    auto c2 = np::connect_block_node_txs(st, b2, NODE_A + 2, NODE_A, NODE_L, hash_at);
    np::BlockNodeTxs b3; b3.heartbeats.push_back(hb(50, 0, tip_for(NODE_A - 1)));   // victim's node heartbeats
    auto c3 = np::connect_block_node_txs(st, b3, NODE_A + 3, NODE_A, NODE_L, hash_at);
    TEST("EXPECTED (v16 rule): attacker bind of a foreign node key is consensus-valid", c1.ok);
    TEST("EXPECTED (v16 rule): the real owner can no longer bind that node key", !c2.ok);
    TEST("EXPECTED (v16 rule): the victim node's heartbeat is credited to the attacker",
         c3.ok && st.heartbeats_in_window(pkh_of(99), NODE_A, NODE_L, NODE_A + NODE_L) == 1 &&
         st.heartbeats_in_window(pkh_of(10), NODE_A, NODE_L, NODE_A + NODE_L) == 0);
    // bounded impact: the victim recovers eligibility by binding a FRESH node key
    np::BlockNodeTxs b4; b4.binds.push_back(bind(10, npk_of(51), 1));
    TEST("impact bounded: the victim can bind a fresh node key immediately",
         np::connect_block_node_txs(st, b4, NODE_A + 4, NODE_A, NODE_L, hash_at).ok);
    // no value moves: node txs carry 0 SOST and never touch the UTXO set
    TEST("impact bounded: node txs carry no SOST value (amount 0, non-spendable output)",
         np::build_node_bind_tx(bind(99, victim_node, 1)).outputs[0].amount == 0 && !np::output_is_spendable(OUT_NODE_PROTOCOL));
}

// ===========================================================================
// Differential proofs for the 2026-10-08 performance refactor + the policy layer.
//  (1) connect_block_node_txs (pre-block state derived ONCE) == the pre-refactor algorithm
//      (bind_acceptable re-derived per bind) on randomized states/blocks: same ok, same
//      reason, same resulting state.
//  (2) judge_node_tx (policy) == connect_block_node_txs on a single-tx block: the policy
//      is never looser (nor stricter) than the consensus rule.
namespace ref {
using namespace sost::node_participation;
static ConnectResult connect_old(NodeState& state, const BlockNodeTxs& txs, int64_t height, int64_t A, int64_t L,
                                 const std::function<bool(int64_t, Bytes32&)>& block_hash_at) {
    ConnectResult r;
    if (!node_participation_active_at(height)) {
        if (!txs.binds.empty() || !txs.heartbeats.empty()) { r.reason = "node_tx_before_activation"; return r; }
        r.ok = true; return r;
    }
    std::set<PubKeyHash> mi; std::set<NodePubKey> no; std::vector<jv2::NodeBindRecord> to_bind;
    for (const auto& b : txs.binds) {
        BindCheck bc = check_bind(b, height);
        if (!bc.ok) { r.reason = bc.reason; return r; }
        if (!mi.insert(bc.mining_pkh).second) { r.reason = "double_bind_same_block"; return r; }
        if (!no.insert(b.node_pubkey).second)  { r.reason = "node_pubkey_twice_same_block"; return r; }
        if (!state.bind_acceptable(bc.mining_pkh, b.node_pubkey, b.bind_seq, height)) { r.reason = "bind_not_acceptable"; return r; }
        jv2::NodeBindRecord rec; rec.mining_pkh = bc.mining_pkh; rec.node_pubkey = b.node_pubkey;
        rec.bind_seq = (int64_t)b.bind_seq; rec.inclusion_height = height; to_bind.push_back(rec);
    }
    const int64_t e = jv2::jv2_epoch_of_height(A, L, height);
    Bytes32 tip{};
    if (e >= 0) { if (!block_hash_at(jv2::jv2_epoch_start(A, L, e) - 1, tip)) { r.reason = "no_tip_ref"; return r; } }
    auto pre = state.active_bindings(height);
    std::set<std::pair<std::array<uint8_t,20>, int64_t>> bh; std::vector<std::pair<PubKeyHash,int64_t>> to_hb;
    for (const auto& h : txs.heartbeats) {
        HeartbeatCheck hc = check_heartbeat(h, height, A, L, tip);
        if (!hc.ok) { r.reason = hc.reason; return r; }
        const PubKeyHash* owner = nullptr;
        for (const auto& kv : pre) if (kv.second.node_pubkey == h.node_pubkey) { owner = &kv.first; break; }
        if (!owner) { r.reason = "heartbeat_node_not_active_preblock"; return r; }
        auto key = std::make_pair(*owner, (int64_t)h.epoch_idx);
        if (!bh.insert(key).second) { r.reason = "dup_heartbeat_same_block"; return r; }
        if (state.has_heartbeat(*owner, (int64_t)h.epoch_idx)) { r.reason = "heartbeat_already_on_chain"; return r; }
        to_hb.emplace_back(*owner, (int64_t)h.epoch_idx);
    }
    for (const auto& x : to_hb) state.record_heartbeat(x.first, x.second);
    for (const auto& rec : to_bind) state.apply_bind(rec.mining_pkh, rec.node_pubkey, (uint64_t)rec.bind_seq, rec.inclusion_height);
    r.ok = true; r.binds_applied = (int)to_bind.size(); r.hbs_applied = (int)to_hb.size();
    return r;
}
} // namespace ref

static bool same_state(const np::NodeState& a, const np::NodeState& b) {
    if (a.binds().size() != b.binds().size() || a.heartbeats().size() != b.heartbeats().size()) return false;
    for (size_t i = 0; i < a.binds().size(); ++i) {
        const auto& x = a.binds()[i]; const auto& y = b.binds()[i];
        if (!(x.mining_pkh == y.mining_pkh && x.node_pubkey == y.node_pubkey && x.bind_seq == y.bind_seq && x.inclusion_height == y.inclusion_height)) return false;
    }
    for (size_t i = 0; i < a.heartbeats().size(); ++i)
        if (!(a.heartbeats()[i].mining_pkh == b.heartbeats()[i].mining_pkh && a.heartbeats()[i].epoch_idx == b.heartbeats()[i].epoch_idx)) return false;
    return true;
}

static void test_differential() {
    std::printf("\n-- differential: refactored block rule == pre-refactor; policy == block rule --\n");
    uint64_t seed = 0x5057d1ffULL;
    auto rnd = [&]() { seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17; return seed; };
    int blocks = 0, mism_block = 0, txs = 0, mism_policy = 0, accepted = 0;
    np::NodeState s_new, s_old;
    for (int step = 0; step < 400; ++step) {
        const int64_t h = NODE_A + 1 + step;
        np::BlockNodeTxs b;
        const int nb = (int)(rnd() % 4), nh = (int)(rnd() % 4);
        for (int i = 0; i < nb; ++i) {
            np::NodeBindTx x = bind(1 + (uint32_t)(rnd() % 12), npk_of(100 + (uint32_t)(rnd() % 10)), 1 + rnd() % 4);
            if (rnd() % 10 == 0) x.mining_sig[3] ^= 1;                  // occasional bad signature
            b.binds.push_back(x);
        }
        const int64_t ep = jv2::jv2_epoch_of_height(NODE_A, NODE_L, h);
        for (int i = 0; i < nh; ++i) {
            const int64_t e = (rnd() % 6 == 0) ? ep + 1 : ep;           // occasional future epoch
            b.heartbeats.push_back(hb(100 + (uint32_t)(rnd() % 10), (uint64_t)e,
                                      tip_for(jv2::jv2_epoch_start(NODE_A, NODE_L, ep) - 1)));
        }
        // (2) policy vs single-tx block rule, against the pre-block state
        for (const auto& x : b.binds) {
            Transaction t = np::build_node_bind_tx(x); std::string w1, w2;
            if (judge(s_new, t, h, w1) != node_txs_valid(s_new, {&t}, h, w2)) ++mism_policy;
            ++txs;
        }
        for (const auto& x : b.heartbeats) {
            Transaction t = np::build_node_heartbeat_tx(x); std::string w1, w2;
            if (judge(s_new, t, h, w1) != node_txs_valid(s_new, {&t}, h, w2)) ++mism_policy;
            ++txs;
        }
        // (1) refactored vs reference block rule
        auto r1 = np::connect_block_node_txs(s_new, b, h, NODE_A, NODE_L, hash_at);
        auto r2 = ref::connect_old(s_old, b, h, NODE_A, NODE_L, hash_at);
        ++blocks; if (r1.ok) ++accepted;
        if (r1.ok != r2.ok || std::string(r1.reason) != std::string(r2.reason) ||
            r1.binds_applied != r2.binds_applied || r1.hbs_applied != r2.hbs_applied || !same_state(s_new, s_old)) ++mism_block;
    }
    char m[200];
    std::snprintf(m, sizeof m, "refactored connect_block_node_txs == pre-refactor on %d random blocks (%d accepted, final binds=%zu hbs=%zu)",
                  blocks, accepted, s_new.binds().size(), s_new.heartbeats().size());
    TEST(m, mism_block == 0 && accepted > 20 && accepted < blocks);
    std::snprintf(m, sizeof m, "judge_node_tx == single-tx block rule on %d random node txs (policy never looser)", txs);
    TEST(m, mism_policy == 0 && txs > 500);
}

// ===========================================================================
static void test_asset_bypass() {
    std::printf("\n-- native-asset bypass (CRITICAL #3) at h=%lld --\n", (long long)ASSET_H);
    Hash256 G; G.fill(0x11);
    PrivKey ak; PubKey ap; GenerateKeyPair(ak, ap); PubKeyHash apkh = ComputePubKeyHash(ap);
    TEST("attacker is not the admin authority", !(apkh == ADMIN_AUTHORITY_PKH));
    UtxoSet u;
    OutPoint fund; fund.txid.fill(0xA1); fund.index = 0;
    UTXOEntry fe; fe.amount = 10'000'000; fe.type = OUT_TRANSFER; fe.pubkey_hash = apkh; fe.height = 100; u.AddUTXO(fund, fe);
    // an asset-carrying UTXO (cannot exist on mainnet; injected to prove S15 on the input side)
    Bytes32 victim{}; victim.fill(0x5A);
    OutPoint aop; aop.txid.fill(0xA2); aop.index = 0;
    UTXOEntry ae; ae.amount = 10'000; ae.type = OUT_ASSET_TRANSFER; ae.pubkey_hash = apkh; ae.height = 100;
    ae.payload = serialize_asset_amount(victim, 1000); ae.payload_len = (uint8_t)ae.payload.size(); u.AddUTXO(aop, ae);
    OutPoint authop; authop.txid.fill(0xA3); authop.index = 0;
    UTXOEntry au = ae; au.type = OUT_ASSET_ISSUE_AUTH; au.payload = serialize_asset_auth(victim); au.payload_len = (uint8_t)au.payload.size(); u.AddUTXO(authop, au);

    auto std_tx = [&](std::vector<TxOutput> outs, std::vector<OutPoint> ins, uint8_t type = TX_TYPE_STANDARD) {
        Transaction t; t.version = 1; t.tx_type = type;
        for (auto& o : ins) { TxInput in; in.prev_txid = o.txid; in.prev_index = o.index; t.inputs.push_back(in); }
        t.outputs = std::move(outs); signAll(t, u, ak, G); return t;
    };
    const auto C = ctxAt(ASSET_H);

    // (1) the audit PoC: STANDARD tx burning 6,000,000 stocks into OUT_ASSET_BURN + counterfeit + auth
    {
        Transaction t = std_tx({ out(OUT_ASSET_BURN, 6'000'000, apkh, serialize_asset_amount(victim, 1)),
                                 out(OUT_ASSET_TRANSFER, 10'000, apkh, serialize_asset_amount(victim, ASSET_MAX_SUPPLY_CEILING)),
                                 out(OUT_ASSET_ISSUE_AUTH, 10'000, apkh, serialize_asset_auth(victim)),
                                 out(OUT_TRANSFER, 3'970'000, apkh) }, {fund});
        auto r = ValidateTransactionConsensus(t, u, C);
        TEST("audit PoC (STANDARD + asset burn/counterfeit/auth) REJECTED by consensus", rejected(r));
        if (ASSET_LIVE) TEST("  ... with S15_ASSET_STATE_NON_ASSET_TX", r.code == TxValCode::S15_ASSET_STATE_NON_ASSET_TX);
        Mempool mp; TEST("audit PoC REJECTED by mempool", !mp.AcceptToMempool(t, u, C, 1700000000).accepted);
    }
    // (2) normal tx + asset output (single)
    TEST("normal tx + OUT_ASSET_TRANSFER output REJECTED",
         rejected(ValidateTransactionConsensus(std_tx({ out(OUT_ASSET_TRANSFER, 10'000, apkh, serialize_asset_amount(victim, 5)),
                                                        out(OUT_TRANSFER, 9'980'000, apkh) }, {fund}), u, C)));
    // (3) SOST burn via OUT_ASSET_BURN in a normal tx
    TEST("normal tx + OUT_ASSET_BURN (SOST burn) REJECTED",
         rejected(ValidateTransactionConsensus(std_tx({ out(OUT_ASSET_BURN, 9'990'000, apkh, serialize_asset_amount(victim, 1)) }, {fund}), u, C)));
    // (4) normal tx + asset input (moves/destroys asset units outside validate_asset_tx)
    {
        auto r = ValidateTransactionConsensus(std_tx({ out(OUT_TRANSFER, 9'000, apkh) }, {aop}), u, C);
        TEST("normal tx spending an OUT_ASSET_TRANSFER UTXO REJECTED (S15)", rejected(r) && r.code == TxValCode::S15_ASSET_STATE_NON_ASSET_TX);
        auto r2 = ValidateTransactionConsensus(std_tx({ out(OUT_TRANSFER, 9'000, apkh) }, {authop}), u, C);
        TEST("normal tx spending an OUT_ASSET_ISSUE_AUTH UTXO REJECTED (S15)", rejected(r2) && r2.code == TxValCode::S15_ASSET_STATE_NON_ASSET_TX);
    }
    // (5) HTLC-typed tx carrying an asset output (any non-asset type is covered)
    TEST("HTLC_CLAIM-typed tx + asset output REJECTED",
         rejected(ValidateTransactionConsensus(std_tx({ out(OUT_ASSET_TRANSFER, 10'000, apkh, serialize_asset_amount(victim, 5)) }, {fund}, TX_TYPE_HTLC_CLAIM), u, C)));
    // (6) fake asset creation by a non-admin (S14 bypass attempt through the asset type)
    {
        AssetDef d; d.symbol = "FAKE"; d.name = "Fake"; d.decimals = 0; d.supply_policy = ASSET_POLICY_FIXED; d.max_supply = 1000;
        Bytes32 id = compute_asset_id(fund.txid, 0);
        Transaction g = std_tx({ out(OUT_ASSET_GENESIS_DEF, 1, apkh, serialize_asset_def(d)),
                                 out(OUT_ASSET_TRANSFER, 1, apkh, serialize_asset_amount(id, 1000)),
                                 out(OUT_TRANSFER, 9'980'000, apkh) }, {fund}, TX_TYPE_ASSET_GENESIS);
        auto r = ValidateTransactionConsensus(g, u, C);
        TEST("fake asset creation by non-admin REJECTED", rejected(r));
        if (MAINNET_BUILD) TEST("  ... mainnet: asset tx type inactive (R2)", r.code == TxValCode::R2_BAD_TX_TYPE);
        else               TEST("  ... devnet: restricted dev mode (S14)", r.code == TxValCode::S14_RESTRICTED_DEV_MODE);
        // S14 bypass: same genesis wrapped as STANDARD -> S15 (or R11 on mainnet)
        Transaction gs = std_tx({ out(OUT_ASSET_GENESIS_DEF, 1, apkh, serialize_asset_def(d)),
                                  out(OUT_ASSET_TRANSFER, 1, apkh, serialize_asset_amount(id, 1000)),
                                  out(OUT_TRANSFER, 9'980'000, apkh) }, {fund}, TX_TYPE_STANDARD);
        TEST("S14 bypass (asset genesis disguised as STANDARD) REJECTED", rejected(ValidateTransactionConsensus(gs, u, C)));
    }
    // (7) supply overflow / destruction bypass in the asset dimension
    {
        NativeAssetIndex ix; UtxoSet v;
        AssetDef d; d.symbol = "C"; d.name = "Capped"; d.decimals = 0; d.supply_policy = ASSET_POLICY_CAPPED_REISSUABLE; d.max_supply = 1000;
        Transaction g; g.version = 1; g.tx_type = TX_TYPE_ASSET_GENESIS; TxInput gi; gi.prev_txid.fill(0x31); gi.prev_index = 0; g.inputs = {gi};
        Bytes32 id = compute_asset_id(gi.prev_txid, 0);
        g.outputs = { out(OUT_ASSET_GENESIS_DEF, 1, apkh, serialize_asset_def(d)),
                      out(OUT_ASSET_TRANSFER, 1, apkh, serialize_asset_amount(id, 400)),
                      out(OUT_ASSET_ISSUE_AUTH, 1, apkh, serialize_asset_auth(id)) };
        Hash256 gid; g.ComputeTxId(gid);
        const auto gr = validate_asset_tx(g, gid, v, ix, ASSET_H);
        if (ASSET_LIVE) {
            TEST("legit capped genesis OK in the asset dimension (control)", gr == AssetTxResult::OK);
            ix.apply(g, gid);
            UTXOEntry ue; ue.amount = 1; ue.type = OUT_ASSET_ISSUE_AUTH; ue.payload = serialize_asset_auth(id); ue.payload_len = (uint8_t)ue.payload.size(); ue.height = ASSET_H;
            v.AddUTXO(OutPoint{gid, 2}, ue);
            Transaction is; is.version = 1; is.tx_type = TX_TYPE_ASSET_ISSUE; TxInput ii; ii.prev_txid = gid; ii.prev_index = 2; is.inputs = {ii};
            is.outputs = { out(OUT_ASSET_TRANSFER, 1, apkh, serialize_asset_amount(id, 601)),   // 400 + 601 > 1000
                           out(OUT_ASSET_ISSUE_AUTH, 1, apkh, serialize_asset_auth(id)) };
            Hash256 iid; is.ComputeTxId(iid);
            TEST("supply overflow (issue beyond max_supply) REJECTED", validate_asset_tx(is, iid, v, ix, ASSET_H + 1) != AssetTxResult::OK);
            // destruction bypass: a STANDARD tx spending the authority (would orphan the asset) -> S15
            UtxoSet uv; PrivKey k2; PubKey p2; GenerateKeyPair(k2, p2); PubKeyHash pk2 = ComputePubKeyHash(p2);
            UTXOEntry ua = ue; ua.pubkey_hash = pk2; ua.amount = 10'000; uv.AddUTXO(OutPoint{gid, 2}, ua);
            Transaction kill; kill.version = 1; kill.tx_type = TX_TYPE_STANDARD; kill.inputs = {ii};
            kill.outputs = { out(OUT_TRANSFER, 5'000, pk2) }; signAll(kill, uv, k2, G);
            auto kr = ValidateTransactionConsensus(kill, uv, C);
            TEST("destruction bypass (STANDARD tx consuming the issue authority) REJECTED (S15)",
                 rejected(kr) && kr.code == TxValCode::S15_ASSET_STATE_NON_ASSET_TX);
        } else {
            TEST("mainnet: validate_asset_tx refuses every asset tx (NOT_ACTIVE)", gr == AssetTxResult::NOT_ACTIVE);
            TEST("supply overflow impossible on mainnet (no asset tx valid)", gr != AssetTxResult::OK);
            TEST("destruction bypass impossible on mainnet (no asset state can exist)", gr != AssetTxResult::OK);
        }
    }
    // (8) legitimate traffic still passes
    {
        Transaction ok = std_tx({ out(OUT_TRANSFER, 9'000'000, apkh), out(OUT_TRANSFER, 990'000, apkh) }, {fund});
        auto r = ValidateTransactionConsensus(ok, u, C);
        TEST("plain STANDARD transfer still VALID (no collateral damage)", r.ok);
    }
}

// ===========================================================================
// SOST native burn must remain impossible on every path.
static void test_no_sost_burn() {
    std::printf("\n-- SOST native burn impossible --\n");
    Hash256 G; G.fill(0x11);
    PrivKey k; PubKey p; GenerateKeyPair(k, p); PubKeyHash pkh = ComputePubKeyHash(p);
    UtxoSet u; OutPoint f; f.txid.fill(0xB1); f.index = 0;
    UTXOEntry e; e.amount = 1'000'000; e.type = OUT_TRANSFER; e.pubkey_hash = pkh; e.height = 10; u.AddUTXO(f, e);
    auto mk_tx = [&](uint8_t out_type, uint8_t tx_type, std::vector<uint8_t> pl = {}) {
        Transaction t; t.version = 1; t.tx_type = tx_type; TxInput in; in.prev_txid = f.txid; in.prev_index = 0; t.inputs = {in};
        t.outputs = { out(out_type, 900'000, pkh, std::move(pl)) }; signAll(t, u, k, G); return t;
    };
    for (int64_t h : {29999LL, 30000LL, 30186LL, 40000LL}) {
        const auto C = ctxAt(h);
        char m[128];
        std::snprintf(m, sizeof m, "h=%lld: OUT_BURN output REJECTED", (long long)h);
        TEST(m, rejected(ValidateTransactionConsensus(mk_tx(OUT_BURN, TX_TYPE_STANDARD), u, C)));
        std::snprintf(m, sizeof m, "h=%lld: valued OUT_NODE_PROTOCOL output REJECTED", (long long)h);
        TEST(m, rejected(ValidateTransactionConsensus(mk_tx(OUT_NODE_PROTOCOL, TX_TYPE_STANDARD), u, C)));
        Bytes32 id{}; id.fill(0x42);
        std::snprintf(m, sizeof m, "h=%lld: STANDARD + OUT_ASSET_BURN REJECTED", (long long)h);
        TEST(m, rejected(ValidateTransactionConsensus(mk_tx(OUT_ASSET_BURN, TX_TYPE_STANDARD, serialize_asset_amount(id, 1)), u, C)));
        if (MAINNET_BUILD) {
            std::snprintf(m, sizeof m, "h=%lld: mainnet ASSET_BURN tx type REJECTED", (long long)h);
            TEST(m, rejected(ValidateTransactionConsensus(mk_tx(OUT_ASSET_BURN, TX_TYPE_ASSET_BURN, serialize_asset_amount(id, 1)), u, C)));
        }
    }
    // a node tx can never carry SOST value (amount must be 0)
    np::NodeBindTx b = bind(1, npk_of(2), 1); Transaction t = np::build_node_bind_tx(b); t.outputs[0].amount = 5;
    np::NodeBindTx tmp; TEST("node tx with non-zero amount fails extraction (no value sink)", !np::extract_bind(t, tmp));
}

int main() {
    std::printf("== test_emergency_v30000 (2026-10-08 audit regressions) ==\n");
    test_constants();
    test_node_poison();
    test_bind_takeover_known();
    test_differential();
    test_asset_bypass();
    test_no_sost_burn();
    std::printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
