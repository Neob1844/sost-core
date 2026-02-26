// =============================================================================
// test_capsule_codec.cpp — SOST Capsule Protocol v1 tests
// Tests: header codec, body validation, policy, tx_validation integration
// =============================================================================

#include "sost/capsule.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <string>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define TEST(name) \
    static void test_##name(); \
    struct reg_##name { reg_##name() { tests().push_back({#name, test_##name}); } } r_##name; \
    static void test_##name()

static std::vector<std::pair<std::string, void(*)()>>& tests() {
    static std::vector<std::pair<std::string, void(*)()>> t;
    return t;
}

#define EXPECT(cond, msg) do { \
    if (!(cond)) { \
        std::cerr << "  FAIL: " << msg << " [" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

// =============================================================================
// Mock UTXO view (same as Phase 3 tests)
// =============================================================================

class MapUtxoView : public IUtxoView {
public:
    std::map<OutPoint, UTXOEntry> db;
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        auto it = db.find(op);
        if (it == db.end()) return std::nullopt;
        return it->second;
    }
    void Add(const Hash256& txid, uint32_t index, const UTXOEntry& entry) {
        db[{txid, index}] = entry;
    }
};

// =============================================================================
// Test keys
// =============================================================================

static Hash256 g_genesis{};
static PrivKey g_priv{};
static PubKey  g_pub{};
static PubKeyHash g_pkh{};

static void InitKeys() {
    std::string err;
    assert(GenerateKeyPair(g_priv, g_pub, &err));
    g_pkh = ComputePubKeyHash(g_pub);
    std::memset(g_genesis.data(), 0xAA, 32);
}

static Hash256 FakeTxid(uint8_t fill) {
    Hash256 h{}; std::memset(h.data(), fill, 32); return h;
}

// Helper: build a signed tx with optional payload, at a given spend_height
struct TxBundle {
    Transaction tx;
    MapUtxoView utxos;
    TxValidationContext ctx;
};

static TxBundle MakeTxWithPayload(
    const std::vector<Byte>& payload,
    int64_t spend_height,
    int64_t capsule_activation = CAPSULE_ACTIVATION_HEIGHT_DEV)
{
    TxBundle b;
    b.ctx.genesis_hash = g_genesis;
    b.ctx.spend_height = spend_height;
    b.ctx.capsule_activation_height = capsule_activation;

    Hash256 prev = FakeTxid(0x55);
    int64_t utxo_amount = 10000000;  // 0.1 SOST

    UTXOEntry entry;
    entry.amount = utxo_amount;
    entry.type = OUT_TRANSFER;
    entry.pubkey_hash = g_pkh;
    entry.height = 0;
    entry.is_coinbase = false;
    b.utxos.Add(prev, 0, entry);

    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev;
    in.prev_index = 0;
    b.tx.inputs.push_back(in);

    TxOutput out;
    out.amount = utxo_amount - 500;  // generous fee
    out.type = OUT_TRANSFER;
    out.pubkey_hash = g_pkh;
    out.payload = payload;
    b.tx.outputs.push_back(out);

    // Sign
    SpentOutput spent{utxo_amount, OUT_TRANSFER};
    std::string err;
    bool ok = SignTransactionInput(b.tx, 0, spent, g_genesis, g_priv, &err);
    if (!ok) {
        std::cerr << "  FAIL: SignTransactionInput failed in MakeTxWithPayload: " << err << "\n";
        g_fail++;
    }

    return b;
}

// =============================================================================
// PART 1: Capsule Codec Tests (Section 16.1)
// =============================================================================

// C01: valid header encode/decode roundtrip
TEST(C01_header_roundtrip) {
    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.flags = CapsuleFlags::ACK_REQUIRED;
    h.template_id = 0;
    h.locator_type = 0;
    h.hash_alg = 0;
    h.enc_alg = 0;
    h.body_len = 5;
    h.reserved = 0;

    std::vector<Byte> buf;
    EncodeCapsuleHeader(h, buf);
    EXPECT(buf.size() == CAPSULE_HEADER_SIZE, "header should be 12 bytes");

    CapsuleHeader h2{};
    std::string err;
    EXPECT(DecodeCapsuleHeader(buf, h2, &err), "decode should succeed");
    EXPECT(h2.capsule_version == h.capsule_version, "version roundtrip");
    EXPECT(h2.capsule_type == h.capsule_type, "type roundtrip");
    EXPECT(h2.flags == h.flags, "flags roundtrip");
    EXPECT(h2.body_len == h.body_len, "body_len roundtrip");
    EXPECT(h2.reserved == 0, "reserved roundtrip");
    g_pass++;
}

