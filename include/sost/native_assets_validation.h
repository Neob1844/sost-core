#pragma once
// -----------------------------------------------------------------------------
// SOST Native Assets (V30000) — consensus validation core (STEP 3-8).
//
// Pure, deterministic validation of the four asset transaction types
// (ASSET_GENESIS / ASSET_ISSUE / ASSET_TRANSFER / ASSET_BURN) against:
//   - per-asset conservation      (sum asset inputs == sum asset outputs, per id)
//   - supply / cap accounting      (issued+mint <= max_supply; FIXED mints exactly cap)
//   - issuance authority           (ISSUE must spend the asset's live auth UTXO)
//   - anti-overflow                (all sums in unsigned __int128, ceiling-checked)
//   - strict SOST/asset separation (asset value never affects SOST value)
//   - duplicate-genesis prevention (asset_id from a spent outpoint can't recur)
//
// SOST value conservation + input signatures for these txs are enforced by the
// node's existing standard machinery (the asset validator is layered ON TOP and
// only judges the ASSET dimension). This header is pure logic over an asset-index
// view + a UTXO view, so it is unit- and adversarially-testable in isolation.
// -----------------------------------------------------------------------------
#include <array>
#include <cstdint>
#include <map>
#include <string>

#include "sost/transaction.h"
#include "sost/tx_validation.h"   // IUtxoView, UTXOEntry, OutPoint
#include "sost/params.h"          // native_assets_active_at
#include "sost/native_assets.h"

