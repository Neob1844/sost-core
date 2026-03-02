// wallet.h — SOST Wallet (real secp256k1 keys via tx_signer)
#pragma once
#include "sost/tx_signer.h"
#include "sost/address.h"
#include "sost/transaction.h"
#include "sost/consensus_constants.h"   // COINBASE_MATURITY
#include <vector>
#include <string>
#include <map>

namespace sost {

// -------------------------------------------------------------------------
// WalletKey: real secp256k1 keypair
// -------------------------------------------------------------------------
struct WalletKey {
    PrivKey privkey;          // 32 bytes secp256k1 private key
    PubKey  pubkey;           // 33 bytes compressed public key
    PubKeyHash pkh;           // 20 bytes RIPEMD160(SHA256(pubkey))
    std::string address;      // "sost1" + hex(pkh)
    std::string label;        // optional user label
};

// -------------------------------------------------------------------------
// WalletUTXO: unspent transaction output tracked by wallet
// -------------------------------------------------------------------------
struct WalletUTXO {
    Hash256  txid;
    uint32_t vout;
    int64_t  amount;          // in stocks
    uint8_t  output_type;     // 0x00 = TRANSFER, etc.
    PubKeyHash pkh;           // owner
    int64_t  height;          // block height (-1 = unconfirmed)
    bool     spent;
};

// -------------------------------------------------------------------------
// Wallet: key management + UTXO tracking + transaction creation
// -------------------------------------------------------------------------
class Wallet {
public:
    Wallet();

    // --- Key management ---
    WalletKey generate_key(const std::string& label = "");
    WalletKey import_privkey(const PrivKey& privkey, const std::string& label = "");
    bool has_address(const std::string& addr) const;
    const WalletKey* find_key(const std::string& addr) const;
    const WalletKey* find_key_by_pkh(const PubKeyHash& pkh) const;
    std::string default_address() const;
    const std::vector<WalletKey>& keys() const { return keys_; }

    // --- UTXO management ---
    void add_utxo(const WalletUTXO& utxo);
    void mark_spent(const Hash256& txid, uint32_t vout);

    // v0.3.2: maturity-aware queries.
    // chain_height >= 0 => exclude coinbase UTXOs with < COINBASE_MATURITY confirmations.
    // chain_height < 0  => no filtering (backward compatible).
    std::vector<WalletUTXO> list_unspent(int64_t chain_height = -1) const;
    std::vector<WalletUTXO> list_unspent(const std::string& addr, int64_t chain_height = -1) const;
    int64_t balance(int64_t chain_height = -1) const;
    int64_t balance(const std::string& addr, int64_t chain_height = -1) const;

    // --- Genesis import ---
    bool import_genesis(const std::string& genesis_json_path, std::string* err = nullptr);

    // --- Transaction creation ---
    bool create_transaction(
        const std::string& to_addr,
        int64_t amount,
        int64_t fee,
        const Hash256& genesis_hash,
        Transaction& out_tx,
        int64_t chain_height = -1,       // maturity filter
        std::string* err = nullptr);

    // --- Persistence ---
    bool save(const std::string& path, std::string* err = nullptr) const;
    bool load(const std::string& path, std::string* err = nullptr);

    // --- Info ---
    size_t num_keys() const { return keys_.size(); }
    size_t num_utxos() const;

private:
    std::vector<WalletKey> keys_;
    std::vector<WalletUTXO> utxos_;
    std::map<std::string, size_t> addr_index_; // address → keys_ index

    void rebuild_index();
    static bool is_mature(const WalletUTXO& u, int64_t chain_height);
};

} // namespace sost