// C02: reject payload > 255
TEST(C02_reject_oversized_payload) {
    std::vector<Byte> big(260, 0x00);
    big[0] = CAPSULE_MAGIC_0; big[1] = CAPSULE_MAGIC_1;
    auto r = ValidateCapsuleHeader(big);
    EXPECT(!r.ok, "should reject >255");
    EXPECT(r.code == CapsuleValCode::PAYLOAD_TOO_LONG, "correct code");
    g_pass++;
}

// C03: reject mismatched body_len
TEST(C03_body_len_mismatch) {
    std::vector<Byte> payload;
    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.body_len = 10;  // claim 10 bytes body
    h.reserved = 0;
    EncodeCapsuleHeader(h, payload);
    // Only append 5 bytes (mismatch)
    payload.insert(payload.end(), 5, 0x41);
    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "should reject body_len mismatch");
    EXPECT(r.code == CapsuleValCode::BAD_BODY_LEN, "correct code");
    g_pass++;
}

// C04: reject invalid magic
TEST(C04_bad_magic) {
    std::vector<Byte> payload(14, 0);
    payload[0] = 'X'; payload[1] = 'Y';  // not "SC"
    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "should reject bad magic");
    EXPECT(r.code == CapsuleValCode::BAD_MAGIC, "correct code");
    g_pass++;
}

// C05: reject unsupported capsule_version
TEST(C05_bad_version) {
    std::vector<Byte> payload;
    CapsuleHeader h{};
    h.capsule_version = 0x02;  // v2 not supported
    h.capsule_type = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.body_len = 0;
    h.reserved = 0;
    EncodeCapsuleHeader(h, payload);
    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "should reject v2");
    EXPECT(r.code == CapsuleValCode::BAD_VERSION, "correct code");
    g_pass++;
}

// C06: reject non-zero reserved
TEST(C06_nonzero_reserved) {
    std::vector<Byte> payload;
    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.body_len = 0;
    h.reserved = 0x1234;  // non-zero
    EncodeCapsuleHeader(h, payload);
    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "should reject non-zero reserved");
    EXPECT(r.code == CapsuleValCode::RESERVED_NONZERO, "correct code");
    g_pass++;
}

// C07: reject reserved flag bits (6,7)
TEST(C07_reserved_flags) {
    std::vector<Byte> payload;
    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.flags = 0x80;  // bit 7 set
    h.body_len = 0;
    h.reserved = 0;
    EncodeCapsuleHeader(h, payload);
    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "should reject reserved flags");
    EXPECT(r.code == CapsuleValCode::RESERVED_FLAGS, "correct code");
    g_pass++;
}

// C08: OPEN_NOTE_INLINE empty and max cases
TEST(C08_open_note_valid) {
    // Valid short note
    std::vector<Byte> payload;
    EXPECT(BuildOpenNotePayload("INV-2026-001", payload), "build should succeed");
    auto r = ValidateCapsulePolicy(payload);
    EXPECT(r.ok, "valid note should pass policy: " + r.message);

    // Max 80 bytes
    std::string max_text(80, 'A');
    std::vector<Byte> payload2;
    EXPECT(BuildOpenNotePayload(max_text, payload2), "build max should succeed");
    auto r2 = ValidateCapsulePolicy(payload2);
    EXPECT(r2.ok, "max note should pass: " + r2.message);

    // Empty note (0 bytes text)
    std::vector<Byte> payload3;
    EXPECT(BuildOpenNotePayload("", payload3), "build empty should succeed");
    auto r3 = ValidateCapsulePolicy(payload3);
    EXPECT(r3.ok, "empty note should pass: " + r3.message);

    g_pass++;
}

// C09: OPEN_NOTE_INLINE > 80 bytes rejected by policy
TEST(C09_open_note_too_long) {
    // Build manually with text_len=81 (bypass BuildOpenNotePayload limit)
    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.body_len = 82;  // 1 + 81
    h.reserved = 0;

    std::vector<Byte> payload;
    EncodeCapsuleHeader(h, payload);
    payload.push_back(81);  // text_len = 81
    payload.insert(payload.end(), 81, 'X');

    auto r = ValidateCapsulePolicy(payload);
    EXPECT(!r.ok, "81-byte note should be rejected");
    EXPECT(r.code == CapsuleValCode::NOTE_TOO_LONG, "correct code");
    g_pass++;
}

