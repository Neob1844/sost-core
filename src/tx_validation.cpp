// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// tx_validation.cpp — SOST Transaction Validation (Phase 3)
// Design v1.2a Section 7 — Consensus rules R1-R14, S1-S12, CB1-CB10
// =============================================================================

#include "sost/tx_validation.h"
#include "sost/capsule.h"
#include "sost/lottery.h"   // V11 Phase 2 (C8) — phase2_coinbase_split

#include <algorithm>
#include <climits>
#include <cstring>
#include <set>
#include <sstream>
#include <iomanip>

namespace sost {

// =============================================================================
// Helpers
// =============================================================================

// Active output types — types valid for consensus acceptance.
// BOND_LOCK and ESCROW_LOCK are active only after bond_activation_height.
static bool IsActiveOutputType(uint8_t type, int64_t height, int64_t bond_activation_height) {
    if (type == OUT_TRANSFER ||
        type == OUT_COINBASE_MINER ||
        type == OUT_COINBASE_GOLD ||
        type == OUT_COINBASE_POPC)
        return true;
    if ((type == OUT_BOND_LOCK || type == OUT_ESCROW_LOCK) &&
        height >= bond_activation_height)
        return true;
    return false;
}

// CompactSize encoded length (matching Phase 1 WriteCompactSize)
static size_t CompactSizeLen(uint64_t n) {
    if (n < 0xFD) return 1;
    if (n <= 0xFFFF) return 3;
    if (n <= 0xFFFFFFFFULL) return 5;
    return 9;
}

static bool IsAllZeros(const uint8_t* data, size_t len) {
    for (size_t i = 0; i < len; ++i)
        if (data[i] != 0) return false;
    return true;
}

static std::string HexU32(uint32_t v) {
    std::ostringstream oss;
    oss << std::hex << std::setw(8) << std::setfill('0') << (uint64_t)v;
    return oss.str();
}

// =============================================================================
// EstimateTxSerializedSize
// =============================================================================
// Matches Phase 1 serialization format exactly:
//   version(4) + tx_type(1) + CompactSize(nin) + inputs + CompactSize(nout) + outputs
// Input: prev_txid(32) + prev_index(4) + signature(64) + pubkey(33) = 133
// Output: amount(8) + type(1) + pubkey_hash(20) + payload_len(2) + payload(N)

size_t EstimateTxSerializedSize(const Transaction& tx) {
    size_t size = 0;
    size += 4;  // version
    size += 1;  // tx_type
    size += CompactSizeLen(tx.inputs.size());
    size += tx.inputs.size() * 133;  // fixed per input
    size += CompactSizeLen(tx.outputs.size());
    for (const auto& out : tx.outputs) {
        size += 8;   // amount
        size += 1;   // type
        size += 20;  // pubkey_hash
        size += 2;   // payload_len (uint16 LE)
        size += out.payload.size();
    }
    return size;
}

// =============================================================================
// Structural validation (R1-R14) — no UTXO access needed
// =============================================================================

static TxValidationResult ValidateStructure(
    const Transaction& tx,
    const TxValidationContext& ctx)
{
    // R1: version == 1
    if (tx.version != 1) {
        return TxValidationResult::Fail(TxValCode::R1_BAD_VERSION,
            "R1: version must be 1, got " + std::to_string(tx.version));
    }

    // R2: tx_type in {0x00, 0x01}
    if (tx.tx_type != TX_TYPE_STANDARD && tx.tx_type != TX_TYPE_COINBASE) {
        return TxValidationResult::Fail(TxValCode::R2_BAD_TX_TYPE,
            "R2: invalid tx_type 0x" + HexStr(&tx.tx_type, 1));
    }

    // R3: 1 <= num_inputs <= 256
    if (tx.inputs.empty() || tx.inputs.size() > MAX_INPUTS_CONSENSUS) {
        return TxValidationResult::Fail(TxValCode::R3_INPUT_COUNT,
            "R3: input count " + std::to_string(tx.inputs.size()) + " out of range [1,256]");
    }

    // R4: 1 <= num_outputs <= 256
    if (tx.outputs.empty() || tx.outputs.size() > MAX_OUTPUTS_CONSENSUS) {
        return TxValidationResult::Fail(TxValCode::R4_OUTPUT_COUNT,
            "R4: output count " + std::to_string(tx.outputs.size()) + " out of range [1,256]");
    }

    // Per-output checks: R5, R6, R11, R13, R14
    int64_t sum_outputs = 0;
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        const auto& out = tx.outputs[i];

        // R5: every output amount > 0
        if (out.amount <= 0) {
            return TxValidationResult::Fail(TxValCode::R5_ZERO_AMOUNT,
                "R5: output[" + std::to_string(i) + "] amount <= 0", -1, (int32_t)i);
        }

        // R6: every output amount <= SUPPLY_MAX_STOCKS
        if (out.amount > SUPPLY_MAX_STOCKS) {
            return TxValidationResult::Fail(TxValCode::R6_AMOUNT_OVERFLOW,
                "R6: output[" + std::to_string(i) + "] amount exceeds supply max",
                -1, (int32_t)i);
        }

        // R7: accumulate for overflow check
        sum_outputs += out.amount;
        if (sum_outputs > SUPPLY_MAX_STOCKS || sum_outputs < 0) {
            return TxValidationResult::Fail(TxValCode::R7_SUM_OVERFLOW,
                "R7: sum of outputs exceeds supply max at output[" +
                std::to_string(i) + "]", -1, (int32_t)i);
        }

        // R11: output type must be active (BOND_LOCK/ESCROW_LOCK require bond_activation_height)
        if (!IsActiveOutputType(out.type, ctx.spend_height, ctx.bond_activation_height)) {
            return TxValidationResult::Fail(TxValCode::R11_INACTIVE_TYPE,
                "R11: output[" + std::to_string(i) + "] type 0x" +
                HexStr(&out.type, 1) + " is not active at height " +
                std::to_string(ctx.spend_height), -1, (int32_t)i);
        }

        // R15: BOND_LOCK payload must be exactly 8 bytes (lock_until)
        if (out.type == OUT_BOND_LOCK) {
            if (out.payload.size() != BOND_LOCK_PAYLOAD_LEN) {
                return TxValidationResult::Fail(TxValCode::R12_PAYLOAD_MISMATCH,
                    "R15: BOND_LOCK output[" + std::to_string(i) +
                    "] payload must be " + std::to_string(BOND_LOCK_PAYLOAD_LEN) +
                    " bytes, got " + std::to_string(out.payload.size()),
                    -1, (int32_t)i);
            }
            uint64_t lock_until = ReadLockUntil(out.payload);
            if (lock_until <= (uint64_t)ctx.spend_height) {
                return TxValidationResult::Fail(TxValCode::R12_PAYLOAD_MISMATCH,
                    "R15: BOND_LOCK output[" + std::to_string(i) +
                    "] lock_until " + std::to_string(lock_until) +
                    " must be > current height " + std::to_string(ctx.spend_height),
                    -1, (int32_t)i);
            }
        }

        // R16: ESCROW_LOCK payload must be exactly 28 bytes (lock_until + beneficiary_pkh)
        if (out.type == OUT_ESCROW_LOCK) {
            if (out.payload.size() != ESCROW_LOCK_PAYLOAD_LEN) {
                return TxValidationResult::Fail(TxValCode::R12_PAYLOAD_MISMATCH,
                    "R16: ESCROW_LOCK output[" + std::to_string(i) +
                    "] payload must be " + std::to_string(ESCROW_LOCK_PAYLOAD_LEN) +
                    " bytes, got " + std::to_string(out.payload.size()),
                    -1, (int32_t)i);
            }
            uint64_t lock_until = ReadLockUntil(out.payload);
            if (lock_until <= (uint64_t)ctx.spend_height) {
                return TxValidationResult::Fail(TxValCode::R12_PAYLOAD_MISMATCH,
                    "R16: ESCROW_LOCK output[" + std::to_string(i) +
                    "] lock_until " + std::to_string(lock_until) +
                    " must be > current height " + std::to_string(ctx.spend_height),
                    -1, (int32_t)i);
            }
        }

        // R13: payload_len <= 512 (consensus limit)
        if (out.payload.size() > 512) {
            return TxValidationResult::Fail(TxValCode::R13_PAYLOAD_TOO_LONG,
                "R13: output[" + std::to_string(i) + "] payload too long (" +
                std::to_string(out.payload.size()) + ")", -1, (int32_t)i);
        }

        // R14: payload rules by output type
        //   - BOND_LOCK/ESCROW_LOCK: payload required (checked above in R15/R16)
        //   - OUT_TRANSFER: payload allowed only after capsule activation
        //   - All others: payload forbidden
        if (!out.payload.empty()) {
            bool payload_allowed = false;
            if (out.type == OUT_BOND_LOCK || out.type == OUT_ESCROW_LOCK) {
                payload_allowed = true; // validated in R15/R16 above
            } else if (ctx.spend_height >= ctx.capsule_activation_height) {
                if (out.type == OUT_TRANSFER) payload_allowed = true;
            }
            if (!payload_allowed) {
                return TxValidationResult::Fail(TxValCode::R14_PAYLOAD_FORBIDDEN,
                    "R14: output[" + std::to_string(i) + "] type 0x" +
                    HexStr(&out.type, 1) +
                    (ctx.spend_height < ctx.capsule_activation_height
                        ? " payload forbidden before capsule activation"
                        : " only OUT_TRANSFER/BOND_LOCK/ESCROW_LOCK may carry payload"),
                    -1, (int32_t)i);
            }
        }
    }

