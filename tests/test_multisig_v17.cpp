// test_multisig_v17.cpp — native M-of-N multisig (V17, #40,000), consensus-level tests.
//
// Usage: test-multisig-v17 <source-dir> <group>
//   groups: vectors serial policy bech32m sighash validation sigchecks activation reorg mempool
// Each group is its own ctest (multisig-<group>). Mainnet parameter build only for the
// height-specific groups; the pure groups run on any build.
//
// Normative references: docs/v40000/NATIVE_MULTISIG_SPEC_40000.md (r4),
// docs/v40000/MULTISIG_OPEN_DECISIONS_CLOSED.md (D1-D13),
// tests/vectors/native_multisig_40000.json (independently generated vectors).
#include "sost/multisig.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/block_validation.h"
#include "sost/utxo_set.h"
#include "sost/mempool.h"
#include "sost/capsule.h"
#include "sost/params.h"
#include "sost/json_rpc.h"
#include "sost/node_participation.h"
#include "sost/crypto.h"

#include <openssl/sha.h>

#include <algorithm>
#include <cstdio>
#include <functional>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { if (cond) { ++g_pass; } else { ++g_fail; \
    std::printf("  FAIL: %s  [%s:%d]\n", std::string(msg).c_str(), __FILE__, __LINE__); } } while (0)

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
static std::string hex(const uint8_t* d, size_t n) { return HexStr(d, n); }
static std::string hexv(const std::vector<Byte>& v) { return HexStr(v.data(), v.size()); }
template <size_t N> static std::string hexa(const std::array<Byte, N>& a) { return HexStr(a.data(), N); }
static std::vector<Byte> unhex(const std::string& h) {
    std::vector<Byte> v;
    for (size_t i = 0; i + 1 < h.size(); i += 2) v.push_back((Byte)std::stoi(h.substr(i, 2), nullptr, 16));
    return v;
}
template <size_t N> static std::array<Byte, N> unhexa(const std::string& h) {
    std::array<Byte, N> a{}; auto v = unhex(h);
    if (v.size() == N) std::memcpy(a.data(), v.data(), N);
    return a;
}
static PrivKey priv(uint64_t n) { PrivKey k{}; for (int i = 0; i < 8; ++i) k[31 - i] = (Byte)(n >> (8 * i)); return k; }
static PubKey33 pub(uint64_t n) { PubKey p{}; DerivePublicKey(priv(n), p); return p; }

static const Hash256 GENESIS = unhexa<32>("6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");
static constexpr int64_t MH = MULTISIG_HEIGHT;

class MapView : public IUtxoView {
public:
    std::map<OutPoint, UTXOEntry> m;
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        auto it = m.find(op); if (it == m.end()) return std::nullopt; return it->second;
    }
    void put(const Hash256& txid, uint32_t idx, int64_t amount, uint8_t type, const PubKeyHash& pkh,
             std::vector<Byte> payload = {}, int64_t h = 1, bool cb = false) {
        UTXOEntry e; e.amount = amount; e.type = type; e.pubkey_hash = pkh; e.payload = payload;
        e.payload_len = (uint16_t)payload.size(); e.height = h; e.is_coinbase = cb;
        m[OutPoint{txid, idx}] = e;
    }
};

static Hash256 seq_hash(uint8_t start) { Hash256 h{}; for (int i = 0; i < 32; ++i) h[i] = (Byte)(start + i); return h; }

// subtract s from n (secp256k1 order) — for high-S variants
static Sig64 high_s(const Sig64& sig) {
    static const uint8_t N[32] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFE,
                                  0xBA,0xAE,0xDC,0xE6,0xAF,0x48,0xA0,0x3B,0xBF,0xD2,0x5E,0x8C,0xD0,0x36,0x41,0x41};
    Sig64 out = sig; int borrow = 0;
    for (int i = 31; i >= 0; --i) {
        int v = (int)N[i] - (int)sig[32 + i] - borrow;
        borrow = v < 0; if (v < 0) v += 256;
        out[32 + i] = (Byte)v;
    }
    return out;
}

// ---- vectors --------------------------------------------------------------
static json::Value g_vec;
static std::string V(const char* k) { std::string s; g_vec.get_str(k, s); return s; }

static std::vector<PubKey33> keys35() {   // sorted PK of privs 1..5
    std::vector<PubKey33> k;
    const json::Value* a = g_vec.find("PK_sorted");
    if (a && a->is_arr()) for (const auto& e : a->a) k.push_back(unhexa<33>(e.s));
    return k;
}
static std::vector<PubKey33> keys23() {   // canonical 2-of-3, privs 1,2,3
    std::vector<PubKey33> out; MakeCanonicalPolicy(2, {pub(1), pub(2), pub(3)}, out); return out;
}
static int index_of(const std::vector<PubKey33>& ks, const PubKey33& k) {
    for (size_t i = 0; i < ks.size(); ++i) if (ks[i] == k) return (int)i; return -1;
}

// V2-TX-1 (spec §15): in0 3-of-5 multisig (10,000,000,000), in1 single-sig priv 1 (250,000,000).
struct Fixture {
    Transaction tx;              // unsigned template
    std::vector<SpentOutput> spent;
    MapView view;
    std::vector<PubKey33> k;
    PubKeyHash msh{};
};
static Fixture v2tx1_fixture() {
    Fixture f;
    f.k = keys35();
    f.msh = ComputeMultisigPolicyHash(3, f.k);
    Transaction& tx = f.tx;
    tx.version = 2; tx.tx_type = TX_TYPE_STANDARD;
    TxInput a; a.prev_txid = seq_hash(0x00); a.prev_index = 0; a.auth_kind = AUTH_MULTISIG; a.ms_m = 3; a.ms_pubkeys = f.k;
    TxInput b; b.prev_txid = seq_hash(0x20); b.prev_index = 7; b.auth_kind = AUTH_SINGLE;
    tx.inputs = {a, b};
    TxOutput o0; o0.amount = 9'000'000'000LL; o0.type = OUT_TRANSFER; o0.pubkey_hash.fill(0x11);
    for (int i = 0; i < 15; ++i) o0.payload.push_back((Byte)i);
    TxOutput o1; o1.amount = 1'249'990'000LL; o1.type = OUT_MULTISIG; o1.pubkey_hash = f.msh;
    tx.outputs = {o0, o1};
    SpentOutput s0; s0.amount = 10'000'000'000LL; s0.type = OUT_MULTISIG; s0.pubkey_hash = f.msh;
    SpentOutput s1; s1.amount = 250'000'000LL; s1.type = OUT_TRANSFER; s1.pubkey_hash = ComputePubKeyHash(pub(1));
    f.spent = {s0, s1};
    f.view.put(a.prev_txid, 0, s0.amount, s0.type, s0.pubkey_hash);
    f.view.put(b.prev_txid, 7, s1.amount, s1.type, s1.pubkey_hash);
    return f;
}
// Sign a fixture-shaped tx: every multisig input with the given privs, every single input with priv 1.
static void sign_all(Transaction& tx, const std::vector<SpentOutput>& spent, const std::vector<uint64_t>& ms_privs,
                     const ChainId& cid = CHAIN_ID_MAINNET) {
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        if (tx.inputs[i].auth_kind == AUTH_MULTISIG) {
            std::vector<MsSignature> sigs;
            for (uint64_t p : ms_privs) {
                MsSignature s; std::string e;
                if (!SignInputV2Multisig(tx, i, spent, cid, GENESIS, priv(p), s.key_index, s.sig, &e)) continue;
                sigs.push_back(s);
            }
            std::sort(sigs.begin(), sigs.end(), [](const MsSignature& x, const MsSignature& y) { return x.key_index < y.key_index; });
            tx.inputs[i].ms_sigs = sigs;
        }
    }
    for (size_t i = 0; i < tx.inputs.size(); ++i)
        if (tx.inputs[i].auth_kind == AUTH_SINGLE) SignInputV2Single(tx, i, spent, cid, GENESIS, priv(1));
}
static TxValidationContext ctx_at(int64_t h, const ChainId& cid = CHAIN_ID_MAINNET) {
    TxValidationContext c; c.genesis_hash = GENESIS; c.spend_height = h; c.chain_id = cid;
    // devnet builds activate multisig (60) long before the mainnet capsule height (7350);
    // the tests reason about capsule-era heights, so open capsules there too (no-op on mainnet).
    if (c.capsule_activation_height > h) c.capsule_activation_height = 1;
    return c;
}
static TxValidationResult validate(const Transaction& tx, const IUtxoView& v, int64_t h = MH,
                                   const ChainId& cid = CHAIN_ID_MAINNET) {
    return ValidateTransactionConsensus(tx, v, ctx_at(h, cid));
}
static bool code_is(const TxValidationResult& r, TxValCode c) { return !r.ok && r.code == c; }
static std::string codestr(const TxValidationResult& r) { return std::to_string((int)r.code) + " " + r.message; }

// Simple v2 tx: one multisig input (policy m/keys) of `amount`, one output to pkh 0x22.
struct Simple { Transaction tx; std::vector<SpentOutput> spent; MapView view; PubKeyHash msh; };
static Simple simple_ms(uint8_t m, const std::vector<PubKey33>& keys, int64_t amount = 5'000'000'000LL,
                        int64_t out_amount = 4'999'000'000LL, uint8_t out_type = OUT_TRANSFER) {
    Simple s;
    s.msh = ComputeMultisigPolicyHash(m, keys);
    s.tx.version = 2; s.tx.tx_type = TX_TYPE_STANDARD;
    TxInput in; in.prev_txid = seq_hash(0x40); in.prev_index = 1; in.auth_kind = AUTH_MULTISIG; in.ms_m = m; in.ms_pubkeys = keys;
    s.tx.inputs = {in};
    TxOutput o; o.amount = out_amount; o.type = out_type; o.pubkey_hash.fill(0x22);
    if (out_type == OUT_MULTISIG) o.pubkey_hash = s.msh;
    s.tx.outputs = {o};
    SpentOutput sp; sp.amount = amount; sp.type = OUT_MULTISIG; sp.pubkey_hash = s.msh;
    s.spent = {sp};
    s.view.put(in.prev_txid, 1, amount, OUT_MULTISIG, s.msh);
    return s;
}
static std::vector<uint64_t> privs_for(const std::vector<PubKey33>& keys, size_t m) {
    std::vector<uint64_t> out;
    for (uint64_t p = 1; p <= 40 && out.size() < m; ++p) if (index_of(keys, pub(p)) >= 0) out.push_back(p);
    return out;
}
static std::vector<PubKey33> keys_n(size_t n) {   // canonical keys of privs 1..n
    std::vector<PubKey33> raw, out; for (size_t i = 1; i <= n; ++i) raw.push_back(pub(i));
    MakeCanonicalPolicy(1, raw, out); return out;
}

// capsule v1 envelope builder (consensus envelope only)
static std::vector<Byte> envelope(uint8_t type, const std::string& body, uint8_t flags = 0) {
    std::vector<Byte> p = {0x53, 0x43, 0x01, type, flags, 0, 0, 0, 0, (Byte)body.size(), 0, 0};
    p.insert(p.end(), body.begin(), body.end());
    return p;
}

