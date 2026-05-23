// Phase 3C — gated wallet/RPC helpers for atomic swap HTLC.
//
// Tests target the internal C++ API in include/sost/atomic_swap_helpers.h.
// With the gate at INT64_MAX (current state) every gated helper returns
// an error with the disabled-message; the unchecked builders construct
// valid transactions; the decoder rejects with the disabled-message;
// GetHtlcStatus returns Unknown.

#include "sost/atomic_swap_helpers.h"
#include "sost/atomic_swap.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/consensus_constants.h"

#include <cstdio>
#include <climits>
#include <optional>

using namespace sost;
using namespace sost::atomic_swap;

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

int main() {
    printf("\n== Atomic Swap HTLC Phase 3C — wallet/RPC helpers ==\n\n");
    printf("  Gate state: ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = %lld\n",
           (long long)ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT);
    const bool enabled = IsAtomicSwapHtlcEnabled();
    printf("  IsAtomicSwapHtlcEnabled() = %s\n\n", enabled ? "true" : "false");

    Hash256 fake_txid{};
    fake_txid.fill(0xAA);
    std::array<uint8_t, 32> hashlock{};
    for (size_t k = 0; k < hashlock.size(); ++k) hashlock[k] = static_cast<uint8_t>(0x10 + k);
    std::array<uint8_t, 20> prev_pkh{};
    prev_pkh.fill(0x33);
    std::array<uint8_t, 20> claim_pkh{};
    claim_pkh.fill(0x55);
    std::array<uint8_t, 20> refund_pkh{};
    refund_pkh.fill(0x77);
    std::array<uint8_t, 32> preimage{};
    for (size_t k = 0; k < preimage.size(); ++k) preimage[k] = static_cast<uint8_t>(0xA0 + k);

    // -----------------------------------------------------------------------
    // T1. IsAtomicSwapHtlcEnabled() reflects the constant.
    // -----------------------------------------------------------------------
    TEST("T1 IsAtomicSwapHtlcEnabled() == (gate != INT64_MAX)",
         enabled == (ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT != INT64_MAX));

    // -----------------------------------------------------------------------
    // T2. BuildHtlcLockTx refuses while gate INT64_MAX.
    // -----------------------------------------------------------------------
    {
        auto r = BuildHtlcLockTx(fake_txid, 0, 200000, prev_pkh, hashlock,
                                  /*refund_height=*/30000, claim_pkh, refund_pkh,
                                  /*lock_amount=*/100000, /*fee=*/2000);
        if (!enabled) {
            TEST("T2 BuildHtlcLockTx refuses while gate closed",
                 !r.ok && r.error.find("disabled until protocol activation") != std::string::npos);
        } else {
            TEST("T2 BuildHtlcLockTx accepts valid params when gate open", r.ok);
        }
    }

    // -----------------------------------------------------------------------
    // T3. BuildHtlcClaimTx refuses while gate INT64_MAX.
    // -----------------------------------------------------------------------
    {
        auto r = BuildHtlcClaimTx(fake_txid, 0, /*lock_amount=*/100000,
                                   preimage, claim_pkh,
                                   /*marker_dust=*/10000, /*fee=*/2000);
        if (!enabled) {
            TEST("T3 BuildHtlcClaimTx refuses while gate closed",
                 !r.ok && r.error.find("disabled until protocol activation") != std::string::npos);
        } else {
            TEST("T3 BuildHtlcClaimTx accepts valid params when gate open", r.ok);
        }
    }

    // -----------------------------------------------------------------------
    // T4. BuildHtlcRefundTx refuses while gate INT64_MAX.
    // -----------------------------------------------------------------------
    {
        auto r = BuildHtlcRefundTx(fake_txid, 0, /*lock_amount=*/100000,
                                    refund_pkh, /*fee=*/2000);
        if (!enabled) {
            TEST("T4 BuildHtlcRefundTx refuses while gate closed",
                 !r.ok && r.error.find("disabled until protocol activation") != std::string::npos);
        } else {
            TEST("T4 BuildHtlcRefundTx accepts valid params when gate open", r.ok);
        }
    }

    // -----------------------------------------------------------------------
    // T5. Unchecked LOCK builder constructs a valid-shape tx regardless of gate.
    // -----------------------------------------------------------------------
    {
        Transaction tx = BuildHtlcLockTx_Unchecked(fake_txid, 0, 200000, prev_pkh,
                                                    hashlock, 30000, claim_pkh, refund_pkh,
                                                    100000, 2000);
        TEST("T5a LOCK tx_type STANDARD", tx.tx_type == TX_TYPE_STANDARD);
        TEST("T5b LOCK has 1 input", tx.inputs.size() == 1);
        TEST("T5c LOCK has 2 outputs (LOCK + change)", tx.outputs.size() == 2);
        TEST("T5d LOCK output type OUT_HTLC_LOCK", tx.outputs[0].type == OUT_HTLC_LOCK);
        TEST("T5e LOCK output payload size 80", tx.outputs[0].payload.size() == HTLC_LOCK_PAYLOAD_LEN);
    }

    // -----------------------------------------------------------------------
    // T6. Unchecked CLAIM builder produces a valid-shape CLAIM tx.
    // -----------------------------------------------------------------------
    {
        Transaction tx = BuildHtlcClaimTx_Unchecked(fake_txid, 0, 100000, preimage,
                                                     claim_pkh, 10000, 2000);
        TEST("T6a CLAIM tx_type HTLC_CLAIM", tx.tx_type == TX_TYPE_HTLC_CLAIM);
        TEST("T6b CLAIM has 1 input", tx.inputs.size() == 1);
        TEST("T6c CLAIM has 2 outputs (marker + transfer)", tx.outputs.size() == 2);
        TEST("T6d CLAIM first output is marker", tx.outputs[0].type == OUT_HTLC_CLAIM_WITNESS);
        TEST("T6e CLAIM marker payload size 32", tx.outputs[0].payload.size() == HTLC_CLAIM_WITNESS_PAYLOAD_LEN);
        TEST("T6f CLAIM preimage roundtrip", ReadHtlcPreimage(tx.outputs[0].payload) == preimage);
    }

    // -----------------------------------------------------------------------
    // T7. Unchecked REFUND builder produces a valid-shape REFUND tx.
    // -----------------------------------------------------------------------
    {
        Transaction tx = BuildHtlcRefundTx_Unchecked(fake_txid, 0, 100000, refund_pkh, 2000);
        TEST("T7a REFUND tx_type HTLC_REFUND", tx.tx_type == TX_TYPE_HTLC_REFUND);
        TEST("T7b REFUND has 1 input", tx.inputs.size() == 1);
        TEST("T7c REFUND has 1 output", tx.outputs.size() == 1);
        TEST("T7d REFUND output is OUT_TRANSFER", tx.outputs[0].type == OUT_TRANSFER);
        TEST("T7e REFUND has no OUT_HTLC_CLAIM_WITNESS marker",
             tx.outputs[0].type != OUT_HTLC_CLAIM_WITNESS);
    }

    // -----------------------------------------------------------------------
    // T8. DecodeHtlc refuses while gate INT64_MAX; accepts when open.
    // -----------------------------------------------------------------------
    {
        Transaction tx = BuildHtlcLockTx_Unchecked(fake_txid, 0, 200000, prev_pkh,
                                                    hashlock, 30000, claim_pkh, refund_pkh,
                                                    100000, 2000);
        DecodedHtlc out;
        auto r = DecodeHtlc(tx, out);
        if (!enabled) {
            TEST("T8 DecodeHtlc refuses while gate closed",
                 !r.ok && r.error.find("disabled until protocol activation") != std::string::npos);
        } else {
            TEST("T8 DecodeHtlc(LOCK tx) reports kind=LOCK",
                 r.ok && out.kind == DecodedHtlc::LOCK &&
                 out.lock.hashlock == hashlock &&
                 out.lock.refund_height == 30000 &&
                 out.lock.claim_pkh == claim_pkh &&
                 out.lock.refund_pkh == refund_pkh);
        }
    }

    // -----------------------------------------------------------------------
    // T9. GetHtlcStatus on an unknown outpoint reports Spent (utxo not present);
    //     gate-closed always reports Unknown.
    // -----------------------------------------------------------------------
    {
        StubUtxoView empty_view;
        Hash256 unknown_txid{};
        unknown_txid.fill(0xCC);
        HtlcStatus s = GetHtlcStatus(unknown_txid, 0, 20000, empty_view);
        if (!enabled) {
            TEST("T9 GetHtlcStatus returns Unknown while gate closed",
                 s == HtlcStatus::Unknown);
        } else {
            TEST("T9 GetHtlcStatus on unknown outpoint returns Spent",
                 s == HtlcStatus::Spent);
        }
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
