// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// SOST — Phase 5.5: Block Validation Implementation
// Compatible with Phase 3 (tx_validation) + Phase 4 (utxo_set)
// =============================================================================

#include <sost/types.h>
#include <sost/block_validation.h>
#include <sost/merkle.h>

#include <sost/subsidy.h>
#include <sost/gold_vault_slice1.h>   // V13 Gold Vault Slice 1 (sentinel-disabled by default)
#include <unordered_set>
#include <string>

namespace sost {

// ---------------------------------------------------------------------------
// GetBlockSubsidy
// NOTE: If you have a real schedule function (e.g. sost_subsidy_stocks),
// you can call it here. For now we default to 50 SOST.
// ---------------------------------------------------------------------------

int64_t GetBlockSubsidy(int64_t height) {
    return ::sost::sost_subsidy_stocks(height); // epoch decay
}

// ==========================================================================
// L1: ValidateBlockStructure (context-free)
// ==========================================================================

bool ValidateBlockStructure(const Block& block, std::string* err) {

    // Size
    size_t block_size = block.EstimateSize();
    if (block_size > MAX_BLOCK_SIZE_CONSENSUS) {
        if (err) *err = "ValidateBlockStructure: block too large ("
                      + std::to_string(block_size) + " > "
                      + std::to_string(MAX_BLOCK_SIZE_CONSENSUS) + ")";
        return false;
    }

    // tx_count >= 1
    if (block.txs.empty()) {
        if (err) *err = "ValidateBlockStructure: no transactions";
        return false;
    }

    // tx_count <= max
    if (block.txs.size() > MAX_BLOCK_TXS_CONSENSUS) {
        if (err) *err = "ValidateBlockStructure: too many txs ("
                      + std::to_string(block.txs.size()) + " > "
                      + std::to_string(MAX_BLOCK_TXS_CONSENSUS) + ")";
        return false;
    }

    // coinbase at [0]
    if (block.txs[0].tx_type != TX_TYPE_COINBASE) {
        if (err) *err = "ValidateBlockStructure: tx[0] is not coinbase";
        return false;
    }

    // others standard
    for (size_t i = 1; i < block.txs.size(); ++i) {
        if (block.txs[i].tx_type != TX_TYPE_STANDARD) {
            if (err) *err = "ValidateBlockStructure: tx[" + std::to_string(i) +
                            "] is not standard";
            return false;
        }
    }

    // Merkle root + mutation detection
    Hash256 computed{};
    bool mutated = false;
    std::string m_err;
    if (!ComputeMerkleRootFromTxs(block.txs, computed, &mutated, &m_err)) {
        if (err) *err = "ValidateBlockStructure: merkle compute: " + m_err;
        return false;
    }
    if (mutated) {
        if (err) *err = "ValidateBlockStructure: mutated merkle root (CVE-2012-2459 style)";
        return false;
    }
    if (computed != block.header.merkle_root) {
        if (err) *err = "ValidateBlockStructure: merkle mismatch (computed "
                      + HexStr(computed) + " != header " + HexStr(block.header.merkle_root) + ")";
        return false;
    }

    return true;
}

// ==========================================================================
// L2: ValidateBlockHeaderContext
// ==========================================================================

bool ValidateBlockHeaderContext(
    const BlockHeader& header,
    const BlockHeader* prev,
    int64_t current_time,
    uint32_t expected_bits_q,
    std::string* err)
{
    // version must match protocol
    if (header.version != BLOCK_HEADER_VERSION) {
        if (err) *err = "ValidateBlockHeaderContext: bad header.version";
        return false;
    }

    // ---- Genesis ----
    if (header.height == 0) {
        if (prev != nullptr) {
            if (err) *err = "ValidateBlockHeaderContext: genesis with non-null prev";
            return false;
        }
        if (header.prev_block_hash != Hash256{}) {
            if (err) *err = "ValidateBlockHeaderContext: genesis prev_block_hash not zero";
            return false;
        }
        if (header.timestamp != GENESIS_TIMESTAMP) {
            if (err) *err = "ValidateBlockHeaderContext: genesis timestamp mismatch";
            return false;
        }
        if (header.bits_q != GENESIS_BITSQ) {
            if (err) *err = "ValidateBlockHeaderContext: genesis bits_q mismatch";
            return false;
        }
        return true;
    }

    // ---- Non-genesis requires prev ----
    if (prev == nullptr) {
        if (err) *err = "ValidateBlockHeaderContext: height requires prev";
        return false;
    }

    // prev hash must match prev block hash
    Hash256 want_prev = prev->ComputeBlockHash();
    if (header.prev_block_hash != want_prev) {
        if (err) *err = "ValidateBlockHeaderContext: prev_block_hash mismatch";
        return false;
    }

    // height continuity
    if (header.height != prev->height + 1) {
        if (err) *err = "ValidateBlockHeaderContext: height mismatch (got="
                      + std::to_string(header.height) + ", expected="
                      + std::to_string(prev->height + 1) + ")";
        return false;
    }

    // Python-aligned (strictly increasing vs. parent).
    // NOTE: Python uses MTP(11). We can't compute full MTP here because this function
    // receives only `prev`, not the last 11 headers. Enforcing strict monotonicity
    // is a safe subset that prevents accepting blocks Python would reject.
    if (header.timestamp <= prev->timestamp) {
        if (err) *err = "ValidateBlockHeaderContext: timestamp not strictly increasing";
        return false;
    }

    // not too far in future (Python uses +600s)
    if (header.timestamp > current_time + MAX_FUTURE_BLOCK_TIME) {
        if (err) *err = "ValidateBlockHeaderContext: timestamp too far in future";
        return false;
    }

    // difficulty bits_q match expected (cASERT bitsQ)
    if (header.bits_q != expected_bits_q) {
        if (err) *err = "ValidateBlockHeaderContext: bits_q mismatch (got="
                      + std::to_string(header.bits_q) + ", expected="
                      + std::to_string(expected_bits_q) + ")";
        return false;
    }

    return true;
}

// ==========================================================================
// L2b: ValidateBlockHeaderContextWithMTP (Python-aligned MTP=11 + drift)
// ==========================================================================
//
// This does NOT replace ValidateBlockHeaderContext().
// It's a stricter variant that matches the Python miner/verifier rules:
//
//   - header.timestamp > MedianTimePast(last 11 blocks)
//   - header.timestamp <= now + MAX_FUTURE_DRIFT
//
// `chain_meta` is expected to contain the existing chain in order (genesis..tip),
// where chain_meta.back() corresponds to `prev`.
//
bool ValidateBlockHeaderContextWithMTP(
    const BlockHeader& header,
    const BlockHeader* prev,
    const std::vector<BlockMeta>& chain_meta,
    int64_t current_time,
    uint32_t expected_bits_q,
    std::string* err)
{
    // Reuse the existing checks first (version, genesis rules, prev-link,
    // height continuity, difficulty match, future drift, etc.)
    //
    // IMPORTANT: Your current ValidateBlockHeaderContext() uses a weaker
    // monotonic time check (prev timestamp). We still call it because it
    // validates many other invariants. Then we apply the strict MTP rule below.
    if (!ValidateBlockHeaderContext(header, prev, current_time, expected_bits_q, err)) {
        return false;
    }

    // Genesis already handled by ValidateBlockHeaderContext().
    if (header.height == 0) return true;

    // Need enough history to compute MTP. Python uses window=11.
    constexpr int MTP_WINDOW = 11;

    // `chain_meta` should include `prev` as its last element for normal validation.
    // If not available, fail-closed (consensus strictness).
    if (chain_meta.empty()) {
        if (err) *err = "ValidateBlockHeaderContextWithMTP: missing chain_meta";
        return false;
    }

    // Compute MedianTimePast over the last up-to-11 timestamps.
    // Python takes last 11 blocks (or fewer if chain shorter).
    const int n = (int)chain_meta.size();
    const int take = (n < MTP_WINDOW) ? n : MTP_WINDOW;

    // Collect timestamps
    int64_t times[MTP_WINDOW];
    for (int i = 0; i < take; ++i) {
        times[i] = chain_meta[n - take + i].time;
    }

    // Sort small array (insertion sort, deterministic)
    for (int i = 1; i < take; ++i) {
        int64_t key = times[i];
        int j = i - 1;
        while (j >= 0 && times[j] > key) {
            times[j + 1] = times[j];
            --j;
        }
        times[j + 1] = key;
    }

    const int64_t mtp = times[take / 2];

    // Python rule: ts MUST be strictly greater than MTP
    if (header.timestamp <= mtp) {
        if (err) *err = "ValidateBlockHeaderContextWithMTP: time-too-old (ts<=MTP)";
        return false;
    }

    return true;
}

// Combined post-fork timestamp policy (block 6400+):
//   (a) ts > MedianTimePast(last TIMESTAMP_MTP_WINDOW blocks)
//   (b) ts >= prev_ts + TIMESTAMP_MIN_DELTA_SECONDS
bool ValidatePostForkTimestamp(
    int64_t ts,
    int64_t prev_ts,
    const std::vector<BlockMeta>& chain_meta,
    std::string* err)
{
    // (a) MTP
    if (chain_meta.empty()) {
        if (err) *err = "ValidatePostForkTimestamp: missing chain_meta";
        return false;
    }
    const int n = (int)chain_meta.size();
    const int take = (n < TIMESTAMP_MTP_WINDOW) ? n : TIMESTAMP_MTP_WINDOW;
    int64_t buf[TIMESTAMP_MTP_WINDOW];
    for (int i = 0; i < take; ++i) buf[i] = chain_meta[(size_t)(n - take + i)].time;
    for (int i = 1; i < take; ++i) {
        int64_t key = buf[i]; int j = i - 1;
        while (j >= 0 && buf[j] > key) { buf[j+1] = buf[j]; --j; }
        buf[j+1] = key;
    }
    const int64_t mtp = buf[take / 2];
    if (ts <= mtp) {
        if (err) *err = "ValidatePostForkTimestamp: ts<=MTP";
        return false;
    }
    // (b) minimum spacing vs. parent
    if (ts < prev_ts + TIMESTAMP_MIN_DELTA_SECONDS) {
        if (err) *err = "ValidatePostForkTimestamp: ts < prev_ts + min_delta";
        return false;
    }
    return true;
}

// ==========================================================================
// L3: ValidateBlockTransactionsConsensus
// ==========================================================================

BlockConsensusResult ValidateBlockTransactionsConsensus(
    const Block& block,
    const UtxoSet& utxos_view,
    const TxValidationContext& base_tx_ctx,
    const PubKeyHash& gold_vault_pkh,
    const PubKeyHash& popc_pool_pkh)
{
    // scratch UTXO view for intra-block spends
    UtxoSet scratch = utxos_view;

    // compute txids + duplicate txid check (R10)
    std::unordered_set<std::string> seen;
    seen.reserve(block.txs.size() * 2);

    std::vector<Hash256> txids(block.txs.size());
    for (size_t i = 0; i < block.txs.size(); ++i) {
        std::string id_err;
        if (!block.txs[i].ComputeTxId(txids[i], &id_err)) {
            return BlockConsensusResult::Fail("tx[" + std::to_string(i) + "] txid: " + id_err);
        }
        std::string hex = HexStr(txids[i]);
        if (seen.count(hex)) {
            return BlockConsensusResult::Fail("duplicate txid " + hex + " at tx[" + std::to_string(i) + "]");
        }
        seen.insert(hex);
    }

    const int64_t height = block.header.height;
    const int64_t subsidy = GetBlockSubsidy(height);

    // validate standard txs, connect into scratch, accumulate fees
    int64_t total_fees = 0;

    for (size_t i = 1; i < block.txs.size(); ++i) {
        const Transaction& tx = block.txs[i];

        // tx context at this block height
        TxValidationContext tx_ctx = base_tx_ctx;
        tx_ctx.spend_height = height;

        auto vr = ValidateTransactionConsensus(tx, scratch, tx_ctx);
        if (!vr.ok) {
            return BlockConsensusResult::Fail("tx[" + std::to_string(i) + "] consensus: " + vr.message);
        }

        // V13 Gold Vault Slice 1 governance check (G1 + G2 + G3a).
        //
        // Sentinel-disabled by default: gv_slice1_active_at(height) returns
        // false at every height until a future commit flips
        // GV_SLICE1_ACTIVATION_HEIGHT from INT64_MAX to V13_HEIGHT. While
        // sentinel-disabled, this block is a no-op for every tx and adds
        // no measurable cost (one int64 compare). When activated, applies:
        //   G1  — every non-change output destination MUST be in the
        //         Slice 1 whitelist.
        //   G2  — the primary and mirror whitelists MUST agree; if not,
        //         fail-closed-reject (catches operator misconfiguration).
        //   G3a — the sum of external outputs from a vault-input tx MUST
        //         be within GV_SLICE1_PER_SPEND_CAP_BPS of the current
        //         vault balance.
        // G3b (rate limit) is unit-tested in test_v13_gold_vault_slice1
        // but NOT wired here — it needs a new StoredBlock field
        // gold_vault_last_spend_height that lands in a separate commit.
        //
        // See docs/V13_POPC_GOLDVAULT_IMPLEMENTATION_PLAN.md and
        // include/sost/gold_vault_slice1.h for the operator-decision
        // blockers (whitelist values, cap basis points, rate-limit blocks)
        // that must be filled BEFORE activation makes any consensus
        // difference.
        if (gv_slice1_active_at(height)) {
            auto lookup_pkh = [&scratch](const Hash256& prev_txid,
                                         uint32_t prev_index,
                                         PubKeyHash& out) -> bool {
                OutPoint op{prev_txid, prev_index};
                auto e = scratch.GetUTXO(op);
                if (!e.has_value()) return false;
                out = e->pubkey_hash;
                return true;
            };
            if (gv_slice1_tx_spends_from_vault(tx, gold_vault_pkh, lookup_pkh)) {
                // G2: dual-whitelist agreement (operator-misconfig catch)
                if (!gv_slice1_whitelists_agree()) {
                    return BlockConsensusResult::Fail(
                        "tx[" + std::to_string(i) +
                        "] gv_slice1: dual whitelist disagreement");
                }
                // G1: every non-change output destination must be in the
                //     whitelist. Outputs back to the vault itself are
                //     treated as change and accepted.
                int64_t total_external_out = 0;
                for (const auto& out : tx.outputs) {
                    if (out.pubkey_hash == gold_vault_pkh) {
                        continue; // change back to the vault
                    }
                    if (!gv_slice1_destination_allowed(out.pubkey_hash)) {
                        return BlockConsensusResult::Fail(
                            "tx[" + std::to_string(i) +
                            "] gv_slice1: destination not in whitelist");
                    }
                    total_external_out += out.amount;
                }
                // G3a: per-spend cap against current vault balance in scratch.
                int64_t vault_balance = 0;
                for (const auto& kv : scratch.GetMap()) {
                    if (kv.second.pubkey_hash == gold_vault_pkh) {
                        vault_balance += kv.second.amount;
                    }
                }
                if (!gv_slice1_amount_within_cap(total_external_out,
                                                 vault_balance)) {
                    return BlockConsensusResult::Fail(
                        "tx[" + std::to_string(i) +
                        "] gv_slice1: spend exceeds per-spend cap");
                }
                // G3a absolute cap (published governance: 1,000 SOST/spend).
                if (!gv_slice1_amount_within_abs_cap(total_external_out)) {
                    return BlockConsensusResult::Fail(
                        "tx[" + std::to_string(i) +
                        "] gv_slice1: spend exceeds absolute per-spend cap");
                }
            }
        }

        // fee calc using current scratch view BEFORE connect
        int64_t sum_in = 0;
        for (const auto& inp : tx.inputs) {
            OutPoint op{inp.prev_txid, inp.prev_index};
            auto e = scratch.GetUTXO(op);
            if (!e.has_value()) {
                return BlockConsensusResult::Fail("tx[" + std::to_string(i) + "] fee: missing input UTXO");
            }
            sum_in += e->amount;
        }
        int64_t sum_out = 0;
        for (const auto& out : tx.outputs) sum_out += out.amount;

        int64_t fee = sum_in - sum_out;
        if (fee < 0) {
            return BlockConsensusResult::Fail("tx[" + std::to_string(i) + "] negative fee");
        }
        total_fees += fee;
        if (total_fees < 0 || total_fees > SUPPLY_MAX_STOCKS) {
            return BlockConsensusResult::Fail("fee overflow");
        }

        // connect tx into scratch
        std::vector<UndoEntry> dummy_undo;
        std::string c_err;
        if (!scratch.ConnectTransaction(tx, txids[i], height, dummy_undo, &c_err)) {
            return BlockConsensusResult::Fail("tx[" + std::to_string(i) + "] connect: " + c_err);
        }
    }

    // validate coinbase EXACT (CB rules) using Phase 3
    {
        auto cr = ValidateCoinbaseConsensus(
            block.txs[0],
            height,
            subsidy,
            total_fees,
            gold_vault_pkh,
            popc_pool_pkh);

        if (!cr.ok) {
            return BlockConsensusResult::Fail("coinbase consensus: " + cr.message);
        }
    }

    return BlockConsensusResult::Ok(total_fees, subsidy);
}

// ==========================================================================
// L4: ConnectValidatedBlockAtomic
// ==========================================================================

bool ConnectValidatedBlockAtomic(
    const Block& block,
    UtxoSet& utxo_set,
    BlockUndo& out_undo,
    std::string* err)
{
    // atomic: mutate only scratch
    UtxoSet scratch = utxo_set;
    BlockUndo tmp{};
    std::string c_err;

    if (!scratch.ConnectBlock(block.txs, block.header.height, tmp, &c_err)) {
        if (err) *err = "ConnectValidatedBlockAtomic: " + c_err;
        return false;
    }

    utxo_set = std::move(scratch);
    out_undo = std::move(tmp);
    return true;
}

// ==========================================================================
// DisconnectBlock
// ==========================================================================

bool DisconnectBlock(
    const Block& block,
    UtxoSet& utxo_set,
    const BlockUndo& undo,
    std::string* err)
{
    if (!utxo_set.DisconnectBlock(block.txs, undo, err)) {
        if (err && !err->empty()) *err = "DisconnectBlock: " + *err;
        return false;
    }
    return true;
}

// ==========================================================================
// V11 Phase 2 — SbPoW consensus gate (height-gated, activates at block 7100)
// ==========================================================================
//
// Thin wrapper around sost::sbpow::validate_sbpow_for_block(). Lives
// in block_validation.cpp so block-validator callers don't need to
// include sbpow.h directly. With V11_PHASE2_HEIGHT = 7100 (set by
// C13), the version gate (v1 pre-Phase 2 / v2 Phase 2) rejects
// premature v2 blocks before height 7100 and demands a verifying
// pubkey + Schnorr signature on every block at height >= 7100.
bool ValidateSbPoW(
    uint32_t                              header_version,
    const Bytes32&                        prev_hash,
    int64_t                               height,
    int64_t                               timestamp,
    uint32_t                              bits_q,
    const Bytes32&                        commit,
    const Bytes32&                        merkle_root,
    uint32_t                              nonce,
    uint32_t                              extra_nonce,
    const sost::sbpow::MinerPubkey&       miner_pubkey,
    const sost::sbpow::MinerSignature&    miner_signature,
    const PubKeyHash&                     coinbase_miner_pkh,
    const Bytes32&                        genesis_hash,
    int64_t                               phase2_height,
    int64_t                               v13_height,
    std::string*                          err)
{
    sost::sbpow::ValidationInputs in;
    in.header_version       = header_version;
    in.prev_hash            = prev_hash;
    in.height               = height;
    in.commit               = commit;
    in.nonce                = nonce;
    in.extra_nonce          = extra_nonce;
    in.miner_pubkey         = miner_pubkey;
    in.miner_signature      = miner_signature;
    in.coinbase_miner_pkh   = coinbase_miner_pkh;
    in.phase2_height        = phase2_height;
    // V13 hardening fields — bound to the signed preimage at height >= v13_height.
    in.v13_height           = v13_height;
    in.timestamp            = timestamp;
    in.bits_q               = bits_q;
    in.merkle_root          = merkle_root;
    in.genesis_hash         = genesis_hash;

    auto r = sost::sbpow::validate_sbpow_for_block(in, err);
    return r == sost::sbpow::ValidationResult::OK ||
           r == sost::sbpow::ValidationResult::SBPOW_NOT_REQUIRED;
}

} // namespace sost
