#pragma once

#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include "sost/consensus_constants.h"
#include <cstdint>
#include <functional>
#include <optional>
#include <string>

namespace sost {


// Capsule activation — payload allowed in OUT_TRANSFER after this height
// Before: R14 enforces payload_len == 0 on all active types (genesis-safe)
// After:  OUT_TRANSFER may carry payload <= 255 (Capsule Protocol v1)
inline constexpr int64_t  CAPSULE_ACTIVATION_HEIGHT_MAINNET = 5000;
inline constexpr int64_t  CAPSULE_ACTIVATION_HEIGHT_TESTNET = 100;
inline constexpr int64_t  CAPSULE_ACTIVATION_HEIGHT_DEV     = 1;

// Policy constants (relay / mining preferences, not consensus-enforced)
inline constexpr int32_t  MAX_TX_BYTES_STANDARD    = 16000;
inline constexpr uint16_t MAX_INPUTS_STANDARD      = 128;
inline constexpr uint16_t MAX_OUTPUTS_STANDARD     = 32;
inline constexpr uint16_t MAX_PAYLOAD_STANDARD     = 255;  // per-type limits in capsule validator
inline constexpr uint8_t  MAX_PAYLOAD_OUTPUTS_STD  = 1;
inline constexpr int64_t  MIN_RELAY_FEE_PER_BYTE   = 1;  // stockshi/byte
inline constexpr int64_t  DUST_THRESHOLD           = 10000; // stockshis

// =============================================================================
// Outpoint — unique reference to an output
// =============================================================================

struct OutPoint {
    Hash256  txid{};
    uint32_t index{0};

    bool operator==(const OutPoint& o) const {
        return txid == o.txid && index == o.index;
    }
    bool operator<(const OutPoint& o) const {
        if (txid != o.txid) return txid < o.txid;
        return index < o.index;
    }
};

// =============================================================================
// UTXOEntry — stored data for an unspent output
// =============================================================================

struct UTXOEntry {
    int64_t  amount{0};
    uint8_t  type{0};
    PubKeyHash pubkey_hash{};
    uint8_t  payload_len{0};
    std::vector<Byte> payload;
    int64_t  height{0};        // height of the block containing this UTXO
    bool     is_coinbase{false};
};

// =============================================================================
// IUtxoView — abstract UTXO lookup interface (adapter pattern)
// =============================================================================

class IUtxoView {
public:
    virtual ~IUtxoView() = default;

    // Returns nullopt if the outpoint is not found (already spent or never existed)
    virtual std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const = 0;
};

// =============================================================================
// Validation error codes
// =============================================================================

enum class TxValCode : int {
    OK = 0,

    // Structural (R1-R14)
    R1_BAD_VERSION         = 101,
    R2_BAD_TX_TYPE         = 102,
    R3_INPUT_COUNT         = 103,
    R4_OUTPUT_COUNT        = 104,
    R5_ZERO_AMOUNT         = 105,
    R6_AMOUNT_OVERFLOW     = 106,
    R7_SUM_OVERFLOW        = 107,
    R8_DUPLICATE_INPUT     = 108,
    R9_OVERSIZE_TX         = 109,
    R10_DUPLICATE_TXID     = 110,
    R11_INACTIVE_TYPE      = 111,
    R12_PAYLOAD_MISMATCH   = 112,
    R13_PAYLOAD_TOO_LONG   = 113,
    R14_PAYLOAD_FORBIDDEN  = 114,

    // Spend / signature (S1-S12)
    S1_UTXO_NOT_FOUND      = 201,
    S2_PKH_MISMATCH        = 202,
    S3_BAD_PUBKEY          = 203,
    S4_ZERO_SIGNATURE      = 204,
    S5_HIGH_S              = 205,
    S6_VERIFY_FAIL         = 206,
    S7_INPUTS_LT_OUTPUTS   = 207,
    S8_FEE_TOO_LOW         = 208,
    S9_BAD_STD_OUTPUT_TYPE = 209,
    S10_COINBASE_IMMATURE  = 210,
    S11_BOND_LOCKED        = 211,
    S12_BURN_UNSPENDABLE   = 212,

