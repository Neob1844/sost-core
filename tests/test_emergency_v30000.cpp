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

// Mirror of the node's validator: authoritative block rule on a scratch state.
static bool node_txs_valid(const np::NodeState& live, const std::vector<const Transaction*>& txs,
                           int64_t height, std::string& why) {
    np::BlockNodeTxs bnt;
    for (const Transaction* t : txs) {
        if (t->tx_type == TX_TYPE_NODE_BIND) { np::NodeBindTx b; if (!np::extract_bind(*t, b)) { why = "enc"; return false; } bnt.binds.push_back(b); }
        else { np::NodeHeartbeatTx h; if (!np::extract_heartbeat(*t, h)) { why = "enc"; return false; } bnt.heartbeats.push_back(h); }
    }
    np::NodeState scratch = live;
    auto r = np::connect_block_node_txs(scratch, bnt, height, NODE_A, NODE_L, hash_at);
    if (!r.ok) { why = r.reason; return false; }
    return true;
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
static void test_node_poison() {
    std::printf("\n-- node-tx poisoning (CRITICAL #2) at h=%lld --\n", (long long)NODE_A);
    np::NodeState live;          // empty chain node state
    Mempool mp; UtxoSet u;
    mp.SetNodeTxValidator([&](const Transaction& tx, int64_t h, std::string& why) {
        return node_txs_valid(live, {&tx}, h, why);
    });
    auto acc = [&](const Transaction& tx, int64_t h) {
        TxValidationContext c; c.spend_height = h; return mp.AcceptToMempool(tx, u, c, 1000);
    };

    // 138-byte poison: canonical shape, garbage signature (the audit PoC F1)
    {
        np::NodeBindTx b = bind(1, npk_of(2), 1); b.mining_sig.fill(0x00);
        Transaction t = np::build_node_bind_tx(b);
        TEST("PoC payload is exactly 138 bytes", t.outputs.size() == 1 && t.outputs[0].payload.size() == 138);
        auto r = acc(t, NODE_A);
        TEST("138-byte bad-sig NODE_BIND REJECTED by mempool", !r.accepted);
        TEST("138-byte poison never reaches the template", mp.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 500 * 1024, NODE_A).txs.empty());
    }
    // invalid NODE_BIND: tampered seq vs signed message
    { np::NodeBindTx b = bind(3, npk_of(4), 1); b.bind_seq = 2;
      TEST("invalid NODE_BIND (seq != signed) REJECTED", !acc(np::build_node_bind_tx(b), NODE_A).accepted); }
    // invalid NODE_HEARTBEAT: node key not bound to anyone
    TEST("invalid NODE_HEARTBEAT (unbound node key) REJECTED",
         !acc(np::build_node_heartbeat_tx(hb(77, 0, tip_for(NODE_A - 1))), NODE_A + 5).accepted);
    // bad signature heartbeat (bind node 6 first so only the sig is wrong)
    live.apply_bind(pkh_of(5), npk_of(6), 1, NODE_A);   // effective NODE_A+1
    { np::NodeHeartbeatTx h = hb(6, 0, tip_for(NODE_A - 1)); h.node_sig[5] ^= 0x01;
      TEST("bad-signature NODE_HEARTBEAT REJECTED", !acc(np::build_node_heartbeat_tx(h), NODE_A + 5).accepted); }
    // future epoch (epoch 1 submitted inside epoch 0)
    TEST("future-epoch NODE_HEARTBEAT REJECTED",
         !acc(np::build_node_heartbeat_tx(hb(6, 1, tip_for(NODE_A + NODE_L - 1))), NODE_A + 5).accepted);
    // wrong tip_ref
    TEST("wrong tip_ref NODE_HEARTBEAT REJECTED",
         !acc(np::build_node_heartbeat_tx(hb(6, 0, tip_for(12345))), NODE_A + 5).accepted);
    // expired heartbeat at the epoch boundary (#30,288 on mainnet geometry)
    {
        Transaction t = np::build_node_heartbeat_tx(hb(6, 0, tip_for(NODE_A - 1)));
        std::string why;
        TEST("epoch-0 heartbeat is INVALID once the block is in epoch 1 (boundary)",
             !node_txs_valid(live, {&t}, NODE_A + NODE_L, why));
        TEST("expired heartbeat REJECTED by mempool at the epoch boundary",
             !acc(t, NODE_A + NODE_L).accepted);
    }
    TEST("node participation live at the V2 height on every build (v16.x rule)", NODE_LIVE);
    {
        // positive controls
        Transaction good = np::build_node_heartbeat_tx(hb(6, 0, tip_for(NODE_A - 1)));
        TEST("valid heartbeat from bound node ACCEPTED (positive control)", acc(good, NODE_A + 5).accepted);
        // stale-in-pool heartbeat: template-time revalidation (what the node's filter does)
        std::string why;
        TEST("in-pool heartbeat becomes invalid at the next epoch -> template filter drops it",
             !node_txs_valid(live, {&good}, NODE_A + NODE_L, why));
        // same-block conflict: two miners bind the SAME node key (F1c)
        Mempool mp2; mp2.SetNodeTxValidator([&](const Transaction& tx, int64_t h, std::string& w) {
            return node_txs_valid(live, {&tx}, h, w); });
        TxValidationContext c; c.spend_height = NODE_A + 1;
        Transaction b1 = np::build_node_bind_tx(bind(10, npk_of(50), 1));
        Transaction b2 = np::build_node_bind_tx(bind(11, npk_of(50), 1));
        const bool a1 = mp2.AcceptToMempool(b1, u, c, 1000).accepted;
        const bool a2 = mp2.AcceptToMempool(b2, u, c, 1000).accepted;
        TEST("F1c: each bind valid alone (both admitted)", a1 && a2);
        TEST("F1c: together they are INVALID -> template keeps only one",
             node_txs_valid(live, {&b1}, NODE_A + 1, why) && !node_txs_valid(live, {&b1, &b2}, NODE_A + 1, why));
    }
    TEST("mempool holds only the one valid heartbeat (no invalid node tx)", mp.Size() == 1);

    // spam bound: the node-tx pool is capped (permissive validator to isolate the cap)
    {
        Mempool sp; sp.SetNodeTxValidator([](const Transaction&, int64_t, std::string&) { return true; });
        TxValidationContext c; c.spend_height = NODE_A + 1;
        size_t admitted = 0;
        for (uint32_t i = 0; i < 4096u + 50; ++i) {
            np::NodeBindTx b; b.mining_pubkey.fill(0x02); b.mining_pubkey[1] = i & 0xff; b.mining_pubkey[2] = (i >> 8) & 0xff;
            b.mining_pubkey[3] = (i >> 16) & 0xff; b.node_pubkey.fill(0x03); b.bind_seq = 1;
            if (sp.AcceptToMempool(np::build_node_bind_tx(b), u, c, 1000).accepted) ++admitted;
        }
        TEST("spam bound: node-tx pool capped at 4096 (Mempool::NODE_TX_MEMPOOL_MAX)", admitted == 4096);
    }
    // fail-closed when the node forgot to install a validator
    {
        Mempool raw; TxValidationContext c; c.spend_height = NODE_A + 1;
        TEST("no validator installed -> valid NODE_BIND still REJECTED (fail-closed)",
             !raw.AcceptToMempool(np::build_node_bind_tx(bind(10, npk_of(51), 1)), u, c, 1000).accepted);
    }
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
    test_asset_bypass();
    test_no_sost_burn();
    std::printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
