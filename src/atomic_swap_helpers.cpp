// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// Phase 3C — gated wallet/RPC helpers for atomic swap HTLC. See
// include/sost/atomic_swap_helpers.h for the API contract and the
// hard invariants every helper enforces.

#include "sost/atomic_swap_helpers.h"
#include "sost/atomic_swap.h"
#include "sost/consensus_constants.h"
#include <climits>

namespace sost {
namespace atomic_swap {

bool IsAtomicSwapHtlcEnabled() {
    return ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT != INT64_MAX;
}

// ---------------------------------------------------------------------------
// Internal unchecked builders
// ---------------------------------------------------------------------------

Transaction BuildHtlcLockTx_Unchecked(
    const Hash256& prev_txid,
    uint32_t prev_vout,
    int64_t prev_amount,
    const std::array<uint8_t, 20>& prev_pkh,
    const std::array<uint8_t, 32>& hashlock,
    uint64_t refund_height,
    const std::array<uint8_t, 20>& claim_pkh,
    const std::array<uint8_t, 20>& refund_pkh,
    int64_t lock_amount,
    int64_t fee)
{
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev_txid;
    in.prev_index = prev_vout;
    // signature + pubkey left zero — caller signs before broadcast.
    tx.inputs.push_back(in);

    // HTLC_LOCK output
    TxOutput lock_out;
    lock_out.amount = lock_amount;
    lock_out.type = OUT_HTLC_LOCK;
    lock_out.pubkey_hash.fill(0);  // LOCK pkh is unused (claim_pkh/refund_pkh in payload)
    WriteHtlcLockPayload(lock_out.payload, hashlock, refund_height, claim_pkh, refund_pkh);
    tx.outputs.push_back(lock_out);

    // Change output back to prev_pkh if there is any change
    int64_t change = prev_amount - lock_amount - fee;
    if (change > 0) {
        TxOutput change_out;
        change_out.amount = change;
        change_out.type = OUT_TRANSFER;
        change_out.pubkey_hash = prev_pkh;
        tx.outputs.push_back(change_out);
    }
    return tx;
}

Transaction BuildHtlcClaimTx_Unchecked(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 32>& preimage,
    const std::array<uint8_t, 20>& claim_destination_pkh,
    int64_t marker_dust_amount,
    int64_t fee)
{
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_HTLC_CLAIM;

    TxInput in;
    in.prev_txid = lock_txid;
    in.prev_index = lock_vout;
    // caller signs.
    tx.inputs.push_back(in);

    // Witness marker output (output[0] — required by R19)
    TxOutput marker;
    marker.amount = marker_dust_amount;
    marker.type = OUT_HTLC_CLAIM_WITNESS;
    marker.pubkey_hash = claim_destination_pkh;  // marker dust returns to claimant
    WriteHtlcClaimWitnessPayload(marker.payload, preimage);
    tx.outputs.push_back(marker);

    // Real destination transfer
    int64_t transfer_amount = lock_amount - marker_dust_amount - fee;
    if (transfer_amount > 0) {
        TxOutput dest;
        dest.amount = transfer_amount;
        dest.type = OUT_TRANSFER;
        dest.pubkey_hash = claim_destination_pkh;
        tx.outputs.push_back(dest);
    }
    return tx;
}

Transaction BuildHtlcRefundTx_Unchecked(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 20>& refund_destination_pkh,
    int64_t fee)
{
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_HTLC_REFUND;

    TxInput in;
    in.prev_txid = lock_txid;
    in.prev_index = lock_vout;
    tx.inputs.push_back(in);

    TxOutput dest;
    dest.amount = lock_amount - fee;
    dest.type = OUT_TRANSFER;
    dest.pubkey_hash = refund_destination_pkh;
    tx.outputs.push_back(dest);
    return tx;
}

// ---------------------------------------------------------------------------
// Gated public builders
// ---------------------------------------------------------------------------

HtlcResult BuildHtlcLockTx(
    const Hash256& prev_txid,
    uint32_t prev_vout,
    int64_t prev_amount,
    const std::array<uint8_t, 20>& prev_pkh,
    const std::array<uint8_t, 32>& hashlock,
    uint64_t refund_height,
    const std::array<uint8_t, 20>& claim_pkh,
    const std::array<uint8_t, 20>& refund_pkh,
    int64_t lock_amount,
    int64_t fee)
{
    HtlcResult r;
    if (!IsAtomicSwapHtlcEnabled()) {
        r.ok = false;
        r.error = DisabledErrorMessage();
        return r;
    }
    if (lock_amount < DUST_THRESHOLD) {
        r.ok = false;
        r.error = "lock_amount below DUST_THRESHOLD";
        return r;
    }
    if (fee < 0) {
        r.ok = false;
        r.error = "fee must be >= 0";
        return r;
    }
    if (prev_amount < lock_amount + fee) {
        r.ok = false;
        r.error = "prev_amount insufficient to cover lock_amount + fee";
        return r;
    }
    r.tx = BuildHtlcLockTx_Unchecked(prev_txid, prev_vout, prev_amount,
                                      prev_pkh, hashlock, refund_height,
                                      claim_pkh, refund_pkh, lock_amount, fee);
    r.ok = true;
    return r;
}

HtlcResult BuildHtlcClaimTx(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 32>& preimage,
    const std::array<uint8_t, 20>& claim_destination_pkh,
    int64_t marker_dust_amount,
    int64_t fee)
{
    HtlcResult r;
    if (!IsAtomicSwapHtlcEnabled()) {
        r.ok = false;
        r.error = DisabledErrorMessage();
        return r;
    }
    if (marker_dust_amount < DUST_THRESHOLD) {
        r.ok = false;
        r.error = "marker_dust_amount must be >= DUST_THRESHOLD";
        return r;
    }
    if (fee < 0) {
        r.ok = false;
        r.error = "fee must be >= 0";
        return r;
    }
    if (lock_amount < marker_dust_amount + fee) {
        r.ok = false;
        r.error = "lock_amount insufficient for marker_dust + fee";
        return r;
    }
    r.tx = BuildHtlcClaimTx_Unchecked(lock_txid, lock_vout, lock_amount,
                                       preimage, claim_destination_pkh,
                                       marker_dust_amount, fee);
    r.ok = true;
    return r;
}

HtlcResult BuildHtlcRefundTx(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 20>& refund_destination_pkh,
    int64_t fee)
{
    HtlcResult r;
    if (!IsAtomicSwapHtlcEnabled()) {
        r.ok = false;
        r.error = DisabledErrorMessage();
        return r;
    }
    if (fee < 0) {
        r.ok = false;
        r.error = "fee must be >= 0";
        return r;
    }
    if (lock_amount <= fee) {
        r.ok = false;
        r.error = "lock_amount must exceed fee";
        return r;
    }
    r.tx = BuildHtlcRefundTx_Unchecked(lock_txid, lock_vout, lock_amount,
                                        refund_destination_pkh, fee);
    r.ok = true;
    return r;
}

// ---------------------------------------------------------------------------
// Decoder
// ---------------------------------------------------------------------------

HtlcResult DecodeHtlc(const Transaction& tx, DecodedHtlc& out) {
    HtlcResult r;
    if (!IsAtomicSwapHtlcEnabled()) {
        r.ok = false;
        r.error = DisabledErrorMessage();
        return r;
    }
    out.kind = DecodedHtlc::NONE;

    // STANDARD tx with a single HTLC_LOCK output -> LOCK
    if (tx.tx_type == TX_TYPE_STANDARD) {
        for (const auto& o : tx.outputs) {
            if (o.type == OUT_HTLC_LOCK) {
                if (o.payload.size() != HTLC_LOCK_PAYLOAD_LEN) {
                    r.ok = false;
                    r.error = "HTLC_LOCK output has wrong payload length";
                    return r;
                }
                out.kind = DecodedHtlc::LOCK;
                out.lock.amount = o.amount;
                out.lock.hashlock = ReadHtlcHashlock(o.payload);
                out.lock.refund_height = ReadHtlcRefundHeight(o.payload);
                out.lock.claim_pkh = ReadHtlcClaimPkh(o.payload);
                out.lock.refund_pkh = ReadHtlcRefundPkh(o.payload);
                r.ok = true;
                return r;
            }
        }
        r.ok = false;
        r.error = "STANDARD tx contains no HTLC_LOCK output";
        return r;
    }

    if (tx.tx_type == TX_TYPE_HTLC_CLAIM) {
        if (tx.inputs.empty() || tx.outputs.empty() ||
            tx.outputs[0].type != OUT_HTLC_CLAIM_WITNESS ||
            tx.outputs[0].payload.size() != HTLC_CLAIM_WITNESS_PAYLOAD_LEN) {
            r.ok = false;
            r.error = "malformed HTLC_CLAIM tx (missing/invalid marker)";
            return r;
        }
        out.kind = DecodedHtlc::CLAIM;
        out.claim.lock_txid = tx.inputs[0].prev_txid;
        out.claim.lock_vout = tx.inputs[0].prev_index;
        out.claim.preimage = ReadHtlcPreimage(tx.outputs[0].payload);
        r.ok = true;
        return r;
    }

    if (tx.tx_type == TX_TYPE_HTLC_REFUND) {
        if (tx.inputs.empty()) {
            r.ok = false;
            r.error = "malformed HTLC_REFUND tx (no inputs)";
            return r;
        }
        out.kind = DecodedHtlc::REFUND;
        out.refund.lock_txid = tx.inputs[0].prev_txid;
        out.refund.lock_vout = tx.inputs[0].prev_index;
        r.ok = true;
        return r;
    }

    r.ok = false;
    r.error = "tx_type is not HTLC-related";
    return r;
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

HtlcStatus GetHtlcStatus(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t current_height,
    const IUtxoView& utxos)
{
    if (!IsAtomicSwapHtlcEnabled()) {
        // Gate closed — refuse to answer.
        return HtlcStatus::Unknown;
    }
    OutPoint op{lock_txid, lock_vout};
    auto utxo_opt = utxos.GetUTXO(op);
    if (!utxo_opt.has_value()) {
        // UTXO not in current set. Could be Spent (claimed or refunded)
        // or have never existed. Without chain history we cannot
        // distinguish; report Spent as the conservative finalised state.
        return HtlcStatus::Spent;
    }
    const auto& utxo = utxo_opt.value();
    if (utxo.type != OUT_HTLC_LOCK) {
        return HtlcStatus::Unknown;
    }
    if (utxo.payload.size() != HTLC_LOCK_PAYLOAD_LEN) {
        return HtlcStatus::Unknown;
    }
    uint64_t refund_height = ReadHtlcRefundHeight(utxo.payload);
    if ((uint64_t)current_height < refund_height) {
        return HtlcStatus::LockedClaimable;
    }
    return HtlcStatus::LockedRefundable;
}

} // namespace atomic_swap
} // namespace sost
