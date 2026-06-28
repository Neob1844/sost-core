// test_htlc_block_path_v14_5.cpp — V14.5 atomic-swap HTLC consensus fix.
//
// This test is the regression guard for the live mainnet bug: the HTLC was
// declared active at V14 (block 15000) but CLAIM (0x10) / REFUND (0x11) txs were
// rejected on the BLOCK PATH ("non-standard tx" / "must be standard"), so locked
// funds could never settle. The fix moves the activation to a dedicated V14.5
// milestone (mainnet block 16000) and exempts the HTLC tx types on the block
// path once atomic_swap_htlc_active_at(height) is true.
//
// It covers BOTH:
//   (A) the unit / validation path  (ValidateTransactionConsensus)
//   (B) the block path              (UtxoSet::ConnectBlock — the exact guard
//                                    that mirrors process_block in sost-node.cpp)
//
// All heights are derived from ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT so the test
// passes IDENTICALLY in the mainnet build (gate == 16000) and the testnet build
// (-DSOST_TESTNET_FORKS, gate == 30).

#include "sost/atomic_swap.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/utxo_set.h"
#include "sost/consensus_constants.h"
#include "sost/crypto.h"

#include <array>
#include <climits>
#include <cstdio>
#include <cstring>
#include <optional>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { std::printf("  PASS: %s\n", msg); ++g_pass; } \
    else { std::printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); ++g_fail; } \
} while (0)

// The gate (single source of truth). On mainnet == 16000, on testnet == 30.
static constexpr int64_t H = ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;

// ---------------------------------------------------------------------------
// Shared HTLC fixtures
// ---------------------------------------------------------------------------
static std::array<uint8_t, 32> g_preimage{};   // the real preimage
static std::array<uint8_t, 32> g_hashlock{};    // sha256(preimage)
static std::array<uint8_t, 20> g_claim_pkh{};
static std::array<uint8_t, 20> g_refund_pkh{};
static constexpr int64_t LOCK_AMOUNT   = 100000;
static int64_t           LOCK_REFUND_H = 0;     // set in main() == H + 10000

static TxValidationContext MakeCtx(int64_t spend_height) {
    TxValidationContext ctx;
    ctx.genesis_hash.fill(0);
    ctx.spend_height = spend_height;
    ctx.capsule_activation_height = CAPSULE_ACTIVATION_HEIGHT_MAINNET;
    ctx.bond_activation_height    = BOND_ACTIVATION_HEIGHT_MAINNET;
    return ctx;
}

// A UtxoView that returns a single HTLC_LOCK utxo at a fixed outpoint.
struct HtlcLockView : IUtxoView {
    Hash256  lock_txid{};
    uint32_t lock_vout{0};
    uint8_t  lock_type{OUT_HTLC_LOCK};
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        if (op.txid != lock_txid || op.index != lock_vout) return std::nullopt;
        UTXOEntry e;
        e.amount = LOCK_AMOUNT;
        e.type = lock_type;
        e.pubkey_hash.fill(0);
        WriteHtlcLockPayload(e.payload, g_hashlock, (uint64_t)LOCK_REFUND_H,
                             g_claim_pkh, g_refund_pkh);
        e.payload_len = (uint16_t)e.payload.size();
        e.height = 100;
        e.is_coinbase = false;
        return e;
    }
};

static Transaction MakeLockTx(int64_t refund_height) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;
    TxInput in;
    in.prev_txid.fill(0xAA);
    in.prev_index = 0;
    in.signature.fill(0x01);
    in.pubkey.fill(0x02);
    tx.inputs.push_back(in);
    TxOutput out;
    out.amount = LOCK_AMOUNT;
    out.type = OUT_HTLC_LOCK;
    out.pubkey_hash.fill(0);
    WriteHtlcLockPayload(out.payload, g_hashlock, (uint64_t)refund_height,
                         g_claim_pkh, g_refund_pkh);
    tx.outputs.push_back(out);
    return tx;
}

static Transaction MakeClaimTx(const Hash256& lock_txid, uint32_t vout,
                               const std::array<uint8_t, 32>& preimage) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_HTLC_CLAIM;
    TxInput in;
    in.prev_txid = lock_txid;
    in.prev_index = vout;
    in.signature.fill(0x01);  // bogus — validation-path tests target R-rules
    in.pubkey.fill(0x02);
    tx.inputs.push_back(in);
    TxOutput m;                // witness marker carrying the preimage (outputs[0])
    m.amount = 10000;
    m.type = OUT_HTLC_CLAIM_WITNESS;
    m.pubkey_hash.fill(0);
    WriteHtlcClaimWitnessPayload(m.payload, preimage);
    tx.outputs.push_back(m);
    TxOutput o;                // the actual transfer output (outputs[1])
    o.amount = 80000;
    o.type = OUT_TRANSFER;
    o.pubkey_hash.fill(0xAB);
    tx.outputs.push_back(o);
    return tx;
}

