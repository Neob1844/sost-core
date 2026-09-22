#pragma once
// ============================================================================
// Sweep planner — consolidating a mining address into batches that the network
// will actually relay.
//
// A mining address accumulates thousands of small coinbase UTXOs. Moving them
// needs many transactions, and the batch size is decided by RELAY POLICY, not
// by consensus: ValidateTransactionPolicy (src/tx_validation.cpp) refuses
// anything over MAX_TX_BYTES_STANDARD (16,000) or MAX_INPUTS_STANDARD (128),
// and src/mempool.cpp calls it before admitting a transaction. A batch built to
// the consensus limit of 256 inputs would be signed, submitted and silently
// never relayed.
//
// So this planner never hardcodes a batch size. It asks the SAME function the
// mempool uses — EstimateTxSerializedSize — so the two cannot drift apart.
//
// It plans; it does not spend. Nothing here signs, broadcasts, or touches a
// private key. The output is a plan plus a journal, both auditable before a
// single stock moves.
// ============================================================================
#include <cstdint>
#include <string>
#include <vector>

namespace sost::sweep {

// One spendable output as the node reports it (getaddressutxos).
struct Utxo {
    std::string txid;          // hex
    uint32_t    vout{0};
    int64_t     amount{0};     // stocks
    int64_t     height{0};
    bool        coinbase{false};
    bool        mature{false};
    bool        spendable{false};

    std::string key() const { return txid + ":" + std::to_string(vout); }
};

// One planned transaction. `inputs` are indices into the filtered UTXO vector.
struct Batch {
    std::vector<Utxo> inputs;
    int64_t total_in{0};
    int64_t fee{0};
    int64_t to_destination{0};   // total_in - fee; a sweep leaves no change
    size_t  est_bytes{0};
};

struct PlanLimits {
    int32_t max_tx_bytes_standard;   // read from the build, not assumed
    uint16_t max_inputs_standard;
    int64_t  fee_rate_stocks_per_byte;
    int32_t  byte_margin;            // headroom left under the byte limit
};

// Default limits, taken from this build's own constants.
PlanLimits default_limits();

// Exact policy size of a transaction with n_in inputs and n_out payload-free
// outputs, computed by calling EstimateTxSerializedSize on a structurally
// identical transaction — never by reimplementing the formula.
size_t policy_size(size_t n_in, size_t n_out);

// Largest input count that still fits the byte limit (minus margin) AND the
// input-count limit. Derived, never hardcoded.
size_t max_inputs_per_batch(const PlanLimits& L);

// Keep only what may legally be spent right now: mature AND spendable, and not
// already consumed by a batch the journal records as still confirmed.
std::vector<Utxo> filter_spendable(const std::vector<Utxo>& all,
                                   const std::vector<std::string>& consumed_keys);

// Deterministic packing: UTXOs are ordered by (txid, vout) first, so the same
// chain state always produces the same plan and two runs can be diffed. Every
// UTXO lands in exactly one batch; the fee is computed from each batch's own
// measured size.
std::vector<Batch> plan_batches(std::vector<Utxo> spendable, const PlanLimits& L);

// ---------------------------------------------------------------------------
// Journal — what was already sent, and whether the chain still agrees.
//
// A confirmation is not irreversibility. Every batch records the exact outpoints
// it consumed, its txid, and the height AND block hash it confirmed in. On every
// run the planner re-asks the node for the hash at that height: if it differs,
// the chain reorganised under us and that batch's inputs must be re-checked
// before anything else is planned — otherwise a sweep can pay twice.
// ---------------------------------------------------------------------------
struct JournalEntry {
    int         batch_index{0};
    std::string txid;                       // empty until submitted
    int64_t     confirmed_height{-1};       // -1 = not confirmed
    std::string confirmed_block_hash;       // hash seen at that height when recorded
    std::vector<std::string> consumed;      // "txid:vout"
    int64_t     total_in{0};
    int64_t     fee{0};
};

struct Journal {
    std::string destination;
    std::string source_address;
    std::vector<JournalEntry> entries;
};

bool journal_load(const std::string& path, Journal& out, std::string* err);
bool journal_save(const std::string& path, const Journal& j, std::string* err);

// Outpoints the journal considers already spent by a still-valid batch.
std::vector<std::string> consumed_keys(const Journal& j);

enum class AuditStatus { Ok, NotConfirmed, Reorged, Unknown };
struct AuditRow {
    int         batch_index{0};
    std::string txid;
    AuditStatus status{AuditStatus::Unknown};
    std::string detail;
};

} // namespace sost::sweep