// ===========================================================================
// group: vectors — byte-exact reproduction of tests/vectors/native_multisig_40000.json
// ===========================================================================
static void g_vectors() {
    std::printf("-- vectors\n");
    auto k = keys35();
    CHECK(k.size() == 5, "vector file has 5 sorted keys");
    // keys are privs 5,1,2,4,3 in sorted order (spec §10.2)
    const uint64_t order[5] = {5, 1, 2, 4, 3};
    for (int i = 0; i < 5 && k.size() == 5; ++i) CHECK(k[i] == pub(order[i]), "PK_sorted[" + std::to_string(i) + "] == pub(priv " + std::to_string(order[i]) + ")");
    CHECK(hexv(SerializeMultisigPolicy(3, k)) == V("policy35"), "policy35 bytes");
    CHECK(hexa(ComputeMultisigPolicyHash(3, k)) == V("msh35"), "msh_vector_3of5");
    CHECK(hexa(ComputeMultisigPolicyHash(2, keys23())) == V("msh23"), "msh_vector_2of3");
    CHECK(hexa(CHAIN_ID_MAINNET) == V("chain_id_mainnet"), "chain_id mainnet literal");
    CHECK(hexa(CHAIN_ID_TESTNET) == V("chain_id_testnet"), "chain_id testnet literal");
    CHECK(hexa(CHAIN_ID_DEVNET) == V("chain_id_devnet"), "chain_id devnet literal");
    auto msh35 = ComputeMultisigPolicyHash(3, k);
    CHECK(MultisigAddressEncode(msh35, MsNetwork::MAINNET) == V("addr35_sostms"), "addr35 mainnet");
    CHECK(MultisigAddressEncode(msh35, MsNetwork::TESTNET) == V("addr35_tsostms"), "addr35 testnet");
    CHECK(MultisigAddressEncode(msh35, MsNetwork::DEVNET) == V("addr35_dsostms"), "addr35 devnet");
    CHECK(MultisigAddressEncode(ComputeMultisigPolicyHash(2, keys23()), MsNetwork::MAINNET) == V("addr23_sostms"), "addr23 mainnet");

    Fixture f = v2tx1_fixture();
    std::vector<Byte> raw;
    CHECK(f.tx.Serialize(raw) && hexv(raw) == V("v2tx1_unsigned_template_hex"), "V2-TX-1 unsigned template bytes");
    auto pre = PrecomputeSighashV2(f.tx, f.spent);
    auto pim = BuildSighashV2Preimage(f.tx, 0, f.spent[0], pre, CHAIN_ID_MAINNET, GENESIS);
    CHECK(pim.size() == 246, "v2 preimage is exactly 246 bytes");
    CHECK(hexv(pim) == V("v2sh1_mainnet_in0_preimage"), "vector_V2_SH_1_preimage_bytes");
    const struct { MsNetwork n; const char* k0; const char* k1; } nets[] = {
        {MsNetwork::MAINNET, "v2sh1_mainnet_in0", "v2sh1_mainnet_in1"},
        {MsNetwork::TESTNET, "v2sh1_testnet_in0", "v2sh1_testnet_in1"},
        {MsNetwork::DEVNET,  "v2sh1_devnet_in0",  "v2sh1_devnet_in1"}};
    for (const auto& n : nets) {
        CHECK(hexa(ComputeSighashV2(f.tx, 0, f.spent[0], pre, ChainIdFor(n.n), GENESIS)) == V(n.k0),
              std::string("vector_V2_SH_1_per_network in0 ") + MsNetworkName(n.n));
        CHECK(hexa(ComputeSighashV2(f.tx, 1, f.spent[1], pre, ChainIdFor(n.n), GENESIS)) == V(n.k1),
              std::string("vector_V2_SH_1_per_network in1 ") + MsNetworkName(n.n));
    }
    Transaction t = f.tx;
    sign_all(t, f.spent, {5, 1, 2});
    CHECK(t.inputs[0].ms_sigs.size() == 3, "3 multisig signatures produced");
    if (t.inputs[0].ms_sigs.size() == 3) {
        CHECK(t.inputs[0].ms_sigs[0].key_index == 0 && t.inputs[0].ms_sigs[1].key_index == 1 && t.inputs[0].ms_sigs[2].key_index == 2,
              "key indexes 0,1,2");
        CHECK(hexa(t.inputs[0].ms_sigs[0].sig) == V("v2tx1_in0_sig_idx0"), "RFC6979 sig idx0");
        CHECK(hexa(t.inputs[0].ms_sigs[1].sig) == V("v2tx1_in0_sig_idx1"), "RFC6979 sig idx1");
        CHECK(hexa(t.inputs[0].ms_sigs[2].sig) == V("v2tx1_in0_sig_idx2"), "RFC6979 sig idx2");
    }
    CHECK(hexa(t.inputs[1].signature) == V("v2tx1_in1_sig"), "RFC6979 single sig in1");
    raw.clear();
    CHECK(t.Serialize(raw) && hexv(raw) == V("v2tx1_signed_hex"), "vector_V2_TX_1_signed_hex");
    CHECK(raw.size() == 618 && TxSerializedSizeExact(t) == 618 && EstimateTxSerializedSize(t) == 618, "V2-TX-1 is 618 bytes (exact size)");
    CHECK(t.ComputeTxIdHex() == V("v2tx1_txid"), "vector_V2_TX_1_txid");
    Transaction back; std::string e;
    CHECK(Transaction::Deserialize(unhex(V("v2tx1_signed_hex")), back, &e), "signed vector parses");
    std::vector<Byte> rt; back.Serialize(rt);
    CHECK(hexv(rt) == V("v2tx1_signed_hex"), "signed vector round-trips byte-for-byte");
    auto r = validate(back, f.view);
    CHECK(r.ok, "V2-TX-1 consensus-valid at MULTISIG_HEIGHT: " + codestr(r));
}

// ===========================================================================
// group: serial — parse rules X1-X6 and layout dispatch (D2)
// ===========================================================================
static void g_serial() {
    std::printf("-- serial\n");
    const auto signed_raw = unhex(V("v2tx1_signed_hex"));
    Transaction t; std::string e;
    CHECK(Transaction::Deserialize(signed_raw, t, &e) && t.version == 2 && t.inputs[0].auth_kind == AUTH_MULTISIG
          && t.inputs[0].ms_pubkeys.size() == 5 && t.inputs[0].ms_sigs.size() == 3, "ms_dispatch_version2_uses_v2_inputs");
    // X1 truncated: every proper prefix fails
    int bad_prefix = 0;
    for (size_t n = 0; n < signed_raw.size(); ++n) {
        std::vector<Byte> p(signed_raw.begin(), signed_raw.begin() + n);
        Transaction x; if (Transaction::Deserialize(p, x, nullptr)) ++bad_prefix;
    }
    CHECK(bad_prefix == 0, "X1: every truncation of V2-TX-1 is rejected");
    // X2 trailing bytes
    { auto p = signed_raw; p.push_back(0); Transaction x; std::string er;
      CHECK(!Transaction::Deserialize(p, x, &er) && er.find("trailing") != std::string::npos, "X2 trailing_bytes"); }
    // offsets inside V2-TX-1: version(4) type(1) nin(1) prev(32) idx(4) auth_kind @42, M @43, N @44
    { auto p = signed_raw; p[42] = 0x02; Transaction x; std::string er;
      CHECK(!Transaction::Deserialize(p, x, &er) && er == "unknown_auth_kind", "X3 unknown_auth_kind (0x02)"); }
    { auto p = signed_raw; p[42] = 0xFF; Transaction x; std::string er;
      CHECK(!Transaction::Deserialize(p, x, &er) && er == "unknown_auth_kind", "X3 unknown_auth_kind (0xff)"); }
    { auto p = signed_raw; p[44] = 0; Transaction x; std::string er;
      CHECK(!Transaction::Deserialize(p, x, &er) && er == "policy_n_range", "X4 N = 0"); }
    { auto p = signed_raw; p[44] = 16; Transaction x; std::string er;
      CHECK(!Transaction::Deserialize(p, x, &er) && er == "policy_n_range", "X4 N = 16"); }
    // K byte at 45 + 33*5 = 210
    CHECK(signed_raw[210] == 3, "K byte located");
    { auto p = signed_raw; p[210] = 16; Transaction x; std::string er;
      CHECK(!Transaction::Deserialize(p, x, &er) && er == "sig_count_range", "X5 K = 16"); }
    // K = 0 parses (unsigned template)
    { Transaction x; CHECK(Transaction::Deserialize(unhex(V("v2tx1_unsigned_template_hex")), x, nullptr) && x.inputs[0].ms_sigs.empty(),
            "K = 0 parses (template)"); }
    // M not checked at parse time: M = 0 parses, rejected later by R26
    { auto p = signed_raw; p[43] = 0; Transaction x; CHECK(Transaction::Deserialize(p, x, nullptr) && x.inputs[0].ms_m == 0, "M = 0 parses (R26 rejects)"); }
    // X6 non-canonical CompactSize for nin
    { std::vector<Byte> p(signed_raw.begin(), signed_raw.begin() + 5);
      p.push_back(0xFD); p.push_back(0x02); p.push_back(0x00);
      p.insert(p.end(), signed_raw.begin() + 6, signed_raw.end());
      Transaction x; CHECK(!Transaction::Deserialize(p, x, nullptr), "noncanonical_compactsize_rejected"); }
    // version 3: v1 layout
    { Transaction v1; v1.version = 3; v1.tx_type = TX_TYPE_STANDARD; TxInput in; in.prev_txid = seq_hash(1); v1.inputs = {in};
      TxOutput o; o.amount = 1; v1.outputs = {o};
      std::vector<Byte> b; v1.Serialize(b);
      CHECK(b.size() == 4 + 1 + 1 + 133 + 1 + 31, "ms_dispatch_version3_uses_v1_inputs (133-byte input)");
      Transaction x; CHECK(Transaction::Deserialize(b, x, nullptr) && x.version == 3, "version 3 round-trips with v1 layout"); }
    // node tx with zero inputs: identical bytes under both layouts
    { node_participation::NodeHeartbeatTx h{}; h.epoch_idx = 7;
      Transaction n1 = node_participation::build_node_heartbeat_tx(h);
      Transaction n2 = n1; n2.version = 2;
      std::vector<Byte> b1, b2; n1.Serialize(b1); n2.Serialize(b2);
      bool same_after_version = b1.size() == b2.size() && std::equal(b1.begin() + 4, b1.end(), b2.begin() + 4);
      Transaction x; bool parses = Transaction::Deserialize(b2, x, nullptr) && x.inputs.empty() && x.outputs.size() == 1;
      CHECK(same_after_version && parses, "ms_node_tx_v2_zero_inputs_parses_identically"); }
    // exact sizes (spec §3.3)
    auto size_of = [](uint8_t m, size_t n, size_t k) { TxInput in; in.auth_kind = AUTH_MULTISIG; in.ms_m = m;
        in.ms_pubkeys.resize(n); in.ms_sigs.resize(k); return TxInputV2Size(in); };
    TxInput single; single.auth_kind = AUTH_SINGLE;
    CHECK(TxInputV2Size(single) == 134, "v2 single-sig input = 134 B");
    CHECK(size_of(1, 1, 1) == 138, "1-of-1 input = 138 B");
    CHECK(size_of(2, 3, 2) == 269, "2-of-3 input = 269 B");
    CHECK(size_of(3, 5, 3) == 400, "3-of-5 input = 400 B");
    CHECK(size_of(5, 5, 5) == 530, "5-of-5 input = 530 B");
    CHECK(size_of(15, 15, 15) == 1510, "tx_size_15of15_input_1510");
    // tx_size == serialized length (v1 corpus + v2)
    int mism = 0;
    for (int nin = 1; nin <= 3; ++nin) for (int nout = 1; nout <= 4; ++nout) for (int pl : {0, 1, 80, 255, 512}) {
        Transaction v; v.version = 1; v.tx_type = TX_TYPE_STANDARD;
        for (int i = 0; i < nin; ++i) { TxInput in; in.prev_txid = seq_hash((uint8_t)i); v.inputs.push_back(in); }
        for (int o = 0; o < nout; ++o) { TxOutput out; out.amount = 1; out.payload.assign((size_t)pl, 0xAB); v.outputs.push_back(out); }
        std::vector<Byte> b; v.Serialize(b);
        if (b.size() != EstimateTxSerializedSize(v) || b.size() != TxSerializedSizeExact(v)) ++mism;
        Transaction w = v; w.version = 2; b.clear(); w.Serialize(b);
        if (b.size() != EstimateTxSerializedSize(w)) ++mism;
    }
    CHECK(mism == 0, "tx_size_equals_serialized_len_v1_corpus (+v2), 60 shapes");
}

