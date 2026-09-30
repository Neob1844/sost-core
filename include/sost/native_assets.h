#pragma once
// -----------------------------------------------------------------------------
// SOST Native Assets (V30000) — model + canonical serialization (STEP 2).
//
// Sovereign, minimal, non-custodial token layer on the SOST UTXO. An asset is
// NEVER new SOST: asset value lives in the output PAYLOAD ({asset_id, amount});
// the output's SOST `amount` field only carries dust/fee economics. SOST supply
// and STOCKS_PER_SOST are unchanged.
//
// Uniqueness without a name registry / arbitrating authority:
//     asset_id = SHA256( genesis_txid(32) || genesis_vout(4 LE) )
// Genesis outpoints are globally unique, so asset_id is collision-free by
// construction. symbol/name are display-only and NON-unique.
//
// This header is model + (de)serialization + field-bound validation ONLY.
// Consensus rules (per-asset conservation, supply/cap, authority, overflow,
// asset/SOST separation) live in the validator (STEP 3). All types are gated by
// native_assets_active_at() (params.h); below activation the validator rejects
// them, so pre-activation / historical replay is byte-identical.
// -----------------------------------------------------------------------------
#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "sost/transaction.h"   // Byte, Hash256, OUT_ASSET_*
#include "sost/types.h"         // Bytes32
#include "sost/crypto.h"        // sha256