// C10: DOC_REF_OPEN with zero file_hash rejected
TEST(C10_doc_ref_zero_hash) {
    DocRefParams p{};
    p.capsule_id = 1;
    p.file_size_bytes = 1024;
    // p.file_hash is all zeros (default)
    p.locator_type = LocatorType::HTTPS_PATH;
    p.locator_ref = {'/', 'd', 'o', 'c', '/', '1'};

    std::vector<Byte> payload;
    EXPECT(BuildDocRefOpenPayload(p, payload), "build should succeed");

    auto r = ValidateCapsulePolicy(payload);
    EXPECT(!r.ok, "zero file_hash should be rejected");
    EXPECT(r.code == CapsuleValCode::DOC_ZERO_HASH, "correct code");
    g_pass++;
}

// C11: DOC_REF_OPEN valid
TEST(C11_doc_ref_open_valid) {
    DocRefParams p{};
    p.capsule_id = 42;
    p.file_size_bytes = 3145728;  // 3 MB
    std::memset(p.file_hash.data(), 0xAB, 32);
    std::memset(p.manifest_hash.data(), 0xCD, 32);
    p.locator_type = LocatorType::IPFS_CID;
    std::string cid = "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG";
    p.locator_ref.assign(cid.begin(), cid.end());

    std::vector<Byte> payload;
    EXPECT(BuildDocRefOpenPayload(p, payload), "build should succeed");
    EXPECT(payload.size() <= 255, "payload within limit");

    auto r = ValidateCapsulePolicy(payload);
    EXPECT(r.ok, "valid doc_ref should pass: " + r.message);
    g_pass++;
}

// C12: DOC_REF_OPEN locator too long
TEST(C12_doc_ref_locator_too_long) {
    DocRefParams p{};
    p.capsule_id = 1;
    p.file_size_bytes = 1024;
    std::memset(p.file_hash.data(), 0xFF, 32);
    p.locator_type = LocatorType::HTTPS_URL;
    p.locator_ref.assign(97, 'x');  // 97 > max 96

    std::vector<Byte> payload;
    EXPECT(BuildDocRefOpenPayload(p, payload), "build should succeed");

    auto r = ValidateCapsulePolicy(payload);
    EXPECT(!r.ok, "locator too long should be rejected");
    EXPECT(r.code == CapsuleValCode::DOC_LOCATOR_TOO_LONG, "correct code");
    g_pass++;
}

// C13: non-standard capsule_type rejected
TEST(C13_experimental_type_rejected) {
    std::vector<Byte> payload;
    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type = 0x80;  // experimental
    h.body_len = 0;
    h.reserved = 0;
    EncodeCapsuleHeader(h, payload);

    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "experimental type should be rejected");
    EXPECT(r.code == CapsuleValCode::BAD_CAPSULE_TYPE, "correct code");
    g_pass++;
}

// C14: payload too short for header
TEST(C14_too_short) {
    std::vector<Byte> payload(5, 0);
    payload[0] = CAPSULE_MAGIC_0; payload[1] = CAPSULE_MAGIC_1;
    auto r = ValidateCapsuleHeader(payload);
    EXPECT(!r.ok, "too short should fail");
    EXPECT(r.code == CapsuleValCode::PAYLOAD_TOO_SHORT, "correct code");
    g_pass++;
}

// =============================================================================
// PART 2: tx_validation integration — R14 conditional by height
// =============================================================================

// Helper: sign tx[0] and fail the test if signing fails
static void SignBundleOrFail(decltype(MakeTxWithPayload(std::vector<Byte>{}, 0, 0))& b) {
    // Ensure pubkey is present (some builders leave it zeroed)
    if (!b.tx.inputs.empty()) {
        b.tx.inputs[0].pubkey = g_pub;
    }
    SpentOutput spent{10000000, OUT_TRANSFER};
    std::string err;
    bool ok = SignTransactionInput(b.tx, 0, spent, g_genesis, g_priv, &err);
    EXPECT(ok, "SignTransactionInput failed: " + err);
}

