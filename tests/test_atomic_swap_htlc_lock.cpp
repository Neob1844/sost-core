// Atomic Swap HTLC — Phase 3A scope-B tests for OUT_HTLC_LOCK only.
//
// These 9 unit tests verify the structural validity rules for the new
// HTLC_LOCK output type, gated by atomic_swap_htlc_active_at(spend_height).
//
// Scope: OUT_HTLC_LOCK output validation only. CLAIM/REFUND spending paths
// are deferred to a follow-up sprint.

#include "sost/atomic_swap.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/consensus_constants.h"
#include "sost/crypto.h"   // sha256() + Bytes32 (Phase 3B-1b tests)

#include <cstdio>
#include <cstring>
#include <climits>
#include <optional>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

struct StubUtxoView : IUtxoView {
    std::optional<UTXOEntry> GetUTXO(const OutPoint&) const override {
        return std::nullopt;
    }
};

static Transaction MakeStdTxWithHtlcLock(
    const std::array<uint8_t, 32>& hashlock,
    uint64_t refund_height,
    const std::array<uint8_t, 20>& claim_pkh,
    const std::array<uint8_t, 20>& refund_pkh,
    int64_t amount)
{
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;
    // Dummy input — must be present so R3 (input count > 0) passes and the
    // per-output R-rules (R11, R17) are reached. The input is bogus and the
    // tx will fail S1 (UTXO_NOT_FOUND) when validation reaches the S-rules,
    // but the R-rules execute BEFORE S-rules so our tests see R11/R17 first.
    TxInput in;
    in.prev_txid.fill(0xAA);
    in.prev_index = 0;
    in.signature.fill(0x01);
    in.pubkey.fill(0x02);
    tx.inputs.push_back(in);
    TxOutput out;
    out.amount = amount;
    out.type = OUT_HTLC_LOCK;
    out.pubkey_hash.fill(0);
    WriteHtlcLockPayload(out.payload, hashlock, refund_height, claim_pkh, refund_pkh);
    tx.outputs.push_back(out);
    return tx;
}

static TxValidationContext MakeCtx(int64_t spend_height) {
    TxValidationContext ctx;
    ctx.genesis_hash.fill(0);
    ctx.spend_height = spend_height;
    ctx.capsule_activation_height = CAPSULE_ACTIVATION_HEIGHT_MAINNET;
    ctx.bond_activation_height    = BOND_ACTIVATION_HEIGHT_MAINNET;
    return ctx;
}

