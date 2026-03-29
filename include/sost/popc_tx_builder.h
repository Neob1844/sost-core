// popc_tx_builder.h — PoPC transaction builders (application-layer)
//
// Builds standard SOST transactions for PoPC bond release and reward
// distribution. All logic is application-layer (no consensus changes).
// The only consensus footprint of PoPC is the 25% coinbase allocation
// enforced by CB-rules in block_validation.
//
// Status: Phase 1 — bond release and reward TX builders
#pragma once
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/popc.h"
#include <string>
#include <vector>

namespace sost {

// Build a TX that spends an expired BOND_LOCK UTXO back to the owner.
// Returns false if the bond hasn't expired yet or input is invalid.
// out_tx is populated on success.
bool build_bond_release_tx(
    Transaction& out_tx,
    const OutPoint& bond_outpoint,
    const UTXOEntry& bond_utxo,
    int64_t current_height,
    const Hash256& genesis_hash,
    const PrivKey& owner_privkey,
    std::string* err = nullptr);

// Build a reward TX from the PoPC Pool to a participant.
// Selects UTXOs from pool_utxos (sorted by height ascending — FIFO).
// Creates a change output back to pool_pkh if change > DUST_THRESHOLD.
// Fee = 1 stock/byte (MIN_RELAY_FEE policy).
// Returns false if pool balance is insufficient.
bool build_reward_tx(
    Transaction& out_tx,
    const std::vector<std::pair<OutPoint, UTXOEntry>>& pool_utxos,
    const PubKeyHash& recipient_pkh,
    int64_t reward_amount,
    const PubKeyHash& pool_pkh,
    const Hash256& genesis_hash,
    const PrivKey& pool_privkey,
    std::string* err = nullptr);

// Build a slash marker: marks a commitment as SLASHED in the registry.
// The bond UTXO itself is recovered via build_bond_release_tx once expired.
// (Actual on-chain slash distribution is a future consensus upgrade.)
bool build_slash_marker(
    PoPCRegistry& registry,
    const Hash256& commitment_id,
    const std::string& reason,
    std::string* err = nullptr);

// Calculate reward amount in stocks using integer arithmetic (no floats).
// reward_pct_bps is in basis points (e.g., 2200 = 22%).
// Returns (bond_stocks * reward_pct_bps) / 10000.
// Returns 0 on overflow guard.
int64_t calculate_reward_stocks(int64_t bond_stocks, uint16_t reward_pct_bps);

} // namespace sost