// ===========================================================================
// group: policy — R26 + MSH
// ===========================================================================
static void g_policy() {
    std::printf("-- policy\n");
    for (size_t n : {1u, 3u, 5u, 15u}) {
        auto ks = keys_n(n);
        for (uint8_t m : {(uint8_t)1, (uint8_t)n}) {
            std::string e;
            CHECK(CheckMultisigPolicy(m, ks, &e), "policy_" + std::to_string(m) + "of" + std::to_string(n) + " accepted");
        }
    }
    CHECK(CheckMultisigPolicy(2, keys_n(3)), "policy_2of3");
    CHECK(CheckMultisigPolicy(3, keys_n(5)), "policy_3of5");
    std::string e;
    CHECK(!CheckMultisigPolicy(0, keys_n(3), &e) && e == "policy_m_zero", "m0 -> R26");
    CHECK(!CheckMultisigPolicy(4, keys_n(3), &e) && e == "policy_m_gt_n", "m_gt_n -> R26");
    { auto ks = keys_n(3); std::swap(ks[0], ks[2]); CHECK(!CheckMultisigPolicy(2, ks, &e), "unsorted -> R26"); }
    { auto ks = keys_n(3); ks[1] = ks[0]; CHECK(!CheckMultisigPolicy(2, ks, &e), "duplicate -> R26"); }
    { auto ks = keys_n(3); ks[0][0] = 0x04; CHECK(!CheckMultisigPolicy(2, ks, &e) && e == "policy_key_prefix", "prefix_04 (uncompressed) -> R26"); }
    { auto ks = keys_n(3); PubKey33 off{}; off[0] = 0x02;            // x = 0 is not on secp256k1
      ks[0] = off; CHECK(!CheckMultisigPolicy(2, ks, &e) && e == "policy_key_off_curve", "off_curve -> R26"); }
    CHECK(!CheckMultisigPolicy(1, {}, &e), "N = 0 -> R26");
    { std::vector<PubKey33> big; for (int i = 1; i <= 16; ++i) big.push_back(pub(i));
      std::vector<PubKey33> out; CHECK(!MakeCanonicalPolicy(1, big, out, &e), "N = 16 -> rejected"); }
    { std::vector<PubKey33> out; CHECK(!MakeCanonicalPolicy(2, {pub(1), pub(2), pub(1)}, out, &e) && e == "policy_duplicate_key",
            "wallet: duplicate key refused"); }
    { std::vector<PubKey33> out; CHECK(MakeCanonicalPolicy(3, {pub(1), pub(2), pub(3), pub(4), pub(5)}, out) && out == keys35(),
            "createmultisig sorting reproduces PK_sorted"); }
    // domain separation: MSH of a 1-of-1 differs from the key's pkh
    CHECK(ComputeMultisigPolicyHash(1, {pub(1)}) != ComputePubKeyHash(pub(1)), "MSH != pkh for the same key (domain separation)");
}

// ===========================================================================
// group: bech32m
// ===========================================================================
static void g_bech32m() {
    std::printf("-- bech32m\n");
    PubKeyHash out{}; std::string e;
    auto msh35 = unhexa<20>(V("msh35"));
    CHECK(MultisigAddressDecode(V("addr35_sostms"), MsNetwork::MAINNET, out, &e) && out == msh35, "decode mainnet vector");
    CHECK(MultisigAddressDecode(V("addr35_tsostms"), MsNetwork::TESTNET, out, &e) && out == msh35, "decode testnet vector");
    CHECK(MultisigAddressDecode(V("addr35_dsostms"), MsNetwork::DEVNET, out, &e) && out == msh35, "decode devnet vector");
    CHECK(MultisigAddressDecode(V("addr23_sostms"), MsNetwork::MAINNET, out, &e) && hexa(out) == V("msh23"), "decode 2-of-3 vector");
    CHECK(V("addr35_sostms").size() == 47 && V("addr35_tsostms").size() == 48 && V("addr35_dsostms").size() == 48, "lengths 47/48/48");
    CHECK(!MultisigAddressDecode("sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6jq", MsNetwork::MAINNET, out, &e) && e == "bad_checksum",
          "last char changed -> REJECT");
    CHECK(!MultisigAddressDecode("tsostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7", MsNetwork::MAINNET, out, &e),
          "testnet HRP on mainnet body -> REJECT");
    CHECK(!MultisigAddressDecode(V("addr35_tsostms"), MsNetwork::MAINNET, out, &e) && e == "wrong_hrp", "wrong HRP for network");
    CHECK(!MultisigAddressDecode(V("addr35_sostms"), MsNetwork::DEVNET, out, &e) && e == "wrong_hrp", "mainnet addr on devnet");
    { std::string up = V("addr35_sostms"); for (auto& c : up) c = (char)toupper(c);
      CHECK(!MultisigAddressDecode(up, MsNetwork::MAINNET, out, &e) && e == "upper_case", "upper case rejected"); }
    { std::string mx = V("addr35_sostms"); mx[7] = (char)toupper(mx[7]);
      CHECK(!MultisigAddressDecode(mx, MsNetwork::MAINNET, out, &e) && e == "mixed_case", "mixed case rejected"); }
    { std::string nb = V("addr35_sostms"); nb[12] = 'b';   // 'b' is not in the alphabet
      CHECK(!MultisigAddressDecode(nb, MsNetwork::MAINNET, out, &e) && e == "char_not_in_alphabet", "char outside alphabet"); }
    CHECK(!MultisigAddressDecode("sostmsq9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7", MsNetwork::MAINNET, out, &e), "missing separator");
    { std::string longs = "sostms1" + std::string(90, 'q'); CHECK(!MultisigAddressDecode(longs, MsNetwork::MAINNET, out, &e) && e == "too_long", "length > 90"); }
    // format byte != 0x01 and length != 21 (valid checksums, wrong content)
    auto enc_raw = [](const std::vector<uint8_t>& raw) {
        std::vector<uint8_t> d5; uint32_t acc = 0; int bits = 0;
        for (uint8_t b : raw) { acc = ((acc << 8) | b) & 0xFFF; bits += 8; while (bits >= 5) { bits -= 5; d5.push_back((acc >> bits) & 31); } }
        if (bits) d5.push_back((acc << (5 - bits)) & 31);
        return Bech32mEncode("sostms", d5);
    };
    { std::vector<uint8_t> r(21, 0x07); r[0] = 0x02; CHECK(!MultisigAddressDecode(enc_raw(r), MsNetwork::MAINNET, out, &e) && e == "bad_format_byte", "format byte != 0x01"); }
    { std::vector<uint8_t> r(22, 0x07); r[0] = 0x01; CHECK(!MultisigAddressDecode(enc_raw(r), MsNetwork::MAINNET, out, &e) && e == "bad_length", "length 22 != 21"); }
    { std::vector<uint8_t> r(20, 0x07); r[0] = 0x01; CHECK(!MultisigAddressDecode(enc_raw(r), MsNetwork::MAINNET, out, &e), "length 20 != 21"); }
    // non-zero padding: flip the low bits of the last data group, recompute checksum
    { std::string hrp; std::vector<uint8_t> d5; Bech32mDecode(V("addr35_sostms"), hrp, d5);
      d5.back() |= 0x01; std::string bad = Bech32mEncode(hrp, d5);
      CHECK(!MultisigAddressDecode(bad, MsNetwork::MAINNET, out, &e) && e == "nonzero_padding", "non-zero padding rejected"); }
    // BIP-350 official valid bech32m checksum vectors
    const char* bip350_valid[] = {
        "a1lqfn3a", "an83characterlonghumanreadablepartthatcontainsthetheexcludedcharactersbioandnumber11sg7hg6",
        "abcdef1l7aum6echk45nj3s0wdvt2fg8x9yrzpqzd3ryx", "11llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllludsr8",
        "split1checkupstagehandshakeupstreamerranterredcaperredlc445v", "?1v759aa"};
    int okv = 0; for (const char* s : bip350_valid) { std::string h; std::vector<uint8_t> d; if (Bech32mDecode(s, h, d)) ++okv; }
    CHECK(okv == 6, "BIP-350 valid bech32m vectors decode (6/6)");
    const char* bip350_invalid[] = {"an84characterslonghumanreadablepartthatcontainsthetheexcludedcharactersbioandnumber11d6pts4",
        "qyrz8wqd2c9m", "1qyrz8wqd2c9m", "y1b0jsk6g", "lt1igcx5c0", "in1muywd", "mm1crxm3i", "au1s5cgom", "M1VUXWEZ",
        "16plkw9", "1p2gdwpf", "a12uel5l" /* bech32 (not m) checksum */};
    int badv = 0; for (const char* s : bip350_invalid) { std::string h; std::vector<uint8_t> d; if (!Bech32mDecode(s, h, d)) ++badv; }
    CHECK(badv == 12, "BIP-350 invalid vectors rejected (12/12)");
    CHECK(LooksLikeMultisigAddress(V("addr35_sostms")) && !LooksLikeMultisigAddress("sost1" + std::string(40, '0')), "classifier");
    // round trip random MSHs
    int rt = 0; for (int i = 0; i < 200; ++i) { PubKeyHash m{}; for (int j = 0; j < 20; ++j) m[j] = (Byte)(i * 31 + j * 7);
        for (auto n : {MsNetwork::MAINNET, MsNetwork::TESTNET, MsNetwork::DEVNET}) {
            PubKeyHash o{}; if (MultisigAddressDecode(MultisigAddressEncode(m, n), n, o) && o == m) ++rt; } }
    CHECK(rt == 600, "encode/decode round trip 600/600");
}

