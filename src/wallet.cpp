// wallet.cpp — SOST Wallet (real secp256k1 keys via tx_signer)
#include "sost/wallet.h"
#include "sost/serialize.h"
#include "sost/emission.h"

#include <openssl/sha.h>
#include <openssl/rand.h>

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
        // Should not happen in practice; GenerateKeyPair retries 100 times
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

std::vector<WalletUTXO> Wallet::list_unspent() const {
    std::vector<WalletUTXO> result;
    for (const auto& u : utxos_) {
        if (!u.spent) result.push_back(u);
    }
    return result;
}

std::vector<WalletUTXO> Wallet::list_unspent(const std::string& addr) const {
    PubKeyHash pkh{};
    if (!address_decode(addr, pkh)) return {};

    std::vector<WalletUTXO> result;
    for (const auto& u : utxos_) {
        if (!u.spent && u.pkh == pkh) result.push_back(u);
    }
    return result;
}

int64_t Wallet::balance() const {
    int64_t total = 0;
    for (const auto& u : utxos_) {
        if (!u.spent) total += u.amount;
    }
    return total;
}

int64_t Wallet::balance(const std::string& addr) const {
    PubKeyHash pkh{};
    if (!address_decode(addr, pkh)) return 0;

    int64_t total = 0;
    for (const auto& u : utxos_) {
        if (!u.spent && u.pkh == pkh) total += u.amount;
    }
    return total;
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
    // Skip whitespace
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

    // Extract block_id (used as txid for coinbase)
    std::string block_id_hex = json_string_value(json, "block_id");
    if (block_id_hex.size() != 64) {
        if (err) *err = "invalid block_id in genesis JSON";
        return false;
    }
    Hash256 block_id = from_hex(block_id_hex);

    // Extract subsidy amounts
    int64_t miner_amt  = json_int_value(json, "miner");
    int64_t gold_amt   = json_int_value(json, "gold_vault");
    int64_t popc_amt   = json_int_value(json, "popc_pool");

    if (miner_amt <= 0 && gold_amt <= 0 && popc_amt <= 0) {
        // Try alternative field names
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

    // Constitutional addresses
    const char* addrs[3] = {
        "sost1f559e05f39486582231179a4985366961d8f8313",  // miner
        "sost1be2302d89daef55af4162127b9656f7604948efa",  // gold_vault
        "sost18a222922bba5ac84979a74d76c392fdeaa59f505",  // popc_pool
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
    std::string* err)
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

    // Select UTXOs (simple: oldest first)
    std::vector<size_t> selected;
    int64_t total_in = 0;
    for (size_t i = 0; i < utxos_.size(); ++i) {
        if (utxos_[i].spent) continue;
        // Only spend UTXOs we have keys for
        if (!find_key_by_pkh(utxos_[i].pkh)) continue;
        selected.push_back(i);
        total_in += utxos_[i].amount;
        if (total_in >= needed) break;
    }

    if (total_in < needed) {
        if (err) {
            char buf[128];
            snprintf(buf, sizeof(buf),
                "insufficient funds: have %lld stocks, need %lld",
                (long long)total_in, (long long)needed);
            *err = buf;
        }
        return false;
    }

    // Build transaction
    out_tx = Transaction{};
    out_tx.version = 1;
    out_tx.tx_type = 0x00;  // TRANSFER

    // Inputs
    for (size_t idx : selected) {
        TxInput inp{};
        inp.prev_txid = utxos_[idx].txid;
        inp.prev_index = utxos_[idx].vout;
        // signature and pubkey will be filled by signing
        out_tx.inputs.push_back(inp);
    }

    // Output 0: payment
    {
        TxOutput out{};
        out.amount = amount;
        out.type = 0x00;
        out.pubkey_hash = to_pkh;
        out_tx.outputs.push_back(out);
    }

    // Output 1: change (if any)
    int64_t change = total_in - needed;
    if (change > 0) {
        // Send change to the first input's address
        const WalletKey* change_key = find_key_by_pkh(utxos_[selected[0]].pkh);
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
        const WalletUTXO& utxo = utxos_[selected[i]];
        const WalletKey* key = find_key_by_pkh(utxo.pkh);
        if (!key) {
            if (err) *err = "no private key for UTXO";
            return false;
        }

        SpentOutput spent;
        spent.amount = utxo.amount;
        spent.type = utxo.output_type;

        if (!SignTransactionInput(out_tx, i, spent, genesis_hash, key->privkey, err)) {
            return false;
        }
    }

    // Mark UTXOs as spent
    for (size_t idx : selected) {
        utxos_[idx].spent = true;
    }

    return true;
}

// =============================================================================
// Persistence — simple JSON format
// =============================================================================

// Helper: bytes to hex string
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

// Helper: hex string to bytes
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

    // Keys
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

    // UTXOs
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
        f << "      \"spent\": " << (u.spent ? "true" : "false") << "\n";
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

    // Parse keys — find each "privkey" entry
    size_t pos = 0;
    while (true) {
        pos = json.find("\"privkey\"", pos);
        if (pos == std::string::npos) break;

        // Extract privkey hex
        auto pk_start = json.find('"', pos + 9);
        if (pk_start == std::string::npos) break;
        pk_start++;
        auto pk_end = json.find('"', pk_start);
        if (pk_end == std::string::npos) break;
        std::string priv_hex = json.substr(pk_start, pk_end - pk_start);

        // Extract label (optional)
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

    // Parse UTXOs — find each "txid" in utxos section
    auto utxos_pos = json.find("\"utxos\"");
    if (utxos_pos != std::string::npos) {
        pos = utxos_pos;
        while (true) {
            auto txid_pos = json.find("\"txid\"", pos);
            if (txid_pos == std::string::npos) break;

            // Find the enclosing object
            auto obj_start = json.rfind('{', txid_pos);
            auto obj_end = json.find('}', txid_pos);
            if (obj_start == std::string::npos || obj_end == std::string::npos) break;

            std::string obj = json.substr(obj_start, obj_end - obj_start + 1);

            WalletUTXO utxo{};

            // Parse fields from this object
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

            utxos_.push_back(utxo);
            pos = obj_end + 1;
        }
    }

    return true;
}

} // namespace sost