    // Coinbase (CB1-CB10)
    CB1_MISSING_COINBASE   = 301,
    CB2_BAD_CB_INPUT       = 302,
    CB3_BAD_CB_SIG_FIELD   = 303,
    CB4_CB_OUTPUT_ORDER    = 304,
    CB5_CB_AMOUNT_MISMATCH = 305,
    CB6_CB_VAULT_MISMATCH  = 306,
    CB7_CB_OUTPUT_COUNT    = 307,
    CB8_CB_MATURITY        = 308,  // informational — enforced via S10
    CB9_CB_PUBKEY_NONZERO  = 309,
    CB10_CB_PAYLOAD        = 310,

    // Policy (not consensus-critical)
    P_TX_TOO_LARGE         = 401,
    P_TOO_MANY_INPUTS      = 402,
    P_TOO_MANY_OUTPUTS     = 403,
    P_PAYLOAD_TOO_LARGE    = 404,
    P_TOO_MANY_PAYLOADS    = 405,
    P_FEE_BELOW_RELAY      = 406,
    P_DUST_OUTPUT          = 407,
    P_BAD_CAPSULE          = 408,   // capsule header/body validation failed

    // Internal
    INTERNAL_ERROR         = 999,
};

// =============================================================================
// TxValidationResult
// =============================================================================

struct TxValidationResult {
    bool       ok{false};
    TxValCode  code{TxValCode::INTERNAL_ERROR};
    std::string message;
    int32_t    input_index{-1};    // which input failed (-1 = N/A)
    int32_t    output_index{-1};   // which output failed (-1 = N/A)

    static TxValidationResult Ok() {
        return {true, TxValCode::OK, "ok", -1, -1};
    }
    static TxValidationResult Fail(TxValCode c, const std::string& msg,
                                    int32_t in = -1, int32_t out = -1) {
        return {false, c, msg, in, out};
    }
};

// =============================================================================
// Validation context
// =============================================================================

struct TxValidationContext {
    Hash256  genesis_hash{};
    int64_t  spend_height{0};   // height of the block being validated
    int64_t  capsule_activation_height{CAPSULE_ACTIVATION_HEIGHT_MAINNET};
};

// =============================================================================
// Core validation functions
// =============================================================================

// Estimate serialized size without actually serializing (cheap upper bound).
// Uses the exact formula matching Phase 1 Serialize().
size_t EstimateTxSerializedSize(const Transaction& tx);

// Validate a STANDARD transaction against consensus rules (R1-R14, S1-S12).
// Does NOT validate coinbase transactions — use ValidateCoinbaseConsensus().
// Requires a UTXO view for input lookups and signature verification.
TxValidationResult ValidateTransactionConsensus(
    const Transaction& tx,
    const IUtxoView& utxos,
    const TxValidationContext& ctx);

// Validate a STANDARD transaction against relay/mining policy.
// Should be called AFTER ValidateTransactionConsensus passes.
// Post-capsule-activation: validates capsule structure on non-empty payloads.
TxValidationResult ValidateTransactionPolicy(
    const Transaction& tx,
    const IUtxoView& utxos,
    const TxValidationContext& ctx);

// Validate a COINBASE transaction (CB1-CB10).
// subsidy = block subsidy at this height (caller computes via sost_subsidy_stockshis)
// total_fees = sum of fees from all standard transactions in the block
// gold_vault_pkh, popc_pool_pkh = constitutional addresses
TxValidationResult ValidateCoinbaseConsensus(
    const Transaction& tx,
    int64_t height,
    int64_t subsidy,
    int64_t total_fees,
    const PubKeyHash& gold_vault_pkh,
    const PubKeyHash& popc_pool_pkh);

} // namespace sost
