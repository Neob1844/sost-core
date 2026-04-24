#pragma once
// =============================================================================
// SOST — Phase 6: Transaction Memory Pool (Mempool)
// =============================================================================

#include <sost/transaction.h>
#include <sost/tx_validation.h>
#include <sost/utxo_set.h>

#include <map>
#include <set>
#include <string>
#include <vector>

namespace sost {

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

inline constexpr size_t DEFAULT_MEMPOOL_MAX_ENTRIES = 5000;
inline constexpr size_t MAX_BLOCK_TX_COUNT          = 4096;

// Dynamic fee policy result
struct DynamicFeeInfo {
    int64_t relay_floor;       // current effective relay fee (stocks/byte)
    int64_t base_fee;          // static base (1 stock/byte)
    int64_t multiplier;        // current multiplier (1x, 2x, 5x, etc.)
    size_t  mempool_size;      // current tx count
    std::string pressure_level; // "none", "low", "medium", "high", "extreme"
    // Fee estimator bands
    int64_t fee_slow;          // minimum to get relayed
    int64_t fee_normal;        // good chance in next 2-3 blocks
    int64_t fee_fast;          // high priority
    int64_t fee_priority;      // top of mempool
};

// RBF policy: replacement requires this much additional fee per byte
inline constexpr int64_t RBF_MIN_FEE_BUMP_PER_BYTE  = 1;
// RBF policy: max number of original transactions that can be replaced
inline constexpr size_t  RBF_MAX_REPLACEMENTS        = 100;

// ---------------------------------------------------------------------------
// MempoolEntry
// ---------------------------------------------------------------------------

struct MempoolEntry {
    Transaction tx;
    Hash256     txid{};
    int64_t     fee{0};        // sum(inputs) - sum(outputs)
    size_t      size{0};       // serialized size
    int64_t     time_added{0}; // unix seconds

    std::vector<OutPoint> spent_outpoints;
};

// ---------------------------------------------------------------------------
// Mempool accept result
// ---------------------------------------------------------------------------

enum class MempoolAcceptCode : int {
    ACCEPTED        = 0,
    ALREADY_IN_POOL = 1,
    CONSENSUS_FAIL  = 2,
    POLICY_FAIL     = 3,
    DOUBLE_SPEND    = 4,
    POOL_FULL       = 5,
    COINBASE_REJECT = 6,
    RBF_REPLACED    = 7,   // accepted via RBF replacement
    RBF_REJECTED    = 8,   // replacement attempt failed
    INTERNAL_ERROR  = 99,
};

struct MempoolAcceptResult {
    bool              accepted{false};
    MempoolAcceptCode code{MempoolAcceptCode::INTERNAL_ERROR};
    std::string       reason;
    Hash256           txid{};
    int64_t           fee{0};
    double            fee_rate{0.0}; // solo informativo para UI/logs

    static MempoolAcceptResult Ok(const Hash256& txid, int64_t fee, double rate) {
        return {true, MempoolAcceptCode::ACCEPTED, "accepted", txid, fee, rate};
    }
    static MempoolAcceptResult Fail(MempoolAcceptCode c, const std::string& msg,
                                    const Hash256& txid = {}) {
        return {false, c, msg, txid, 0, 0.0};
    }
};

// ---------------------------------------------------------------------------
// Mempool
// ---------------------------------------------------------------------------

class Mempool {
public:
    explicit Mempool(size_t max_entries = DEFAULT_MEMPOOL_MAX_ENTRIES);

    // Enable/disable full RBF (default: enabled)
    void SetRBFEnabled(bool enabled) { rbf_enabled_ = enabled; }
    bool RBFEnabled() const { return rbf_enabled_; }

    MempoolAcceptResult AcceptToMempool(
        const Transaction& tx,
        const UtxoSet& utxos,
        const TxValidationContext& ctx,
        int64_t current_time = 0);

    bool RemoveTransaction(const Hash256& txid);

    size_t RemoveForBlock(const std::vector<Transaction>& block_txs);

    struct BlockTemplate {
        std::vector<Transaction> txs;
        std::vector<Hash256>     txids;
        int64_t total_fees{0};
        size_t  total_size{0};
    };

    // Standard block template (individual fee-rate ordering)
    BlockTemplate BuildBlockTemplate(
        size_t max_txs = MAX_BLOCK_TX_COUNT,
        size_t max_block_size = 1000000) const;

    // CPFP-aware block template (package fee-rate ordering)
    BlockTemplate BuildBlockTemplateCPFP(
        size_t max_txs = MAX_BLOCK_TX_COUNT,
        size_t max_block_size = 1000000) const;

    bool HasTransaction(const Hash256& txid) const;
    const MempoolEntry* GetEntry(const Hash256& txid) const;
    bool IsSpent(const OutPoint& op) const;

    size_t Size() const { return entries_.size(); }
    int64_t TotalFees() const;
    size_t TotalSize() const;

    void Clear();
    size_t MaxEntries() const { return max_entries_; }

    // Dynamic fee policy (block 10,000+)
    int64_t GetDynamicRelayFloor(int64_t chain_height) const;
    DynamicFeeInfo GetFeeInfo(int64_t chain_height) const;
    size_t CountByAddress(const std::string& address) const;

private:
    size_t max_entries_;
    bool rbf_enabled_{true};  // full RBF enabled by default

    // txid → entry
    std::map<Hash256, MempoolEntry> entries_;

    // Fee-rate index using exact rational ordering: fee/size
    struct FeeRateKey {
        int64_t fee;
        size_t  size;
        Hash256 txid;

        bool operator<(const FeeRateKey& o) const {
            // Compare fee/size without floating point:
            // fee1/size1 < fee2/size2  <=> fee1*size2 < fee2*size1
            __int128 lhs = (__int128)fee * (__int128)o.size;
            __int128 rhs = (__int128)o.fee * (__int128)size;
            if (lhs != rhs) return lhs < rhs;

            // tie-breaker: smaller size loses? (optional)
            if (size != o.size) return size < o.size;

            // final tie-breaker: txid
            return txid < o.txid;
        }
    };
    std::set<FeeRateKey> fee_rate_index_;

    // outpoint → txid
    std::map<OutPoint, Hash256> spent_index_;

    void AddToIndexes(const MempoolEntry& entry);
    void RemoveFromIndexes(const MempoolEntry& entry);

    static bool ComputeFee(
        const Transaction& tx,
        const IUtxoView& utxos,
        int64_t& out_fee,
        std::string* err = nullptr);
};

} // namespace sost

