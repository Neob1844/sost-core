// popc_tx_builder.cpp — PoPC transaction builders (application-layer)
//
// Implements build_bond_release_tx, build_reward_tx, build_slash_marker,
// and calculate_reward_stocks. All amounts are in stocks (int64_t).
// Fee policy: 1 stock/byte (MIN_RELAY_FEE).
//
// See: include/sost/popc_tx_builder.h

#include "sost/popc_tx_builder.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include <algorithm>
#include <cstdint>
#include <climits>

namespace sost {

// =========================================================================
// calculate_reward_stocks
// Integer arithmetic: (bond_stocks * reward_pct_bps) / 10000
// Overflow guard: if bond_stocks * reward_pct_bps would exceed INT64_MAX,
// return 0 (caller should treat as error / use smaller bond).
// =========================================================================
int64_t calculate_reward_stocks(int64_t bond_stocks, uint16_t reward_pct_bps) {
    if (bond_stocks <= 0 || reward_pct_bps == 0) return 0;

    // Overflow check: bond_stocks * reward_pct_bps > INT64_MAX?
    // Since reward_pct_bps <= 65535 < 2^16, overflow occurs when
    // bond_stocks > INT64_MAX / reward_pct_bps.
    if (bond_stocks > (int64_t)(INT64_MAX / (int64_t)reward_pct_bps)) {
        return 0; // overflow guard
    }

    return (bond_stocks * (int64_t)reward_pct_bps) / 10000;
}

// =========================================================================
// build_bond_release_tx
// Spends a BOND_LOCK UTXO back to the owner once lock_until <= current_height.
// TX structure: 1 input (bond UTXO), 1 output (OUT_TRANSFER to owner).
// Amount = bond_utxo.amount - fee.
// Fee = estimated serialized size * 1 stock/byte.
// =========================================================================
bool build_bond_release_tx(
    Transaction& out_tx,
    const OutPoint& bond_outpoint,
    const UTXOEntry& bond_utxo,
    int64_t current_height,
    const Hash256& genesis_hash,
    const PrivKey& owner_privkey,
    std::string* err)
{
    // Validate output type
    if (bond_utxo.type != OUT_BOND_LOCK) {
        if (err) *err = "UTXO is not a BOND_LOCK output";
        return false;
    }

    // Check lock expiry: lock_until is stored in payload bytes [0..7] LE
    uint64_t lock_until = ReadLockUntil(bond_utxo.payload);
    if ((uint64_t)current_height < lock_until) {
        if (err) *err = "bond has not expired yet (lock_until=" +
                        std::to_string(lock_until) +
                        ", current_height=" +
                        std::to_string(current_height) + ")";
        return false;
    }

    // Build the unsigned transaction (1 input, 1 output placeholder for size estimation)
    Transaction tx;
    tx.version  = 1;
    tx.tx_type  = TX_TYPE_STANDARD;

    // Input: spend the bond UTXO
    TxInput inp;
    inp.prev_txid   = bond_outpoint.txid;
    inp.prev_index  = bond_outpoint.index;
    // signature and pubkey will be filled by SignTransactionInput
    tx.inputs.push_back(inp);

    // Output placeholder (to estimate size)
    TxOutput out;
    out.type   = OUT_TRANSFER;
    out.amount = bond_utxo.amount; // will be adjusted after fee calc

    // Derive owner pubkey hash from privkey
    PubKey owner_pubkey;
    std::string deriv_err;
    if (!DerivePublicKey(owner_privkey, owner_pubkey, &deriv_err)) {
        if (err) *err = "DerivePublicKey failed: " + deriv_err;
        return false;
    }
    out.pubkey_hash = ComputePubKeyHash(owner_pubkey);
    tx.outputs.push_back(out);

    // Estimate fee = serialized size * 1 stock/byte
    int64_t fee = (int64_t)EstimateTxSerializedSize(tx);
    int64_t send_amount = bond_utxo.amount - fee;

    if (send_amount <= DUST_THRESHOLD) {
        if (err) *err = "bond amount too small to cover fee";
        return false;
    }

    // Apply fee
    tx.outputs[0].amount = send_amount;

    // Sign the input
    SpentOutput spent;
    spent.amount = bond_utxo.amount;
    spent.type   = bond_utxo.type;

    std::string sign_err;
    if (!SignTransactionInput(tx, 0, spent, genesis_hash, owner_privkey, &sign_err)) {
        if (err) *err = "SignTransactionInput failed: " + sign_err;
        return false;
    }

    out_tx = std::move(tx);
    return true;
}

// =========================================================================
// build_reward_tx
// Selects UTXOs from pool_utxos (FIFO by height), builds TX:
//   N inputs (pool UTXOs), 1 output to recipient (reward_amount),
//   1 change output to pool_pkh if change > DUST_THRESHOLD.
// Fee = estimated serialized size * 1 stock/byte.
// =========================================================================
bool build_reward_tx(
    Transaction& out_tx,
    const std::vector<std::pair<OutPoint, UTXOEntry>>& pool_utxos,
    const PubKeyHash& recipient_pkh,
    int64_t reward_amount,
    const PubKeyHash& pool_pkh,
    const Hash256& genesis_hash,
    const PrivKey& pool_privkey,
    std::string* err)
{
    if (reward_amount <= 0) {
        if (err) *err = "reward_amount must be > 0";
        return false;
    }

    if (pool_utxos.empty()) {
        if (err) *err = "PoPC Pool balance insufficient (no UTXOs)";
        return false;
    }

    // Sort pool UTXOs by height ascending (FIFO — spend oldest first)
    std::vector<std::pair<OutPoint, UTXOEntry>> sorted_utxos = pool_utxos;
    std::sort(sorted_utxos.begin(), sorted_utxos.end(),
        [](const std::pair<OutPoint, UTXOEntry>& a,
           const std::pair<OutPoint, UTXOEntry>& b) {
            return a.second.height < b.second.height;
        });

    // Build transaction structure iteratively to get accurate fee estimate
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    // Accumulate inputs until we have enough for reward + estimated fee
    int64_t input_total = 0;
    std::vector<std::pair<OutPoint, UTXOEntry>> selected;

    for (const auto& utxo_pair : sorted_utxos) {
        selected.push_back(utxo_pair);
        input_total += utxo_pair.second.amount;

        // Build a draft TX to estimate size
        tx.inputs.clear();
        tx.outputs.clear();

        for (const auto& sel : selected) {
            TxInput inp;
            inp.prev_txid  = sel.first.txid;
            inp.prev_index = sel.first.index;
            tx.inputs.push_back(inp);
        }

        // Recipient output
        TxOutput recipient_out;
        recipient_out.type       = OUT_TRANSFER;
        recipient_out.amount     = reward_amount;
        recipient_out.pubkey_hash = recipient_pkh;
        tx.outputs.push_back(recipient_out);

        // Tentative change output (for size estimation)
        TxOutput change_out;
        change_out.type       = OUT_TRANSFER;
        change_out.amount     = 0; // placeholder
        change_out.pubkey_hash = pool_pkh;
        tx.outputs.push_back(change_out);

        int64_t fee      = (int64_t)EstimateTxSerializedSize(tx);
        int64_t change   = input_total - reward_amount - fee;

        if (change >= 0) {
            // We have enough. Decide if change output is needed.
            if (change <= DUST_THRESHOLD) {
                // Absorb dust into fee — remove change output
                tx.outputs.pop_back();
                // Recalculate fee without change output
                fee    = (int64_t)EstimateTxSerializedSize(tx);
                change = input_total - reward_amount - fee;
                if (change < 0) {
                    // Edge case: removing change output made fee insufficient —
                    // try the next UTXO instead.
                    tx.inputs.clear();
                    tx.outputs.clear();
                    continue;
                }
                // Finalize with no change output
                tx.outputs[0].amount = reward_amount;
                break;
            } else {
                // Finalize with change output
                tx.outputs[0].amount = reward_amount;
                tx.outputs[1].amount = change;
                break;
            }
        }
        // Not enough yet — loop to add more UTXOs
        tx.inputs.clear();
        tx.outputs.clear();
    }

    if (tx.inputs.empty()) {
        if (err) *err = "PoPC Pool balance insufficient";
        return false;
    }

    // Sign all inputs with pool_privkey
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        const auto& sel = selected[i];
        SpentOutput spent;
        spent.amount = sel.second.amount;
        spent.type   = sel.second.type;

        std::string sign_err;
        if (!SignTransactionInput(tx, i, spent, genesis_hash, pool_privkey, &sign_err)) {
            if (err) *err = "SignTransactionInput failed for input " +
                            std::to_string(i) + ": " + sign_err;
            return false;
        }
    }

    out_tx = std::move(tx);
    return true;
}

// =========================================================================
// build_slash_marker
// Marks the commitment as SLASHED in the registry.
// On-chain bond recovery happens separately via build_bond_release_tx
// after the bond's lock_until expires (slash = registry status change only).
// =========================================================================
bool build_slash_marker(
    PoPCRegistry& registry,
    const Hash256& commitment_id,
    const std::string& reason,
    std::string* err)
{
    return registry.slash(commitment_id, reason, err);
}

} // namespace sost