namespace sost {

// Per-asset chain state (the "asset index"): the immutable definition + derived
// running totals. issued = genesis mint + all ISSUE mints; burned = all ASSET_BURN.
// circulating = issued - burned (always reproducible from chain).
struct AssetState {
    AssetDef def;
    uint64_t issued{0};
    uint64_t burned{0};
};

// Read-only asset-index view (the node backs this with its persisted index).
class IAssetView {
public:
    virtual ~IAssetView() = default;
    // nullptr if the asset does not exist (yet).
    virtual const AssetState* GetAsset(const Bytes32& id) const = 0;
};

enum class AssetTxResult {
    OK = 0,
    NOT_ACTIVE,            // below activation height
    NOT_AN_ASSET_TX,       // tx_type not an ASSET_* type
    BAD_PAYLOAD,           // malformed asset payload
    GENESIS_DUP,           // asset_id already exists
    GENESIS_SHAPE,         // wrong genesis structure (def count, mixed assets, etc.)
    GENESIS_SUPPLY,        // genesis mint != cap (FIXED) or > cap (CAPPED)
    UNKNOWN_ASSET,         // referenced asset does not exist
    NOT_REISSUABLE,        // ISSUE on a FIXED asset
    NO_AUTHORITY,          // ISSUE without spending the live issuance-authority UTXO
    CAP_EXCEEDED,          // issued + mint > max_supply
    CONSERVATION,          // sum(asset inputs) != sum(asset outputs) for some asset
    BURN_SHAPE,            // burn tx without a positive burn output
    ASSET_SOST_CONFUSION,  // asset value leaked into a SOST field or vice versa
    OVERFLOW_,             // amount/sum overflow or over ceiling
    MIXED_TYPES,           // disallowed output/input mix for this tx_type
};

inline const char* asset_tx_result_str(AssetTxResult r) {
    switch (r) {
        case AssetTxResult::OK: return "OK";
        case AssetTxResult::NOT_ACTIVE: return "native assets not active at height";
        case AssetTxResult::NOT_AN_ASSET_TX: return "not an asset tx";
        case AssetTxResult::BAD_PAYLOAD: return "malformed asset payload";
        case AssetTxResult::GENESIS_DUP: return "duplicate asset genesis";
        case AssetTxResult::GENESIS_SHAPE: return "bad genesis structure";
        case AssetTxResult::GENESIS_SUPPLY: return "genesis mint vs cap mismatch";
        case AssetTxResult::UNKNOWN_ASSET: return "unknown asset";
        case AssetTxResult::NOT_REISSUABLE: return "asset is not reissuable";
        case AssetTxResult::NO_AUTHORITY: return "issue without issuance authority";
        case AssetTxResult::CAP_EXCEEDED: return "issue exceeds max supply";
        case AssetTxResult::CONSERVATION: return "asset conservation violated";
        case AssetTxResult::BURN_SHAPE: return "burn without positive burn output";
        case AssetTxResult::ASSET_SOST_CONFUSION: return "asset/SOST value confusion";
        case AssetTxResult::OVERFLOW_: return "amount overflow / over ceiling";
        case AssetTxResult::MIXED_TYPES: return "disallowed type mix for this tx_type";
    }
    return "?";
}

namespace detail {
// overflow-safe accumulator bounded by the per-asset ceiling
inline bool add_ceil(unsigned __int128& acc, uint64_t v) {
    acc += (unsigned __int128)v;
    return acc <= (unsigned __int128)ASSET_MAX_SUPPLY_CEILING;
}
} // namespace detail

// Validate the ASSET dimension of a transaction. `txid` is this tx's canonical id
// (the node computes it; used to derive the genesis asset_id). Pure & deterministic.
inline AssetTxResult validate_asset_tx(const Transaction& tx,
                                       const Hash256& txid,
                                       const IUtxoView& utxos,
                                       const IAssetView& assets,
                                       int64_t height,
                                       std::string* err = nullptr) {
    auto set = [&](AssetTxResult r) { if (err) *err = asset_tx_result_str(r); return r; };

    const uint8_t tt = tx.tx_type;
    if (tt != TX_TYPE_ASSET_GENESIS && tt != TX_TYPE_ASSET_ISSUE &&
        tt != TX_TYPE_ASSET_TRANSFER && tt != TX_TYPE_ASSET_BURN)
        return AssetTxResult::NOT_AN_ASSET_TX;               // caller shouldn't route non-asset txs here
    if (!native_assets_active_at(height)) return set(AssetTxResult::NOT_ACTIVE);

    // ---- gather per-asset INPUT amounts + spent issuance authorities ----
    std::map<Bytes32, unsigned __int128> in_amt;
    std::map<Bytes32, int> auth_spent;   // asset_id -> count of auth UTXOs spent
    for (const auto& tin : tx.inputs) {
        OutPoint op; op.txid = tin.prev_txid; op.index = tin.prev_index;
        auto u = utxos.GetUTXO(op);
        if (!u) continue;                                   // SOST-side validity handled elsewhere
        if (u->type == OUT_ASSET_TRANSFER) {
            Bytes32 id; uint64_t a;
            if (!parse_asset_amount(u->payload, id, a)) return set(AssetTxResult::BAD_PAYLOAD);
            if (!detail::add_ceil(in_amt[id], a)) return set(AssetTxResult::OVERFLOW_);
        } else if (u->type == OUT_ASSET_ISSUE_AUTH) {
            Bytes32 id;
            if (!parse_asset_auth(u->payload, id)) return set(AssetTxResult::BAD_PAYLOAD);
            auth_spent[id] += 1;
        }
        // any other UTXO type = SOST-only, irrelevant to asset conservation
    }

    // ---- gather per-asset OUTPUT amounts, burns, auth creations, genesis def ----
    std::map<Bytes32, unsigned __int128> out_amt;   // OUT_ASSET_TRANSFER
    std::map<Bytes32, unsigned __int128> burn_amt;  // OUT_ASSET_BURN
    std::map<Bytes32, int> auth_created;
    int genesis_def_count = 0; size_t genesis_def_vout = 0; AssetDef gdef;
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        const auto& o = tx.outputs[i];
        switch (o.type) {
            case OUT_ASSET_TRANSFER: {
                Bytes32 id; uint64_t a;
                if (!parse_asset_amount(o.payload, id, a)) return set(AssetTxResult::BAD_PAYLOAD);
                if (o.amount < ASSET_OUTPUT_DUST_STOCKS) return set(AssetTxResult::ASSET_SOST_CONFUSION);
                if (!detail::add_ceil(out_amt[id], a)) return set(AssetTxResult::OVERFLOW_);
            } break;
            case OUT_ASSET_BURN: {
                Bytes32 id; uint64_t a;
                if (!parse_asset_amount(o.payload, id, a)) return set(AssetTxResult::BAD_PAYLOAD);
                if (!detail::add_ceil(burn_amt[id], a)) return set(AssetTxResult::OVERFLOW_);
            } break;
            case OUT_ASSET_ISSUE_AUTH: {
                Bytes32 id;
                if (!parse_asset_auth(o.payload, id)) return set(AssetTxResult::BAD_PAYLOAD);
                if (o.amount < ASSET_OUTPUT_DUST_STOCKS) return set(AssetTxResult::ASSET_SOST_CONFUSION);
                auth_created[id] += 1;
            } break;
            case OUT_ASSET_GENESIS_DEF: {
                if (!parse_asset_def(o.payload, gdef)) return set(AssetTxResult::BAD_PAYLOAD);
                genesis_def_count += 1; genesis_def_vout = i;
            } break;
            default: break; // OUT_TRANSFER etc. = SOST-only; asset value never here
        }
    }