    // R9: serialized size <= MAX_TX_BYTES_CONSENSUS
    size_t est_size = EstimateTxSerializedSize(tx);
    if (est_size > (size_t)MAX_TX_BYTES_CONSENSUS) {
        return TxValidationResult::Fail(TxValCode::R9_OVERSIZE_TX,
            "R9: estimated tx size " + std::to_string(est_size) +
            " exceeds consensus max " + std::to_string(MAX_TX_BYTES_CONSENSUS));
    }

    return TxValidationResult::Ok();
}

// =============================================================================
// Duplicate input detection (R8)
// =============================================================================

static TxValidationResult CheckDuplicateInputs(const Transaction& tx) {
    std::set<OutPoint> seen;
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        OutPoint op;
        op.txid = tx.inputs[i].prev_txid;
        op.index = tx.inputs[i].prev_index;
        if (!seen.insert(op).second) {
            return TxValidationResult::Fail(TxValCode::R8_DUPLICATE_INPUT,
                "R8: duplicate input at index " + std::to_string(i), (int32_t)i);
        }
    }
    return TxValidationResult::Ok();
}

// =============================================================================
// UTXO lookup + signature verification (S1-S6, S10, S12)
// =============================================================================

static TxValidationResult ValidateInputs(
    const Transaction& tx,
    const IUtxoView& utxos,
    const TxValidationContext& ctx,
    int64_t& out_input_sum)
{
    out_input_sum = 0;

    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        const auto& txin = tx.inputs[i];

        OutPoint op;
        op.txid = txin.prev_txid;
        op.index = txin.prev_index;

        auto utxo_opt = utxos.GetUTXO(op);
        if (!utxo_opt.has_value()) {
            return TxValidationResult::Fail(TxValCode::S1_UTXO_NOT_FOUND,
                "S1: input[" + std::to_string(i) + "] references missing UTXO",
                (int32_t)i);
        }
        const UTXOEntry& utxo = utxo_opt.value();

        if (utxo.type == OUT_BURN) {
            return TxValidationResult::Fail(TxValCode::S12_BURN_UNSPENDABLE,
                "S12: input[" + std::to_string(i) + "] references burned output",
                (int32_t)i);
        }

        if (utxo.type == OUT_BOND_LOCK || utxo.type == OUT_ESCROW_LOCK) {
            uint64_t lock_until = ReadLockUntil(utxo.payload);
            if ((uint64_t)ctx.spend_height < lock_until) {
                return TxValidationResult::Fail(TxValCode::S11_BOND_LOCKED,
                    "S11: input[" + std::to_string(i) + "] locked until height " +
                    std::to_string(lock_until) + " (current: " +
                    std::to_string(ctx.spend_height) + ")",
                    (int32_t)i);
            }
            // Lock expired — output is spendable by the owner (pubkey_hash match)
        }

        if (utxo.is_coinbase) {
            int64_t confirmations = ctx.spend_height - utxo.height;
            if (confirmations < COINBASE_MATURITY) {
                return TxValidationResult::Fail(TxValCode::S10_COINBASE_IMMATURE,
                    "S10: input[" + std::to_string(i) + "] coinbase immature (" +
                    std::to_string(confirmations) + " < " +
                    std::to_string(COINBASE_MATURITY) + ")", (int32_t)i);
            }
        }

        SpentOutput spent;
        spent.amount = utxo.amount;
        spent.type = utxo.type;

        // DEBUG: show UTXO entry as seen by node validation
        {
            auto hex = [](const uint8_t* d, size_t n) {
                std::string s; s.reserve(n*2);
                for (size_t i=0;i<n;i++) { char buf[3]; snprintf(buf,3,"%02x",d[i]); s+=buf; }
                return s;
            };
            printf("[NODE-UTXO] input[%zu] utxo.amount=%lld utxo.type=0x%02x utxo.is_coinbase=%d utxo.height=%lld\n",
                   i, (long long)utxo.amount, utxo.type, utxo.is_coinbase, (long long)utxo.height);
            printf("[NODE-UTXO] input[%zu] utxo.pkh=%s\n", i, hex(utxo.pubkey_hash.data(),20).c_str());
        }

        std::string verify_err;
        if (!VerifyTransactionInput(tx, i, spent, ctx.genesis_hash,
                                    utxo.pubkey_hash, &verify_err)) {
            TxValCode code = TxValCode::S6_VERIFY_FAIL;
            if (verify_err.find("hash mismatch") != std::string::npos)
                code = TxValCode::S2_PKH_MISMATCH;
            else if (verify_err.find("all zeros") != std::string::npos)
                code = TxValCode::S4_ZERO_SIGNATURE;
            else if (verify_err.find("LOW-S") != std::string::npos ||
                     verify_err.find("low-S") != std::string::npos ||
                     verify_err.find("High-S") != std::string::npos)
                code = TxValCode::S5_HIGH_S;

            return TxValidationResult::Fail(code,
                "input[" + std::to_string(i) + "]: " + verify_err, (int32_t)i);
        }

        out_input_sum += utxo.amount;
        if (out_input_sum > SUPPLY_MAX_STOCKS || out_input_sum < 0) {
            return TxValidationResult::Fail(TxValCode::R7_SUM_OVERFLOW,
                "input sum overflow at input[" + std::to_string(i) + "]",
                (int32_t)i);
        }
    }

    return TxValidationResult::Ok();
}

