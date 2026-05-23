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
    const bool gate_open = atomic_swap_htlc_active_at(15000);
    printf("  Gate is %s at height 15000 (post-activation tests %s)\n\n",
           gate_open ? "OPEN" : "CLOSED",
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
        auto ctx = MakeCtx(14999);
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
        auto ctx = MakeCtx(15000);
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
        auto ctx = MakeCtx(15000);
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
        auto ctx = MakeCtx(15000);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T5 amount < DUST rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T6: refund_height == spend_height rejected with R17
    if (!gate_open) {
        printf("  SKIP: T6 (gate closed; R17 unreachable while LOCK is inactive)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 15000, claim_pkh, refund_pkh, 100000);
        auto ctx = MakeCtx(15000);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T6 refund_height == spend_height rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T7: refund_height in past rejected with R17
    if (!gate_open) {
        printf("  SKIP: T7 (gate closed; R17 unreachable while LOCK is inactive)\n");
    } else {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 14000, claim_pkh, refund_pkh, 100000);
        auto ctx = MakeCtx(15000);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T7 refund_height in past rejected with R17",
             !r.ok && r.code == TxValCode::R17_HTLC_PAYLOAD_INVALID);
    }

    // T8: pre-activation malformed payload — R11 fires first (inactive type)
    {
        Transaction tx = MakeStdTxWithHtlcLock(hashlock, 20000, claim_pkh, refund_pkh, 100000);
        tx.outputs[0].payload.resize(5);
        auto ctx = MakeCtx(14999);
        auto r = ValidateTransactionConsensus(tx, utxos, ctx);
        TEST("T8 pre-activation malformed HTLC_LOCK rejected (R11 fires first)",
             !r.ok && r.code == TxValCode::R11_INACTIVE_TYPE);
    }

    // T9: gate helper boundaries
    {
        constexpr int64_t H = ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;
        bool at_zero          = atomic_swap_htlc_active_at(0);
        bool at_v13           = atomic_swap_htlc_active_at(12000);
        bool at_H             = atomic_swap_htlc_active_at(H);
        TEST("T9a active_at(0) == false",          !at_zero);
        TEST("T9b active_at(V13=12000) == false",  !at_v13);
        TEST("T9c active_at(H) == true",            at_H);
        if (H > 0 && H != INT64_MAX) {
            bool at_just_below_H = atomic_swap_htlc_active_at(H - 1);
            TEST("T9d active_at(H-1) == false",    !at_just_below_H);
        }
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