    // ============================ per-type rules ============================
    if (tt == TX_TYPE_ASSET_GENESIS) {
        (void)genesis_def_vout;
        if (genesis_def_count != 1) return set(AssetTxResult::GENESIS_SHAPE);
        if (tx.inputs.empty()) return set(AssetTxResult::GENESIS_SHAPE);  // need an outpoint to derive id
        if (!in_amt.empty()) return set(AssetTxResult::GENESIS_SHAPE);   // genesis consumes no assets
        if (!burn_amt.empty()) return set(AssetTxResult::GENESIS_SHAPE);
        // asset_id derives from the FIRST INPUT's outpoint (unique, known before outputs are
        // built) — NOT from this tx's txid, which would be circular (the mint output carries
        // the asset_id, so it cannot depend on the txid that hashes that output).
        Bytes32 new_id = compute_asset_id(tx.inputs[0].prev_txid, tx.inputs[0].prev_index);
        if (assets.GetAsset(new_id) != nullptr) return set(AssetTxResult::GENESIS_DUP);
        // every asset-bearing output must reference exactly this new asset_id
        for (const auto& kv : out_amt)      if (!(kv.first == new_id)) return set(AssetTxResult::GENESIS_SHAPE);
        for (const auto& kv : auth_created) if (!(kv.first == new_id)) return set(AssetTxResult::GENESIS_SHAPE);
        unsigned __int128 mint = out_amt.count(new_id) ? out_amt[new_id] : 0;
        if (mint == 0) return set(AssetTxResult::GENESIS_SUPPLY);
        if (mint > (unsigned __int128)gdef.max_supply) return set(AssetTxResult::GENESIS_SUPPLY);
        if (gdef.supply_policy == ASSET_POLICY_FIXED) {
            if (mint != (unsigned __int128)gdef.max_supply) return set(AssetTxResult::GENESIS_SUPPLY);
            if (auth_created.count(new_id)) return set(AssetTxResult::GENESIS_SHAPE);   // FIXED: no authority
        } else { // CAPPED_REISSUABLE: exactly one authority created
            if (auth_created[new_id] != 1) return set(AssetTxResult::GENESIS_SHAPE);
        }
        return AssetTxResult::OK;
    }

