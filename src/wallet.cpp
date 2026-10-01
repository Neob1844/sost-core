// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// wallet.cpp — SOST Wallet (real secp256k1 keys via tx_signer)
#include "sost/wallet.h"
#include "sost/serialize.h"
#include "sost/emission.h"
#include "sost/popc_v15.h"      // POPC_V15_MARKER_PKH (testnet PoPC carrier tooling)

#include <openssl/sha.h>
#include <openssl/rand.h>
#include <openssl/evp.h>
#include <openssl/kdf.h>

#include <fstream>
#include <sstream>
#include <algorithm>
#include <cstring>
#include <cstdio>

namespace sost {

// =============================================================================
// Construction
// =============================================================================

Wallet::Wallet() {}

// =============================================================================
// Key management
// =============================================================================

WalletKey Wallet::generate_key(const std::string& label) {
    WalletKey wk;
    std::string err;
    if (!GenerateKeyPair(wk.privkey, wk.pubkey, &err)) {
        throw std::runtime_error("generate_key: " + err);
    }
    wk.pkh = ComputePubKeyHash(wk.pubkey);
    wk.address = address_encode(wk.pkh);
    wk.label = label;

    addr_index_[wk.address] = keys_.size();
    keys_.push_back(wk);
    return wk;
}

WalletKey Wallet::import_privkey(const PrivKey& privkey, const std::string& label) {
    WalletKey wk;
    wk.privkey = privkey;

    std::string err;
    if (!DerivePublicKey(privkey, wk.pubkey, &err)) {
        throw std::runtime_error("import_privkey: " + err);
    }
    wk.pkh = ComputePubKeyHash(wk.pubkey);
    wk.address = address_encode(wk.pkh);
    wk.label = label;

    // Don't import duplicates
    if (addr_index_.count(wk.address)) {
        return keys_[addr_index_[wk.address]];
    }

    addr_index_[wk.address] = keys_.size();
    keys_.push_back(wk);
    return wk;
}

bool Wallet::has_address(const std::string& addr) const {
    return addr_index_.count(addr) > 0;
}

const WalletKey* Wallet::find_key(const std::string& addr) const {
    auto it = addr_index_.find(addr);
    if (it == addr_index_.end()) return nullptr;
    return &keys_[it->second];
}

const WalletKey* Wallet::find_key_by_pkh(const PubKeyHash& pkh) const {
    std::string addr = address_encode(pkh);
    return find_key(addr);
}

const WalletKey* Wallet::find_key_by_label(const std::string& label) const {
    if (label.empty()) return nullptr;
    for (const auto& k : keys_) {
        if (k.label == label) return &k;
    }
    return nullptr;
}

std::string Wallet::default_address() const {
    if (keys_.empty()) return "";
    return keys_[0].address;
}

void Wallet::rebuild_index() {
    addr_index_.clear();
    for (size_t i = 0; i < keys_.size(); ++i) {
        addr_index_[keys_[i].address] = i;
    }
}

// =============================================================================
// UTXO management
// =============================================================================

void Wallet::add_utxo(const WalletUTXO& utxo) {
    // Check for duplicate
    for (const auto& u : utxos_) {
        if (u.txid == utxo.txid && u.vout == utxo.vout) return;
    }
    utxos_.push_back(utxo);
}

void Wallet::mark_spent(const Hash256& txid, uint32_t vout) {
    for (auto& u : utxos_) {
        if (u.txid == txid && u.vout == vout) {
            u.spent = true;
            return;
        }
    }
}

// =============================================================================
// Maturity filter
// =============================================================================

bool Wallet::is_mature(const WalletUTXO& u, int64_t chain_height) {
    if (chain_height < 0) return true;  // no filtering

    bool is_cb = (u.output_type == OUT_COINBASE_MINER ||
                  u.output_type == OUT_COINBASE_GOLD  ||
                  u.output_type == OUT_COINBASE_POPC);
    if (!is_cb) return true;

    if (u.height < 0) return false;  // unconfirmed coinbase = never mature

    return (chain_height - u.height) >= COINBASE_MATURITY;
}

// =============================================================================
// Maturity-aware queries
// =============================================================================

std::vector<WalletUTXO> Wallet::list_unspent(int64_t chain_height) const {
    std::vector<WalletUTXO> result;
    for (const auto& u : utxos_) {
        if (u.spent) continue;
        if (!is_mature(u, chain_height)) continue;
        result.push_back(u);
    }
    return result;
}

std::vector<WalletUTXO> Wallet::list_unspent(const std::string& addr, int64_t chain_height) const {
    PubKeyHash pkh{};
    if (!address_decode(addr, pkh)) return {};
    std::vector<WalletUTXO> result;
    for (const auto& u : utxos_) {
        if (u.spent || u.pkh != pkh) continue;
        if (!is_mature(u, chain_height)) continue;
        result.push_back(u);
    }
    return result;
}

int64_t Wallet::balance(int64_t chain_height) const {
    int64_t total = 0;
    for (const auto& u : utxos_) {
        if (u.spent) continue;
        if (!is_mature(u, chain_height)) continue;
        total += u.amount;
    }
    return total;
}

int64_t Wallet::balance(const std::string& addr, int64_t chain_height) const {
    PubKeyHash pkh{};
    if (!address_decode(addr, pkh)) return 0;
    int64_t total = 0;
    for (const auto& u : utxos_) {
        if (u.spent || u.pkh != pkh) continue;
        if (!is_mature(u, chain_height)) continue;
        total += u.amount;
    }
    return total;
}

int64_t Wallet::locked_balance(int64_t chain_height) const {
    int64_t total = 0;
    for (const auto& u : utxos_) {
        if (u.spent) continue;
        if (u.output_type != OUT_BOND_LOCK && u.output_type != OUT_ESCROW_LOCK) continue;
        if (chain_height >= 0 && (uint64_t)chain_height >= u.lock_until) continue; // unlocked
        total += u.amount;
    }
    return total;
}

int64_t Wallet::available_balance(int64_t chain_height) const {
    return balance(chain_height) - locked_balance(chain_height);
}

std::vector<WalletUTXO> Wallet::list_bonds(int64_t chain_height) const {
    std::vector<WalletUTXO> result;
    for (const auto& u : utxos_) {
        if (u.spent) continue;
        if (u.output_type != OUT_BOND_LOCK && u.output_type != OUT_ESCROW_LOCK) continue;
        if (!is_mature(u, chain_height)) continue;
        result.push_back(u);
    }
    return result;
}

size_t Wallet::num_utxos() const {
    size_t count = 0;
    for (const auto& u : utxos_) {
        if (!u.spent) ++count;
    }
    return count;
}

// =============================================================================
// Genesis import
// =============================================================================

// Minimal JSON string value extractor (no dependency on json library)
static std::string json_string_value(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    auto end = json.find('"', pos + 1);
    if (end == std::string::npos) return "";
    return json.substr(pos + 1, end - pos - 1);
}

static int64_t json_int_value(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return -1;
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return -1;
    while (pos + 1 < json.size() && (json[pos + 1] == ' ' || json[pos + 1] == '\t')) ++pos;
    return std::stoll(json.substr(pos + 1));
}

bool Wallet::import_genesis(const std::string& genesis_json_path, std::string* err) {
    std::ifstream f(genesis_json_path);
    if (!f) {
        if (err) *err = "cannot open " + genesis_json_path;
        return false;
    }
    std::string json((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());

    std::string block_id_hex = json_string_value(json, "block_id");
    if (block_id_hex.size() != 64) {
        if (err) *err = "invalid block_id in genesis JSON";
        return false;
    }
    Hash256 block_id = from_hex(block_id_hex);

    int64_t miner_amt  = json_int_value(json, "miner");
    int64_t gold_amt   = json_int_value(json, "gold_vault");
    int64_t popc_amt   = json_int_value(json, "popc_pool");

    if (miner_amt <= 0 && gold_amt <= 0 && popc_amt <= 0) {
        int64_t total = json_int_value(json, "subsidy");
        if (total > 0) {
            CoinbaseSplit split = coinbase_split(total);
            miner_amt = split.miner;
            gold_amt  = split.gold_vault;
            popc_amt  = split.popc_pool;
        } else {
            if (err) *err = "cannot find subsidy amounts in genesis JSON";
            return false;
        }
    }

    const char* addrs[3] = {
        "sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33",
        "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d",
        "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",
    };
    int64_t amounts[3] = { miner_amt, gold_amt, popc_amt };

    int imported = 0;
    for (int i = 0; i < 3; ++i) {
        if (has_address(addrs[i])) {
            PubKeyHash pkh{};
            address_decode(addrs[i], pkh);

            WalletUTXO utxo;
            utxo.txid = block_id;
            utxo.vout = (uint32_t)i;
            utxo.amount = amounts[i];
            utxo.output_type = (i == 0) ? 0x01 : (i == 1) ? 0x02 : 0x03;
            utxo.pkh = pkh;
            utxo.height = 0;
            utxo.spent = false;

            add_utxo(utxo);
            ++imported;
        }
    }

    if (imported == 0) {
        if (err) *err = "no wallet addresses match genesis coinbase outputs";
        return false;
    }

    return true;
}

// =============================================================================
// Transaction creation
// =============================================================================

bool Wallet::create_transaction(
    const std::string& to_addr,
    int64_t amount,
    int64_t fee,
    const Hash256& genesis_hash,
    Transaction& out_tx,
    int64_t chain_height,
    std::string* err,
    const std::vector<Byte>* capsule_payload,
    bool mark_spent,
    const PubKeyHash* from_pkh,
    const std::vector<Byte>* popc_carrier_payload)
{
    if (amount <= 0) {
        if (err) *err = "amount must be positive";
        return false;
    }
    if (fee < 0) {
        if (err) *err = "fee must be non-negative";
        return false;
    }

    PubKeyHash to_pkh{};
    if (!address_decode(to_addr, to_pkh)) {
        if (err) *err = "invalid destination address: " + to_addr;
        return false;
    }

    int64_t needed = amount + fee;

    // Select UTXOs (simple: oldest first) — maturity-aware
    auto unspent = list_unspent(chain_height);

    std::vector<size_t> selected;
    int64_t total_in = 0;

    for (size_t i = 0; i < unspent.size(); ++i) {
        const auto& u = unspent[i];
        // Only spend UTXOs we have keys for
        if (!find_key_by_pkh(u.pkh)) continue;
        // --from-label / --from-address pin: restrict to one source pkh.
        if (from_pkh && u.pkh != *from_pkh) continue;
        // Never spend constitutional UTXOs (gold vault, popc pool) in transfers
        std::string utxo_addr = address_encode(u.pkh);
        if (utxo_addr == "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d" ||  // GOLD VAULT
            utxo_addr == "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f") {  // POPC POOL
            continue;
        }
        selected.push_back(i);
        total_in += u.amount;
        if (total_in >= needed) break;
    }

// ==========================================================================
// PATCH for wallet.cpp — replace the "insufficient funds" block inside
// create_transaction() with this version.
//
// FIND this code (around line ~240):
//
//     if (total_in < needed) {
//         if (err) {
//             char buf[128];
//             snprintf(buf, sizeof(buf),
//                 "insufficient funds: have %lld stocks, need %lld",
//                 (long long)total_in, (long long)needed);
//             *err = buf;
//         }
//         return false;
//     }
//
// REPLACE WITH:
// ==========================================================================

    if (total_in < needed) {
        if (err) {
            // v1.3: distinguish "no mature balance" from "not enough total"
            //       so the user knows WHY the tx failed
            int64_t immature_total = 0;
            int     immature_count = 0;
            int64_t earliest_height = INT64_MAX;

            for (const auto& u : utxos_) {
                if (u.spent) continue;
                if (!is_mature(u, chain_height)) {
                    immature_total += u.amount;
                    immature_count++;
                    if (u.height >= 0 && u.height < earliest_height)
                        earliest_height = u.height;
                }
            }

            char buf[512];
            if (immature_count > 0 && total_in == 0) {
                // All funds are immature — common case before height 1000
                int64_t first_matures_at = earliest_height + COINBASE_MATURITY;
                snprintf(buf, sizeof(buf),
                    "insufficient mature balance\n"
                    "  Spendable:  0 SOST (0 mature UTXOs)\n"
                    "  Immature:   %lld.%08lld SOST (%d coinbase UTXOs)\n"
                    "  Need:       %lld confirmations per coinbase (COINBASE_MATURITY)\n"
                    "  Current height: %lld\n"
                    "  First UTXO matures at height: %lld  (~%lld blocks to go)",
                    (long long)(immature_total / 100000000LL),
                    (long long)(immature_total % 100000000LL),
                    immature_count,
                    (long long)COINBASE_MATURITY,
                    (long long)chain_height,
                    (long long)first_matures_at,
                    (long long)(first_matures_at - chain_height));
            } else if (immature_count > 0) {
                // Some funds mature, some not — but not enough mature
                snprintf(buf, sizeof(buf),
                    "insufficient mature funds: have %lld.%08lld SOST spendable, "
                    "need %lld.%08lld SOST\n"
                    "  (%d additional coinbase UTXOs with %lld.%08lld SOST still immature)",
                    (long long)(total_in / 100000000LL),
                    (long long)(total_in % 100000000LL),
                    (long long)(needed / 100000000LL),
                    (long long)(needed % 100000000LL),
                    immature_count,
                    (long long)(immature_total / 100000000LL),
                    (long long)(immature_total % 100000000LL));
            } else {
                // Genuinely insufficient — no immature UTXOs either
                snprintf(buf, sizeof(buf),
                    "insufficient funds: have %lld.%08lld SOST, need %lld.%08lld SOST",
                    (long long)(total_in / 100000000LL),
                    (long long)(total_in % 100000000LL),
                    (long long)(needed / 100000000LL),
                    (long long)(needed % 100000000LL));
            }
            *err = buf;
        }
        return false;
    }

    // Build transaction
    out_tx = Transaction{};
    out_tx.version = 1;
    out_tx.tx_type = 0x00;  // TRANSFER

    // Inputs — reference the original utxos_ vector for txid/vout
    for (size_t idx : selected) {
        const auto& u = unspent[idx];
        TxInput inp{};
        inp.prev_txid = u.txid;
        inp.prev_index = u.vout;
        out_tx.inputs.push_back(inp);
    }

    // Output 0: payment (with optional capsule payload attached).
    // The payload is signed in alongside the rest of the output bytes;
    // mempool / standardness validation runs ValidateCapsulePolicy on it
    // post-broadcast. Caller must build a valid SCPv1 capsule —
    // see sost/capsule.h::BuildXxxPayload helpers.
    {
        TxOutput out{};
        out.amount = amount;
        out.type = 0x00;
        out.pubkey_hash = to_pkh;
        if (capsule_payload && !capsule_payload->empty()) {
            out.payload = *capsule_payload;
        }
        out_tx.outputs.push_back(out);
    }

    // Optional PoPC V15 carrier: an extra 0-value output to the unspendable
    // marker pkh carrying the (already-signed) carrier payload. Appended before
    // change so it is committed in every input's sighash.
    if (popc_carrier_payload && !popc_carrier_payload->empty()) {
        TxOutput carrier{};
        carrier.amount = 0;
        carrier.type = 0x00;
        for (size_t i = 0; i < carrier.pubkey_hash.size() && i < sost::POPC_V15_MARKER_PKH.size(); ++i)
            carrier.pubkey_hash[i] = sost::POPC_V15_MARKER_PKH[i];
        carrier.payload = *popc_carrier_payload;
        out_tx.outputs.push_back(carrier);
    }

    // Output: change (if any). Returns to the explicit source address
    // when from_pkh is set (so spending from key A never silently moves
    // change to key B); otherwise falls back to the first input's pkh.
    int64_t change = total_in - needed;
    if (change > 0) {
        const PubKeyHash& change_pkh = from_pkh ? *from_pkh
                                                : unspent[selected[0]].pkh;
        const WalletKey* change_key = find_key_by_pkh(change_pkh);
        if (!change_key) {
            if (err) *err = "internal error: no key for change address";
            return false;
        }
        TxOutput out{};
        out.amount = change;
        out.type = 0x00;
        out.pubkey_hash = change_key->pkh;
        out_tx.outputs.push_back(out);
    }

    // Sign each input
    for (size_t i = 0; i < selected.size(); ++i) {
        const auto& u = unspent[selected[i]];
        const WalletKey* key = find_key_by_pkh(u.pkh);
        if (!key) {
            if (err) *err = "no private key for UTXO";
            return false;
        }

        SpentOutput spent;
        spent.amount = u.amount;
        spent.type = u.output_type;

        if (!SignTransactionInput(out_tx, i, spent, genesis_hash, key->privkey, err)) {
            return false;
        }
    }

    // Mark UTXOs as spent in the main utxos_ vector. Skipped when
    // mark_spent=false; the caller (typically a CLI fee-pass loop) is then
    // responsible for calling mark_tx_inputs_spent(tx) after broadcast OK.
    if (mark_spent) {
        for (size_t idx : selected) {
            const auto& u = unspent[idx];
            this->mark_spent(u.txid, u.vout);
        }
    }

    return true;
}

// =============================================================================
// sendmany — single tx, N outputs, one input set, one change output.
//
// Mirrors create_transaction() above but accepts a recipient vector instead
// of a single (addr, amount) pair. Output ordering: recipients in input
// order, then change output (if any) appended last. Constitutional UTXO
// guard preserved (gold vault / popc pool never spent).
// =============================================================================
bool Wallet::create_transaction_many(
    const std::vector<Recipient>& recipients,
    int64_t fee,
    const Hash256& genesis_hash,
    Transaction& out_tx,
    int64_t chain_height,
    std::string* err)
{
    if (recipients.empty()) {
        if (err) *err = "no recipients";
        return false;
    }
    if (fee < 0) {
        if (err) *err = "fee must be non-negative";
        return false;
    }

    // Decode all destination addresses up front.
    std::vector<PubKeyHash> to_pkhs;
    to_pkhs.reserve(recipients.size());
    int64_t total_out = 0;
    for (size_t i = 0; i < recipients.size(); ++i) {
        const auto& r = recipients[i];
        if (r.amount <= 0) {
            if (err) {
                char buf[128];
                snprintf(buf, sizeof(buf),
                    "recipient %zu (%s): amount must be positive",
                    i, r.address.c_str());
                *err = buf;
            }
            return false;
        }
        PubKeyHash pkh{};
        if (!address_decode(r.address, pkh)) {
            if (err) *err = "invalid destination address: " + r.address;
            return false;
        }
        to_pkhs.push_back(pkh);
        total_out += r.amount;
    }

    int64_t needed = total_out + fee;

    // Select UTXOs (oldest first) — maturity-aware, constitutional-aware.
    auto unspent = list_unspent(chain_height);
    std::vector<size_t> selected;
    int64_t total_in = 0;
    for (size_t i = 0; i < unspent.size(); ++i) {
        const auto& u = unspent[i];
        if (!find_key_by_pkh(u.pkh)) continue;
        std::string utxo_addr = address_encode(u.pkh);
        if (utxo_addr == "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d" ||
            utxo_addr == "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f") continue;
        selected.push_back(i);
        total_in += u.amount;
        if (total_in >= needed) break;
    }

    if (total_in < needed) {
        if (err) {
            char buf[256];
            snprintf(buf, sizeof(buf),
                "insufficient funds: have %lld.%08lld SOST, need %lld.%08lld SOST "
                "(%zu recipients + fee)",
                (long long)(total_in / 100000000LL),
                (long long)(total_in % 100000000LL),
                (long long)(needed / 100000000LL),
                (long long)(needed % 100000000LL),
                recipients.size());
            *err = buf;
        }
        return false;
    }

    out_tx = Transaction{};
    out_tx.version = 1;
    out_tx.tx_type = 0x00;  // TRANSFER

    for (size_t idx : selected) {
        const auto& u = unspent[idx];
        TxInput inp{};
        inp.prev_txid  = u.txid;
        inp.prev_index = u.vout;
        out_tx.inputs.push_back(inp);
    }

    // Outputs 0..N-1: recipients in declared order.
    for (size_t i = 0; i < recipients.size(); ++i) {
        TxOutput out{};
        out.amount = recipients[i].amount;
        out.type   = 0x00;
        out.pubkey_hash = to_pkhs[i];
        out_tx.outputs.push_back(out);
    }

    // Optional change output appended last → first input's address.
    int64_t change = total_in - needed;
    if (change > 0) {
        const WalletKey* change_key = find_key_by_pkh(unspent[selected[0]].pkh);
        if (!change_key) {
            if (err) *err = "internal error: no key for change address";
            return false;
        }
        TxOutput out{};
        out.amount = change;
        out.type   = 0x00;
        out.pubkey_hash = change_key->pkh;
        out_tx.outputs.push_back(out);
    }

    // Sign each input.
    for (size_t i = 0; i < selected.size(); ++i) {
        const auto& u = unspent[selected[i]];
        const WalletKey* key = find_key_by_pkh(u.pkh);
        if (!key) {
            if (err) *err = "no private key for UTXO";
            return false;
        }
        SpentOutput spent;
        spent.amount = u.amount;
        spent.type   = u.output_type;
        if (!SignTransactionInput(out_tx, i, spent, genesis_hash, key->privkey, err)) {
            return false;
        }
    }

    // NOTE: do NOT mark inputs as spent here. The CLI's sendmany flow
    // calls this function 2-3 times during fee estimation; marking inputs
    // on the first pass would either drop them from list_unspent on
    // subsequent passes or force a re-sync between passes. Caller must
    // invoke Wallet::mark_tx_inputs_spent(tx) ONLY after the broadcast
    // succeeds — that way an aborted/rejected tx leaves the wallet's
    // local UTXO state untouched.
    return true;
}

// =============================================================================
// Bond/Escrow transaction creation
// =============================================================================

bool Wallet::create_bond_transaction(
    int64_t amount,
    int64_t fee,
    uint64_t lock_until,
    const Hash256& genesis_hash,
    Transaction& out_tx,
    int64_t chain_height,
    std::string* err)
{
    if (amount <= 0) { if (err) *err = "amount must be positive"; return false; }
    if (fee < 0) { if (err) *err = "fee must be non-negative"; return false; }

    int64_t needed = amount + fee;
    auto unspent = list_unspent(chain_height);

    // Select spendable UTXOs (exclude locked bonds, constitutional addresses)
    std::vector<size_t> selected;
    int64_t total_in = 0;
    for (size_t i = 0; i < unspent.size(); ++i) {
        const auto& u = unspent[i];
        if (!find_key_by_pkh(u.pkh)) continue;
        // Skip constitutional
        std::string utxo_addr = address_encode(u.pkh);
        if (utxo_addr == "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d" ||
            utxo_addr == "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f") continue;
        // Skip still-locked bonds/escrows
        if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) &&
            chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
        selected.push_back(i);
        total_in += u.amount;
        if (total_in >= needed) break;
    }

    if (total_in < needed) {
        if (err) {
            char buf[256];
            snprintf(buf, sizeof(buf),
                "insufficient funds: have %lld stocks, need %lld",
                (long long)total_in, (long long)needed);
            *err = buf;
        }
        return false;
    }

    out_tx = Transaction{};
    out_tx.version = 1;
    out_tx.tx_type = TX_TYPE_STANDARD;

    for (size_t idx : selected) {
        const auto& u = unspent[idx];
        TxInput inp{};
        inp.prev_txid = u.txid;
        inp.prev_index = u.vout;
        out_tx.inputs.push_back(inp);
    }

    // Output 0: BOND_LOCK — locks to the sender's own address
    {
        const WalletKey* sender_key = find_key_by_pkh(unspent[selected[0]].pkh);
        TxOutput out{};
        out.amount = amount;
        out.type = OUT_BOND_LOCK;
        out.pubkey_hash = sender_key->pkh;
        WriteLockUntil(out.payload, lock_until);
        out_tx.outputs.push_back(out);
    }

    // Output 1: change
    int64_t change = total_in - needed;
    if (change > 0) {
        const WalletKey* change_key = find_key_by_pkh(unspent[selected[0]].pkh);
        TxOutput out{};
        out.amount = change;
        out.type = OUT_TRANSFER;
        out.pubkey_hash = change_key->pkh;
        out_tx.outputs.push_back(out);
    }

    // Sign
    for (size_t i = 0; i < selected.size(); ++i) {
        const auto& u = unspent[selected[i]];
        const WalletKey* key = find_key_by_pkh(u.pkh);
        SpentOutput spent;
        spent.amount = u.amount;
        spent.type = u.output_type;
        if (!SignTransactionInput(out_tx, i, spent, genesis_hash, key->privkey, err))
            return false;
    }

    for (size_t idx : selected) {
        const auto& u = unspent[idx];
        mark_spent(u.txid, u.vout);
    }
    return true;
}

bool Wallet::create_escrow_transaction(
    int64_t amount,
    int64_t fee,
    uint64_t lock_until,
    const PubKeyHash& beneficiary_pkh,
    const Hash256& genesis_hash,
    Transaction& out_tx,
    int64_t chain_height,
    std::string* err)
{
    if (amount <= 0) { if (err) *err = "amount must be positive"; return false; }
    if (fee < 0) { if (err) *err = "fee must be non-negative"; return false; }

    int64_t needed = amount + fee;
    auto unspent = list_unspent(chain_height);

    std::vector<size_t> selected;
    int64_t total_in = 0;
    for (size_t i = 0; i < unspent.size(); ++i) {
        const auto& u = unspent[i];
        if (!find_key_by_pkh(u.pkh)) continue;
        std::string utxo_addr = address_encode(u.pkh);
        if (utxo_addr == "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d" ||
            utxo_addr == "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f") continue;
        if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) &&
            chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
        selected.push_back(i);
        total_in += u.amount;
        if (total_in >= needed) break;
    }