static Transaction MakeRefundTx(const Hash256& lock_txid, uint32_t vout) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_HTLC_REFUND;
    TxInput in;
    in.prev_txid = lock_txid;
    in.prev_index = vout;
    in.signature.fill(0x01);
    in.pubkey.fill(0x02);
    tx.inputs.push_back(in);
    TxOutput o;
    o.amount = 90000;
    o.type = OUT_TRANSFER;
    o.pubkey_hash = g_refund_pkh;  // refund destination
    tx.outputs.push_back(o);
    return tx;
}

static Transaction MakeMinimalCoinbase(int64_t height) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;
    TxInput cbin;
    cbin.prev_txid.fill(0);
    cbin.prev_index = 0xFFFFFFFF;
    cbin.signature.fill(0);
    uint64_t h = (uint64_t)height;
    std::memcpy(cbin.signature.data(), &h, 8);
    cbin.pubkey.fill(0);
    tx.inputs.push_back(cbin);
    TxOutput o;
    o.amount = 1000000;
    o.type = OUT_TRANSFER;
    o.pubkey_hash.fill(0x33);
    tx.outputs.push_back(o);
    return tx;
}

// Seed a fresh UtxoSet with one HTLC_LOCK utxo at the given outpoint.
static void SeedLock(UtxoSet& uset, const Hash256& lock_txid) {
    UTXOEntry e;
    e.amount = LOCK_AMOUNT;
    e.type = OUT_HTLC_LOCK;
    e.pubkey_hash.fill(0);
    WriteHtlcLockPayload(e.payload, g_hashlock, (uint64_t)LOCK_REFUND_H,
                         g_claim_pkh, g_refund_pkh);
    e.payload_len = (uint16_t)e.payload.size();
    e.height = 100;
    e.is_coinbase = false;
    std::string err;
    if (!uset.AddUTXO(OutPoint{lock_txid, 0}, e, &err))
        std::printf("  (seed AddUTXO failed: %s)\n", err.c_str());
}