    if (tt == TX_TYPE_ASSET_ISSUE) {
        if (genesis_def_count != 0) return set(AssetTxResult::MIXED_TYPES);
        if (!burn_amt.empty()) return set(AssetTxResult::MIXED_TYPES);
        // exactly one asset receives new units and exactly its authority is spent
        if (out_amt.size() != 1) return set(AssetTxResult::GENESIS_SHAPE);
        const Bytes32 id = out_amt.begin()->first;
        const AssetState* st = assets.GetAsset(id);
        if (!st) return set(AssetTxResult::UNKNOWN_ASSET);
        if (st->def.supply_policy != ASSET_POLICY_CAPPED_REISSUABLE) return set(AssetTxResult::NOT_REISSUABLE);
        if (auth_spent[id] < 1) return set(AssetTxResult::NO_AUTHORITY);
        // ISSUE mints from nothing: no asset transfer INPUTS of this id allowed
        if (in_amt.count(id)) return set(AssetTxResult::MIXED_TYPES);
        // authority must be recreated (continue) or omitted (permanently sealed): 0 or 1
        if (auth_created[id] > 1) return set(AssetTxResult::GENESIS_SHAPE);
        for (const auto& kv : auth_created) if (!(kv.first == id)) return set(AssetTxResult::MIXED_TYPES);
        unsigned __int128 mint = out_amt[id];
        unsigned __int128 after = (unsigned __int128)st->issued + mint;
        if (after > (unsigned __int128)st->def.max_supply) return set(AssetTxResult::CAP_EXCEEDED);
        if (after > (unsigned __int128)ASSET_MAX_SUPPLY_CEILING) return set(AssetTxResult::OVERFLOW_);
        return AssetTxResult::OK;
    }

    if (tt == TX_TYPE_ASSET_TRANSFER) {
        if (genesis_def_count != 0 || !burn_amt.empty()) return set(AssetTxResult::MIXED_TYPES);
        if (!auth_created.empty() || !auth_spent.empty()) return set(AssetTxResult::MIXED_TYPES);
        if (in_amt.empty()) return set(AssetTxResult::CONSERVATION);
        // strict per-asset conservation over the union of touched asset ids
        std::map<Bytes32, bool> ids;
        for (auto& kv : in_amt) ids[kv.first] = true;
        for (auto& kv : out_amt) ids[kv.first] = true;
        for (auto& kv : ids) {
            unsigned __int128 vi = in_amt.count(kv.first) ? in_amt[kv.first] : 0;
            unsigned __int128 vo = out_amt.count(kv.first) ? out_amt[kv.first] : 0;
            if (vi != vo) return set(AssetTxResult::CONSERVATION);
        }
        return AssetTxResult::OK;
    }

    // TX_TYPE_ASSET_BURN
    if (genesis_def_count != 0) return set(AssetTxResult::MIXED_TYPES);
    if (!auth_created.empty() || !auth_spent.empty()) return set(AssetTxResult::MIXED_TYPES);
    if (burn_amt.empty()) return set(AssetTxResult::BURN_SHAPE);
    {
        std::map<Bytes32, bool> ids;
        for (auto& kv : in_amt) ids[kv.first] = true;
        for (auto& kv : out_amt) ids[kv.first] = true;
        for (auto& kv : burn_amt) ids[kv.first] = true;
        bool any_burn = false;
        for (auto& kv : ids) {
            unsigned __int128 vi = in_amt.count(kv.first) ? in_amt[kv.first] : 0;
            unsigned __int128 vo = out_amt.count(kv.first) ? out_amt[kv.first] : 0;
            unsigned __int128 vb = burn_amt.count(kv.first) ? burn_amt[kv.first] : 0;
            if (vb > 0) {
                any_burn = true;
                if (assets.GetAsset(kv.first) == nullptr) return set(AssetTxResult::UNKNOWN_ASSET);
            }
            // inputs == transferred-out + burned  (burn destroys the difference)
            if (vi != vo + vb) return set(AssetTxResult::CONSERVATION);
        }
        if (!any_burn) return set(AssetTxResult::BURN_SHAPE);
    }
    return AssetTxResult::OK;
}

} // namespace sost