    if (total_in < needed) {
        if (err) {
            char buf[256];
            snprintf(buf, sizeof(buf),
                "insufficient funds: have %lld stocks, need %lld",
                (long long)total_in, (long long)needed);
            *err = buf;
        }
        return false;
    }

    out_tx = Transaction{};
    out_tx.version = 1;
    out_tx.tx_type = TX_TYPE_STANDARD;

    for (size_t idx : selected) {
        const auto& u = unspent[idx];
        TxInput inp{};
        inp.prev_txid = u.txid;
        inp.prev_index = u.vout;
        out_tx.inputs.push_back(inp);
    }

    // Output 0: ESCROW_LOCK — locks to sender, with beneficiary in payload
    {
        const WalletKey* sender_key = find_key_by_pkh(unspent[selected[0]].pkh);
        TxOutput out{};
        out.amount = amount;
        out.type = OUT_ESCROW_LOCK;
        out.pubkey_hash = sender_key->pkh;
        // Payload: lock_until (8 bytes) + beneficiary_pkh (20 bytes) = 28 bytes
        WriteLockUntil(out.payload, lock_until);
        out.payload.resize(28);
        std::copy(beneficiary_pkh.begin(), beneficiary_pkh.end(),
                  out.payload.begin() + 8);
        out_tx.outputs.push_back(out);
    }