int main() {
    printf("\n== Atomic Swap HTLC Phase 3A — OUT_HTLC_LOCK structural tests ==\n\n");
    printf("  Gate state: ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = %lld\n",
           (long long)ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT);
    // Gate-relative heights so this test tracks the activation height in BOTH the
    // mainnet build (gate == V14_5_HEIGHT == 16000) and the testnet build (gate
    // low). All "post-activation" heights are >= the gate; "pre" is gate-1.
    const int64_t GATE_H   = ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;
    const int64_t PRE_H    = GATE_H - 1;          // inactive (below gate)
    const int64_t POST_H   = GATE_H;              // first active height
    const int64_t MID_H    = GATE_H + 1000;       // active, before the lock's refund_height
    const int64_t REFUND_H = GATE_H + 20000;      // the lock's refund_height
    const int64_t LATE_H   = REFUND_H + 5000;     // active, at/after timeout
    const bool gate_open = atomic_swap_htlc_active_at(POST_H);
    printf("  Gate is %s at POST_H=%lld (gate-relative; post-activation tests %s)\n\n",
           gate_open ? "OPEN" : "CLOSED", (long long)POST_H,
           gate_open ? "WILL RUN" : "WILL BE SKIPPED");

    StubUtxoView utxos;

    std::array<uint8_t, 32> hashlock{};
    for (size_t i = 0; i < hashlock.size(); ++i) hashlock[i] = static_cast<uint8_t>(0x10 + i);
    std::array<uint8_t, 20> claim_pkh{};
    for (size_t i = 0; i < claim_pkh.size(); ++i) claim_pkh[i] = static_cast<uint8_t>(0x40 + i);
    std::array<uint8_t, 20> refund_pkh{};
    for (size_t i = 0; i < refund_pkh.size(); ++i) refund_pkh[i] = static_cast<uint8_t>(0x80 + i);

    // T1: payload helpers roundtrip
    {
        std::vector<uint8_t> payload;
        WriteHtlcLockPayload(payload, hashlock, 20000, claim_pkh, refund_pkh);
        TEST("T1a payload size == 80", payload.size() == HTLC_LOCK_PAYLOAD_LEN);
        TEST("T1b hashlock roundtrip", ReadHtlcHashlock(payload) == hashlock);
        TEST("T1c refund_height roundtrip", ReadHtlcRefundHeight(payload) == 20000ULL);
        TEST("T1d claim_pkh roundtrip", ReadHtlcClaimPkh(payload) == claim_pkh);
        TEST("T1e refund_pkh roundtrip", ReadHtlcRefundPkh(payload) == refund_pkh);
    }

    // T2: pre-activation HTLC_LOCK rejected with R11
    {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 20000, claim_pkh, refund_pkh, 100000);
        auto ctx = MakeCtx(PRE_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T2 pre-activation HTLC_LOCK rejected at all", !r.ok);
        TEST("T2 pre-activation HTLC_LOCK rejected with R11_INACTIVE_TYPE",
             !r.ok && r.code == TxValCode::R11_INACTIVE_TYPE);
    }

    // T3: post-activation valid HTLC_LOCK passes R-side rules (R11, R17)
    if (!gate_open) {
        printf("  SKIP: T3 (gate closed; post-activation acceptance not testable)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 20000, claim_pkh, refund_pkh, 100000);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T3 post-activation not rejected with R11",
             r.code != TxValCode::R11_INACTIVE_TYPE);
        TEST("T3 post-activation not rejected with R17",
             r.code != TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T4: wrong payload length rejected with R17
    if (!gate_open) {
        printf("  SKIP: T4 (gate closed; R17 unreachable while LOCK is inactive)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 20000, claim_pkh, refund_pkh, 100000);
        tx.outputs[0].payload.resize(79);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T4 wrong payload length rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T5: amount < DUST rejected with R17
    if (!gate_open) {
        printf("  SKIP: T5 (gate closed; R17 unreachable while LOCK is inactive)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 20000, claim_pkh, refund_pkh,
                                                DUST_THRESHOLD - 1);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T5 amount < DUST rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T6: refund_height == spend_height rejected with R17
    if (!gate_open) {
        printf("  SKIP: T6 (gate closed; R17 unreachable while LOCK is inactive)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, POST_H, claim_pkh, refund_pkh, 100000);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T6 refund_height == spend_height rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T7: refund_height in past rejected with R17
    if (!gate_open) {
        printf("  SKIP: T7 (gate closed; R17 unreachable while LOCK is inactive)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, PRE_H, claim_pkh, refund_pkh, 100000);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T7 refund_height in past rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T8: pre-activation malformed payload — R11 fires first (inactive type)
    {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 20000, claim_pkh, refund_pkh, 100000);
        tx.outputs[0].payload.resize(5);
        auto ctx = MakeCtx(PRE_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T8 pre-activation malformed HTLC_LOCK rejected (R11 fires first)",
             !r.ok && r.code == TxValCode::R11_INACTIVE_TYPE);
    }

    // T9: gate helper boundaries (gate-relative so it holds in both builds)
    {
        constexpr int64_t H = ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;
        const int64_t pre_sample = (H > 1) ? (H / 2) : 0;   // a height safely below the gate
        bool at_zero          = atomic_swap_htlc_active_at(0);
        bool at_pre           = atomic_swap_htlc_active_at(pre_sample);
        bool at_H             = atomic_swap_htlc_active_at(H);
        TEST("T9a active_at(0) == false",            !at_zero);
        TEST("T9b active_at(pre-gate) == false",     !at_pre);
        TEST("T9c active_at(H) == true",              at_H);
        if (H > 0 && H != INT64_MAX) {
            bool at_just_below_H = atomic_swap_htlc_active_at(H - 1);
            TEST("T9d active_at(H-1) == false",      !at_just_below_H);
        }
    }

    // -----------------------------------------------------------------------
    // T10. Phase 3B-1a — HTLC_CLAIM_WITNESS payload helpers roundtrip
    // -----------------------------------------------------------------------
    {
        std::array<uint8_t, 32> preimage{};
        for (size_t k = 0; k < preimage.size(); ++k)
            preimage[k] = static_cast<uint8_t>(0xA0 + k);
        std::vector<uint8_t> wpayload;
        WriteHtlcClaimWitnessPayload(wpayload, preimage);
        TEST("T10a witness payload size == 32",
             wpayload.size() == HTLC_CLAIM_WITNESS_PAYLOAD_LEN);
        TEST("T10b preimage roundtrip",
             ReadHtlcPreimage(wpayload) == preimage);
    }

    // -----------------------------------------------------------------------
    // T11. Phase 3B-1a — pre-activation HTLC_CLAIM_WITNESS output rejected
    //      Constructs a STANDARD tx carrying an OUT_HTLC_CLAIM_WITNESS output.
    //      With the gate closed (INT64_MAX), R11 rejects the output type as
    //      inactive at any spend_height.
    // -----------------------------------------------------------------------
    {
        std::array<uint8_t, 32> preimage{};
        preimage[0] = 0xDE; preimage[1] = 0xAD; preimage[2] = 0xBE; preimage[3] = 0xEF;
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_STANDARD;
        // Dummy input so R3 passes
        TxInput in;
        in.prev_txid.fill(0xAA);
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput out;
        out.amount = 10000;
        out.type = OUT_HTLC_CLAIM_WITNESS;
        out.pubkey_hash.fill(0);
        WriteHtlcClaimWitnessPayload(out.payload, preimage);
        tx.outputs.push_back(out);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T11 pre-activation HTLC_CLAIM_WITNESS rejected at all", !r.ok);
        if (!gate_open) {
            TEST("T11 pre-activation HTLC_CLAIM_WITNESS rejected with R11_INACTIVE_TYPE",
                 r.code == TxValCode::R11_INACTIVE_TYPE);
        } else {
            // When gate is open (future state), the marker output would survive
            // R11 but R18 rejects it because tx_type is STANDARD, not CLAIM.
            TEST("T11 (gate open) HTLC_CLAIM_WITNESS in STANDARD tx rejected with R18",
                 r.code == TxValCode::R18_HTLC_CLAIM_WITNESS_INVALID);
        }
    }

    // -----------------------------------------------------------------------
    // T12. Phase 3B-1a — pre-activation TX_TYPE_HTLC_CLAIM rejected by R2
    // -----------------------------------------------------------------------
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_HTLC_CLAIM;  // 0x10
        TxInput in;
        in.prev_txid.fill(0xAA);
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput out;
        out.amount = 10000;
        out.type = OUT_TRANSFER;
        out.pubkey_hash.fill(0);
        tx.outputs.push_back(out);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        if (!gate_open) {
            TEST("T12 pre-activation TX_TYPE_HTLC_CLAIM rejected with R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            // With the gate open, R2 lets TX_TYPE_HTLC_CLAIM through. The tx will
            // then fail later rules (no LOCK reference, missing witness, etc.) —
            // 3B-1b adds the CLAIM-specific validation. For now we just assert
            // R2 is NOT the rule that fires.
            TEST("T12 (gate open) TX_TYPE_HTLC_CLAIM passes R2", r.code != TxValCode::R2_BAD_TX_TYPE);
        }
    }

    // -----------------------------------------------------------------------
    // T13. Phase 3B-1a — pre-activation TX_TYPE_HTLC_REFUND rejected by R2
    // -----------------------------------------------------------------------
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_HTLC_REFUND;  // 0x11
        TxInput in;
        in.prev_txid.fill(0xAA);
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput out;
        out.amount = 10000;
        out.type = OUT_TRANSFER;
        out.pubkey_hash.fill(0);
        tx.outputs.push_back(out);
        auto ctx = MakeCtx(POST_H);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        if (!gate_open) {
            TEST("T13 pre-activation TX_TYPE_HTLC_REFUND rejected with R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T13 (gate open) TX_TYPE_HTLC_REFUND passes R2", r.code != TxValCode::R2_BAD_TX_TYPE);
        }
    }

    // =========================================================================
    // Phase 3B-1b — HTLC_CLAIM consensus rules R19-R22.
    //
    // When gate is CLOSED (INT64_MAX): every TX_TYPE_HTLC_CLAIM tx is rejected
    // at R2 (we assert each test gets R2_BAD_TX_TYPE — the safest possible
    // post-condition while CLAIM validation is dormant).
    //
    // When gate is OPEN (V14_HEIGHT): each test reaches the inner CLAIM rule
    // it targets and we assert the specific R19/R20/R21/R22/etc code.
    //
    // A synthetic UtxoView returns a hand-built HTLC_LOCK utxo when asked
    // for the specific outpoint each test uses.
    // =========================================================================

    struct HtlcLockUtxoView : IUtxoView {
        std::array<uint8_t, 32> lock_hashlock{};
        uint64_t lock_refund_height{0};
        std::array<uint8_t, 20> lock_claim_pkh{};
        std::array<uint8_t, 20> lock_refund_pkh{};
        int64_t lock_amount{100000};
        uint8_t lock_type{OUT_HTLC_LOCK};
        Hash256 lock_txid{};
        uint32_t lock_vout{0};

        std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
            if (op.txid != lock_txid || op.index != lock_vout) return std::nullopt;
            UTXOEntry e;
            e.amount = lock_amount;
            e.type = lock_type;
            e.pubkey_hash.fill(0);
            WriteHtlcLockPayload(e.payload, lock_hashlock, lock_refund_height,
                                  lock_claim_pkh, lock_refund_pkh);
            e.height = 100;
            e.is_coinbase = false;
            return e;
        }
    };

    // Helper: build a CLAIM tx that spends a specific HTLC_LOCK outpoint
    // and carries the witness marker (containing preimage) as outputs[0]
    // and one transfer output as outputs[1].
    auto MakeClaimTx = [&](const Hash256& lock_txid,
                            uint32_t lock_vout,
                            const std::array<uint8_t, 32>& preimage_to_use,
                            int64_t marker_amount = 10000,
                            int64_t transfer_amount = 80000) -> Transaction {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_HTLC_CLAIM;
        TxInput in;
        in.prev_txid = lock_txid;
        in.prev_index = lock_vout;
        in.signature.fill(0x01);  // bogus; tests only target R-rules pre-S6
        in.pubkey.fill(0x02);     // bogus; S2/S6 may fail but we look at R-codes
        tx.inputs.push_back(in);
        // marker output
        TxOutput m;
        m.amount = marker_amount;
        m.type = OUT_HTLC_CLAIM_WITNESS;
        m.pubkey_hash.fill(0);
        WriteHtlcClaimWitnessPayload(m.payload, preimage_to_use);
        tx.outputs.push_back(m);
        // real transfer output
        TxOutput o;
        o.amount = transfer_amount;
        o.type = OUT_TRANSFER;
        o.pubkey_hash.fill(0xAB);
        tx.outputs.push_back(o);
        return tx;
    };

    HtlcLockUtxoView htlc_view;
    htlc_view.lock_txid.fill(0xCC);
    htlc_view.lock_vout = 0;
    htlc_view.lock_amount = 100000;
    htlc_view.lock_refund_height = REFUND_H;
    // hashlock = sha256("the secret 32 bytes test preimage!")
    std::array<uint8_t, 32> the_preimage{};
    for (size_t k = 0; k < the_preimage.size(); ++k) the_preimage[k] = static_cast<uint8_t>(k);
    {
        Bytes32 hl = sha256(the_preimage.data(), the_preimage.size());
        std::copy(hl.begin(), hl.end(), htlc_view.lock_hashlock.begin());
    }
    htlc_view.lock_claim_pkh.fill(0x55);
    htlc_view.lock_refund_pkh.fill(0x77);

    auto ctx_v14 = MakeCtx(MID_H);  // active, before refund_height

    // ------------------------------------------------------------------
    // T14: valid CLAIM (when gate open) — wrong preimage rejected with R21
    // ------------------------------------------------------------------
    {
        std::array<uint8_t, 32> bad_preimage{};
        bad_preimage[0] = 0xFF;  // not the right preimage
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, bad_preimage);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T14 (closed) wrong-preimage CLAIM rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T14 (open) wrong-preimage CLAIM rejected by R21_HTLC_CLAIM_PREIMAGE_MISMATCH",
                 !r.ok && r.code == TxValCode::R21_HTLC_CLAIM_PREIMAGE_MISMATCH);
        }
    }

    // ------------------------------------------------------------------
    // T15: claim-after-timeout rejected with R22
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        auto late_ctx = MakeCtx(LATE_H);  // > refund_height
        auto r = ValidateTransactionConsensus(tx, htlc_view, late_ctx);
        if (!gate_open) {
            TEST("T15 (closed) claim-after-timeout rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T15 (open) claim-after-timeout rejected by R22_HTLC_CLAIM_TIMEOUT",
                 !r.ok && r.code == TxValCode::R22_HTLC_CLAIM_TIMEOUT);
        }
    }

    // ------------------------------------------------------------------
    // T16: missing witness — first output is OUT_TRANSFER, not marker
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        // Swap outputs[0] (marker) with a transfer output
        TxOutput plain;
        plain.amount = 80000;
        plain.type = OUT_TRANSFER;
        plain.pubkey_hash.fill(0xAB);
        tx.outputs[0] = plain;  // marker is gone
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T16 (closed) missing-witness rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T16 (open) missing-witness rejected by R19_HTLC_CLAIM_STRUCTURE_INVALID",
                 !r.ok && r.code == TxValCode::R19_HTLC_CLAIM_STRUCTURE_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T17: duplicate witness — two markers in outputs
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        TxOutput dup;
        dup.amount = 5000;
        dup.type = OUT_HTLC_CLAIM_WITNESS;
        dup.pubkey_hash.fill(0);
        WriteHtlcClaimWitnessPayload(dup.payload, the_preimage);
        tx.outputs.push_back(dup);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T17 (closed) duplicate-witness rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T17 (open) duplicate-witness rejected by R19_HTLC_CLAIM_STRUCTURE_INVALID",
                 !r.ok && r.code == TxValCode::R19_HTLC_CLAIM_STRUCTURE_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T18: witness not first — marker at outputs[1], transfer at [0]
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        std::swap(tx.outputs[0], tx.outputs[1]);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T18 (closed) witness-not-first rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T18 (open) witness-not-first rejected by R19_HTLC_CLAIM_STRUCTURE_INVALID",
                 !r.ok && r.code == TxValCode::R19_HTLC_CLAIM_STRUCTURE_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T19: wrong witness length — marker payload not 32 bytes
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        tx.outputs[0].payload.resize(31);  // short
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T19 (closed) bad-witness-length rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T19 (open) bad-witness-length rejected by R18_HTLC_CLAIM_WITNESS_INVALID",
                 !r.ok && r.code == TxValCode::R18_HTLC_CLAIM_WITNESS_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T20: no LOCK reference — CLAIM input points to nonexistent UTXO
    // ------------------------------------------------------------------
    {
        Hash256 missing{};
        missing.fill(0x99);
        Transaction tx = MakeClaimTx(missing, 0, the_preimage);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T20 (closed) missing-utxo CLAIM rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T20 (open) missing-utxo CLAIM rejected by S1_UTXO_NOT_FOUND",
                 !r.ok && r.code == TxValCode::S1_UTXO_NOT_FOUND);
        }
    }

    // ------------------------------------------------------------------
    // T21: CLAIM references a non-HTLC utxo (OUT_TRANSFER instead of LOCK)
    // ------------------------------------------------------------------
    {
        HtlcLockUtxoView transfer_view = htlc_view;
        transfer_view.lock_type = OUT_TRANSFER;
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        auto r = ValidateTransactionConsensus(tx, transfer_view, ctx_v14);
        if (!gate_open) {
            TEST("T21 (closed) non-LOCK ref CLAIM rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T21 (open) non-LOCK ref CLAIM rejected by R20_HTLC_CLAIM_INPUT_INVALID",
                 !r.ok && r.code == TxValCode::R20_HTLC_CLAIM_INPUT_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T22: HTLC_LOCK spent by a STANDARD-tx (non-HTLC tx_type) rejected by R20
    // ------------------------------------------------------------------
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_STANDARD;
        TxInput in;
        in.prev_txid = htlc_view.lock_txid;
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput o;
        o.amount = 80000;
        o.type = OUT_TRANSFER;
        o.pubkey_hash.fill(0xAB);
        tx.outputs.push_back(o);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            // Pre-activation: HTLC_LOCK utxos cannot exist (R11 prevented).
            // But our test stub returns one anyway. The validator would
            // either reject the LOCK type as inactive via the lookup path
            // or fall through to standard verification. Either way the
            // tx fails — we just assert it fails at all.
            TEST("T22 (closed) STANDARD tx spending LOCK rejected at all",
                 !r.ok);
        } else {
            TEST("T22 (open) STANDARD tx spending LOCK rejected by R20_HTLC_CLAIM_INPUT_INVALID",
                 !r.ok && r.code == TxValCode::R20_HTLC_CLAIM_INPUT_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T23: HTLC_REFUND spending LOCK before the timeout window. 3B-2 REFUND validation is
    //      implemented, so an early refund is now rejected by R24_HTLC_REFUND_BEFORE_TIMEOUT
    //      (spend_height < the LOCK's refund_height), superseding the old R20 placeholder.
    // ------------------------------------------------------------------
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_HTLC_REFUND;
        TxInput in;
        in.prev_txid = htlc_view.lock_txid;
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput o;
        o.amount = 80000;
        o.type = OUT_TRANSFER;
        o.pubkey_hash.fill(0xAB);
        tx.outputs.push_back(o);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T23 (closed) REFUND rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T23 (open) early REFUND rejected by R24_HTLC_REFUND_BEFORE_TIMEOUT",
                 !r.ok && r.code == TxValCode::R24_HTLC_REFUND_BEFORE_TIMEOUT);
        }
    }

    // ------------------------------------------------------------------
    // T24: extra inputs in CLAIM — rejected by R19 (post-activation)
    //      Pre-activation: R2 rejects first.
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, the_preimage);
        TxInput extra;
        extra.prev_txid.fill(0xDD);
        extra.prev_index = 7;
        extra.signature.fill(0x03);
        extra.pubkey.fill(0x04);
        tx.inputs.push_back(extra);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T24 (closed) CLAIM with extra inputs rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T24 (open) CLAIM with extra inputs rejected by R19_HTLC_CLAIM_STRUCTURE_INVALID",
                 !r.ok && r.code == TxValCode::R19_HTLC_CLAIM_STRUCTURE_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T25: normal STANDARD tx serialization unchanged (regression guard)
    //      Build a standard transfer tx; it must not be impacted by any
    //      new HTLC logic and must still fail/succeed identically to
    //      pre-patch behavior (it will fail S1 because we use stub utxos
    //      that return nullopt by default — we assert S1 is the failure).
    // ------------------------------------------------------------------
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_STANDARD;
        TxInput in;
        in.prev_txid.fill(0xEE);  // not in htlc_view
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput o;
        o.amount = 50000;
        o.type = OUT_TRANSFER;
        o.pubkey_hash.fill(0xAB);
        tx.outputs.push_back(o);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        TEST("T25 normal STANDARD tx unaffected — fails S1 as expected",
             !r.ok && r.code == TxValCode::S1_UTXO_NOT_FOUND);
    }

    // =========================================================================
    // Phase 3B-2 — HTLC_REFUND consensus rules R23-R24.
    //
    // REFUND is the timeout path. No marker, no preimage. spend_height must
    // be >= refund_height. Refund_pkh from LOCK payload [60..79] is the
    // expected pubkey hash for the input signature (overrides utxo.pubkey_hash
    // in the VerifyTransactionInput call).
    // =========================================================================

    auto MakeRefundTx = [&](const Hash256& lock_txid,
                            uint32_t lock_vout,
                            int64_t out_amount = 90000) -> Transaction {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_HTLC_REFUND;
        TxInput in;
        in.prev_txid = lock_txid;
        in.prev_index = lock_vout;
        in.signature.fill(0x01);  // bogus; signature path may fail S2/S6
        in.pubkey.fill(0x02);     // bogus
        tx.inputs.push_back(in);
        TxOutput o;
        o.amount = out_amount;
        o.type = OUT_TRANSFER;
        o.pubkey_hash.fill(0x77);  // refund destination (matches refund_pkh of htlc_view)
        tx.outputs.push_back(o);
        return tx;
    };

    // ------------------------------------------------------------------
    // T26: REFUND before timeout rejected by R24
    //      (closed: R2; open: R24 because spend_height < refund_height 30000)
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeRefundTx(htlc_view.lock_txid, 0);
        auto early_ctx = MakeCtx(MID_H);  // < refund_height
        auto r = ValidateTransactionConsensus(tx, htlc_view, early_ctx);
        if (!gate_open) {
            TEST("T26 (closed) REFUND before timeout rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T26 (open) REFUND before timeout rejected by R24_HTLC_REFUND_BEFORE_TIMEOUT",
                 !r.ok && r.code == TxValCode::R24_HTLC_REFUND_BEFORE_TIMEOUT);
        }
    }

    // ------------------------------------------------------------------
    // T27: REFUND at exactly refund_height should be accepted by R24
    //      (boundary check; the rule is spend_height >= refund_height).
    //      Pre-activation: R2 fires. Post-activation: R24 passes, the tx
    //      then fails the signature check (S2) because our test uses bogus
    //      pubkey — but at least R24 must NOT be the failing code.
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeRefundTx(htlc_view.lock_txid, 0);
        auto at_boundary_ctx = MakeCtx(REFUND_H);  // == refund_height
        auto r = ValidateTransactionConsensus(tx, htlc_view, at_boundary_ctx);
        if (!gate_open) {
            TEST("T27 (closed) REFUND at boundary rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T27 (open) REFUND at refund_height boundary does NOT trigger R24",
                 r.code != TxValCode::R24_HTLC_REFUND_BEFORE_TIMEOUT);
        }
    }

    // ------------------------------------------------------------------
    // T28: REFUND with OUT_HTLC_CLAIM_WITNESS marker rejected
    //      (R18 fires during ValidateStructure; pre-activation R2 first).
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeRefundTx(htlc_view.lock_txid, 0);
        TxOutput marker;
        marker.amount = 5000;
        marker.type = OUT_HTLC_CLAIM_WITNESS;
        marker.pubkey_hash.fill(0);
        WriteHtlcClaimWitnessPayload(marker.payload, the_preimage);
        tx.outputs.push_back(marker);
        auto late_ctx = MakeCtx(LATE_H);  // > refund_height
        auto r = ValidateTransactionConsensus(tx, htlc_view, late_ctx);
        if (!gate_open) {
            TEST("T28 (closed) REFUND with witness marker rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            // With gate open R18 fires during ValidateStructure because the
            // marker is not allowed outside a TX_TYPE_HTLC_CLAIM tx.
            TEST("T28 (open) REFUND with witness marker rejected by R18_HTLC_CLAIM_WITNESS_INVALID",
                 !r.ok && r.code == TxValCode::R18_HTLC_CLAIM_WITNESS_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T29: REFUND referencing non-HTLC utxo (OUT_TRANSFER) rejected by R20
    // ------------------------------------------------------------------
    {
        HtlcLockUtxoView transfer_view = htlc_view;
        transfer_view.lock_type = OUT_TRANSFER;
        Transaction tx = MakeRefundTx(htlc_view.lock_txid, 0);
        auto late_ctx = MakeCtx(LATE_H);
        auto r = ValidateTransactionConsensus(tx, transfer_view, late_ctx);
        if (!gate_open) {
            TEST("T29 (closed) REFUND non-LOCK ref rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T29 (open) REFUND non-LOCK ref rejected by R20_HTLC_CLAIM_INPUT_INVALID",
                 !r.ok && r.code == TxValCode::R20_HTLC_CLAIM_INPUT_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T30: REFUND with extra inputs rejected by R23
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeRefundTx(htlc_view.lock_txid, 0);
        TxInput extra;
        extra.prev_txid.fill(0xDD);
        extra.prev_index = 7;
        extra.signature.fill(0x03);
        extra.pubkey.fill(0x04);
        tx.inputs.push_back(extra);
        auto late_ctx = MakeCtx(LATE_H);
        auto r = ValidateTransactionConsensus(tx, htlc_view, late_ctx);
        if (!gate_open) {
            TEST("T30 (closed) REFUND with extra inputs rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T30 (open) REFUND with extra inputs rejected by R23_HTLC_REFUND_STRUCTURE_INVALID",
                 !r.ok && r.code == TxValCode::R23_HTLC_REFUND_STRUCTURE_INVALID);
        }
    }

    // ------------------------------------------------------------------
    // T31: REFUND with bogus refund_pkh (signature check fails)
    //      Pre-activation: R2. Post-activation: S2 (PKH mismatch) since
    //      our test uses bogus signature/pubkey that won't match.
    // ------------------------------------------------------------------
    {
        Transaction tx = MakeRefundTx(htlc_view.lock_txid, 0);
        auto late_ctx = MakeCtx(LATE_H);
        auto r = ValidateTransactionConsensus(tx, htlc_view, late_ctx);
        if (!gate_open) {
            TEST("T31 (closed) REFUND bogus pubkey rejected by R2_BAD_TX_TYPE",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            // Post-activation: R23/R24 pass; signature path fails.
            // The exact code (S2/S4/S5/S6) depends on the bogus
            // signature/pubkey shape. Assert it is one of the S-codes.
            bool is_s_code = (r.code == TxValCode::S2_PKH_MISMATCH ||
                              r.code == TxValCode::S4_ZERO_SIGNATURE ||
                              r.code == TxValCode::S5_HIGH_S ||
                              r.code == TxValCode::S6_VERIFY_FAIL);
            TEST("T31 (open) REFUND bogus pubkey rejected by S-rule", !r.ok && is_s_code);
        }
    }

    // ------------------------------------------------------------------
    // T32: CLAIM regression — wrong preimage still rejected post-REFUND
    //      (assertion mirror of T14; serves as defense against REFUND patch
    //      accidentally affecting CLAIM rule dispatch)
    // ------------------------------------------------------------------
    {
        std::array<uint8_t, 32> bad{};
        bad[0] = 0xBA;
        Transaction tx = MakeClaimTx(htlc_view.lock_txid, 0, bad);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        if (!gate_open) {
            TEST("T32 (closed) CLAIM wrong preimage still rejected by R2",
                 !r.ok && r.code == TxValCode::R2_BAD_TX_TYPE);
        } else {
            TEST("T32 (open) CLAIM wrong preimage still rejected by R21 (no drift)",
                 !r.ok && r.code == TxValCode::R21_HTLC_CLAIM_PREIMAGE_MISMATCH);
        }
    }

    // ------------------------------------------------------------------
    // T33: Normal STANDARD tx regression guard — must still fail S1
    //      identically post-REFUND patch.
    // ------------------------------------------------------------------
    {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_STANDARD;
        TxInput in;
        in.prev_txid.fill(0xEE);
        in.prev_index = 0;
        in.signature.fill(0x01);
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);
        TxOutput o;
        o.amount = 50000;
        o.type = OUT_TRANSFER;
        o.pubkey_hash.fill(0xAB);
        tx.outputs.push_back(o);
        auto r = ValidateTransactionConsensus(tx, htlc_view, ctx_v14);
        TEST("T33 (regression guard) normal STANDARD tx still fails S1",
             !r.ok && r.code == TxValCode::S1_UTXO_NOT_FOUND);
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