// C20: pre-activation: payload on OUT_TRANSFER rejected by consensus
TEST(C20_pre_activation_payload_rejected) {
    std::vector<Byte> note_payload;
    BuildOpenNotePayload("test", note_payload);

    // spend_height=50, activation=5000 → pre-activation
    auto b = MakeTxWithPayload(note_payload, 50, 5000);
    SignBundleOrFail(b);

    auto r = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(!r.ok, "pre-activation payload should fail consensus");
    EXPECT(r.code == TxValCode::R14_PAYLOAD_FORBIDDEN, "R14 code");
    g_pass++;
}

// C21: post-activation: payload on OUT_TRANSFER passes consensus
TEST(C21_post_activation_payload_passes) {
    std::vector<Byte> note_payload;
    BuildOpenNotePayload("INV-2026-001", note_payload);

    // spend_height=5001, activation=5000 → post-activation
    auto b = MakeTxWithPayload(note_payload, 5001, 5000);
    SignBundleOrFail(b);

    auto r = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r.ok, "post-activation payload should pass consensus: " + r.message);
    g_pass++;
}

// C22: post-activation: valid capsule passes full policy
TEST(C22_post_activation_capsule_policy_pass) {
    std::vector<Byte> note_payload;
    BuildOpenNotePayload("Payment for order #42", note_payload);

    auto b = MakeTxWithPayload(note_payload, 5001, 5000);
    SignBundleOrFail(b);

    auto r1 = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r1.ok, "consensus should pass: " + r1.message);

    auto r2 = ValidateTransactionPolicy(b.tx, b.utxos, b.ctx);
    EXPECT(r2.ok, "policy should pass: " + r2.message);
    g_pass++;
}

// C23: post-activation: bad capsule magic rejected by policy
TEST(C23_bad_capsule_magic_policy_fail) {
    // Build raw payload with wrong magic
    std::vector<Byte> bad_payload = {0xFF, 0xFF, 0x01, 0x01, 0x00, 0x00,
                                     0x00, 0x00, 0x00, 0x02, 0x00, 0x00,
                                     0x01, 'X'};

    auto b = MakeTxWithPayload(bad_payload, 5001, 5000);
    SignBundleOrFail(b);

    // Consensus should pass (only checks size <=255 and type==OUT_TRANSFER post-activation)
    auto r1 = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r1.ok, "consensus should pass bad capsule: " + r1.message);

    // Policy should reject bad magic
    auto r2 = ValidateTransactionPolicy(b.tx, b.utxos, b.ctx);
    EXPECT(!r2.ok, "policy should reject bad capsule magic");
    EXPECT(r2.code == TxValCode::P_BAD_CAPSULE, "P_BAD_CAPSULE code");
    g_pass++;
}

// C24: post-activation: no payload → still passes (normal transfer)
TEST(C24_post_activation_no_payload_ok) {
    std::vector<Byte> empty_payload;
    auto b = MakeTxWithPayload(empty_payload, 5001, 5000);
    SignBundleOrFail(b);

    auto r1 = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r1.ok, "no payload should pass: " + r1.message);

    auto r2 = ValidateTransactionPolicy(b.tx, b.utxos, b.ctx);
    EXPECT(r2.ok, "no payload policy should pass: " + r2.message);
    g_pass++;
}

// C25: exactly at activation height: payload allowed
TEST(C25_exact_activation_height) {
    std::vector<Byte> note;
    BuildOpenNotePayload("activated", note);

    auto b = MakeTxWithPayload(note, 5000, 5000);  // exactly at boundary
    SignBundleOrFail(b);

    auto r = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r.ok, "at exact activation height payload should pass: " + r.message);
    g_pass++;
}

// C26: activation height=1 (DEV mode) — payload at height 1
TEST(C26_dev_activation) {
    std::vector<Byte> note;
    BuildOpenNotePayload("dev-test", note);

    auto b = MakeTxWithPayload(note, 1, CAPSULE_ACTIVATION_HEIGHT_DEV);
    SignBundleOrFail(b);

    auto r = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r.ok, "DEV mode payload at height 1: " + r.message);
    g_pass++;
}

// C27: pre-activation: no payload still works (genesis-safe)
TEST(C27_pre_activation_no_payload_ok) {
    std::vector<Byte> empty;
    auto b = MakeTxWithPayload(empty, 1, 5000);
    SignBundleOrFail(b);

    auto r = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r.ok, "pre-activation no payload: " + r.message);
    g_pass++;
}