// ===========================================================================
// group: sighash — CHAIN_ID, spent-output commitment, D1 payload length
// ===========================================================================
static void g_sighash() {
    std::printf("-- sighash\n");
    CHECK(CHAIN_ID_MAINNET != CHAIN_ID_TESTNET && CHAIN_ID_MAINNET != CHAIN_ID_DEVNET && CHAIN_ID_TESTNET != CHAIN_ID_DEVNET,
          "chain_ids_pairwise_distinct");
    // provenance re-derivation (informative)
    for (auto n : {MsNetwork::MAINNET, MsNetwork::TESTNET, MsNetwork::DEVNET}) {
        std::string pre = std::string("SOST-CHAIN-ID-V1|") + (n == MsNetwork::MAINNET ? "mainnet" : n == MsNetwork::TESTNET ? "testnet" : "devnet") +
                          "|6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37";
        auto h = sha256(reinterpret_cast<const uint8_t*>(pre.data()), pre.size());
        CHECK(std::equal(h.begin(), h.end(), ChainIdFor(n).begin()), std::string("chain_id provenance ") + MsNetworkName(n));
    }
    MsNetwork dn; CHECK(MsNetworkFromName("dev", dn) && dn == MsNetwork::DEVNET && ChainIdFor(dn) == CHAIN_ID_DEVNET,
                        "cli_network_dev_maps_to_devnet_chain_id");
#if !defined(SOST_DEVNET_FORKS) && !defined(SOST_TESTNET_FORKS)
    CHECK(ACTIVE_CHAIN_ID == CHAIN_ID_MAINNET && ActiveMsNetwork() == MsNetwork::MAINNET, "mainnet build selects the mainnet CHAIN_ID");
#endif
    Fixture f = v2tx1_fixture();
    // cross-network replay: sign on X, validate on Y
    const struct { MsNetwork sign; MsNetwork val; const char* name; } cases[] = {
        {MsNetwork::MAINNET, MsNetwork::TESTNET, "v2_sig_mainnet_rejected_on_testnet"},
        {MsNetwork::MAINNET, MsNetwork::DEVNET,  "v2_sig_mainnet_rejected_on_devnet"},
        {MsNetwork::TESTNET, MsNetwork::MAINNET, "v2_sig_testnet_rejected_on_mainnet"},
        {MsNetwork::DEVNET,  MsNetwork::MAINNET, "v2_sig_devnet_rejected_on_mainnet"}};
    for (const auto& c : cases) {
        Transaction t = f.tx; sign_all(t, f.spent, {5, 1, 2}, ChainIdFor(c.sign));
        auto ok_same = validate(t, f.view, MH, ChainIdFor(c.sign));
        auto bad = validate(t, f.view, MH, ChainIdFor(c.val));
        CHECK(ok_same.ok && code_is(bad, TxValCode::S18_MS_SIG_INVALID), std::string(c.name) + ": " + codestr(bad));
    }
    // single-sig v2 input cross-network: S6
    { Transaction t = f.tx; sign_all(t, f.spent, {5, 1, 2}, CHAIN_ID_TESTNET);
      // replace multisig sigs with mainnet ones so only the single input is wrong
      Transaction m = f.tx; sign_all(m, f.spent, {5, 1, 2}, CHAIN_ID_MAINNET);
      t.inputs[0].ms_sigs = m.inputs[0].ms_sigs;
      auto r = validate(t, f.view);
      CHECK(code_is(r, TxValCode::S6_VERIFY_FAIL) && r.input_index == 1, "v2 single-sig signed for testnet rejected on mainnet (S6): " + codestr(r)); }
    // lying spent outputs (D12): signer is told a false amount/type/payload for the OTHER input
    auto lie = [&](const char* name, std::function<void(std::vector<SpentOutput>&)> mut) {
        auto sp = f.spent; mut(sp);
        Transaction t = f.tx; sign_all(t, sp, {5, 1, 2});
        auto r = validate(t, f.view);
        CHECK(code_is(r, TxValCode::S18_MS_SIG_INVALID) && r.input_index == 0, std::string(name) + ": " + codestr(r));
    };
    lie("lying_spent_amount_other_input_invalidates_sig", [](std::vector<SpentOutput>& s) { s[1].amount += 1; });
    lie("lying_spent_type_invalidates_sig", [](std::vector<SpentOutput>& s) { s[1].type = OUT_COINBASE_MINER; });
    lie("lying_spent_payload_invalidates_sig", [](std::vector<SpentOutput>& s) { s[1].payload = {0x01}; });
    lie("lying_spent_lock_invalidates_sig", [](std::vector<SpentOutput>& s) { s[1].pubkey_hash[0] ^= 1; });
    lie("wrong_spent_amount_own_input", [](std::vector<SpentOutput>& s) { s[0].amount -= 1; });
    // D1: hashOutputs_v2 uses the wire u16 length
    {
        Transaction t = f.tx; t.outputs[0].payload.assign(256, 0x5A);
        auto pre = PrecomputeSighashV2(t, f.spent);
        std::vector<Byte> wire;
        for (const auto& o : t.outputs) { std::vector<Byte> b; o.SerializeTo(b); wire.insert(wire.end(), b.begin(), b.end()); }
        Hash256 a{}, b{}; SHA256(wire.data(), wire.size(), a.data()); SHA256(a.data(), 32, b.data());
        CHECK(pre.ok && pre.hash_outputs == b, "v2_hashoutputs_matches_wire_bytes (+ v2_hashoutputs_u16_len_256_payload)");
        Transaction t2 = f.tx; t2.outputs[0].payload.assign(512, 0x5A);
        sign_all(t2, f.spent, {5, 1, 2});
        auto r = validate(t2, f.view);
        CHECK(r.ok, "v2_hashoutputs_512_payload_signs_and_verifies: " + codestr(r));
    }
    // v1 sighash unchanged + v1 255 cap unchanged
    {
        Transaction v1; v1.version = 1; v1.tx_type = TX_TYPE_STANDARD;
        TxInput in; in.prev_txid = seq_hash(0x60); in.prev_index = 0; v1.inputs = {in};
        TxOutput o; o.amount = 99'000'000; o.pubkey_hash.fill(0x22); o.payload.assign(256, 0x41); v1.outputs = {o};
        SpentOutput sp; sp.amount = 100'000'000; sp.type = OUT_TRANSFER;
        std::string er;
        CHECK(!SignTransactionInput(v1, 0, sp, GENESIS, priv(1), &er), "v1_sighash_255_cap_unchanged (signer refuses 256-byte payload)");
        MapView mv; mv.put(in.prev_txid, 0, sp.amount, OUT_TRANSFER, ComputePubKeyHash(pub(1)));
        auto r = validate(v1, mv);
        CHECK(!r.ok && r.code == TxValCode::S6_VERIFY_FAIL, "v1 tx with 256-byte payload stays S6 at MULTISIG_HEIGHT: " + codestr(r));
        // v1 sighash bytes: 146-byte preimage formula reproduced independently
        Transaction v1b = v1; v1b.outputs[0].payload.clear();
        Hash256 h = ComputeSighash(v1b, 0, sp, GENESIS);
        std::vector<Byte> pre;
        auto put32 = [&](uint32_t x) { for (int i = 0; i < 4; ++i) pre.push_back((Byte)(x >> (8 * i))); };
        auto put64 = [&](int64_t x) { for (int i = 0; i < 8; ++i) pre.push_back((Byte)((uint64_t)x >> (8 * i))); };
        put32(1); pre.push_back(0);
        std::vector<Byte> hp(in.prev_txid.begin(), in.prev_txid.end()); for (int i = 0; i < 4; ++i) hp.push_back(0);
        Hash256 t1{}, hpo{}; SHA256(hp.data(), hp.size(), t1.data()); SHA256(t1.data(), 32, hpo.data());
        pre.insert(pre.end(), hpo.begin(), hpo.end());
        pre.insert(pre.end(), in.prev_txid.begin(), in.prev_txid.end()); put32(0); put64(sp.amount); pre.push_back(OUT_TRANSFER);
        std::vector<Byte> ho; { int64_t a = 99'000'000; for (int i = 0; i < 8; ++i) ho.push_back((Byte)((uint64_t)a >> (8 * i))); }
        ho.push_back(0); for (int i = 0; i < 20; ++i) ho.push_back(0x22); ho.push_back(0);   // ONE length byte in v1
        Hash256 t2{}, hou{}; SHA256(ho.data(), ho.size(), t2.data()); SHA256(t2.data(), 32, hou.data());
        pre.insert(pre.end(), hou.begin(), hou.end()); pre.insert(pre.end(), GENESIS.begin(), GENESIS.end());
        Hash256 t3{}, want{}; SHA256(pre.data(), pre.size(), t3.data()); SHA256(t3.data(), 32, want.data());
        CHECK(pre.size() == 146 && h == want, "v1_sighash_bytes_unchanged_vector (146-byte preimage)");
    }
}