int main() {
    std::printf("\n== V14.5 atomic-swap HTLC consensus fix — block-path + validation ==\n\n");

    // Fixtures
    for (size_t i = 0; i < g_preimage.size(); ++i) g_preimage[i] = (uint8_t)i;
    {
        Bytes32 hl = sha256(g_preimage.data(), g_preimage.size());
        std::copy(hl.begin(), hl.end(), g_hashlock.begin());
    }
    g_claim_pkh.fill(0x55);
    g_refund_pkh.fill(0x77);
    LOCK_REFUND_H = H + 10000;

    std::printf("  ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = %lld\n", (long long)H);
    std::printf("  V14_5_HEIGHT = %lld  V14_HEIGHT = %lld  V15_HEIGHT = %lld\n\n",
                (long long)V14_5_HEIGHT, (long long)V14_HEIGHT, (long long)V15_HEIGHT);

    // =====================================================================
    // 0. GATE / SEPARATION CONSTANT ASSERTIONS
    // =====================================================================
    TEST("gate == V14_5_HEIGHT", H == V14_5_HEIGHT);
    TEST("gate is finite (feature activates)", H != INT64_MAX);
    TEST("HTLC gate is SEPARATE from V15 (PoPC/Gold)", H != V15_HEIGHT);
    TEST("HTLC gate moved off V14 (the broken declaration)", H != V14_HEIGHT);
#ifndef SOST_TESTNET_FORKS
    TEST("MAINNET gate == 16000", H == 16000);
    TEST("MAINNET V15_HEIGHT still 20000 (untouched)", V15_HEIGHT == 20000);
    TEST("MAINNET V14_HEIGHT still 15000 (untouched)", V14_HEIGHT == 15000);
#else
    TEST("TESTNET gate is low (regtest soak fits)", H <= 1000);
#endif

    const bool open = atomic_swap_htlc_active_at(H);
    TEST("active_at(H) == true",   open);
    TEST("active_at(H-1) == false", !atomic_swap_htlc_active_at(H - 1));
    TEST("active_at(0) == false",  !atomic_swap_htlc_active_at(0));

    HtlcLockView view;
    view.lock_txid.fill(0xCC);
    view.lock_vout = 0;

    // =====================================================================
    // (A) VALIDATION-PATH TESTS  (ValidateTransactionConsensus)
    // =====================================================================
    std::printf("\n-- (A) validation path --\n");

    // A1. pre-activation: LOCK output rejected as inactive type (R11) → inert.
    {
        Transaction tx = MakeLockTx(H + 5000);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H - 1));
        TEST("A1 pre-activation LOCK rejected (R11_INACTIVE_TYPE)",
             !r.ok && r.code == TxValCode::R11_INACTIVE_TYPE);
    }
    // A2. pre-activation: CLAIM tx_type rejected (R2) → inert.
    {
        Transaction tx = MakeClaimTx(view.lock_txid, 0, g_preimage);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H - 1));
        TEST("A2 pre-activation CLAIM rejected (R2_BAD_TX_TYPE)",
             !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
    }
    // A3. pre-activation: REFUND tx_type rejected (R2) → inert.
    {
        Transaction tx = MakeRefundTx(view.lock_txid, 0);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H - 1));
        TEST("A3 pre-activation REFUND rejected (R2_BAD_TX_TYPE)",
             !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
    }
    // A4. post-activation: LOCK passes the HTLC structural rules (not R11/R17).
    //     (It later fails S1 because the dummy input utxo is absent — expected.)
    {
        Transaction tx = MakeLockTx(H + 5000);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H));
        TEST("A4 post-activation LOCK not rejected by R11", r.code != TxValCode::R11_INACTIVE_TYPE);
        TEST("A4 post-activation LOCK not rejected by R17", r.code != TxValCode::R17_HTLC_PAYLOAD_INVALID);
        TEST("A4 post-activation LOCK not rejected by S9",  r.code != TxValCode::S9_BAD_STD_OUTPUT_TYPE);
    }
    // A5. post-activation: CLAIM with CORRECT preimage passes the HTLC rules
    //     (no R19–R22). It then fails at the signature path (bogus key) — proof
    //     the preimage/timeout gates are satisfied.
    {
        Transaction tx = MakeClaimTx(view.lock_txid, 0, g_preimage);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H + 1));
        TEST("A5 correct-preimage CLAIM passes R2",  r.code != TxValCode::R2_BAD_TX_TYPE);
        TEST("A5 correct-preimage CLAIM passes R21", r.code != TxValCode::R21_HTLC_CLAIM_PREIMAGE_MISMATCH);
        TEST("A5 correct-preimage CLAIM passes R22", r.code != TxValCode::R22_HTLC_CLAIM_TIMEOUT);
    }
    // A6. post-activation: CLAIM with WRONG preimage rejected (R21).
    {
        std::array<uint8_t, 32> bad{};
        bad[0] = 0xFF;
        Transaction tx = MakeClaimTx(view.lock_txid, 0, bad);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H + 1));
        TEST("A6 wrong-preimage CLAIM rejected (R21_HTLC_CLAIM_PREIMAGE_MISMATCH)",
             !r.ok && r.code == TxValCode::R21_HTLC_CLAIM_PREIMAGE_MISMATCH);
    }
    // A7. post-activation: CLAIM at/after timeout rejected (R22).
    {
        Transaction tx = MakeClaimTx(view.lock_txid, 0, g_preimage);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(LOCK_REFUND_H));  // == refund_height
        TEST("A7 claim-at-timeout rejected (R22_HTLC_CLAIM_TIMEOUT)",
             !r.ok && r.code == TxValCode::R22_HTLC_CLAIM_TIMEOUT);
    }
    // A8. post-activation: REFUND before refund_height rejected (R24).
    {
        Transaction tx = MakeRefundTx(view.lock_txid, 0);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(LOCK_REFUND_H - 1));
        TEST("A8 refund-before-timeout rejected (R24_HTLC_REFUND_BEFORE_TIMEOUT)",
             !r.ok && r.code == TxValCode::R24_HTLC_REFUND_BEFORE_TIMEOUT);
    }
    // A9. post-activation: REFUND at refund_height passes the timeout rule (no R24).
    //     (Fails later at the signature path with the bogus key — expected.)
    {
        Transaction tx = MakeRefundTx(view.lock_txid, 0);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(LOCK_REFUND_H));
        TEST("A9 refund-at-timeout passes R24", r.code != TxValCode::R24_HTLC_REFUND_BEFORE_TIMEOUT);
        TEST("A9 refund-at-timeout passes R23", r.code != TxValCode::R23_HTLC_REFUND_STRUCTURE_INVALID);
    }
    // A10. regression: a normal STANDARD transfer is unaffected (fails S1 only).
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_STANDARD;
        TxInput in; in.prev_txid.fill(0xEE); in.prev_index = 0;
        in.signature.fill(0x01); in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput o; o.amount = 50000; o.type = OUT_TRANSFER; o.pubkey_hash.fill(0xAB);
        tx.outputs.push_back(o);
        auto r = ValidateTransactionConsensus(tx, view, MakeCtx(H + 1));
        TEST("A10 normal STANDARD tx unaffected (fails S1)",
             !r.ok && r.code == TxValCode::S1_UTXO_NOT_FOUND);
    }

    // =====================================================================
    // (B) BLOCK-PATH TESTS  (UtxoSet::ConnectBlock — same tx_type guard as
    //     process_block in sost-node.cpp). This is the path the bug lived on
    //     and that the old unit tests never exercised.
    // =====================================================================
    std::printf("\n-- (B) block path (ConnectBlock) --\n");

    Hash256 lock_txid; lock_txid.fill(0xCC);

    // B1. below activation: a block containing a CLAIM is rejected "must be standard".
    {
        UtxoSet uset; SeedLock(uset, lock_txid);
        std::vector<Transaction> block = { MakeMinimalCoinbase(H - 1),
                                           MakeClaimTx(lock_txid, 0, g_preimage) };
        BlockUndo undo; std::string err;
        bool ok = uset.ConnectBlock(block, H - 1, undo, &err);
        TEST("B1 below-gate CLAIM block rejected",
             !ok && err.find("must be standard") != std::string::npos);
    }
    // B2. below activation: a block containing a REFUND is rejected "must be standard".
    {
        UtxoSet uset; SeedLock(uset, lock_txid);
        std::vector<Transaction> block = { MakeMinimalCoinbase(H - 1),
                                           MakeRefundTx(lock_txid, 0) };
        BlockUndo undo; std::string err;
        bool ok = uset.ConnectBlock(block, H - 1, undo, &err);
        TEST("B2 below-gate REFUND block rejected",
             !ok && err.find("must be standard") != std::string::npos);
    }
    // B3. at activation: a block containing a CLAIM is ACCEPTED (guard exempts it,
    //     the LOCK utxo is spent). This is the core fix.
    {
        UtxoSet uset; SeedLock(uset, lock_txid);
        std::vector<Transaction> block = { MakeMinimalCoinbase(H),
                                           MakeClaimTx(lock_txid, 0, g_preimage) };
        BlockUndo undo; std::string err;
        bool ok = uset.ConnectBlock(block, H, undo, &err);
        TEST("B3 at-gate CLAIM block ACCEPTED (was the live bug)", ok);
        TEST("B3 LOCK utxo consumed by the CLAIM", !uset.HasUTXO(OutPoint{lock_txid, 0}));
    }
    // B4. at activation: a block containing a REFUND is ACCEPTED.
    {
        UtxoSet uset; SeedLock(uset, lock_txid);
        std::vector<Transaction> block = { MakeMinimalCoinbase(H),
                                           MakeRefundTx(lock_txid, 0) };
        BlockUndo undo; std::string err;
        bool ok = uset.ConnectBlock(block, H, undo, &err);
        TEST("B4 at-gate REFUND block ACCEPTED", ok);
        TEST("B4 LOCK utxo consumed by the REFUND", !uset.HasUTXO(OutPoint{lock_txid, 0}));
    }
    // B5. regression: below the gate, a block whose non-coinbase txs are all
    //     STANDARD still connects (the guard exemption did not loosen anything).
    {
        UtxoSet uset;
        // seed a plain transfer utxo to spend
        Hash256 prev; prev.fill(0x42);
        UTXOEntry pe; pe.amount = 50000; pe.type = OUT_TRANSFER; pe.pubkey_hash.fill(0x01);
        pe.payload_len = 0; pe.height = 1; pe.is_coinbase = false;
        std::string serr; uset.AddUTXO(OutPoint{prev, 0}, pe, &serr);
        Transaction std_tx;
        std_tx.version = 1; std_tx.tx_type = TX_TYPE_STANDARD;
        TxInput in; in.prev_txid = prev; in.prev_index = 0;
        in.signature.fill(0x01); in.pubkey.fill(0x02); std_tx.inputs.push_back(in);
        TxOutput o; o.amount = 40000; o.type = OUT_TRANSFER; o.pubkey_hash.fill(0x09);
        std_tx.outputs.push_back(o);
        std::vector<Transaction> block = { MakeMinimalCoinbase(H - 1), std_tx };
        BlockUndo undo; std::string err;
        bool ok = uset.ConnectBlock(block, H - 1, undo, &err);
        TEST("B5 below-gate STANDARD-only block still connects", ok);
    }
    // B6. below the gate, an UNKNOWN non-standard tx_type is STILL rejected
    //     (the exemption is narrow: only CLAIM/REFUND, only when active).
    {
        UtxoSet uset; SeedLock(uset, lock_txid);
        Transaction weird = MakeClaimTx(lock_txid, 0, g_preimage);
        weird.tx_type = 0x42;  // not standard, not a known HTLC type
        std::vector<Transaction> block = { MakeMinimalCoinbase(H), weird };
        BlockUndo undo; std::string err;
        bool ok = uset.ConnectBlock(block, H, undo, &err);
        TEST("B6 at-gate UNKNOWN non-standard tx still rejected",
             !ok && err.find("must be standard") != std::string::npos);
    }

    std::printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
