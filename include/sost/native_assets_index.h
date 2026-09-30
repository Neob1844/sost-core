#pragma once
// -----------------------------------------------------------------------------
// SOST Native Assets (V30000) — asset index (chain state) + reorg-safe apply/undo
// (STEP 4 / 11 / 12).
//
// The asset index is derived chain state, exactly like the UTXO set: a map
// asset_id -> {AssetDef, issued, burned}. It is reproducible by replaying the
// chain and is bounded (one entry per created asset). apply_asset_tx_to_index()
// mutates it forward and returns an AssetIndexDelta that undo_asset_index_delta()
// reverses byte-for-byte — so a reorg that disconnects a block restores the index
// exactly (the deltas are journaled in BlockUndo alongside spent UTXOs).
//
// Only ASSET_GENESIS / ASSET_ISSUE / ASSET_BURN change supply; ASSET_TRANSFER
// leaves the index untouched (pure UTXO movement). apply MUST be called only on a
// tx that already passed validate_asset_tx() at this height.
// -----------------------------------------------------------------------------
#include <cstdint>
#include <map>
#include <optional>

#include "sost/transaction.h"
#include "sost/native_assets.h"
#include "sost/native_assets_validation.h"   // AssetState, IAssetView

namespace sost {

// Journalled reversal record for one applied asset tx.
struct AssetIndexDelta {
    uint8_t  kind{0};          // 0 = no-op (transfer), 1 = genesis, 2 = issue, 3 = burn
    Bytes32  asset_id{};
    uint64_t prev_issued{0};   // for issue/burn undo
    uint64_t prev_burned{0};
};

// In-memory asset index; also serves as the IAssetView the validator consumes.
class NativeAssetIndex : public IAssetView {
public:
    const AssetState* GetAsset(const Bytes32& id) const override {
        auto it = assets_.find(id);
        return it == assets_.end() ? nullptr : &it->second;
    }
    size_t size() const { return assets_.size(); }
    void clear() { assets_.clear(); }
    const std::map<Bytes32, AssetState>& map() const { return assets_; }

    // Apply a VALIDATED asset tx forward. Returns the undo delta. `txid` is the tx id.
    AssetIndexDelta apply(const Transaction& tx, const Hash256& txid) {
        AssetIndexDelta d;
        switch (tx.tx_type) {
            case TX_TYPE_ASSET_GENESIS: {
                // locate the def output + its vout, and the minted amount for this asset
                AssetDef def; size_t def_vout = 0; bool have_def = false;
                for (size_t i = 0; i < tx.outputs.size(); ++i)
                    if (tx.outputs[i].type == OUT_ASSET_GENESIS_DEF) {
                        parse_asset_def(tx.outputs[i].payload, def); def_vout = i; have_def = true; break;
                    }
                if (!have_def) { d.kind = 0; return d; }             // defensive (validated upstream)
                Bytes32 id = compute_asset_id(txid, (uint32_t)def_vout);
                uint64_t mint = 0;
                for (const auto& o : tx.outputs)
                    if (o.type == OUT_ASSET_TRANSFER) {
                        Bytes32 aid; uint64_t a;
                        if (parse_asset_amount(o.payload, aid, a) && aid == id) mint += a;
                    }
                AssetState st; st.def = def; st.issued = mint; st.burned = 0;
                assets_[id] = st;
                d.kind = 1; d.asset_id = id;
                return d;
            }
            case TX_TYPE_ASSET_ISSUE: {
                // single asset minted (validated); find it + amount
                Bytes32 id{}; uint64_t mint = 0; bool found = false;
                for (const auto& o : tx.outputs)
                    if (o.type == OUT_ASSET_TRANSFER) {
                        Bytes32 aid; uint64_t a;
                        if (parse_asset_amount(o.payload, aid, a)) { id = aid; mint += a; found = true; }
                    }
                if (!found) { d.kind = 0; return d; }
                auto it = assets_.find(id);
                if (it == assets_.end()) { d.kind = 0; return d; }   // defensive
                d.kind = 2; d.asset_id = id; d.prev_issued = it->second.issued;
                it->second.issued += mint;
                return d;
            }
            case TX_TYPE_ASSET_BURN: {
                Bytes32 id{}; uint64_t burned = 0; bool found = false;
                for (const auto& o : tx.outputs)
                    if (o.type == OUT_ASSET_BURN) {
                        Bytes32 aid; uint64_t a;
                        if (parse_asset_amount(o.payload, aid, a)) { id = aid; burned += a; found = true; }
                    }
                if (!found) { d.kind = 0; return d; }
                auto it = assets_.find(id);
                if (it == assets_.end()) { d.kind = 0; return d; }
                d.kind = 3; d.asset_id = id; d.prev_burned = it->second.burned;
                it->second.burned += burned;
                return d;
            }
            default:  // TX_TYPE_ASSET_TRANSFER (or non-asset): no index change
                d.kind = 0;
                return d;
        }
    }

    // Reverse a previously-applied delta (reorg disconnect). Deltas of a block are
    // undone in REVERSE order of application.
    void undo(const AssetIndexDelta& d) {
        switch (d.kind) {
            case 1: assets_.erase(d.asset_id); break;                       // genesis -> remove
            case 2: { auto it = assets_.find(d.asset_id); if (it != assets_.end()) it->second.issued = d.prev_issued; } break;
            case 3: { auto it = assets_.find(d.asset_id); if (it != assets_.end()) it->second.burned = d.prev_burned; } break;
            default: break;                                                  // no-op
        }
    }

private:
    std::map<Bytes32, AssetState> assets_;
};

} // namespace sost