// =============================================================================
// ValidateTransactionConsensus (R1-R14, S1-S12)
// =============================================================================

TxValidationResult ValidateTransactionConsensus(
    const Transaction& tx,
    const IUtxoView& utxos,
    const TxValidationContext& ctx)
{
    if (tx.tx_type == TX_TYPE_COINBASE) {
        return TxValidationResult::Fail(TxValCode::R2_BAD_TX_TYPE,
            "use ValidateCoinbaseConsensus for coinbase transactions");
    }

    auto r = ValidateStructure(tx, ctx);
    if (!r.ok) return r;

    r = CheckDuplicateInputs(tx);
    if (!r.ok) return r;

    int64_t input_sum = 0;
    r = ValidateInputs(tx, utxos, ctx, input_sum);
    if (!r.ok) return r;

    int64_t output_sum = 0;
    for (const auto& out : tx.outputs) output_sum += out.amount;

    if (input_sum < output_sum) {
        return TxValidationResult::Fail(TxValCode::S7_INPUTS_LT_OUTPUTS,
            "S7: input sum " + std::to_string(input_sum) +
            " < output sum " + std::to_string(output_sum));
    }

    int64_t fee = input_sum - output_sum;
    size_t tx_size = EstimateTxSerializedSize(tx);
    int64_t min_fee = (int64_t)tx_size * 1;
    if (fee < min_fee) {
        return TxValidationResult::Fail(TxValCode::S8_FEE_TOO_LOW,
            "S8: fee " + std::to_string(fee) + " < min " + std::to_string(min_fee) +
            " (" + std::to_string(tx_size) + " bytes × 1)");
    }

    // S9: standard tx outputs must be OUT_TRANSFER, or BOND_LOCK/ESCROW_LOCK (post-activation).
    // Payload allowance is governed by R14/R15/R16.
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        uint8_t t = tx.outputs[i].type;
        bool allowed = (t == OUT_TRANSFER);
        if (!allowed && ctx.spend_height >= ctx.bond_activation_height) {
            allowed = (t == OUT_BOND_LOCK || t == OUT_ESCROW_LOCK);
        }
        if (!allowed) {
            return TxValidationResult::Fail(TxValCode::S9_BAD_STD_OUTPUT_TYPE,
                "S9: standard tx output[" + std::to_string(i) +
                "] type 0x" + HexStr(&t, 1) + " not allowed", -1, (int32_t)i);
        }
    }

    return TxValidationResult::Ok();
}

