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

// ---------------------------------------------------------------------------
// Phase 3C-1: RPC layer helpers
// ---------------------------------------------------------------------------

namespace {

// Pure ASCII hex -> bytes. Returns false on any invalid char or odd length.
bool decode_hex_n(const std::string& hex, size_t expected_bytes,
                  std::vector<uint8_t>& out)
{
    if (hex.size() != expected_bytes * 2) return false;
    out.assign(expected_bytes, 0);
    auto nib = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
        if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
        return -1;
    };
    for (size_t i = 0; i < expected_bytes; ++i) {
        int hi = nib(hex[2 * i]);
        int lo = nib(hex[2 * i + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}

bool decode_hex_any(const std::string& hex, std::vector<uint8_t>& out) {
    if (hex.size() % 2 != 0) return false;
    out.assign(hex.size() / 2, 0);
    auto nib = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
        if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
        return -1;
    };
    for (size_t i = 0; i < out.size(); ++i) {
        int hi = nib(hex[2 * i]);
        int lo = nib(hex[2 * i + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}

bool parse_int64(const std::string& s, int64_t& out) {
    if (s.empty()) return false;
    size_t i = 0;
    bool neg = false;
    if (s[0] == '-') { neg = true; i = 1; if (i == s.size()) return false; }
    int64_t v = 0;
    for (; i < s.size(); ++i) {
        if (s[i] < '0' || s[i] > '9') return false;
        int64_t d = s[i] - '0';
        if (v > (INT64_MAX - d) / 10) return false;  // overflow guard
        v = v * 10 + d;
    }
    out = neg ? -v : v;
    return true;
}

bool parse_uint32(const std::string& s, uint32_t& out) {
    int64_t v = 0;
    if (!parse_int64(s, v)) return false;
    if (v < 0 || v > (int64_t)UINT32_MAX) return false;
    out = static_cast<uint32_t>(v);
    return true;
}

std::string to_hex_lower(const uint8_t* data, size_t n) {
    std::string s; s.reserve(n * 2);
    static const char* HEX = "0123456789abcdef";
    for (size_t i = 0; i < n; ++i) {
        s.push_back(HEX[(data[i] >> 4) & 0xF]);
        s.push_back(HEX[data[i] & 0xF]);
    }
    return s;
}

template <size_t N>
std::array<uint8_t, N> to_arr(const std::vector<uint8_t>& v) {
    std::array<uint8_t, N> a{};
    for (size_t i = 0; i < N && i < v.size(); ++i) a[i] = v[i];
    return a;
}

HtlcRpcResult disabled_result() {
    HtlcRpcResult r;
    r.ok = false;
    r.error_code = -32603;
    r.body = DisabledErrorMessage();
    return r;
}

HtlcRpcResult invalid_params(const std::string& msg) {
    HtlcRpcResult r;
    r.ok = false;
    r.error_code = -32602;  // JSON-RPC invalid params
    r.body = msg;
    return r;
}

HtlcRpcResult internal_error(const std::string& msg) {
    HtlcRpcResult r;
    r.ok = false;
    r.error_code = -32603;
    r.body = msg;
    return r;
}

} // namespace

HtlcRpcResult HandleCreateHtlcLockRpc(const std::vector<std::string>& params) {
    if (!IsAtomicSwapHtlcEnabled()) return disabled_result();
    if (params.size() < 10) return invalid_params("createhtlclock: expected 10 positional params");

    std::vector<uint8_t> prev_txid_bytes, prev_pkh_bytes, hashlock_bytes,
                         claim_pkh_bytes, refund_pkh_bytes;
    if (!decode_hex_n(params[0], 32, prev_txid_bytes))
        return invalid_params("createhtlclock: prev_txid must be 64 hex chars");
    uint32_t prev_vout = 0;
    if (!parse_uint32(params[1], prev_vout))
        return invalid_params("createhtlclock: prev_vout must be uint32");
    int64_t prev_amount = 0;
    if (!parse_int64(params[2], prev_amount) || prev_amount < 0)
        return invalid_params("createhtlclock: prev_amount must be non-negative int64");
    if (!decode_hex_n(params[3], 20, prev_pkh_bytes))
        return invalid_params("createhtlclock: prev_pkh must be 40 hex chars");
    if (!decode_hex_n(params[4], 32, hashlock_bytes))
        return invalid_params("createhtlclock: hashlock must be 64 hex chars");
    int64_t refund_height_i = 0;
    if (!parse_int64(params[5], refund_height_i) || refund_height_i < 0)
        return invalid_params("createhtlclock: refund_height must be non-negative int64");
    if (!decode_hex_n(params[6], 20, claim_pkh_bytes))
        return invalid_params("createhtlclock: claim_pkh must be 40 hex chars");
    if (!decode_hex_n(params[7], 20, refund_pkh_bytes))
        return invalid_params("createhtlclock: refund_pkh must be 40 hex chars");
    int64_t lock_amount = 0;
    if (!parse_int64(params[8], lock_amount) || lock_amount < 0)
        return invalid_params("createhtlclock: lock_amount must be non-negative int64");
    int64_t fee = 0;
    if (!parse_int64(params[9], fee) || fee < 0)
        return invalid_params("createhtlclock: fee must be non-negative int64");

    Hash256 prev_txid{};
    for (size_t i = 0; i < 32; ++i) prev_txid[i] = prev_txid_bytes[i];

    HtlcResult br = BuildHtlcLockTx(prev_txid, prev_vout, prev_amount,
                                     to_arr<20>(prev_pkh_bytes),
                                     to_arr<32>(hashlock_bytes),
                                     (uint64_t)refund_height_i,
                                     to_arr<20>(claim_pkh_bytes),
                                     to_arr<20>(refund_pkh_bytes),
                                     lock_amount, fee);
    if (!br.ok) return internal_error("createhtlclock: " + br.error);

    std::vector<uint8_t> raw;
    std::string err;
    if (!br.tx.Serialize(raw, &err))
        return internal_error("createhtlclock serialize: " + err);

    HtlcRpcResult ok;
    ok.ok = true;
    ok.body = "{\"raw_tx_hex\":\"" + to_hex_lower(raw.data(), raw.size()) +
              "\",\"unsigned\":true}";
    return ok;
}

HtlcRpcResult HandleClaimHtlcRpc(const std::vector<std::string>& params) {
    if (!IsAtomicSwapHtlcEnabled()) return disabled_result();
    if (params.size() < 7) return invalid_params("claimhtlc: expected 7 positional params");

    std::vector<uint8_t> lock_txid_bytes, preimage_bytes, dest_pkh_bytes;
    if (!decode_hex_n(params[0], 32, lock_txid_bytes))
        return invalid_params("claimhtlc: lock_txid must be 64 hex chars");
    uint32_t lock_vout = 0;
    if (!parse_uint32(params[1], lock_vout))
        return invalid_params("claimhtlc: lock_vout must be uint32");
    int64_t lock_amount = 0;
    if (!parse_int64(params[2], lock_amount) || lock_amount < 0)
        return invalid_params("claimhtlc: lock_amount must be non-negative int64");
    if (!decode_hex_n(params[3], 32, preimage_bytes))
        return invalid_params("claimhtlc: preimage must be 64 hex chars (32 bytes)");
    if (!decode_hex_n(params[4], 20, dest_pkh_bytes))
        return invalid_params("claimhtlc: claim_destination_pkh must be 40 hex chars");
    int64_t marker = 0;
    if (!parse_int64(params[5], marker) || marker < 0)
        return invalid_params("claimhtlc: marker_dust_amount must be non-negative int64");
    int64_t fee = 0;
    if (!parse_int64(params[6], fee) || fee < 0)
        return invalid_params("claimhtlc: fee must be non-negative int64");

    Hash256 lock_txid{};
    for (size_t i = 0; i < 32; ++i) lock_txid[i] = lock_txid_bytes[i];

    HtlcResult br = BuildHtlcClaimTx(lock_txid, lock_vout, lock_amount,
                                      to_arr<32>(preimage_bytes),
                                      to_arr<20>(dest_pkh_bytes), marker, fee);
    if (!br.ok) return internal_error("claimhtlc: " + br.error);

    std::vector<uint8_t> raw;
    std::string err;
    if (!br.tx.Serialize(raw, &err))
        return internal_error("claimhtlc serialize: " + err);

    HtlcRpcResult ok;
    ok.ok = true;
    ok.body = "{\"raw_tx_hex\":\"" + to_hex_lower(raw.data(), raw.size()) +
              "\",\"unsigned\":true}";
    return ok;
}

HtlcRpcResult HandleRefundHtlcRpc(const std::vector<std::string>& params) {
    if (!IsAtomicSwapHtlcEnabled()) return disabled_result();
    if (params.size() < 5) return invalid_params("refundhtlc: expected 5 positional params");

    std::vector<uint8_t> lock_txid_bytes, dest_pkh_bytes;
    if (!decode_hex_n(params[0], 32, lock_txid_bytes))
        return invalid_params("refundhtlc: lock_txid must be 64 hex chars");
    uint32_t lock_vout = 0;
    if (!parse_uint32(params[1], lock_vout))
        return invalid_params("refundhtlc: lock_vout must be uint32");
    int64_t lock_amount = 0;
    if (!parse_int64(params[2], lock_amount) || lock_amount < 0)
        return invalid_params("refundhtlc: lock_amount must be non-negative int64");
    if (!decode_hex_n(params[3], 20, dest_pkh_bytes))
        return invalid_params("refundhtlc: refund_destination_pkh must be 40 hex chars");
    int64_t fee = 0;
    if (!parse_int64(params[4], fee) || fee < 0)
        return invalid_params("refundhtlc: fee must be non-negative int64");

    Hash256 lock_txid{};
    for (size_t i = 0; i < 32; ++i) lock_txid[i] = lock_txid_bytes[i];

    HtlcResult br = BuildHtlcRefundTx(lock_txid, lock_vout, lock_amount,
                                       to_arr<20>(dest_pkh_bytes), fee);
    if (!br.ok) return internal_error("refundhtlc: " + br.error);

    std::vector<uint8_t> raw;
    std::string err;
    if (!br.tx.Serialize(raw, &err))
        return internal_error("refundhtlc serialize: " + err);

    HtlcRpcResult ok;
    ok.ok = true;
    ok.body = "{\"raw_tx_hex\":\"" + to_hex_lower(raw.data(), raw.size()) +
              "\",\"unsigned\":true}";
    return ok;
}

HtlcRpcResult HandleDecodeHtlcRpc(const std::vector<std::string>& params) {
    if (!IsAtomicSwapHtlcEnabled()) return disabled_result();
    if (params.empty()) return invalid_params("decodehtlc: expected 1 param (raw_tx_hex)");

    std::vector<uint8_t> raw;
    if (!decode_hex_any(params[0], raw))
        return invalid_params("decodehtlc: raw_tx_hex is not valid hex");

    Transaction tx;
    std::string err;
    if (!Transaction::Deserialize(raw, tx, &err))
        return invalid_params("decodehtlc: tx deserialize failed: " + err);

    DecodedHtlc out;
    HtlcResult dr = DecodeHtlc(tx, out);
    if (!dr.ok) return internal_error("decodehtlc: " + dr.error);

    std::string body;
    if (out.kind == DecodedHtlc::LOCK) {
        body = "{\"kind\":\"LOCK\",\"amount\":" + std::to_string(out.lock.amount) +
               ",\"hashlock\":\"" + to_hex_lower(out.lock.hashlock.data(), 32) + "\"" +
               ",\"refund_height\":" + std::to_string(out.lock.refund_height) +
               ",\"claim_pkh\":\"" + to_hex_lower(out.lock.claim_pkh.data(), 20) + "\"" +
               ",\"refund_pkh\":\"" + to_hex_lower(out.lock.refund_pkh.data(), 20) + "\"}";
    } else if (out.kind == DecodedHtlc::CLAIM) {
        body = "{\"kind\":\"CLAIM\",\"lock_txid\":\"" +
               to_hex_lower(out.claim.lock_txid.data(), 32) + "\"" +
               ",\"lock_vout\":" + std::to_string(out.claim.lock_vout) +
               ",\"preimage\":\"" + to_hex_lower(out.claim.preimage.data(), 32) + "\"}";
    } else if (out.kind == DecodedHtlc::REFUND) {
        body = "{\"kind\":\"REFUND\",\"lock_txid\":\"" +
               to_hex_lower(out.refund.lock_txid.data(), 32) + "\"" +
               ",\"lock_vout\":" + std::to_string(out.refund.lock_vout) + "}";
    } else {
        return internal_error("decodehtlc: unrecognised HTLC kind");
    }

    HtlcRpcResult ok;
    ok.ok = true;
    ok.body = body;
    return ok;
}

HtlcRpcResult HandleGetHtlcStatusRpc(
    const std::vector<std::string>& params,
    int64_t current_height,
    const IUtxoView& utxos)
{
    if (!IsAtomicSwapHtlcEnabled()) return disabled_result();
    if (params.size() < 2) return invalid_params("gethtlcstatus: expected 2 params (lock_txid, lock_vout)");

    std::vector<uint8_t> lock_txid_bytes;
    if (!decode_hex_n(params[0], 32, lock_txid_bytes))
        return invalid_params("gethtlcstatus: lock_txid must be 64 hex chars");
    uint32_t lock_vout = 0;
    if (!parse_uint32(params[1], lock_vout))
        return invalid_params("gethtlcstatus: lock_vout must be uint32");

    Hash256 lock_txid{};
    for (size_t i = 0; i < 32; ++i) lock_txid[i] = lock_txid_bytes[i];

    HtlcStatus s = GetHtlcStatus(lock_txid, lock_vout, current_height, utxos);
    const char* status_str = "Unknown";
    switch (s) {
        case HtlcStatus::Unknown:          status_str = "Unknown"; break;
        case HtlcStatus::LockedClaimable:  status_str = "LockedClaimable"; break;
        case HtlcStatus::LockedRefundable: status_str = "LockedRefundable"; break;
        case HtlcStatus::Spent:            status_str = "Spent"; break;
    }

    HtlcRpcResult ok;
    ok.ok = true;
    ok.body = std::string("{\"status\":\"") + status_str + "\"}";
    return ok;
}

} // namespace atomic_swap
} // namespace sost