// ===========================================================================
// group: validation — full valid/invalid matrix at MULTISIG_HEIGHT
// ===========================================================================
static void g_validation() {
    std::printf("-- validation\n");
    // M/N bounds, full signing
    const struct { uint8_t m; size_t n; } shapes[] = {{1, 1}, {2, 3}, {3, 5}, {5, 5}, {15, 15}, {1, 15}};
    for (const auto& sh : shapes) {
        auto ks = keys_n(sh.n);
        Simple s = simple_ms(sh.m, ks);
        sign_all(s.tx, s.spent, privs_for(ks, sh.m));
        auto r = validate(s.tx, s.view);
        CHECK(r.ok, "valid " + std::to_string(sh.m) + "-of-" + std::to_string(sh.n) + " spend: " + codestr(r));
    }
    auto ks5 = keys35();
    Simple base = simple_ms(3, ks5);
    Transaction good = base.tx; sign_all(good, base.spent, {5, 1, 2});
    CHECK(validate(good, base.view).ok, "baseline 3-of-5 valid");
    auto expect = [&](const char* name, const Transaction& t, TxValCode c, const MapView* v = nullptr) {
        auto r = validate(t, v ? *v : base.view);
        CHECK(code_is(r, c), std::string(name) + ": got " + codestr(r));
    };
    // R26 inside a tx
    { Transaction t = good; std::swap(t.inputs[0].ms_pubkeys[0], t.inputs[0].ms_pubkeys[1]); expect("unsorted keys in tx -> R26", t, TxValCode::R26_MS_POLICY); }
    { Transaction t = good; t.inputs[0].ms_pubkeys[1] = t.inputs[0].ms_pubkeys[0]; expect("duplicate key in tx -> R26", t, TxValCode::R26_MS_POLICY); }
    { Transaction t = good; t.inputs[0].ms_pubkeys[0][0] = 0x04; expect("uncompressed (0x04) key in tx -> R26", t, TxValCode::R26_MS_POLICY); }
    { Transaction t = good; t.inputs[0].ms_m = 0; t.inputs[0].ms_sigs.clear(); expect("M = 0 -> R26", t, TxValCode::R26_MS_POLICY); }
    { Transaction t = good; t.inputs[0].ms_m = 6; expect("M > N -> R26", t, TxValCode::R26_MS_POLICY); }
    // R27
    { Transaction t = good; t.inputs[0].ms_sigs.pop_back(); expect("M-1 signatures -> R27", t, TxValCode::R27_MS_SIG_COUNT); }
    { Transaction t = base.tx; sign_all(t, base.spent, {5, 1, 2, 4}); expect("M+1 signatures -> R27 (third_party_cannot_add_sig)", t, TxValCode::R27_MS_SIG_COUNT); }
    { Transaction t = good; t.inputs[0].ms_sigs.clear(); expect("K = 0 template -> R27", t, TxValCode::R27_MS_SIG_COUNT); }
    // R28
    { Transaction t = good; std::swap(t.inputs[0].ms_sigs[0], t.inputs[0].ms_sigs[1]); expect("third_party_cannot_reorder_sigs_R28", t, TxValCode::R28_MS_KEY_INDEX); }
    { Transaction t = good; t.inputs[0].ms_sigs[1].key_index = t.inputs[0].ms_sigs[0].key_index; expect("repeated key index -> R28", t, TxValCode::R28_MS_KEY_INDEX); }
    { Transaction t = good; t.inputs[0].ms_sigs[2].key_index = 5; expect("key index >= N -> R28", t, TxValCode::R28_MS_KEY_INDEX); }
    // S4 / S5 / S18
    { Transaction t = good; t.inputs[0].ms_sigs[1].sig.fill(0); expect("all-zero multisig sig -> S4", t, TxValCode::S4_ZERO_SIGNATURE); }
    { Transaction t = good; t.inputs[0].ms_sigs[1].sig = high_s(t.inputs[0].ms_sigs[1].sig); expect("high_s_variant_rejected_S5", t, TxValCode::S5_HIGH_S); }
    { Transaction t = good; for (int i = 0; i < 32; ++i) t.inputs[0].ms_sigs[0].sig[i] = 0xFF; expect("r >= n -> S5", t, TxValCode::S5_HIGH_S); }
    { Transaction t = good; for (int i = 0; i < 32; ++i) t.inputs[0].ms_sigs[0].sig[32 + i] = 0; expect("s = 0 -> S5", t, TxValCode::S5_HIGH_S); }
    { Transaction t = good; t.inputs[0].ms_sigs[0].sig[5] ^= 0x01; expect("tampered multisig sig -> S18", t, TxValCode::S18_MS_SIG_INVALID); }
    { // signature by a key NOT at the claimed index: sign with priv 4 (index 3) but label index 0
      Transaction t = good; MsSignature s; std::string e;
      SignInputV2Multisig(base.tx, 0, base.spent, CHAIN_ID_MAINNET, GENESIS, priv(4), s.key_index, s.sig, &e);
      t.inputs[0].ms_sigs[0].sig = s.sig; expect("sig of another policy key at wrong index -> S18 (no trial matching)", t, TxValCode::S18_MS_SIG_INVALID); }
    { Transaction t = good; t.outputs[0].amount -= 1; expect("output changed after signing -> S18", t, TxValCode::S18_MS_SIG_INVALID); }
    // S17
    { MapView v = base.view; for (auto& kv : v.m) kv.second.pubkey_hash[0] ^= 0x01; expect("MSH mismatch -> S17", good, TxValCode::S17_MSH_MISMATCH, &v); }
    { Transaction t = good; std::vector<PubKey33> ks; MakeCanonicalPolicy(3, {pub(6), pub(7), pub(8), pub(9), pub(10)}, ks);
      t.inputs[0].ms_pubkeys = ks;   // different policy, same shape
      expect("different policy than the lock -> S17", t, TxValCode::S17_MSH_MISMATCH); }
    // combiner subset malleability (D6)
    { Transaction a = base.tx, b = base.tx; sign_all(a, base.spent, {5, 1, 2}); sign_all(b, base.spent, {5, 1, 4});
      CHECK(validate(a, base.view).ok && validate(b, base.view).ok && a.ComputeTxIdHex() != b.ComputeTxIdHex() &&
            a.outputs[0].amount == b.outputs[0].amount, "combiner_subset_changes_txid_not_effect"); }

    // ---- S16 auth-kind table (spec §6, D5) ----
    PubKeyHash pk1 = ComputePubKeyHash(pub(1));
    {   // v1 input spending 0x50
        Transaction t; t.version = 1; t.tx_type = TX_TYPE_STANDARD; TxInput in; in.prev_txid = seq_hash(0x40); in.prev_index = 1; t.inputs = {in};
        TxOutput o; o.amount = 4'999'000'000LL; o.pubkey_hash.fill(0x22); t.outputs = {o};
        SpentOutput sp; sp.amount = 5'000'000'000LL; sp.type = OUT_MULTISIG;
        SignTransactionInput(t, 0, sp, GENESIS, priv(1), nullptr);
        expect("v1_input_spending_0x50_rejected_S16", t, TxValCode::S16_AUTH_KIND_MISMATCH);
    }
    {   // v2 single spending 0x50
        Transaction t = base.tx; t.inputs[0] = TxInput{}; t.inputs[0].prev_txid = seq_hash(0x40); t.inputs[0].prev_index = 1;
        SignInputV2Single(t, 0, base.spent, CHAIN_ID_MAINNET, GENESIS, priv(1));
        expect("v2_single_spending_0x50_rejected_S16", t, TxValCode::S16_AUTH_KIND_MISMATCH);
    }
    {   // v2 multisig spending OUT_TRANSFER
        MapView v; v.put(seq_hash(0x40), 1, 5'000'000'000LL, OUT_TRANSFER, base.msh);
        expect("v2_multisig_spending_transfer_rejected_S16", good, TxValCode::S16_AUTH_KIND_MISMATCH, &v);
    }
    std::vector<Byte> lock_payload; std::array<Byte, 32> preimage{}; preimage.fill(0x77);
    Bytes32 hl = sha256(preimage.data(), 32);
    std::array<Byte, 32> hla{}; std::copy(hl.begin(), hl.end(), hla.begin());
    WriteHtlcLockPayload(lock_payload, hla, (uint64_t)MH + 100, pk1, pk1);
    {   // v2 multisig spending HTLC lock -> S16 ; v2 single spending HTLC lock -> R20
        MapView v; v.put(seq_hash(0x40), 1, 5'000'000'000LL, OUT_HTLC_LOCK, base.msh, lock_payload);
        expect("v2_multisig_spending_htlc_lock_rejected_S16", good, TxValCode::S16_AUTH_KIND_MISMATCH, &v);
        Transaction t = base.tx; t.inputs[0] = TxInput{}; t.inputs[0].prev_txid = seq_hash(0x40); t.inputs[0].prev_index = 1;
        std::vector<SpentOutput> sp = {SpentOutput{5'000'000'000LL, OUT_HTLC_LOCK, base.msh, lock_payload}};
        SignInputV2Single(t, 0, sp, CHAIN_ID_MAINNET, GENESIS, priv(1));
        expect("v2_single_spending_htlc_lock_rejected_R20", t, TxValCode::R20_HTLC_CLAIM_INPUT_INVALID, &v);
    }
    {   // HTLC claim (v1) paying to OUT_MULTISIG is fine; the same claim as v2 -> R25
        MapView v; v.put(seq_hash(0x50), 0, 5'000'000'000LL, OUT_HTLC_LOCK, pk1, lock_payload);
        Transaction c; c.version = 1; c.tx_type = TX_TYPE_HTLC_CLAIM;
        TxInput in; in.prev_txid = seq_hash(0x50); in.prev_index = 0; c.inputs = {in};
        TxOutput w; w.amount = DUST_THRESHOLD; w.type = OUT_HTLC_CLAIM_WITNESS; w.pubkey_hash = pk1;
        w.payload.assign(preimage.begin(), preimage.end());
        TxOutput ms; ms.amount = 4'998'000'000LL; ms.type = OUT_MULTISIG; ms.pubkey_hash = base.msh;
        c.outputs = {w, ms};
        SpentOutput sp; sp.amount = 5'000'000'000LL; sp.type = OUT_HTLC_LOCK;
        SignTransactionInput(c, 0, sp, GENESIS, priv(1), nullptr);
        auto r = validate(c, v);
        CHECK(r.ok, "htlc_claim_paying_to_0x50_ok: " + codestr(r));
        auto r39 = validate(c, v, MH - 1);
        CHECK(code_is(r39, TxValCode::R11_INACTIVE_TYPE), "htlc claim paying to 0x50 below MH -> R11: " + codestr(r39));
        Transaction c2 = c; c2.version = 2; expect("v2_htlc_claim_rejected_R25", c2, TxValCode::R25_V2_TX_TYPE, &v);
        Transaction c3 = c; c3.version = 2; c3.tx_type = TX_TYPE_HTLC_REFUND; expect("v2_htlc_refund_rejected_R25", c3, TxValCode::R25_V2_TX_TYPE, &v);
    }
    {   // multisig funding an HTLC lock: OK
        Transaction t = base.tx; t.outputs[0].type = OUT_HTLC_LOCK; t.outputs[0].pubkey_hash = base.msh; t.outputs[0].payload = lock_payload;
        sign_all(t, base.spent, {5, 1, 2});
        auto r = validate(t, base.view);
        CHECK(r.ok, "multisig_funding_htlc_lock_ok: " + codestr(r));
    }
    {   // asset tx v2 -> R25 (before R2)
        Transaction t = good; t.tx_type = TX_TYPE_ASSET_TRANSFER; expect("v2_asset_tx_rejected_R25", t, TxValCode::R25_V2_TX_TYPE);
    }
    {   // coinbase with version 2 -> CB path R1
        Transaction cb; cb.version = 2; cb.tx_type = TX_TYPE_COINBASE; TxInput in; in.prev_index = 0xFFFFFFFFu; cb.inputs = {in};
        TxOutput o; o.amount = 1; o.type = OUT_COINBASE_MINER; cb.outputs = {o};
        auto r = ValidateCoinbaseConsensus(cb, MH, 1, 0, PubKeyHash{}, PubKeyHash{});
        CHECK(code_is(r, TxValCode::R1_BAD_VERSION), "v2_coinbase_rejected_CB");
    }
    // ---- R29 / D10 payload envelope on 0x50 ----
    auto out_case = [&](const char* name, std::vector<Byte> payload, int64_t amount, bool want_ok, TxValCode c = TxValCode::OK) {
        Transaction t = base.tx;
        TxOutput o; o.amount = amount; o.type = OUT_MULTISIG; o.pubkey_hash = base.msh; o.payload = payload;
        t.outputs = {o}; if (amount < 4'000'000'000LL) { TxOutput ch; ch.amount = 4'000'000'000LL; ch.pubkey_hash.fill(0x22); t.outputs.push_back(ch); }
        sign_all(t, base.spent, {5, 1, 2});
        auto r = validate(t, base.view);
        if (want_ok) CHECK(r.ok, std::string(name) + ": " + codestr(r));
        else CHECK(code_is(r, c), std::string(name) + ": " + codestr(r));
        return t;
    };
    out_case("ms_output_payload_empty_ok", {}, 4'000'000'000LL, true);
    std::vector<Byte> note; BuildOpenNotePayload("vault deposit", note);
    Transaction tnote = out_case("ms_output_open_note_ok", note, 4'000'000'000LL, true);
    { auto p = note; p[0] = 0x54; out_case("ms_output_bad_magic_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = note; p[2] = 0x02; out_case("ms_output_version2_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = note; p[9] += 1;   out_case("ms_output_body_len_mismatch_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = note; p[10] = 1;   out_case("ms_output_reserved_nonzero_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = note; p[4] |= 0x40; out_case("ms_output_flag_bit6_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = note; p[4] |= 0x80; out_case("ms_output_flag_bit7_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { std::vector<Byte> p(11, 0); p[0] = 0x53; p[1] = 0x43; p[2] = 1; out_case("ms_output_len_11_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = envelope(0x01, std::string(244, 'a')); out_case("ms_output_payload_256_rejected_R29", p, 4'000'000'000LL, false, TxValCode::R29_MULTISIG_OUTPUT); }
    { auto p = envelope(0x01, std::string(243, 'a')); CHECK(p.size() == 255 && MultisigOutputPayloadOk(p), "255-byte envelope is the maximum (accepted)"); }
    {   // unknown capsule type: consensus OK, policy reject
        Transaction t = out_case("ms_output_unknown_capsule_type_consensus_ok", envelope(0x7E, "x"), 4'000'000'000LL, true);
        auto pr = ValidateTransactionPolicy(t, base.view, ctx_at(MH));
        CHECK(code_is(pr, TxValCode::P_BAD_CAPSULE), "ms_output_unknown_capsule_type_policy_reject: " + codestr(pr));
        auto pn = ValidateTransactionPolicy(tnote, base.view, ctx_at(MH));
        CHECK(pn.ok, "open note on 0x50 passes relay policy: " + codestr(pn));
    }
    out_case("ms_output_amount_9999_R29", {}, 9'999, false, TxValCode::R29_MULTISIG_OUTPUT);
    out_case("ms_output_amount_10000_ok", {}, 10'000, true);
    {   // reserved custody codes 0x51-0x5F never active
        int act = 0;
        for (int c = 0x51; c <= 0x5F; ++c) { Transaction t = good; t.outputs[0].type = (uint8_t)c;
            auto r = validate(t, base.view); if (!code_is(r, TxValCode::R11_INACTIVE_TYPE)) ++act; }
        CHECK(act == 0, "0x51-0x5F rejected by R11 at MULTISIG_HEIGHT (15/15)");
    }
    // ---- D11: R9 / S8 count exact v2 size ----
    {
        auto ks = keys_n(15);
        Transaction t; t.version = 2; t.tx_type = TX_TYPE_STANDARD;
        MapView v; std::vector<SpentOutput> sp;
        PubKeyHash msh = ComputeMultisigPolicyHash(15, ks);
        for (int i = 0; i < 67; ++i) {
            TxInput in; in.prev_txid = seq_hash((uint8_t)(0x80 + i)); in.prev_index = 0; in.auth_kind = AUTH_MULTISIG; in.ms_m = 15; in.ms_pubkeys = ks;
            in.ms_sigs.resize(15); for (int k = 0; k < 15; ++k) { in.ms_sigs[k].key_index = (uint8_t)k; in.ms_sigs[k].sig.fill(1); }
            t.inputs.push_back(in); v.put(in.prev_txid, 0, 1'000'000'000LL, OUT_MULTISIG, msh);
        }
        TxOutput o; o.amount = 1; o.pubkey_hash.fill(0x22); t.outputs = {o};
        CHECK(EstimateTxSerializedSize(t) == 4 + 1 + 1 + 67 * 1510 + 1 + 31 && EstimateTxSerializedSize(t) > 100000 && 67 * 133 < 100000,
              "67 x 15-of-15 inputs = 101,208 B exact (133-B estimate would be 8,911)");
        CHECK(code_is(validate(t, v), TxValCode::R9_OVERSIZE_TX), "r9_counts_v2_exact_size");
        // S8: a 1-in 3-of-5 spend is 438 bytes exact; the 133-byte estimate would say 171.
        Simple s = simple_ms(3, ks5, 5'000'000'000LL, 5'000'000'000LL - 500);
        sign_all(s.tx, s.spent, {5, 1, 2});
        size_t exact = EstimateTxSerializedSize(s.tx);
        std::vector<Byte> sraw; s.tx.Serialize(sraw);
        CHECK(exact == 438 && sraw.size() == 438, "1-in 3-of-5 spend: exact size 438 == serialized length");
        Simple s2 = simple_ms(3, ks5, 5'000'000'000LL, 5'000'000'000LL - 437);
        sign_all(s2.tx, s2.spent, {5, 1, 2});
        CHECK(code_is(validate(s2.tx, s2.view), TxValCode::S8_FEE_TOO_LOW), "s8_fee_uses_exact_size (fee 437 < 438 bytes)");
        Simple s3 = simple_ms(3, ks5, 5'000'000'000LL, 5'000'000'000LL - 438);
        sign_all(s3.tx, s3.spent, {5, 1, 2});
        CHECK(validate(s3.tx, s3.view).ok, "fee == exact size accepted");
    }
    // ---- v2 single-sig matrix ----
    {
        Fixture f = v2tx1_fixture(); Transaction t = f.tx; sign_all(t, f.spent, {5, 1, 2});
        CHECK(validate(t, f.view).ok, "mixed multisig + single-sig v2 tx valid");
        Transaction a = t; a.inputs[1].signature.fill(0); expect("v2 single all-zero sig -> S4", a, TxValCode::S4_ZERO_SIGNATURE, &f.view);
        Transaction b = t; b.inputs[1].signature = high_s(b.inputs[1].signature); expect("v2 single high-S -> S5", b, TxValCode::S5_HIGH_S, &f.view);
        Transaction c = t; c.inputs[1].pubkey = pub(2); expect("v2 single wrong pubkey -> S2", c, TxValCode::S2_PKH_MISMATCH, &f.view);
        Transaction d = t; d.inputs[1].signature[3] ^= 1; expect("v2 single bad sig -> S6", d, TxValCode::S6_VERIFY_FAIL, &f.view);
        Transaction e = t; e.inputs[0].ms_sigs[0].sig[3] ^= 1; expect("vector tx with tampered in0 -> S18", e, TxValCode::S18_MS_SIG_INVALID, &f.view);
        MapView missing = f.view; missing.m.erase(OutPoint{seq_hash(0x20), 7});
        expect("missing UTXO of the other input -> S1", t, TxValCode::S1_UTXO_NOT_FOUND, &missing);
    }
    // ---- coinbase can never create 0x50 ----
    {
        Transaction cb; cb.version = 1; cb.tx_type = TX_TYPE_COINBASE; TxInput in; in.prev_index = 0xFFFFFFFFu;
        for (int i = 0; i < 8; ++i) in.signature[i] = (Byte)((uint64_t)MH >> (8 * i)); cb.inputs = {in};
        TxOutput o; o.amount = 100; o.type = OUT_MULTISIG; cb.outputs = {o};
        auto r = ValidateCoinbaseConsensus(cb, MH, 100, 0, PubKeyHash{}, PubKeyHash{});
        CHECK(!r.ok, "coinbase creating OUT_MULTISIG rejected");
    }
}

// ===========================================================================
// group: sigchecks — counting table + block cap (D4)
// ===========================================================================
static Transaction ms_garbage_tx(size_t n_inputs, uint8_t k_per_input, uint8_t seed) {
    Transaction t; t.version = 2; t.tx_type = TX_TYPE_STANDARD;
    for (size_t i = 0; i < n_inputs; ++i) {
        TxInput in; in.prev_txid = seq_hash(seed); in.prev_txid[31] = (Byte)i; in.prev_txid[30] = (Byte)(i >> 8);
        in.prev_index = (uint32_t)i; in.auth_kind = AUTH_MULTISIG; in.ms_m = 1; in.ms_pubkeys = {pub(1)};
        in.ms_sigs.resize(k_per_input);
        for (size_t k = 0; k < k_per_input; ++k) { in.ms_sigs[k].key_index = (uint8_t)k; in.ms_sigs[k].sig.fill(0x33); }
        t.inputs.push_back(in);
    }
    TxOutput o; o.amount = 1; o.pubkey_hash.fill(0x22); t.outputs = {o};
    return t;
}
static Transaction coinbase_at(int64_t h) {
    Transaction cb; cb.version = 1; cb.tx_type = TX_TYPE_COINBASE; TxInput in; in.prev_index = 0xFFFFFFFFu;
    for (int i = 0; i < 8; ++i) in.signature[i] = (Byte)((uint64_t)h >> (8 * i));
    cb.inputs = {in}; TxOutput o; o.amount = 1; o.type = OUT_COINBASE_MINER; cb.outputs = {o};
    return cb;
}
static void g_sigchecks() {
    std::printf("-- sigchecks\n");
    CHECK(TxSigchecks(coinbase_at(1)) == 0, "count_coinbase_0");
    { Transaction j; j.tx_type = TX_TYPE_JACKPOT; j.inputs.resize(9); CHECK(TxSigchecks(j) == 0, "count_jackpot_0"); }
    { Transaction t; t.version = 1; t.inputs.resize(7); CHECK(TxSigchecks(t) == 7, "count_v1_inputs"); }
    { Transaction t; t.version = 1; t.tx_type = TX_TYPE_HTLC_CLAIM; t.inputs.resize(1); CHECK(TxSigchecks(t) == 1, "count_htlc_claim_1"); }
    { Transaction t; t.version = 1; t.tx_type = TX_TYPE_ASSET_TRANSFER; t.inputs.resize(3); CHECK(TxSigchecks(t) == 3, "count_asset_inputs"); }
    { Transaction t; t.version = 2; t.inputs.resize(1); CHECK(TxSigchecks(t) == 1, "count_v2_single_1"); }
    { Transaction t = ms_garbage_tx(1, 3, 1); CHECK(TxSigchecks(t) == 3, "count_v2_3of5_3 (K)"); }
    { Fixture f = v2tx1_fixture(); sign_all(f.tx, f.spent, {5, 1, 2}); CHECK(TxSigchecks(f.tx) == 4, "V2-TX-1 = 3 + 1 sigchecks"); }
    { node_participation::NodeBindTx b{}; CHECK(TxSigchecks(node_participation::build_node_bind_tx(b)) == 2, "count_node_bind_2"); }
    { node_participation::NodeHeartbeatTx h{}; CHECK(TxSigchecks(node_participation::build_node_heartbeat_tx(h)) == 1, "count_heartbeat_1"); }
    { Transaction t; t.version = 1; t.tx_type = 0x99; t.inputs.resize(4); CHECK(TxSigchecks(t) == 4, "unknown tx type = inputs"); }

    // block of exactly 12,000 and 12,001 sigchecks (< 1,000,000 bytes: K = 15 sigs on N = 1 keys parse)
    std::vector<Transaction> blk = {coinbase_at(MH)};
    for (int t = 0; t < 8; ++t) blk.push_back(ms_garbage_tx(100, 15, (uint8_t)(t + 1)));   // 8 x 1,500 = 12,000
    int64_t sc = 0; uint64_t by = 0; for (const auto& t : blk) { sc += TxSigchecks(t); by += TxSerializedSizeExact(t); }
    CHECK(sc == 12000 && by < 1000000, "constructed block: 12,000 sigchecks in " + std::to_string(by) + " bytes");
    std::string why;
    CHECK(CheckBlockLimitsV17(blk, MH, &why), "block_exactly_12000_valid (limit check passes)");
    auto blk2 = blk; blk2.push_back(ms_garbage_tx(1, 1, 99));
    CHECK(!CheckBlockLimitsV17(blk2, MH, &why) && why == "BLOCK_TOO_MANY_SIGCHECKS", "block_12001_invalid: " + why);
    CHECK(CheckBlockLimitsV17(blk2, MH - 1, &why), "cap_not_applied_below_MH (12,001 at MH-1)");
    {   // decided before any signature verification: library block validator reports the cap,
        // not the (garbage) signatures, even though the first tx is invalid
        Block b; b.header.height = MH; b.txs = blk2;
        UtxoSet u; TxValidationContext c = ctx_at(MH);
        auto r = ValidateBlockTransactionsConsensus(b, u, c, PubKeyHash{}, PubKeyHash{});
        CHECK(!r.ok && r.message == "BLOCK_TOO_MANY_SIGCHECKS", "block_12001_invalid_before_verification: " + r.message);
        Block b0 = b; b0.txs = blk;
        auto r0 = ValidateBlockTransactionsConsensus(b0, u, c, PubKeyHash{}, PubKeyHash{});
        CHECK(!r0.ok && r0.message.find("consensus") != std::string::npos, "12,000-sigcheck block proceeds to tx validation (fails there on garbage)");
    }
    // policy 1,500 per tx
    {
        Transaction t1500 = ms_garbage_tx(100, 15, 7), t1501 = ms_garbage_tx(100, 15, 8);
        t1501.inputs.push_back(ms_garbage_tx(1, 1, 9).inputs[0]);
        MapView v; auto r = ValidateTransactionPolicy(t1501, v, ctx_at(MH));
        CHECK(code_is(r, TxValCode::P_TOO_MANY_SIGCHECKS), "policy_tx_1501_rejected");
        auto r2 = ValidateTransactionPolicy(t1500, v, ctx_at(MH));
        CHECK(!code_is(r2, TxValCode::P_TOO_MANY_SIGCHECKS), "policy tx with 1,500 sigchecks passes the sigcheck rule");
    }
}

// ===========================================================================
// group: activation — boundaries 39998..40001, block limits, node-tx fence
// ===========================================================================
static std::vector<Transaction> filler_block(int64_t h, uint64_t target_bytes) {
    // v1 txs (1 input, payload outputs <= 512 B) so the serialized tx bytes total exactly target_bytes
    std::vector<Transaction> b = {coinbase_at(h)};
    uint64_t total = TxSerializedSizeExact(b[0]);
    int n = 0;
    while (total < target_bytes) {
        const uint64_t remaining = target_bytes - total;            // always >= 171 here
        uint64_t room = std::min<uint64_t>(90000, remaining - 140);
        const uint64_t left = remaining - 140 - room;
        if (left > 0 && left < 171) room -= (171 - left);           // keep a feasible remainder
        Transaction t; t.version = 1; t.tx_type = TX_TYPE_STANDARD;
        TxInput in; in.prev_txid = seq_hash((uint8_t)n); in.prev_txid[0] = (Byte)(n >> 8); in.prev_txid[1] = 0xF1; t.inputs = {in};
        const uint64_t k = (room + 542) / 543;                     // outputs needed (31 + <=512 each)
        uint64_t payload = room - 31 * k;
        for (uint64_t j = 0; j < k; ++j) {
            TxOutput o; o.amount = 1; o.pubkey_hash.fill(0x22);
            uint64_t pl = payload / (k - j);
            o.payload.assign((size_t)pl, 0x5A); payload -= pl;
            t.outputs.push_back(o);
        }
        total += TxSerializedSizeExact(t); b.push_back(t); ++n;
    }
    return b;
}
static void g_activation() {
    std::printf("-- activation\n");
#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
    std::printf("  non-mainnet build: skipped (mainnet heights)\n");
    return;
#else
    CHECK(V17_HEIGHT == 40000 && MULTISIG_HEIGHT == 40000, "mainnet V17_HEIGHT == MULTISIG_HEIGHT == 40000");
    Simple s = simple_ms(3, keys35());
    sign_all(s.tx, s.spent, {5, 1, 2});
    for (int64_t h : {(int64_t)39998, (int64_t)39999}) {
        auto r = validate(s.tx, s.view, h);
        CHECK(code_is(r, TxValCode::R1_BAD_VERSION), "v2 tx rejected (R1) at " + std::to_string(h));
        Transaction v1; v1.version = 1; v1.tx_type = TX_TYPE_STANDARD; TxInput in; in.prev_txid = seq_hash(0x61); v1.inputs = {in};
        TxOutput o; o.amount = 1'000'000; o.type = OUT_MULTISIG; o.pubkey_hash = s.msh; v1.outputs = {o};
        MapView mv; mv.put(in.prev_txid, 0, 2'000'000, OUT_TRANSFER, ComputePubKeyHash(pub(1)));
        SpentOutput sp; sp.amount = 2'000'000; sp.type = OUT_TRANSFER; SignTransactionInput(v1, 0, sp, GENESIS, priv(1), nullptr);
        auto r1 = validate(v1, mv, h);
        CHECK(code_is(r1, TxValCode::R11_INACTIVE_TYPE), "v1 tx creating 0x50 rejected (R11) at " + std::to_string(h));
        { Transaction p = v1; p.outputs[0].payload = envelope(1, "x"); CHECK(code_is(validate(p, mv, h), TxValCode::R11_INACTIVE_TYPE), "ms_output_payload_before_MH_R11 at " + std::to_string(h)); }
        CHECK(!multisig_active_at(h) && !v17_block_limits_active_at(h) && !node_tx_version_fence_at(h), "gates closed at " + std::to_string(h));
    }
    for (int64_t h : {(int64_t)40000, (int64_t)40001}) {
        auto r = validate(s.tx, s.view, h);
        CHECK(r.ok, "v2 multisig spend valid at " + std::to_string(h) + ": " + codestr(r));
        Transaction v1; v1.version = 1; v1.tx_type = TX_TYPE_STANDARD; TxInput in; in.prev_txid = seq_hash(0x61); v1.inputs = {in};
        TxOutput o; o.amount = 1'000'000; o.type = OUT_MULTISIG; o.pubkey_hash = s.msh; v1.outputs = {o};
        MapView mv; mv.put(in.prev_txid, 0, 2'000'000, OUT_TRANSFER, ComputePubKeyHash(pub(1)));
        SpentOutput sp; sp.amount = 2'000'000; sp.type = OUT_TRANSFER; SignTransactionInput(v1, 0, sp, GENESIS, priv(1), nullptr);
        CHECK(validate(v1, mv, h).ok, "v1 STANDARD funding a 0x50 output valid at " + std::to_string(h));
        CHECK(multisig_active_at(h) && v17_block_limits_active_at(h) && node_tx_version_fence_at(h), "gates open at " + std::to_string(h));
        Transaction v3 = s.tx; v3.version = 3; CHECK(code_is(validate(v3, s.view, h), TxValCode::R1_BAD_VERSION), "version 3 still R1 at " + std::to_string(h));
    }
    // ---- D9 block limits at 39,999 (accepted as before) vs 40,000 (rejected) ----
    std::string why;
    auto b1m = filler_block(MH, 1000000), b1m1 = filler_block(MH, 1000001);
    uint64_t s1 = 0, s2 = 0; for (auto& t : b1m) s1 += TxSerializedSizeExact(t); for (auto& t : b1m1) s2 += TxSerializedSizeExact(t);
    CHECK(s1 == 1000000 && s2 == 1000001, "filler blocks are exactly 1,000,000 / 1,000,001 tx bytes");
    CHECK(CheckBlockLimitsV17(b1m, 40000, &why), "block_tx_bytes_1000000_valid_at_MH");
    CHECK(!CheckBlockLimitsV17(b1m1, 40000, &why) && why == "BLOCK_TX_BYTES_EXCEEDED", "block_tx_bytes_1000001_invalid_at_MH");
    CHECK(!CheckBlockLimitsV17(b1m1, 40001, &why) && why == "BLOCK_TX_BYTES_EXCEEDED", "1,000,001 bytes invalid at 40001");
    CHECK(CheckBlockLimitsV17(b1m1, 39999, &why) && CheckBlockLimitsV17(b1m1, 39998, &why), "oversize_block_unchanged_below_MH (39998/39999)");
    auto big = filler_block(MH, 2'500'000);
    CHECK(CheckBlockLimitsV17(big, 39999, &why) && !CheckBlockLimitsV17(big, 40000, &why), "2.5 MB block: accepted-as-before at 39,999, rejected at 40,000");
    {
        std::vector<Transaction> many(65537, coinbase_at(MH));
        for (size_t i = 1; i < many.size(); ++i) { many[i].tx_type = TX_TYPE_STANDARD; many[i].inputs[0].prev_index = (uint32_t)i; }
        CHECK(!CheckBlockLimitsV17(many, 40000, &why) && why == "BLOCK_TOO_MANY_TXS", "block_65537_txs_invalid_at_MH");
        CHECK(CheckBlockLimitsV17(many, 39999, &why), "65,537 txs unchanged below MH");
        many.pop_back();
        CHECK(CheckBlockLimitsV17(many, 40000, &why) || why != "BLOCK_TOO_MANY_TXS", "65,536 txs pass the count rule at MH");
        Block bb; bb.header.height = 40000; bb.txs = b1m1; UtxoSet u;
        auto r = ValidateBlockTransactionsConsensus(bb, u, ctx_at(40000), PubKeyHash{}, PubKeyHash{});
        CHECK(!r.ok && r.message == "BLOCK_TX_BYTES_EXCEEDED", "library block validator enforces bytes at MH: " + r.message);
    }
    // ---- D2 / R30 node-tx outer version fence ----
    namespace np = node_participation;
    np::NodeBindTx bind{}; bind.version = 2;
    Transaction bt = np::build_node_bind_tx(bind);
    np::NodeBindTx out; const char* why_c = nullptr;
    Transaction bt2 = bt; bt2.version = 2;
    CHECK(np::extract_bind_at(bt2, 39999, out, &why_c), "node_bind_outer_v2_accepted_below_MH (shape)");
    CHECK(!np::extract_bind_at(bt2, 40000, out, &why_c) && std::string(why_c) == "node_tx_bad_version", "node_bind_outer_v2_rejected_at_MH_R30");
    CHECK(np::extract_bind_at(bt, 40000, out, &why_c), "node bind outer v1 accepted at MH");
    np::NodeHeartbeatTx hb{};
    Transaction ht = np::build_node_heartbeat_tx(hb); ht.version = 0;
    np::NodeHeartbeatTx hout;
    CHECK(np::extract_heartbeat_at(ht, 39999, hout, &why_c), "heartbeat outer v0 accepted below MH");
    CHECK(!np::extract_heartbeat_at(ht, 40000, hout, &why_c) && std::string(why_c) == "node_tx_bad_version", "node_heartbeat_outer_v0_rejected_at_MH_R30");
    {   // mempool / template predicate (judge_node_tx) shares the rule
        np::NodeTxPolicyContext c; c.height = 40000; c.active = true;
        np::NodeState live;
        auto v = np::judge_node_tx(c, live, bt2);
        CHECK(!v.ok && v.reason.find("node_tx_bad_version") != std::string::npos, "mempool_node_tx_outer_v2_rejected_at_MH: " + v.reason);
        std::string w;
        CHECK(!np::node_txs_valid_for_block(live, {&bt2}, 40000, HIST_JACKPOT_V2_HEIGHT, NODE_EPOCH_LENGTH,
                                            [](int64_t, Bytes32&) { return false; }, &w) && w.find("node_tx_bad_version") != std::string::npos,
              "block rule (node_txs_valid_for_block) rejects outer v2 at MH: " + w);
    }
#endif
}

// ===========================================================================
// group: reorg — connect/disconnect a multisig spend; UTXO policy never mutates
// ===========================================================================
static void g_reorg() {
    std::printf("-- reorg\n");
    auto ks = keys35();
    PubKeyHash msh = ComputeMultisigPolicyHash(3, ks);
    UtxoSet u;
    // block A at MH: v1 funding tx creates a 0x50 output
    Transaction cbA = coinbase_at(MH);
    Hash256 fund_prev = seq_hash(0x70);
    UTXOEntry fe; fe.amount = 6'000'000'000LL; fe.type = OUT_TRANSFER; fe.pubkey_hash = ComputePubKeyHash(pub(1)); fe.height = 1;
    u.AddUTXO(OutPoint{fund_prev, 0}, fe);
    Transaction fund; fund.version = 1; fund.tx_type = TX_TYPE_STANDARD; TxInput fin; fin.prev_txid = fund_prev; fund.inputs = {fin};
    TxOutput mo; mo.amount = 5'000'000'000LL; mo.type = OUT_MULTISIG; mo.pubkey_hash = msh; fund.outputs = {mo};
    SpentOutput fsp; fsp.amount = fe.amount; fsp.type = OUT_TRANSFER; SignTransactionInput(fund, 0, fsp, GENESIS, priv(1), nullptr);
    CHECK(ValidateTransactionConsensus(fund, u, ctx_at(MH)).ok, "funding v1 -> 0x50 valid at MH");
    BlockUndo undoA; std::string e;
    CHECK(u.ConnectBlock({cbA, fund}, MH, undoA, &e), "connect funding block: " + e);
    Hash256 fid{}; fund.ComputeTxId(fid);
    auto ms_utxo = u.GetUTXO(OutPoint{fid, 0});
    CHECK(ms_utxo && ms_utxo->type == OUT_MULTISIG && ms_utxo->pubkey_hash == msh, "0x50 UTXO stored with MSH lock");
    // block B at MH+1: rotation 3-of-5 -> new 2-of-3 policy (spend old policy, never mutate)
    auto k23 = keys23(); PubKeyHash msh23 = ComputeMultisigPolicyHash(2, k23);
    Transaction rot; rot.version = 2; rot.tx_type = TX_TYPE_STANDARD;
    TxInput ri; ri.prev_txid = fid; ri.prev_index = 0; ri.auth_kind = AUTH_MULTISIG; ri.ms_m = 3; ri.ms_pubkeys = ks; rot.inputs = {ri};
    TxOutput ro; ro.amount = 4'999'990'000LL; ro.type = OUT_MULTISIG; ro.pubkey_hash = msh23; rot.outputs = {ro};
    std::vector<SpentOutput> rsp = {SpentOutput{ms_utxo->amount, OUT_MULTISIG, msh, {}}};
    sign_all(rot, rsp, {1, 3, 4});
    auto rv = ValidateTransactionConsensus(rot, u, ctx_at(MH + 1));
    CHECK(rv.ok, "rotation spend (old policy signs, new policy output) valid: " + codestr(rv));
    BlockUndo undoB;
    CHECK(u.ConnectBlock({coinbase_at(MH + 1), rot}, MH + 1, undoB, &e), "connect rotation block: " + e);
    Hash256 rid{}; rot.ComputeTxId(rid);
    CHECK(!u.GetUTXO(OutPoint{fid, 0}) && u.GetUTXO(OutPoint{rid, 0}) && u.GetUTXO(OutPoint{rid, 0})->pubkey_hash == msh23,
          "old-policy UTXO spent, new-policy UTXO created");
    // disconnect B: old UTXO restored byte-identical, new removed
    CHECK(u.DisconnectBlock({coinbase_at(MH + 1), rot}, undoB, &e), "disconnect rotation block: " + e);
    auto back = u.GetUTXO(OutPoint{fid, 0});
    CHECK(back && back->type == OUT_MULTISIG && back->pubkey_hash == msh && back->amount == ms_utxo->amount && !u.GetUTXO(OutPoint{rid, 0}),
          "reorg undo restores the 0x50 UTXO exactly");
    CHECK(ValidateTransactionConsensus(rot, u, ctx_at(MH + 1)).ok, "same multisig spend valid again after disconnect (reconnect)");
    BlockUndo undoB2;
    CHECK(u.ConnectBlock({coinbase_at(MH + 1), rot}, MH + 1, undoB2, &e), "reconnect rotation block");
    // the new policy can spend; the old one cannot spend the new output (no policy mutation)
    Transaction sp2; sp2.version = 2; sp2.tx_type = TX_TYPE_STANDARD;
    TxInput si; si.prev_txid = rid; si.prev_index = 0; si.auth_kind = AUTH_MULTISIG; si.ms_m = 3; si.ms_pubkeys = ks; sp2.inputs = {si};
    TxOutput so; so.amount = 4'999'980'000LL; so.pubkey_hash.fill(0x22); sp2.outputs = {so};
    std::vector<SpentOutput> s2 = {SpentOutput{ro.amount, OUT_MULTISIG, msh23, {}}};
    Transaction old_try = sp2; sign_all(old_try, s2, {1, 3, 4});
    CHECK(code_is(ValidateTransactionConsensus(old_try, u, ctx_at(MH + 2)), TxValCode::S17_MSH_MISMATCH), "old policy cannot spend the rotated UTXO (S17)");
    Transaction new_try = sp2; new_try.inputs[0].ms_m = 2; new_try.inputs[0].ms_pubkeys = k23; sign_all(new_try, s2, {2, 3});
    CHECK(ValidateTransactionConsensus(new_try, u, ctx_at(MH + 2)).ok, "new 2-of-3 policy spends the rotated UTXO");
    // disconnect everything back to before MH
    CHECK(u.DisconnectBlock({coinbase_at(MH + 1), rot}, undoB2, &e) && u.DisconnectBlock({cbA, fund}, undoA, &e) &&
          u.GetUTXO(OutPoint{fund_prev, 0}) && !u.GetUTXO(OutPoint{fid, 0}), "full disconnect back across activation restores pre-MH state");
}

// ===========================================================================
// group: mempool — activation boundary + reorg eviction + template cap
// ===========================================================================
static void g_mempool() {
    std::printf("-- mempool\n");
    auto ks = keys35();
    PubKeyHash msh = ComputeMultisigPolicyHash(3, ks);
    UtxoSet u; UTXOEntry e; e.amount = 5'000'000'000LL; e.type = OUT_MULTISIG; e.pubkey_hash = msh; e.height = 1;
    u.AddUTXO(OutPoint{seq_hash(0x40), 1}, e);
    Simple s = simple_ms(3, ks, 5'000'000'000LL, 4'999'000'000LL);
    sign_all(s.tx, s.spent, {5, 1, 2});
    Mempool mp;
    auto before = mp.AcceptToMempool(s.tx, u, ctx_at(MH - 1));
    CHECK(!before.accepted && before.code == MempoolAcceptCode::CONSENSUS_FAIL && before.reason.find("R1") != std::string::npos,
          "v2 tx submitted for next height MH-1 rejected: " + before.reason);
    auto after = mp.AcceptToMempool(s.tx, u, ctx_at(MH));
    CHECK(after.accepted, "the same v2 tx accepted for next height MH: " + after.reason);
    // funding v1 creating 0x50 in the pool too
    UTXOEntry f; f.amount = 3'000'000'000LL; f.type = OUT_TRANSFER; f.pubkey_hash = ComputePubKeyHash(pub(1)); f.height = 1;
    u.AddUTXO(OutPoint{seq_hash(0x71), 0}, f);
    Transaction fund; fund.version = 1; TxInput in; in.prev_txid = seq_hash(0x71); fund.inputs = {in};
    TxOutput o; o.amount = 2'999'000'000LL; o.type = OUT_MULTISIG; o.pubkey_hash = msh; fund.outputs = {o};
    SpentOutput sp; sp.amount = f.amount; sp.type = OUT_TRANSFER; SignTransactionInput(fund, 0, sp, GENESIS, priv(1), nullptr);
    CHECK(!mp.AcceptToMempool(fund, u, ctx_at(MH - 1)).accepted, "v1 tx creating 0x50 rejected before MH");
    CHECK(mp.AcceptToMempool(fund, u, ctx_at(MH)).accepted, "v1 tx creating 0x50 accepted at MH");
    // an ordinary v1 tx that must survive the eviction
    UTXOEntry g = f; u.AddUTXO(OutPoint{seq_hash(0x72), 0}, g);
    Transaction plain; plain.version = 1; TxInput pin; pin.prev_txid = seq_hash(0x72); plain.inputs = {pin};
    TxOutput po; po.amount = 2'999'000'000LL; po.pubkey_hash.fill(0x33); plain.outputs = {po};
    SignTransactionInput(plain, 0, sp, GENESIS, priv(1), nullptr);
    CHECK(mp.AcceptToMempool(plain, u, ctx_at(MH)).accepted, "plain v1 tx accepted");
    CHECK(mp.Size() == 3, "pool holds 3 txs");
    CHECK(mp.RemoveMultisigBeforeActivation(MH) == 0 && mp.Size() == 3, "no eviction while next height >= MH");
    size_t ev = mp.RemoveMultisigBeforeActivation(MH - 1);
    CHECK(ev == 2 && mp.Size() == 1 && mp.HasTransaction([&] { Hash256 h{}; plain.ComputeTxId(h); return h; }()),
          "reorg below MH evicts the v2 tx and the 0x50-creating tx, keeps the plain tx (evicted " + std::to_string(ev) + ")");
    // template sigcheck budget: 82 relay-standard txs of 10 x 15-of-15 inputs (150 sigchecks
    // each, 12,300 total) are all admitted; a template built without a byte limit must stop
    // at 80 txs = 12,000 sigchecks.
    {
        auto k15 = keys_n(15);
        PubKeyHash m15 = ComputeMultisigPolicyHash(15, k15);
        std::vector<uint64_t> p15 = privs_for(k15, 15);
        Mempool m2; UtxoSet u2; int admitted = 0;
        for (int t = 0; t < 82; ++t) {
            Transaction tx; tx.version = 2; tx.tx_type = TX_TYPE_STANDARD;
            std::vector<SpentOutput> sp;
            for (int i = 0; i < 10; ++i) {
                TxInput in; in.prev_txid = seq_hash((uint8_t)i); in.prev_txid[0] = (Byte)t; in.prev_txid[1] = 0xE7;
                in.auth_kind = AUTH_MULTISIG; in.ms_m = 15; in.ms_pubkeys = k15; tx.inputs.push_back(in);
                UTXOEntry ue; ue.amount = 100'000'000; ue.type = OUT_MULTISIG; ue.pubkey_hash = m15; ue.height = 1;
                u2.AddUTXO(OutPoint{in.prev_txid, 0}, ue);
                sp.push_back(SpentOutput{ue.amount, OUT_MULTISIG, m15, {}});
            }
            TxOutput o; o.amount = 10 * 100'000'000LL - 1'000'000; o.pubkey_hash.fill(0x22); tx.outputs = {o};
            sign_all(tx, sp, p15);
            auto r = m2.AcceptToMempool(tx, u2, ctx_at(MH));
            if (r.accepted) ++admitted; else std::printf("  note: %s\n", r.reason.c_str());
        }
        CHECK(admitted == 82, "82 x 150-sigcheck txs admitted (" + std::to_string(admitted) + ")");
        auto t1 = m2.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 100'000'000, MH);
        int64_t sc = 0; for (const auto& x : t1.txs) sc += TxSigchecks(x);
        CHECK(t1.txs.size() == 80 && sc == 12000, "template_respects_cap: " + std::to_string(t1.txs.size()) + " txs / " + std::to_string(sc) + " sigchecks");
        auto t2 = m2.BuildBlockTemplateCPFP(MAX_BLOCK_TX_COUNT, 100'000'000, MH);
        int64_t sc2 = 0; for (const auto& x : t2.txs) sc2 += TxSigchecks(x);
        CHECK(sc2 <= 12000 && t2.txs.size() == 80, "CPFP template respects the cap: " + std::to_string(sc2));
    }
    // policy: 3-of-5 tx is standard; sigchecks 3
    auto pol = ValidateTransactionPolicy(s.tx, u, ctx_at(MH));
    CHECK(pol.ok, "3-of-5 spend is relay-standard: " + codestr(pol));
}

// ===========================================================================
// group: fuzzlite — deterministic mutation campaign (not the >= 1e7 libFuzzer run)
// ===========================================================================
static void g_fuzzlite() {
    std::printf("-- fuzzlite\n");
    const auto seed_tx = unhex(V("v2tx1_signed_hex"));
    const auto seed_tpl = unhex(V("v2tx1_unsigned_template_hex"));
    uint64_t x = 0x9E3779B97F4A7C15ULL;
    auto rnd = [&]() { x ^= x << 13; x ^= x >> 7; x ^= x << 17; return x; };
    int parsed = 0, roundtrip_bad = 0, policy_calls = 0;
    const int ITER = 300000;
    for (int it = 0; it < ITER; ++it) {
        std::vector<Byte> b = (it & 1) ? seed_tx : seed_tpl;
        int nm = 1 + (int)(rnd() % 4);
        for (int k = 0; k < nm; ++k) {
            switch (rnd() % 4) {
                case 0: b[rnd() % b.size()] ^= (Byte)(1u << (rnd() % 8)); break;
                case 1: b[rnd() % b.size()] = (Byte)rnd(); break;
                case 2: if (b.size() > 8) b.resize(b.size() - 1 - rnd() % 8); break;
                default: b.insert(b.begin() + (long)(rnd() % b.size()), (Byte)rnd()); break;
            }
        }
        Transaction t;
        if (Transaction::Deserialize(b, t, nullptr)) {
            ++parsed;
            std::vector<Byte> again;
            bool big = false; for (const auto& o : t.outputs) if (o.payload.size() > 512) big = true;
            const bool sok = t.Serialize(again);
            if (big ? sok : (!sok || again != b)) ++roundtrip_bad;   // canonical: one encoding per tx (R13-invalid >512 payloads cannot re-serialize)
            for (const auto& in : t.inputs) if (in.auth_kind == AUTH_MULTISIG) { CheckMultisigPolicy(in.ms_m, in.ms_pubkeys); ++policy_calls; }
            (void)TxSigchecks(t); (void)TxSerializedSizeExact(t);
            if (TxSerializedSizeExact(t) != b.size()) ++roundtrip_bad;
        }
    }
    CHECK(roundtrip_bad == 0, "every parseable mutation re-serializes byte-identically and its exact size == length (" +
          std::to_string(parsed) + " parsed of " + std::to_string(ITER) + ")");
    CHECK(parsed > 1000 && policy_calls > 1000, "mutation campaign reached the v2 parser and the policy checker");
    // bech32m decoder on random strings over the alphabet + noise
    int dec_ok = 0;
    const std::string base = V("addr35_sostms");
    for (int it = 0; it < 200000; ++it) {
        std::string a = base;
        int nm = 1 + (int)(rnd() % 3);
        for (int k = 0; k < nm; ++k) a[7 + rnd() % (a.size() - 7)] = "qpzry9x8gf2tvdw0s3jn54khce6mua7lQB1-"[rnd() % 36];
        if (a == base) continue;                               // mutation was a no-op
        PubKeyHash o{}; if (MultisigAddressDecode(a, MsNetwork::MAINNET, o)) ++dec_ok;
    }
    CHECK(dec_ok == 0, "random 1-3 character corruptions of an address are rejected (accepted " + std::to_string(dec_ok) + " of 200000)");
}

int main(int argc, char** argv) {
    if (argc < 3) { std::printf("usage: test-multisig-v17 <source-dir> <group>\n"); return 2; }
    std::string root = argv[1], group = argv[2];
    {
        std::ifstream f(root + "/tests/vectors/native_multisig_40000.json");
        std::stringstream ss; ss << f.rdbuf();
        std::string err;
        if (!json::parse(ss.str(), g_vec, &err) || !g_vec.is_obj()) { std::printf("cannot load vectors: %s\n", err.c_str()); return 2; }
    }
    std::printf("=== multisig-%s ===\n", group.c_str());
    if (group == "vectors") g_vectors();
    else if (group == "serial") g_serial();
    else if (group == "policy") g_policy();
    else if (group == "bech32m") g_bech32m();
    else if (group == "sighash") g_sighash();
    else if (group == "validation") g_validation();
    else if (group == "sigchecks") g_sigchecks();
    else if (group == "activation") g_activation();
    else if (group == "reorg") g_reorg();
    else if (group == "mempool") g_mempool();
    else if (group == "fuzzlite") g_fuzzlite();
    else { std::printf("unknown group\n"); return 2; }
    std::printf("=== %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