// =============================================================================
// ValidateTransactionPolicy (relay/mining policy checks)
// PRECONDICIÓN: debe llamarse DESPUÉS de ValidateTransactionConsensus.
// =============================================================================

TxValidationResult ValidateTransactionPolicy(
    const Transaction& tx,
    const IUtxoView& utxos,
    const TxValidationContext& ctx)
{
    size_t tx_size = EstimateTxSerializedSize(tx);
    if (tx_size > (size_t)MAX_TX_BYTES_STANDARD) {
        return TxValidationResult::Fail(TxValCode::P_TX_TOO_LARGE,
            "Policy: tx size " + std::to_string(tx_size) +
            " exceeds standard limit " + std::to_string(MAX_TX_BYTES_STANDARD));
    }

    if (tx.inputs.size() > MAX_INPUTS_STANDARD) {
        return TxValidationResult::Fail(TxValCode::P_TOO_MANY_INPUTS,
            "Policy: " + std::to_string(tx.inputs.size()) +
            " inputs exceeds standard " + std::to_string(MAX_INPUTS_STANDARD));
    }

    if (tx.outputs.size() > MAX_OUTPUTS_STANDARD) {
        return TxValidationResult::Fail(TxValCode::P_TOO_MANY_OUTPUTS,
            "Policy: " + std::to_string(tx.outputs.size()) +
            " outputs exceeds standard " + std::to_string(MAX_OUTPUTS_STANDARD));
    }

    int payload_count = 0;
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        if (!tx.outputs[i].payload.empty()) {
            ++payload_count;

            if (tx.outputs[i].payload.size() > MAX_PAYLOAD_STANDARD) {
                return TxValidationResult::Fail(TxValCode::P_PAYLOAD_TOO_LARGE,
                    "Policy: output[" + std::to_string(i) + "] payload " +
                    std::to_string(tx.outputs[i].payload.size()) +
                    " exceeds standard " + std::to_string(MAX_PAYLOAD_STANDARD),
                    -1, (int32_t)i);
            }

            if (ctx.spend_height >= ctx.capsule_activation_height) {
                auto cap_result = ValidateCapsulePolicy(tx.outputs[i].payload);
                if (!cap_result.ok) {
                    return TxValidationResult::Fail(TxValCode::P_BAD_CAPSULE,
                        "Policy: output[" + std::to_string(i) +
                        "] bad capsule: " + cap_result.message,
                        -1, (int32_t)i);
                }
            }
        }
    }

    if (payload_count > MAX_PAYLOAD_OUTPUTS_STD) {
        return TxValidationResult::Fail(TxValCode::P_TOO_MANY_PAYLOADS,
            "Policy: " + std::to_string(payload_count) +
            " outputs with payload exceeds standard " +
            std::to_string(MAX_PAYLOAD_OUTPUTS_STD));
    }

    // relay fee: require all inputs resolvable (no silent skipping)
    int64_t input_sum = 0;
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        OutPoint op{tx.inputs[i].prev_txid, tx.inputs[i].prev_index};
        auto utxo_opt = utxos.GetUTXO(op);
        if (!utxo_opt.has_value()) {
            return TxValidationResult::Fail(TxValCode::INTERNAL_ERROR,
                "Policy: missing UTXO for input[" + std::to_string(i) +
                "] (precondition: call ValidateTransactionConsensus first)");
        }
        input_sum += utxo_opt->amount;
    }

    int64_t output_sum = 0;
    for (const auto& out : tx.outputs) output_sum += out.amount;

    int64_t fee = input_sum - output_sum;
    int64_t min_relay_fee = (int64_t)tx_size * MIN_RELAY_FEE_PER_BYTE;
    if (fee < min_relay_fee) {
        return TxValidationResult::Fail(TxValCode::P_FEE_BELOW_RELAY,
            "Policy: fee " + std::to_string(fee) + " < relay min " +
            std::to_string(min_relay_fee));
    }

    // dust
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        if (tx.outputs[i].amount < DUST_THRESHOLD) {
            return TxValidationResult::Fail(TxValCode::P_DUST_OUTPUT,
                "Policy: output[" + std::to_string(i) + "] amount " +
                std::to_string(tx.outputs[i].amount) + " below dust threshold " +
                std::to_string(DUST_THRESHOLD), -1, (int32_t)i);
        }
    }

    return TxValidationResult::Ok();
}