namespace sost {

// ---- field limits (consensus) ----
inline constexpr size_t   ASSET_SYMBOL_MAX             = 12;   // display, non-unique
inline constexpr size_t   ASSET_NAME_MAX               = 32;   // display, non-unique
inline constexpr uint8_t  ASSET_DECIMALS_MAX           = 18;
inline constexpr uint8_t  ASSET_POLICY_FIXED           = 0;    // mint-once at genesis, no reissue
inline constexpr uint8_t  ASSET_POLICY_CAPPED_REISSUABLE = 1;  // issuer may issue more up to max_supply
inline constexpr uint8_t  ASSET_DEF_VERSION            = 1;
inline constexpr size_t   ASSET_ID_LEN                 = 32;
// asset-carrying output payload = [asset_id(32) | amount(8 LE)]
inline constexpr size_t   ASSET_AMOUNT_PAYLOAD_LEN     = 40;
// issuance-authority output payload = [asset_id(32)]
inline constexpr size_t   ASSET_AUTH_PAYLOAD_LEN       = 32;
// an asset-carrying output must hold >= this many SOST stocks so it is economically
// spendable and not a zero-fee spam vector (SOST-side dust rule).
inline constexpr int64_t  ASSET_OUTPUT_DUST_STOCKS     = 1;
// hard ceiling on any single asset's max_supply (base units). Kept well below
// UINT64_MAX so per-asset conservation sums never overflow uint64 (a tx has a
// bounded number of outputs, each <= max_supply <= this ceiling).
inline constexpr uint64_t ASSET_MAX_SUPPLY_CEILING     = 4611686018427387904ULL; // 2^62

// ---- asset_id: deterministic, collision-free from the genesis outpoint ----
inline Bytes32 compute_asset_id(const Hash256& genesis_txid, uint32_t genesis_vout) {
    std::vector<uint8_t> buf;
    buf.reserve(ASSET_ID_LEN + 4);
    buf.insert(buf.end(), genesis_txid.begin(), genesis_txid.end());
    for (int i = 0; i < 4; ++i) buf.push_back((uint8_t)((genesis_vout >> (8 * i)) & 0xff)); // LE
    return sha256(buf.data(), buf.size());
}

// ---- asset definition (carried in the OUT_ASSET_GENESIS_DEF payload) ----
struct AssetDef {
    std::string symbol;                       // <= ASSET_SYMBOL_MAX
    std::string name;                         // <= ASSET_NAME_MAX
    uint8_t     decimals{0};                  // 0..18
    uint8_t     supply_policy{ASSET_POLICY_FIXED};
    uint64_t    max_supply{0};                // base units; FIXED: == genesis mint; CAPPED: ceiling
    Bytes32     manifest_hash{};              // Passport manifest SHA-256 (all-zero = none)
};

// canonical layout: [ver(1)][symlen(1)][sym][namelen(1)][name][decimals(1)]
//                   [policy(1)][max_supply(8 LE)][manifest_hash(32)]
inline std::vector<uint8_t> serialize_asset_def(const AssetDef& d) {
    std::vector<uint8_t> o;
    o.push_back(ASSET_DEF_VERSION);
    o.push_back((uint8_t)d.symbol.size());
    o.insert(o.end(), d.symbol.begin(), d.symbol.end());
    o.push_back((uint8_t)d.name.size());
    o.insert(o.end(), d.name.begin(), d.name.end());
    o.push_back(d.decimals);
    o.push_back(d.supply_policy);
    for (int i = 0; i < 8; ++i) o.push_back((uint8_t)((d.max_supply >> (8 * i)) & 0xff)); // LE
    o.insert(o.end(), d.manifest_hash.begin(), d.manifest_hash.end());
    return o;
}

// Strict, bounds-checked, CANONICAL parse (rejects trailing bytes / bad fields).
// Field-bound validation only — supply/authority/conservation are the validator's job.
inline bool parse_asset_def(const std::vector<uint8_t>& p, AssetDef& out, std::string* err = nullptr) {
    auto fail = [&](const char* m) { if (err) *err = m; return false; };
    size_t i = 0;
    if (p.size() < 1)                       return fail("assetdef: empty");
    if (p[i++] != ASSET_DEF_VERSION)        return fail("assetdef: bad version");
    if (i >= p.size())                      return fail("assetdef: trunc symlen");
    uint8_t sl = p[i++];
    if (sl > ASSET_SYMBOL_MAX)              return fail("assetdef: symbol too long");
    if (i + sl > p.size())                  return fail("assetdef: trunc symbol");
    out.symbol.assign((const char*)&p[i], sl); i += sl;
    if (i >= p.size())                      return fail("assetdef: trunc namelen");
    uint8_t nl = p[i++];
    if (nl > ASSET_NAME_MAX)                return fail("assetdef: name too long");
    if (i + nl > p.size())                  return fail("assetdef: trunc name");
    out.name.assign((const char*)&p[i], nl); i += nl;
    if (i + 1 + 1 + 8 + 32 > p.size())      return fail("assetdef: trunc tail");
    out.decimals = p[i++];
    if (out.decimals > ASSET_DECIMALS_MAX)  return fail("assetdef: decimals > 18");
    out.supply_policy = p[i++];
    if (out.supply_policy != ASSET_POLICY_FIXED &&
        out.supply_policy != ASSET_POLICY_CAPPED_REISSUABLE)
                                            return fail("assetdef: bad policy");
    uint64_t ms = 0; for (int b = 0; b < 8; ++b) ms |= (uint64_t)p[i++] << (8 * b);
    out.max_supply = ms;
    if (out.max_supply == 0)                return fail("assetdef: max_supply must be > 0");
    if (out.max_supply > ASSET_MAX_SUPPLY_CEILING)
                                            return fail("assetdef: max_supply exceeds ceiling");
    for (int b = 0; b < 32; ++b) out.manifest_hash[b] = p[i++];
    if (i != p.size())                      return fail("assetdef: trailing bytes"); // canonical
    return true;
}

// ---- asset-carrying (transfer / burn) output payload: [asset_id(32)][amount(8 LE)] ----
inline std::vector<uint8_t> serialize_asset_amount(const Bytes32& asset_id, uint64_t amount) {
    std::vector<uint8_t> o; o.reserve(ASSET_AMOUNT_PAYLOAD_LEN);
    o.insert(o.end(), asset_id.begin(), asset_id.end());
    for (int i = 0; i < 8; ++i) o.push_back((uint8_t)((amount >> (8 * i)) & 0xff)); // LE
    return o;
}
inline bool parse_asset_amount(const std::vector<uint8_t>& p, Bytes32& asset_id,
                               uint64_t& amount, std::string* err = nullptr) {
    if (p.size() != ASSET_AMOUNT_PAYLOAD_LEN) { if (err) *err = "asset payload: bad length"; return false; }
    for (int i = 0; i < 32; ++i) asset_id[i] = p[i];
    uint64_t a = 0; for (int b = 0; b < 8; ++b) a |= (uint64_t)p[32 + b] << (8 * b);
    amount = a;
    if (amount == 0)                     { if (err) *err = "asset amount must be > 0"; return false; }
    if (amount > ASSET_MAX_SUPPLY_CEILING) { if (err) *err = "asset amount exceeds ceiling"; return false; }
    return true;
}

// ---- issuance-authority output payload: [asset_id(32)] ----
inline std::vector<uint8_t> serialize_asset_auth(const Bytes32& asset_id) {
    return std::vector<uint8_t>(asset_id.begin(), asset_id.end());
}
inline bool parse_asset_auth(const std::vector<uint8_t>& p, Bytes32& asset_id, std::string* err = nullptr) {
    if (p.size() != ASSET_AUTH_PAYLOAD_LEN) { if (err) *err = "asset auth payload: bad length"; return false; }
    for (int i = 0; i < 32; ++i) asset_id[i] = p[i];
    return true;
}

// ---- output-type classifiers (consensus helpers) ----
// carries an {asset_id, amount} pair (contributes to per-asset conservation sums)
inline bool is_asset_amount_output(uint8_t t) {
    return t == OUT_ASSET_TRANSFER || t == OUT_ASSET_BURN;
}
inline bool is_asset_output(uint8_t t) {
    return t == OUT_ASSET_TRANSFER || t == OUT_ASSET_ISSUE_AUTH ||
           t == OUT_ASSET_BURN     || t == OUT_ASSET_GENESIS_DEF;
}
// spendable in a later tx (creates a live UTXO with an asset facet)
inline bool is_spendable_asset_output(uint8_t t) {
    return t == OUT_ASSET_TRANSFER || t == OUT_ASSET_ISSUE_AUTH;
}

} // namespace sost