// C28: 2 payload outputs rejected by policy (max=1)
TEST(C28_too_many_payload_outputs) {
    std::vector<Byte> note;
    BuildOpenNotePayload("note1", note);

    auto b = MakeTxWithPayload(note, 5001, 5000);

    // Add second output with payload
    TxOutput out2;
    out2.amount = 100000;
    out2.type = OUT_TRANSFER;
    out2.pubkey_hash = g_pkh;
    BuildOpenNotePayload("note2", out2.payload);
    b.tx.outputs.push_back(out2);

    // Adjust output amounts to be valid
    b.tx.outputs[0].amount = 5000000;
    b.tx.outputs[1].amount = 4999000;

    // Re-sign (hashOutputs changed)
    b.tx.inputs[0].pubkey = g_pub;
    SpentOutput spent{10000000, OUT_TRANSFER};
    std::string err;
    EXPECT(SignTransactionInput(b.tx, 0, spent, g_genesis, g_priv, &err), "SignTransactionInput failed: " + err);

    auto r = ValidateTransactionPolicy(b.tx, b.utxos, b.ctx);
    EXPECT(!r.ok, "2 payload outputs should fail policy");
    EXPECT(r.code == TxValCode::P_TOO_MANY_PAYLOADS, "correct code");
    g_pass++;
}

// C29: DOC_REF_OPEN full integration (consensus + policy)
TEST(C29_doc_ref_open_integration) {
    DocRefParams p{};
    p.capsule_id = 2026001;
    p.file_size_bytes = 3145728;
    std::memset(p.file_hash.data(), 0xDE, 32);
    p.locator_type = LocatorType::HTTPS_PATH;
    std::string loc = "/caps/2026/03/contract-a.cap";
    p.locator_ref.assign(loc.begin(), loc.end());

    std::vector<Byte> payload;
    BuildDocRefOpenPayload(p, payload);

    auto b = MakeTxWithPayload(payload, 5001, 5000);
    SignBundleOrFail(b);

    auto r1 = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(r1.ok, "DOC_REF consensus: " + r1.message);

    auto r2 = ValidateTransactionPolicy(b.tx, b.utxos, b.ctx);
    EXPECT(r2.ok, "DOC_REF policy: " + r2.message);
    g_pass++;
}

// C30: coinbase outputs never allow payload (even post-activation)
TEST(C30_coinbase_no_payload) {
    // Build valid coinbase
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;

    TxInput cbin;
    std::memset(cbin.prev_txid.data(), 0, 32);
    cbin.prev_index = 0xFFFFFFFF;
    std::memset(cbin.signature.data(), 0, 64);
    uint64_t h = 5001;
    std::memcpy(cbin.signature.data(), &h, 8);
    std::memset(cbin.pubkey.data(), 0, 33);
    tx.inputs.push_back(cbin);

    int64_t subsidy = 785100863;
    int64_t q = subsidy / 4;

    TxOutput o1; o1.amount = subsidy - q - q; o1.type = OUT_COINBASE_MINER;
    std::memset(o1.pubkey_hash.data(), 0xDD, 20);
    tx.outputs.push_back(o1);

    TxOutput o2; o2.amount = q; o2.type = OUT_COINBASE_GOLD;
    PubKeyHash gold_pkh{}; std::memset(gold_pkh.data(), 0xBB, 20);
    o2.pubkey_hash = gold_pkh;
    // Add payload to coinbase output → should fail CB10
    o2.payload = {0x53, 0x43, 0x01};
    tx.outputs.push_back(o2);

    TxOutput o3; o3.amount = q; o3.type = OUT_COINBASE_POPC;
    PubKeyHash popc_pkh{}; std::memset(popc_pkh.data(), 0xCC, 20);
    o3.pubkey_hash = popc_pkh;
    tx.outputs.push_back(o3);

    auto r = ValidateCoinbaseConsensus(tx, 5001, subsidy, 0, gold_pkh, popc_pkh);
    EXPECT(!r.ok, "coinbase with payload should fail");
    EXPECT(r.code == TxValCode::CB10_CB_PAYLOAD, "CB10 code");
    g_pass++;
}

// =============================================================================
// main
// =============================================================================

int main() {
    InitKeys();

    std::cout << "=== Capsule Protocol v1 + tx_validation integration tests ===\n\n";

    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev = g_pass;
        int prev_f = g_fail;
        fn();
        if (g_pass > prev) std::cout << "PASS\n";
        else if (g_fail == prev_f) std::cout << "SKIP\n";
    }

    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail << " failed"
              << " out of " << (g_pass + g_fail) << " ===\n";
    return g_fail > 0 ? 1 : 0;
}