// =============================================================================
// ValidateCoinbaseConsensus (CB1-CB10 + V11 Phase 2 CB11-CB14)
// =============================================================================

TxValidationResult ValidateCoinbaseConsensus(
    const Transaction& tx,
    int64_t height,
    int64_t subsidy,
    int64_t total_fees,
    const PubKeyHash& gold_vault_pkh,
    const PubKeyHash& popc_pool_pkh,
    const Phase2CoinbaseContext* phase2_ctx)
{
    // -------------------------------------------------------------------------
    // Common header checks (apply to every coinbase, every height) — CB1, CB2,
    // CB3, CB9. These predate V11 Phase 2 and are not affected by it.
    // -------------------------------------------------------------------------

    if (tx.tx_type != TX_TYPE_COINBASE) {
        return TxValidationResult::Fail(TxValCode::CB1_MISSING_COINBASE,
            "CB1: tx_type must be COINBASE (0x01)");
    }

    if (tx.version != 1) {
        return TxValidationResult::Fail(TxValCode::R1_BAD_VERSION,
            "R1: coinbase version must be 1");
    }

    if (tx.inputs.size() != 1) {
        return TxValidationResult::Fail(TxValCode::CB2_BAD_CB_INPUT,
            "CB2: coinbase must have exactly 1 input, got " +
            std::to_string(tx.inputs.size()));
    }

    const auto& cbin = tx.inputs[0];
    Hash256 zero_hash{};
    if (cbin.prev_txid != zero_hash) {
        return TxValidationResult::Fail(TxValCode::CB2_BAD_CB_INPUT,
            "CB2: coinbase prev_txid must be all zeros");
    }
    if (cbin.prev_index != 0xFFFFFFFFu) {
        return TxValidationResult::Fail(TxValCode::CB2_BAD_CB_INPUT,
            "CB2: coinbase prev_index must be 0xFFFFFFFF, got 0x" + HexU32(cbin.prev_index));
    }

    // CB3: signature[0..7] = height as uint64 LE (portable)
    uint64_t encoded_height = 0;
    for (int i = 0; i < 8; ++i) {
        encoded_height |= (uint64_t)cbin.signature[i] << (8 * i);
    }
    if ((int64_t)encoded_height != height) {
        return TxValidationResult::Fail(TxValCode::CB3_BAD_CB_SIG_FIELD,
            "CB3: coinbase height mismatch: encoded " +
            std::to_string(encoded_height) + " != block height " +
            std::to_string(height));
    }

    // CB9: pubkey must be 0x00*33
    if (!IsAllZeros(cbin.pubkey.data(), 33)) {
        return TxValidationResult::Fail(TxValCode::CB9_CB_PUBKEY_NONZERO,
            "CB9: coinbase input pubkey must be all zeros");
    }

    // -------------------------------------------------------------------------
    // V11 Phase 2 (C8) — height-gated branch.
    //
    // The Phase 2 coinbase shape only kicks in when ALL of the following
    // hold:
    //   1. Caller provided a Phase2CoinbaseContext (non-null).
    //   2. The context's phase2_height is finite (!= INT64_MAX). In
    //      production today this is INT64_MAX (params.h), so the Phase 2
    //      path is unreachable from any real chain block.
    //   3. The current block's height is at or above phase2_height.
    //   4. The block is a triggered lottery block (caller computes via
    //      sost::lottery::is_lottery_block).
    //
    // Non-triggered Phase-2 blocks fall through to the pre-Phase-2 path
    // below — same 3-output MINER/GOLD/POPC shape with 50/25/25 split,
    // because the chain-state pending value is unchanged on those
    // blocks (the consensus emission invariant degrades to the standard
    // sum(outputs) == subsidy + fees rule).
    // -------------------------------------------------------------------------

    const bool phase2_triggered =
        phase2_ctx
        && phase2_ctx->phase2_height != INT64_MAX
        && height >= phase2_ctx->phase2_height
        && phase2_ctx->triggered;

    if (phase2_triggered) {
        const int64_t total_reward = subsidy + total_fees;
        const auto split = sost::lottery::phase2_coinbase_split(total_reward);
        const int64_t expected_miner   = split.miner_share;
        const int64_t expected_lottery = split.lottery_share;

        if (phase2_ctx->paid_out) {
            // -------- PAYOUT — 2 outputs (MINER + LOTTERY) --------

            if (tx.outputs.size() != 2) {
                return TxValidationResult::Fail(TxValCode::CB11_LOTTERY_SHAPE,
                    "CB11: Phase 2 PAYOUT coinbase must have exactly 2 outputs, got " +
                    std::to_string(tx.outputs.size()));
            }

            // CB4 (Phase 2 PAYOUT): output[0]=MINER, output[1]=LOTTERY
            if (tx.outputs[0].type != OUT_COINBASE_MINER) {
                return TxValidationResult::Fail(TxValCode::CB4_CB_OUTPUT_ORDER,
                    "CB4: PAYOUT output[0] must be OUT_COINBASE_MINER (0x01)", -1, 0);
            }
            if (tx.outputs[1].type != OUT_COINBASE_LOTTERY) {
                return TxValidationResult::Fail(TxValCode::CB4_CB_OUTPUT_ORDER,
                    "CB4: PAYOUT output[1] must be OUT_COINBASE_LOTTERY (0x04)", -1, 1);
            }

            // CB12: amounts (PAYOUT). The lottery output amount MUST be
            // exactly lottery_share + pending_before — no miner discretion.
            const int64_t expected_lottery_payout =
                expected_lottery + phase2_ctx->pending_before;
            if (tx.outputs[0].amount != expected_miner) {
                return TxValidationResult::Fail(TxValCode::CB12_LOTTERY_AMOUNT,
                    "CB12: PAYOUT miner amount " + std::to_string(tx.outputs[0].amount) +
                    " != expected " + std::to_string(expected_miner), -1, 0);
            }
            if (tx.outputs[1].amount != expected_lottery_payout) {
                return TxValidationResult::Fail(TxValCode::CB12_LOTTERY_AMOUNT,
                    "CB12: PAYOUT lottery amount " + std::to_string(tx.outputs[1].amount) +
                    " != expected lottery_share + pending_before = " +
                    std::to_string(expected_lottery_payout) +
                    " (lottery_share=" + std::to_string(expected_lottery) +
                    ", pending_before=" + std::to_string(phase2_ctx->pending_before) + ")",
                    -1, 1);
            }

            // Cross-check against caller-supplied context (defence in
            // depth — caller and validator agree on the same number).
            if (phase2_ctx->lottery_payout != expected_lottery_payout) {
                return TxValidationResult::Fail(TxValCode::CB12_LOTTERY_AMOUNT,
                    "CB12: PAYOUT context lottery_payout " +
                    std::to_string(phase2_ctx->lottery_payout) +
                    " != lottery_share + pending_before " +
                    std::to_string(expected_lottery_payout));
            }

            // CB13: lottery output address MUST equal the deterministic
            // winner picked by the caller (select_lottery_winner_index).
            if (tx.outputs[1].pubkey_hash != phase2_ctx->expected_winner_pkh) {
                return TxValidationResult::Fail(TxValCode::CB13_LOTTERY_WINNER,
                    "CB13: PAYOUT OUT_COINBASE_LOTTERY pubkey_hash does not match "
                    "deterministic winner expected by chain context", -1, 1);
            }

            // CB10 (Phase 2): empty payload on both outputs.
            for (size_t i = 0; i < tx.outputs.size(); ++i) {
                if (!tx.outputs[i].payload.empty()) {
                    return TxValidationResult::Fail(TxValCode::CB10_CB_PAYLOAD,
                        "CB10: coinbase output[" + std::to_string(i) +
                        "] must have empty payload", -1, (int32_t)i);
                }
            }

            // R5/R6 on the two PAYOUT outputs. lottery_share + pending_before
            // is always > 0 on a triggered block at non-zero subsidy/fee
            // levels (lottery_share = total_reward/2 > 0 for any realistic
            // SOST mining height).
            for (size_t i = 0; i < tx.outputs.size(); ++i) {
                if (tx.outputs[i].amount <= 0) {
                    return TxValidationResult::Fail(TxValCode::R5_ZERO_AMOUNT,
                        "R5: PAYOUT output[" + std::to_string(i) + "] amount <= 0",
                        -1, (int32_t)i);
                }
                if (tx.outputs[i].amount > SUPPLY_MAX_STOCKS) {
                    return TxValidationResult::Fail(TxValCode::R6_AMOUNT_OVERFLOW,
                        "R6: PAYOUT output[" + std::to_string(i) +
                        "] amount exceeds supply max", -1, (int32_t)i);
                }
            }

            // CB14: emission invariant cross-check —
            //   sum(outputs) + (pending_after - pending_before) == subsidy + fees
            //
            // PAYOUT case:
            //   sum   = miner_share + (lottery_share + pending_before)
            //         = total_reward + pending_before
            //   Δpending = expected_pending_after - pending_before
            //            = 0 - pending_before = -pending_before
            //   sum + Δpending = total_reward = subsidy + fees ✓
            //
            // expected_pending_after on PAYOUT MUST be 0.
            if (phase2_ctx->expected_pending_after != 0) {
                return TxValidationResult::Fail(TxValCode::CB14_LOTTERY_INVARIANT,
                    "CB14: PAYOUT expected_pending_after must be 0, got " +
                    std::to_string(phase2_ctx->expected_pending_after));
            }
            const int64_t sum_outputs =
                tx.outputs[0].amount + tx.outputs[1].amount;
            const int64_t delta_pending =
                phase2_ctx->expected_pending_after - phase2_ctx->pending_before;
            if (sum_outputs + delta_pending != total_reward) {
                return TxValidationResult::Fail(TxValCode::CB14_LOTTERY_INVARIANT,
                    "CB14: emission invariant broken on PAYOUT: "
                    "sum(outputs)=" + std::to_string(sum_outputs) +
                    " + Δpending=" + std::to_string(delta_pending) +
                    " != subsidy+fees=" + std::to_string(total_reward));
            }
            return TxValidationResult::Ok();
        }

        // -------- UPDATE — 1 output (MINER only) --------
        // Triggered + empty eligibility set: the lottery share is
        // withheld in chain-state pending, and the coinbase emits
        // ONLY a miner output. GOLD and POPC outputs are OMITTED.

        if (tx.outputs.size() != 1) {
            return TxValidationResult::Fail(TxValCode::CB11_LOTTERY_SHAPE,
                "CB11: Phase 2 UPDATE coinbase must have exactly 1 output, got " +
                std::to_string(tx.outputs.size()));
        }

        if (tx.outputs[0].type != OUT_COINBASE_MINER) {
            return TxValidationResult::Fail(TxValCode::CB4_CB_OUTPUT_ORDER,
                "CB4: UPDATE output[0] must be OUT_COINBASE_MINER (0x01)", -1, 0);
        }
        if (tx.outputs[0].amount != expected_miner) {
            return TxValidationResult::Fail(TxValCode::CB12_LOTTERY_AMOUNT,
                "CB12: UPDATE miner amount " + std::to_string(tx.outputs[0].amount) +
                " != expected " + std::to_string(expected_miner), -1, 0);
        }
        if (!tx.outputs[0].payload.empty()) {
            return TxValidationResult::Fail(TxValCode::CB10_CB_PAYLOAD,
                "CB10: coinbase output[0] must have empty payload", -1, 0);
        }
        if (tx.outputs[0].amount <= 0) {
            return TxValidationResult::Fail(TxValCode::R5_ZERO_AMOUNT,
                "R5: UPDATE output[0] amount <= 0", -1, 0);
        }
        if (tx.outputs[0].amount > SUPPLY_MAX_STOCKS) {
            return TxValidationResult::Fail(TxValCode::R6_AMOUNT_OVERFLOW,
                "R6: UPDATE output[0] amount exceeds supply max", -1, 0);
        }

        // CB14: emission invariant — UPDATE case.
        //   sum   = miner_share
        //   Δpending = (pending_before + lottery_share) - pending_before
        //            = +lottery_share
        //   sum + Δpending = miner_share + lottery_share = total_reward ✓
        const int64_t expected_pending_after =
            phase2_ctx->pending_before + expected_lottery;
        if (phase2_ctx->expected_pending_after != expected_pending_after) {
            return TxValidationResult::Fail(TxValCode::CB14_LOTTERY_INVARIANT,
                "CB14: UPDATE expected_pending_after " +
                std::to_string(phase2_ctx->expected_pending_after) +
                " != pending_before + lottery_share = " +
                std::to_string(expected_pending_after));
        }
        const int64_t sum_outputs_u = tx.outputs[0].amount;
        const int64_t delta_pending_u =
            phase2_ctx->expected_pending_after - phase2_ctx->pending_before;
        if (sum_outputs_u + delta_pending_u != total_reward) {
            return TxValidationResult::Fail(TxValCode::CB14_LOTTERY_INVARIANT,
                "CB14: emission invariant broken on UPDATE: "
                "sum(outputs)=" + std::to_string(sum_outputs_u) +
                " + Δpending=" + std::to_string(delta_pending_u) +
                " != subsidy+fees=" + std::to_string(total_reward));
        }
        return TxValidationResult::Ok();
    }

    // -------------------------------------------------------------------------
    // PRE-PHASE-2 PATH (and Phase 2 non-triggered blocks).
    //
    // Identical to the original CB1-CB10 logic: 3 outputs MINER/GOLD/POPC
    // with the canonical 50/25/25 split. Phase 2 non-triggered blocks
    // satisfy the same invariant trivially (Δpending == 0).
    // -------------------------------------------------------------------------

    // CB7: exactly 3 outputs
    if (tx.outputs.size() != 3) {
        return TxValidationResult::Fail(TxValCode::CB7_CB_OUTPUT_COUNT,
            "CB7: coinbase must have exactly 3 outputs, got " +
            std::to_string(tx.outputs.size()));
    }

    // CB4: output type order
    if (tx.outputs[0].type != OUT_COINBASE_MINER) {
        return TxValidationResult::Fail(TxValCode::CB4_CB_OUTPUT_ORDER,
            "CB4: output[0] must be OUT_COINBASE_MINER (0x01)", -1, 0);
    }
    if (tx.outputs[1].type != OUT_COINBASE_GOLD) {
        return TxValidationResult::Fail(TxValCode::CB4_CB_OUTPUT_ORDER,
            "CB4: output[1] must be OUT_COINBASE_GOLD (0x02)", -1, 1);
    }
    if (tx.outputs[2].type != OUT_COINBASE_POPC) {
        return TxValidationResult::Fail(TxValCode::CB4_CB_OUTPUT_ORDER,
            "CB4: output[2] must be OUT_COINBASE_POPC (0x03)", -1, 2);
    }

    // CB5: exact split of (subsidy + fees): quarter, quarter, remainder-to-miner
    int64_t total_reward = subsidy + total_fees;
    int64_t quarter = total_reward / 4;
    int64_t expected_gold = quarter;
    int64_t expected_popc = quarter;
    int64_t expected_miner = total_reward - expected_gold - expected_popc;

    if (tx.outputs[0].amount != expected_miner) {
        return TxValidationResult::Fail(TxValCode::CB5_CB_AMOUNT_MISMATCH,
            "CB5: miner amount " + std::to_string(tx.outputs[0].amount) +
            " != expected " + std::to_string(expected_miner), -1, 0);
    }
    if (tx.outputs[1].amount != expected_gold) {
        return TxValidationResult::Fail(TxValCode::CB5_CB_AMOUNT_MISMATCH,
            "CB5: gold amount " + std::to_string(tx.outputs[1].amount) +
            " != expected " + std::to_string(expected_gold), -1, 1);
    }
    if (tx.outputs[2].amount != expected_popc) {
        return TxValidationResult::Fail(TxValCode::CB5_CB_AMOUNT_MISMATCH,
            "CB5: popc amount " + std::to_string(tx.outputs[2].amount) +
            " != expected " + std::to_string(expected_popc), -1, 2);
    }

    // CB6: vault destinations must match constitutional PKHs
    if (tx.outputs[1].pubkey_hash != gold_vault_pkh) {
        return TxValidationResult::Fail(TxValCode::CB6_CB_VAULT_MISMATCH,
            "CB6: gold vault pubkey_hash mismatch", -1, 1);
    }
    if (tx.outputs[2].pubkey_hash != popc_pool_pkh) {
        return TxValidationResult::Fail(TxValCode::CB6_CB_VAULT_MISMATCH,
            "CB6: popc pool pubkey_hash mismatch", -1, 2);
    }

    // CB10: coinbase outputs payload must be empty
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        if (!tx.outputs[i].payload.empty()) {
            return TxValidationResult::Fail(TxValCode::CB10_CB_PAYLOAD,
                "CB10: coinbase output[" + std::to_string(i) +
                "] must have empty payload", -1, (int32_t)i);
        }
    }

    // R5/R6 on coinbase outputs
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        if (tx.outputs[i].amount <= 0) {
            return TxValidationResult::Fail(TxValCode::R5_ZERO_AMOUNT,
                "R5: coinbase output[" + std::to_string(i) + "] amount <= 0",
                -1, (int32_t)i);
        }
        if (tx.outputs[i].amount > SUPPLY_MAX_STOCKS) {
            return TxValidationResult::Fail(TxValCode::R6_AMOUNT_OVERFLOW,
                "R6: coinbase output[" + std::to_string(i) + "] amount exceeds supply max",
                -1, (int32_t)i);
        }
    }

    return TxValidationResult::Ok();
}

} // namespace sost