    // Output 1: change
    int64_t change = total_in - needed;
    if (change > 0) {
        const WalletKey* change_key = find_key_by_pkh(unspent[selected[0]].pkh);
        TxOutput out{};
        out.amount = change;
        out.type = OUT_TRANSFER;
        out.pubkey_hash = change_key->pkh;
        out_tx.outputs.push_back(out);
    }

    // Sign
    for (size_t i = 0; i < selected.size(); ++i) {
        const auto& u = unspent[selected[i]];
        const WalletKey* key = find_key_by_pkh(u.pkh);
        SpentOutput spent;
        spent.amount = u.amount;
        spent.type = u.output_type;
        if (!SignTransactionInput(out_tx, i, spent, genesis_hash, key->privkey, err))
            return false;
    }

    for (size_t idx : selected) {
        const auto& u = unspent[idx];
        mark_spent(u.txid, u.vout);
    }
    return true;
}

// ===========================================================================
// V30000 — native asset transaction builders. Mirror create_bond_transaction:
// select the sender's spendable UTXOs, build typed outputs + change, sign each
// input. SOST value conservation: sum(SOST in) == dust*(#asset outputs) + fee +
// SOST change. Asset value lives in the output payload, never in the SOST amount.
// ===========================================================================
namespace {
constexpr const char* kConstA = "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d";
constexpr const char* kConstB = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f";
} // namespace

// Common: pick SOST-spendable UTXOs (own key, not asset, not locked, not constitutional)
// up to `need_stocks`; returns indices + total. Returns false if insufficient.
bool Wallet::create_asset_genesis_transaction(
    const AssetDef& def, uint64_t mint_amount, int64_t dust, int64_t fee,
    const Hash256& genesis_hash, Transaction& out_tx, Bytes32* out_asset_id,
    int64_t chain_height, std::string* err)
{
    if (mint_amount == 0) { if (err) *err = "mint_amount must be > 0"; return false; }
    if (dust <= 0 || fee < 0) { if (err) *err = "bad dust/fee"; return false; }
    if (def.supply_policy == ASSET_POLICY_FIXED && mint_amount != def.max_supply) {
        if (err) *err = "FIXED asset must mint exactly max_supply"; return false; }
    if (mint_amount > def.max_supply) { if (err) *err = "mint > max_supply"; return false; }

    int n_asset_out = 2 + (def.supply_policy == ASSET_POLICY_CAPPED_REISSUABLE ? 1 : 0); // def+mint(+auth)
    int64_t need = fee + dust * (int64_t)n_asset_out;
    auto unspent = list_unspent(chain_height);
    std::vector<size_t> sel; int64_t total_in = 0;
    for (size_t i = 0; i < unspent.size() && total_in < need; ++i) {
        const auto& u = unspent[i];
        if (!find_key_by_pkh(u.pkh)) continue;
        if (sost::is_asset_output(u.output_type)) continue;   // asset UTXO not SOST-spendable for fee
        std::string a = address_encode(u.pkh);
        if (a == kConstA || a == kConstB) continue;
        if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) &&
            chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
        sel.push_back(i); total_in += u.amount;
    }
    if (total_in < need) { if (err) *err = "insufficient SOST for genesis fee+dust"; return false; }

    out_tx = Transaction{}; out_tx.version = 1; out_tx.tx_type = TX_TYPE_ASSET_GENESIS;
    for (size_t idx : sel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    const PubKeyHash sender = unspent[sel[0]].pkh;
    Bytes32 asset_id = sost::compute_asset_id(out_tx.inputs[0].prev_txid, out_tx.inputs[0].prev_index);
    if (out_asset_id) *out_asset_id = asset_id;
    // output 0: genesis def
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_GENESIS_DEF; o.pubkey_hash = sender; o.payload = sost::serialize_asset_def(def); out_tx.outputs.push_back(o); }
    // output 1: mint to sender
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = sender; o.payload = sost::serialize_asset_amount(asset_id, mint_amount); out_tx.outputs.push_back(o); }
    // output 2 (CAPPED only): issuance authority to sender
    if (def.supply_policy == ASSET_POLICY_CAPPED_REISSUABLE) {
        TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_ISSUE_AUTH; o.pubkey_hash = sender; o.payload = sost::serialize_asset_auth(asset_id); out_tx.outputs.push_back(o); }
    // SOST change
    int64_t change = total_in - need;
    if (change > 0) { TxOutput o{}; o.amount = change; o.type = OUT_TRANSFER; o.pubkey_hash = sender; out_tx.outputs.push_back(o); }
    // sign
    for (size_t i = 0; i < sel.size(); ++i) {
        const auto& u = unspent[sel[i]]; const WalletKey* k = find_key_by_pkh(u.pkh);
        SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type;
        if (!SignTransactionInput(out_tx, i, sp, genesis_hash, k->privkey, err)) return false;
    }
    for (size_t idx : sel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    return true;
}

// Shared helper for transfer/burn: select the sender's asset UTXOs of `asset_id`
// (>= want) + SOST UTXOs for the fee/dust shortfall. `out_tx` gets inputs + the
// asset change output; caller adds the destination/burn output before signing.
bool Wallet::create_asset_transfer_transaction(
    const Bytes32& asset_id, const PubKeyHash& to_pkh, uint64_t asset_amount,
    int64_t dust, int64_t fee, const Hash256& genesis_hash, Transaction& out_tx,
    int64_t chain_height, std::string* err)
{
    if (asset_amount == 0) { if (err) *err = "asset_amount must be > 0"; return false; }
    if (dust <= 0 || fee < 0) { if (err) *err = "bad dust/fee"; return false; }
    auto unspent = list_unspent(chain_height);
    // 1) select asset UTXOs of this id
    std::vector<size_t> asel; uint64_t asset_in = 0; int64_t asset_dust_in = 0;
    for (size_t i = 0; i < unspent.size() && asset_in < asset_amount; ++i) {
        const auto& u = unspent[i];
        if (u.output_type != OUT_ASSET_TRANSFER) continue;
        if (!find_key_by_pkh(u.pkh)) continue;
        Bytes32 aid; uint64_t amt;
        if (!sost::parse_asset_amount(u.payload, aid, amt) || !(aid == asset_id)) continue;
        asel.push_back(i); asset_in += amt; asset_dust_in += u.amount;
    }
    if (asset_in < asset_amount) { if (err) *err = "insufficient asset balance"; return false; }
    uint64_t asset_change = asset_in - asset_amount;
    int n_asset_out = 1 + (asset_change > 0 ? 1 : 0);
    // 2) SOST needed = fee + dust*(#asset outputs) - asset dust already flowing in
    int64_t need_sost = fee + dust * (int64_t)n_asset_out - asset_dust_in;
    std::vector<size_t> ssel; int64_t sost_in = 0;
    if (need_sost > 0) {
        for (size_t i = 0; i < unspent.size() && sost_in < need_sost; ++i) {
            const auto& u = unspent[i];
            if (!find_key_by_pkh(u.pkh)) continue;
            if (sost::is_asset_output(u.output_type)) continue;
            std::string a = address_encode(u.pkh);
            if (a == kConstA || a == kConstB) continue;
            if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) &&
                chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
            ssel.push_back(i); sost_in += u.amount;
        }
        if (sost_in < need_sost) { if (err) *err = "insufficient SOST for fee/dust"; return false; }
    }
    out_tx = Transaction{}; out_tx.version = 1; out_tx.tx_type = TX_TYPE_ASSET_TRANSFER;
    for (size_t idx : asel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    for (size_t idx : ssel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    const PubKeyHash sender = unspent[asel[0]].pkh;
    // dest asset output
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = to_pkh; o.payload = sost::serialize_asset_amount(asset_id, asset_amount); out_tx.outputs.push_back(o); }
    // asset change
    if (asset_change > 0) { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = sender; o.payload = sost::serialize_asset_amount(asset_id, asset_change); out_tx.outputs.push_back(o); }
    // SOST change = (asset dust in + sost in) - dust*(#asset outputs) - fee
    int64_t sost_change = (asset_dust_in + sost_in) - dust * (int64_t)n_asset_out - fee;
    if (sost_change > 0) { TxOutput o{}; o.amount = sost_change; o.type = OUT_TRANSFER; o.pubkey_hash = sender; out_tx.outputs.push_back(o); }
    // sign all inputs (asset then sost)
    size_t si = 0;
    for (size_t idx : asel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : ssel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : asel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    for (size_t idx : ssel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    return true;
}

bool Wallet::create_asset_swap_transaction(
    const Bytes32& asset_id, uint64_t asset_amount,
    const PubKeyHash& asset_from, const PubKeyHash& asset_to,
    const PubKeyHash& sost_from, const PubKeyHash& sost_to,
    uint64_t price_sost, int64_t dust, int64_t fee,
    const Hash256& genesis_hash, Transaction& out_tx, int64_t chain_height, std::string* err)
{
    if (asset_amount == 0) { if (err) *err = "asset_amount must be > 0"; return false; }
    if (price_sost == 0)  { if (err) *err = "price_sost must be > 0"; return false; }
    if (dust <= 0 || fee < 0) { if (err) *err = "bad dust/fee"; return false; }
    auto unspent = list_unspent(chain_height);
    // 1) asset side: select seller's (asset_from) asset UTXOs of this id
    std::vector<size_t> asel; uint64_t asset_in = 0; int64_t asset_dust_in = 0;
    for (size_t i = 0; i < unspent.size() && asset_in < asset_amount; ++i) {
        const auto& u = unspent[i];
        if (u.output_type != OUT_ASSET_TRANSFER) continue;
        if (!(u.pkh == asset_from) || !find_key_by_pkh(u.pkh)) continue;
        Bytes32 aid; uint64_t amt;
        if (!sost::parse_asset_amount(u.payload, aid, amt) || !(aid == asset_id)) continue;
        asel.push_back(i); asset_in += amt; asset_dust_in += u.amount;
    }
    if (asset_in < asset_amount) { if (err) *err = "insufficient asset balance (seller)"; return false; }
    uint64_t asset_change = asset_in - asset_amount;
    int n_asset_out = 1 + (asset_change > 0 ? 1 : 0);
    // 2) SOST side: buyer (sost_from) must cover price + fee + dust*(#asset outputs),
    //    reusing the seller's inbound asset dust.
    int64_t need_sost = (int64_t)price_sost + fee + dust * (int64_t)n_asset_out - asset_dust_in;
    std::vector<size_t> ssel; int64_t sost_in = 0;
    for (size_t i = 0; i < unspent.size() && sost_in < need_sost; ++i) {
        const auto& u = unspent[i];
        if (!(u.pkh == sost_from) || !find_key_by_pkh(u.pkh)) continue;
        if (sost::is_asset_output(u.output_type)) continue;
        std::string a = address_encode(u.pkh);
        if (a == kConstA || a == kConstB) continue;
        if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) &&
            chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
        ssel.push_back(i); sost_in += u.amount;
    }
    if (sost_in < need_sost) { if (err) *err = "insufficient SOST (buyer) for price+fee"; return false; }
    out_tx = Transaction{}; out_tx.version = 1; out_tx.tx_type = TX_TYPE_ASSET_TRANSFER;
    for (size_t idx : asel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    for (size_t idx : ssel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    // asset -> buyer
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = asset_to; o.payload = sost::serialize_asset_amount(asset_id, asset_amount); out_tx.outputs.push_back(o); }
    // asset change -> seller
    if (asset_change > 0) { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = asset_from; o.payload = sost::serialize_asset_amount(asset_id, asset_change); out_tx.outputs.push_back(o); }
    // SOST price -> seller
    { TxOutput o{}; o.amount = (int64_t)price_sost; o.type = OUT_TRANSFER; o.pubkey_hash = sost_to; out_tx.outputs.push_back(o); }
    // SOST change -> buyer
    int64_t sost_change = (asset_dust_in + sost_in) - (int64_t)price_sost - dust * (int64_t)n_asset_out - fee;
    if (sost_change > 0) { TxOutput o{}; o.amount = sost_change; o.type = OUT_TRANSFER; o.pubkey_hash = sost_from; out_tx.outputs.push_back(o); }
    // sign all inputs (asset then sost)
    size_t si = 0;
    for (size_t idx : asel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : ssel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : asel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    for (size_t idx : ssel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    return true;
}

bool Wallet::create_asset_burn_transaction(
    const Bytes32& asset_id, uint64_t asset_amount, int64_t dust, int64_t fee,
    const Hash256& genesis_hash, Transaction& out_tx, int64_t chain_height, std::string* err)
{
    if (asset_amount == 0) { if (err) *err = "burn amount must be > 0"; return false; }
    if (dust <= 0 || fee < 0) { if (err) *err = "bad dust/fee"; return false; }
    auto unspent = list_unspent(chain_height);
    std::vector<size_t> asel; uint64_t asset_in = 0; int64_t asset_dust_in = 0;
    for (size_t i = 0; i < unspent.size() && asset_in < asset_amount; ++i) {
        const auto& u = unspent[i];
        if (u.output_type != OUT_ASSET_TRANSFER || !find_key_by_pkh(u.pkh)) continue;
        Bytes32 aid; uint64_t amt;
        if (!sost::parse_asset_amount(u.payload, aid, amt) || !(aid == asset_id)) continue;
        asel.push_back(i); asset_in += amt; asset_dust_in += u.amount;
    }
    if (asset_in < asset_amount) { if (err) *err = "insufficient asset balance to burn"; return false; }
    uint64_t asset_change = asset_in - asset_amount;
    int n_asset_out = 1 + (asset_change > 0 ? 1 : 0); // burn output (+ change)
    int64_t need_sost = fee + dust * (int64_t)n_asset_out - asset_dust_in;
    std::vector<size_t> ssel; int64_t sost_in = 0;
    if (need_sost > 0) {
        for (size_t i = 0; i < unspent.size() && sost_in < need_sost; ++i) {
            const auto& u = unspent[i];
            if (!find_key_by_pkh(u.pkh) || sost::is_asset_output(u.output_type)) continue;
            std::string a = address_encode(u.pkh); if (a == kConstA || a == kConstB) continue;
            if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) && chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
            ssel.push_back(i); sost_in += u.amount;
        }
        if (sost_in < need_sost) { if (err) *err = "insufficient SOST for burn fee/dust"; return false; }
    }
    out_tx = Transaction{}; out_tx.version = 1; out_tx.tx_type = TX_TYPE_ASSET_BURN;
    for (size_t idx : asel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    for (size_t idx : ssel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    const PubKeyHash sender = unspent[asel[0]].pkh;
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_BURN; o.pubkey_hash = sender; o.payload = sost::serialize_asset_amount(asset_id, asset_amount); out_tx.outputs.push_back(o); }
    if (asset_change > 0) { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = sender; o.payload = sost::serialize_asset_amount(asset_id, asset_change); out_tx.outputs.push_back(o); }
    int64_t sost_change = (asset_dust_in + sost_in) - dust * (int64_t)n_asset_out - fee;
    if (sost_change > 0) { TxOutput o{}; o.amount = sost_change; o.type = OUT_TRANSFER; o.pubkey_hash = sender; out_tx.outputs.push_back(o); }
    size_t si = 0;
    for (size_t idx : asel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : ssel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : asel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    for (size_t idx : ssel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    return true;
}

bool Wallet::create_asset_issue_transaction(
    const Bytes32& asset_id, uint64_t mint_amount, int64_t dust, int64_t fee,
    const Hash256& genesis_hash, Transaction& out_tx, int64_t chain_height, std::string* err)
{
    if (mint_amount == 0) { if (err) *err = "mint_amount must be > 0"; return false; }
    if (dust <= 0 || fee < 0) { if (err) *err = "bad dust/fee"; return false; }
    auto unspent = list_unspent(chain_height);
    // find the issuance-authority UTXO for this asset owned by us
    int auth_idx = -1; int64_t auth_dust = 0;
    for (size_t i = 0; i < unspent.size(); ++i) {
        const auto& u = unspent[i];
        if (u.output_type != OUT_ASSET_ISSUE_AUTH || !find_key_by_pkh(u.pkh)) continue;
        Bytes32 aid;
        if (sost::parse_asset_auth(u.payload, aid) && aid == asset_id) { auth_idx = (int)i; auth_dust = u.amount; break; }
    }
    if (auth_idx < 0) { if (err) *err = "no issuance-authority UTXO for this asset in wallet"; return false; }
    int n_asset_out = 2; // mint + recreated authority
    int64_t need_sost = fee + dust * (int64_t)n_asset_out - auth_dust;
    std::vector<size_t> ssel; int64_t sost_in = 0;
    if (need_sost > 0) {
        for (size_t i = 0; i < unspent.size() && sost_in < need_sost; ++i) {
            const auto& u = unspent[i];
            if (!find_key_by_pkh(u.pkh) || sost::is_asset_output(u.output_type)) continue;
            std::string a = address_encode(u.pkh); if (a == kConstA || a == kConstB) continue;
            if ((u.output_type == OUT_BOND_LOCK || u.output_type == OUT_ESCROW_LOCK) && chain_height >= 0 && (uint64_t)chain_height < u.lock_until) continue;
            ssel.push_back(i); sost_in += u.amount;
        }
        if (sost_in < need_sost) { if (err) *err = "insufficient SOST for issue fee/dust"; return false; }
    }
    out_tx = Transaction{}; out_tx.version = 1; out_tx.tx_type = TX_TYPE_ASSET_ISSUE;
    { TxInput in{}; in.prev_txid = unspent[auth_idx].txid; in.prev_index = unspent[auth_idx].vout; out_tx.inputs.push_back(in); }
    for (size_t idx : ssel) { TxInput in{}; in.prev_txid = unspent[idx].txid; in.prev_index = unspent[idx].vout; out_tx.inputs.push_back(in); }
    const PubKeyHash sender = unspent[auth_idx].pkh;
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_TRANSFER; o.pubkey_hash = sender; o.payload = sost::serialize_asset_amount(asset_id, mint_amount); out_tx.outputs.push_back(o); }
    { TxOutput o{}; o.amount = dust; o.type = OUT_ASSET_ISSUE_AUTH; o.pubkey_hash = sender; o.payload = sost::serialize_asset_auth(asset_id); out_tx.outputs.push_back(o); }
    int64_t sost_change = (auth_dust + sost_in) - dust * (int64_t)n_asset_out - fee;
    if (sost_change > 0) { TxOutput o{}; o.amount = sost_change; o.type = OUT_TRANSFER; o.pubkey_hash = sender; out_tx.outputs.push_back(o); }
    size_t si = 0;
    { const auto& u = unspent[auth_idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    for (size_t idx : ssel) { const auto& u = unspent[idx]; const WalletKey* k = find_key_by_pkh(u.pkh); SpentOutput sp; sp.amount = u.amount; sp.type = u.output_type; if (!SignTransactionInput(out_tx, si++, sp, genesis_hash, k->privkey, err)) return false; }
    mark_spent(unspent[auth_idx].txid, unspent[auth_idx].vout);
    for (size_t idx : ssel) mark_spent(unspent[idx].txid, unspent[idx].vout);
    return true;
}

// Walks tx.inputs and marks each (prev_txid, prev_index) as spent in the
// wallet's UTXO list. Used by callers that build a tx via the no-mark
// variants (create_transaction_many) and only want the local state to
// reflect the spend after the broadcast actually went through.
void Wallet::mark_tx_inputs_spent(const Transaction& tx) {
    for (const auto& in : tx.inputs) {
        mark_spent(in.prev_txid, in.prev_index);
    }
}

// =============================================================================
// Persistence — simple JSON format
// =============================================================================

static std::string to_hex(const uint8_t* data, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s;
    s.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        s += hx[data[i] >> 4];
        s += hx[data[i] & 0xF];
    }
    return s;
}

static bool from_hex_bytes(const std::string& hex, uint8_t* out, size_t len) {
    if (hex.size() != len * 2) return false;
    auto hv = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + c - 'a';
        if (c >= 'A' && c <= 'F') return 10 + c - 'A';
        return -1;
    };
    for (size_t i = 0; i < len; ++i) {
        int hi = hv(hex[i * 2]);
        int lo = hv(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

bool Wallet::save(const std::string& path, std::string* err) const {
    std::ofstream f(path);
    if (!f) {
        if (err) *err = "cannot open " + path + " for writing";
        return false;
    }

    f << "{\n";
    f << "  \"version\": 1,\n";
    f << "  \"warning\": \"PRIVATE KEYS ARE UNENCRYPTED — KEEP THIS FILE SECURE\",\n";

    f << "  \"keys\": [\n";
    for (size_t i = 0; i < keys_.size(); ++i) {
        const auto& k = keys_[i];
        f << "    {\n";
        f << "      \"privkey\": \"" << to_hex(k.privkey.data(), 32) << "\",\n";
        f << "      \"pubkey\": \"" << to_hex(k.pubkey.data(), 33) << "\",\n";
        f << "      \"address\": \"" << k.address << "\",\n";
        f << "      \"label\": \"" << k.label << "\"\n";
        f << "    }" << (i + 1 < keys_.size() ? "," : "") << "\n";
    }
    f << "  ],\n";

    f << "  \"utxos\": [\n";
    size_t utxo_count = 0;
    for (size_t i = 0; i < utxos_.size(); ++i) {
        const auto& u = utxos_[i];
        if (i > 0) f << ",\n";
        f << "    {\n";
        f << "      \"txid\": \"" << to_hex(u.txid.data(), 32) << "\",\n";
        f << "      \"vout\": " << u.vout << ",\n";
        f << "      \"amount\": " << u.amount << ",\n";
        f << "      \"output_type\": " << (int)u.output_type << ",\n";
        f << "      \"pkh\": \"" << to_hex(u.pkh.data(), 20) << "\",\n";
        f << "      \"height\": " << u.height << ",\n";
        f << "      \"spent\": " << (u.spent ? "true" : "false");
        if (u.lock_until > 0) {
            f << ",\n      \"lock_until\": " << u.lock_until;
            if (u.output_type == OUT_ESCROW_LOCK) {
                f << ",\n      \"beneficiary\": \"" << to_hex(u.beneficiary.data(), 20) << "\"";
            }
        }
        f << "\n";
        f << "    }";
        ++utxo_count;
    }
    if (utxo_count > 0) f << "\n";
    f << "  ]\n";
    f << "}\n";

    return true;
}

bool Wallet::load(const std::string& path, std::string* err) {
    std::ifstream f(path);
    if (!f) {
        if (err) *err = "cannot open " + path;
        return false;
    }

    std::string json((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());

    keys_.clear();
    utxos_.clear();
    addr_index_.clear();

    size_t pos = 0;
    while (true) {
        pos = json.find("\"privkey\"", pos);
        if (pos == std::string::npos) break;

        auto pk_start = json.find('"', pos + 9);
        if (pk_start == std::string::npos) break;
        pk_start++;
        auto pk_end = json.find('"', pk_start);
        if (pk_end == std::string::npos) break;
        std::string priv_hex = json.substr(pk_start, pk_end - pk_start);

        std::string label;
        auto label_pos = json.find("\"label\"", pk_end);
        if (label_pos != std::string::npos && label_pos < json.find("\"privkey\"", pk_end)) {
            auto lb_start = json.find('"', label_pos + 7);
            if (lb_start != std::string::npos) {
                lb_start++;
                auto lb_end = json.find('"', lb_start);
                if (lb_end != std::string::npos) {
                    label = json.substr(lb_start, lb_end - lb_start);
                }
            }
        }

        PrivKey priv{};
        if (from_hex_bytes(priv_hex, priv.data(), 32)) {
            try {
                import_privkey(priv, label);
            } catch (...) {
                // Skip invalid keys
            }
        }

        pos = pk_end + 1;
    }

    auto utxos_pos = json.find("\"utxos\"");
    if (utxos_pos != std::string::npos) {
        pos = utxos_pos;
        while (true) {
            auto txid_pos = json.find("\"txid\"", pos);
            if (txid_pos == std::string::npos) break;

            auto obj_start = json.rfind('{', txid_pos);
            auto obj_end = json.find('}', txid_pos);
            if (obj_start == std::string::npos || obj_end == std::string::npos) break;

            std::string obj = json.substr(obj_start, obj_end - obj_start + 1);

            WalletUTXO utxo{};

            std::string txid_hex = json_string_value(obj, "txid");
            if (txid_hex.size() == 64) {
                from_hex_bytes(txid_hex, utxo.txid.data(), 32);
            }

            utxo.vout = (uint32_t)json_int_value(obj, "vout");
            utxo.amount = json_int_value(obj, "amount");
            utxo.output_type = (uint8_t)json_int_value(obj, "output_type");

            std::string pkh_hex = json_string_value(obj, "pkh");
            if (pkh_hex.size() == 40) {
                from_hex_bytes(pkh_hex, utxo.pkh.data(), 20);
            }

            utxo.height = json_int_value(obj, "height");
            utxo.spent = (obj.find("\"spent\": true") != std::string::npos ||
                          obj.find("\"spent\":true") != std::string::npos);

            int64_t lu = json_int_value(obj, "lock_until");
            utxo.lock_until = (lu > 0) ? (uint64_t)lu : 0;

            std::string ben_hex = json_string_value(obj, "beneficiary");
            if (ben_hex.size() == 40) {
                from_hex_bytes(ben_hex, utxo.beneficiary.data(), 20);
            }

            utxos_.push_back(utxo);
            pos = obj_end + 1;
        }
    }

    return true;
}

// =============================================================================
// Encrypted persistence — AES-256-GCM + scrypt (v2 format)
// =============================================================================

static const uint64_t SCRYPT_N = 32768;  // 2^15
static const uint64_t SCRYPT_R = 8;
static const uint64_t SCRYPT_P = 1;
static const size_t   SCRYPT_KEYLEN = 32;  // AES-256
static const size_t   SALT_LEN = 32;
static const size_t   IV_LEN   = 12;      // GCM standard
static const size_t   TAG_LEN  = 16;      // GCM tag

static bool derive_key_scrypt(const std::string& passphrase,
                               const uint8_t* salt, size_t salt_len,
                               uint8_t* key_out) {
    EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new_id(EVP_PKEY_SCRYPT, nullptr);
    if (!ctx) return false;
    bool ok = false;
    do {
        if (EVP_PKEY_derive_init(ctx) <= 0) break;
        if (EVP_PKEY_CTX_set1_pbe_pass(ctx, passphrase.data(), passphrase.size()) <= 0) break;
        if (EVP_PKEY_CTX_set1_scrypt_salt(ctx, salt, salt_len) <= 0) break;
        if (EVP_PKEY_CTX_set_scrypt_N(ctx, SCRYPT_N) <= 0) break;
        if (EVP_PKEY_CTX_set_scrypt_r(ctx, SCRYPT_R) <= 0) break;
        if (EVP_PKEY_CTX_set_scrypt_p(ctx, SCRYPT_P) <= 0) break;
        size_t outlen = SCRYPT_KEYLEN;
        if (EVP_PKEY_derive(ctx, key_out, &outlen) <= 0) break;
        ok = true;
    } while (false);
    EVP_PKEY_CTX_free(ctx);
    return ok;
}

static bool aes256gcm_encrypt(const uint8_t* key, const uint8_t* iv,
                               const uint8_t* plaintext, size_t pt_len,
                               std::vector<uint8_t>& ciphertext,
                               uint8_t* tag_out) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;
    bool ok = false;
    ciphertext.resize(pt_len + 16);  // GCM doesn't expand, but be safe
    int outlen = 0, tmplen = 0;
    do {
        if (EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, IV_LEN, nullptr) != 1) break;
        if (EVP_EncryptInit_ex(ctx, nullptr, nullptr, key, iv) != 1) break;
        if (EVP_EncryptUpdate(ctx, ciphertext.data(), &outlen, plaintext, (int)pt_len) != 1) break;
        if (EVP_EncryptFinal_ex(ctx, ciphertext.data() + outlen, &tmplen) != 1) break;
        outlen += tmplen;
        ciphertext.resize(outlen);
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, TAG_LEN, tag_out) != 1) break;
        ok = true;
    } while (false);
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}

static bool aes256gcm_decrypt(const uint8_t* key, const uint8_t* iv,
                               const uint8_t* ciphertext, size_t ct_len,
                               const uint8_t* tag,
                               std::vector<uint8_t>& plaintext) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;
    bool ok = false;
    plaintext.resize(ct_len);
    int outlen = 0, tmplen = 0;
    do {
        if (EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, IV_LEN, nullptr) != 1) break;
        if (EVP_DecryptInit_ex(ctx, nullptr, nullptr, key, iv) != 1) break;
        if (EVP_DecryptUpdate(ctx, plaintext.data(), &outlen, ciphertext, (int)ct_len) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, TAG_LEN,
                                 const_cast<uint8_t*>(tag)) != 1) break;
        if (EVP_DecryptFinal_ex(ctx, plaintext.data() + outlen, &tmplen) != 1) break;
        outlen += tmplen;
        plaintext.resize(outlen);
        ok = true;
    } while (false);
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}

bool Wallet::save_encrypted(const std::string& path, const std::string& passphrase,
                             std::string* err) const {
    if (passphrase.empty()) {
        if (err) *err = "passphrase must not be empty";
        return false;
    }

    // Build plaintext keys blob: each key as "privkey_hex:label\n"
    std::string keys_plain;
    for (const auto& k : keys_) {
        keys_plain += to_hex(k.privkey.data(), 32) + ":" + k.label + "\n";
    }

    // Generate salt + IV
    uint8_t salt[SALT_LEN], iv[IV_LEN];
    if (RAND_bytes(salt, SALT_LEN) != 1 || RAND_bytes(iv, IV_LEN) != 1) {
        if (err) *err = "RAND_bytes failed";
        return false;
    }

    // Derive key
    uint8_t key[SCRYPT_KEYLEN];
    if (!derive_key_scrypt(passphrase, salt, SALT_LEN, key)) {
        if (err) *err = "scrypt key derivation failed";
        return false;
    }

    // Encrypt
    std::vector<uint8_t> ct;
    uint8_t tag[TAG_LEN];
    if (!aes256gcm_encrypt(key, iv,
                            reinterpret_cast<const uint8_t*>(keys_plain.data()),
                            keys_plain.size(), ct, tag)) {
        if (err) *err = "AES-256-GCM encryption failed";
        return false;
    }

    // Zeroize key material
    OPENSSL_cleanse(key, SCRYPT_KEYLEN);
    OPENSSL_cleanse(&keys_plain[0], keys_plain.size());

    // Write file
    std::ofstream f(path);
    if (!f) {
        if (err) *err = "cannot open " + path + " for writing";
        return false;
    }

    f << "{\n";
    f << "  \"version\": 2,\n";
    f << "  \"encrypted\": true,\n";
    f << "  \"scrypt_N\": " << SCRYPT_N << ",\n";
    f << "  \"scrypt_r\": " << SCRYPT_R << ",\n";
    f << "  \"scrypt_p\": " << SCRYPT_P << ",\n";
    f << "  \"salt\": \"" << to_hex(salt, SALT_LEN) << "\",\n";
    f << "  \"iv\": \"" << to_hex(iv, IV_LEN) << "\",\n";
    f << "  \"tag\": \"" << to_hex(tag, TAG_LEN) << "\",\n";
    f << "  \"keys_ct\": \"" << to_hex(ct.data(), ct.size()) << "\",\n";
    f << "  \"num_addresses\": " << keys_.size() << ",\n";

    // Public info (addresses) — not secret, useful for watch-only
    f << "  \"addresses\": [\n";
    for (size_t i = 0; i < keys_.size(); ++i) {
        f << "    \"" << keys_[i].address << "\"" << (i + 1 < keys_.size() ? "," : "") << "\n";
    }
    f << "  ],\n";

    // UTXOs — not encrypted
    f << "  \"utxos\": [\n";
    size_t utxo_count = 0;
    for (size_t i = 0; i < utxos_.size(); ++i) {
        const auto& u = utxos_[i];
        if (i > 0) f << ",\n";
        f << "    {\n";
        f << "      \"txid\": \"" << to_hex(u.txid.data(), 32) << "\",\n";
        f << "      \"vout\": " << u.vout << ",\n";
        f << "      \"amount\": " << u.amount << ",\n";
        f << "      \"output_type\": " << (int)u.output_type << ",\n";
        f << "      \"pkh\": \"" << to_hex(u.pkh.data(), 20) << "\",\n";
        f << "      \"height\": " << u.height << ",\n";
        f << "      \"spent\": " << (u.spent ? "true" : "false");
        if (u.lock_until > 0) {
            f << ",\n      \"lock_until\": " << u.lock_until;
            if (u.output_type == OUT_ESCROW_LOCK) {
                f << ",\n      \"beneficiary\": \"" << to_hex(u.beneficiary.data(), 20) << "\"";
            }
        }
        f << "\n";
        f << "    }";
        ++utxo_count;
    }
    if (utxo_count > 0) f << "\n";
    f << "  ]\n";
    f << "}\n";

    return true;
}

bool Wallet::load_encrypted(const std::string& path, const std::string& passphrase,
                              std::string* err) {
    if (passphrase.empty()) {
        if (err) *err = "passphrase must not be empty";
        return false;
    }

    std::ifstream f(path);
    if (!f) {
        if (err) *err = "cannot open " + path;
        return false;
    }

    std::string json((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());

    // Check version
    int64_t ver = json_int_value(json, "version");
    if (ver != 2) {
        if (err) *err = "not an encrypted wallet (version " + std::to_string(ver) + ")";
        return false;
    }

    // Read crypto params
    std::string salt_hex = json_string_value(json, "salt");
    std::string iv_hex   = json_string_value(json, "iv");
    std::string tag_hex  = json_string_value(json, "tag");
    std::string ct_hex   = json_string_value(json, "keys_ct");

    if (salt_hex.size() != SALT_LEN * 2 || iv_hex.size() != IV_LEN * 2 ||
        tag_hex.size() != TAG_LEN * 2 || ct_hex.empty()) {
        if (err) *err = "invalid encrypted wallet format";
        return false;
    }

    uint8_t salt[SALT_LEN], iv[IV_LEN], tag[TAG_LEN];
    from_hex_bytes(salt_hex, salt, SALT_LEN);
    from_hex_bytes(iv_hex, iv, IV_LEN);
    from_hex_bytes(tag_hex, tag, TAG_LEN);

    std::vector<uint8_t> ct(ct_hex.size() / 2);
    if (!from_hex_bytes(ct_hex, ct.data(), ct.size())) {
        if (err) *err = "invalid ciphertext hex";
        return false;
    }

    // Derive key
    uint8_t key[SCRYPT_KEYLEN];
    if (!derive_key_scrypt(passphrase, salt, SALT_LEN, key)) {
        if (err) *err = "scrypt key derivation failed";
        return false;
    }

    // Decrypt
    std::vector<uint8_t> plaintext;
    if (!aes256gcm_decrypt(key, iv, ct.data(), ct.size(), tag, plaintext)) {
        OPENSSL_cleanse(key, SCRYPT_KEYLEN);
        if (err) *err = "decryption failed — wrong passphrase or corrupted file";
        return false;
    }
    OPENSSL_cleanse(key, SCRYPT_KEYLEN);

    // Parse decrypted keys: "privkey_hex:label\n" per line
    keys_.clear();
    utxos_.clear();
    addr_index_.clear();

    std::string pt(reinterpret_cast<const char*>(plaintext.data()), plaintext.size());
    std::istringstream ss(pt);
    std::string line;
    while (std::getline(ss, line)) {
        if (line.empty()) continue;
        auto colon = line.find(':');
        std::string priv_hex = (colon != std::string::npos) ? line.substr(0, colon) : line;
        std::string label = (colon != std::string::npos) ? line.substr(colon + 1) : "";

        PrivKey priv{};
        if (from_hex_bytes(priv_hex, priv.data(), 32)) {
            try {
                import_privkey(priv, label);
            } catch (...) {}
        }
    }
    OPENSSL_cleanse(&pt[0], pt.size());
    OPENSSL_cleanse(plaintext.data(), plaintext.size());

    // Load UTXOs (same parsing as v1)
    auto utxos_pos = json.find("\"utxos\"");
    if (utxos_pos != std::string::npos) {
        size_t pos = utxos_pos;
        while (true) {
            auto txid_pos = json.find("\"txid\"", pos);
            if (txid_pos == std::string::npos) break;

            auto obj_start = json.rfind('{', txid_pos);
            auto obj_end = json.find('}', txid_pos);
            if (obj_start == std::string::npos || obj_end == std::string::npos) break;

            std::string obj = json.substr(obj_start, obj_end - obj_start + 1);

            WalletUTXO utxo{};

            std::string txid_hex = json_string_value(obj, "txid");
            if (txid_hex.size() == 64) {
                from_hex_bytes(txid_hex, utxo.txid.data(), 32);
            }

            utxo.vout = (uint32_t)json_int_value(obj, "vout");
            utxo.amount = json_int_value(obj, "amount");
            utxo.output_type = (uint8_t)json_int_value(obj, "output_type");

            std::string pkh_hex = json_string_value(obj, "pkh");
            if (pkh_hex.size() == 40) {
                from_hex_bytes(pkh_hex, utxo.pkh.data(), 20);
            }

            utxo.height = json_int_value(obj, "height");
            utxo.spent = (obj.find("\"spent\": true") != std::string::npos ||
                          obj.find("\"spent\":true") != std::string::npos);

            int64_t lu = json_int_value(obj, "lock_until");
            utxo.lock_until = (lu > 0) ? (uint64_t)lu : 0;

            std::string ben_hex = json_string_value(obj, "beneficiary");
            if (ben_hex.size() == 40) {
                from_hex_bytes(ben_hex, utxo.beneficiary.data(), 20);
            }

            utxos_.push_back(utxo);
            pos = obj_end + 1;
        }
    }

    return true;
}

} // namespace sost
