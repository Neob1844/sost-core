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
    uint64_t lock_until{0};   // BOND_LOCK/ESCROW_LOCK: height at which output unlocks (0 = no lock)
    PubKeyHash beneficiary{}; // ESCROW_LOCK only: beneficiary pubkey hash
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
    // V11 Phase 2 — look up a WalletKey by user-assigned label. Returns the
    // first match (labels are NOT guaranteed unique; users typically only
    // label one key per role: e.g. "mining"). Returns nullptr if not found.
    const WalletKey* find_key_by_label(const std::string& label) const;
    std::string default_address() const;
    const std::vector<WalletKey>& keys() const { return keys_; }

    // --- UTXO management ---
    void add_utxo(const WalletUTXO& utxo);
    void clear_utxos() { utxos_.clear(); }
    void mark_spent(const Hash256& txid, uint32_t vout);

    // v0.3.2: maturity-aware queries.
    // chain_height >= 0 => exclude coinbase UTXOs with < COINBASE_MATURITY confirmations.
    // chain_height < 0  => no filtering (backward compatible).
    std::vector<WalletUTXO> list_unspent(int64_t chain_height = -1) const;
    std::vector<WalletUTXO> list_unspent(const std::string& addr, int64_t chain_height = -1) const;
    int64_t balance(int64_t chain_height = -1) const;
    int64_t balance(const std::string& addr, int64_t chain_height = -1) const;

    // v1.4: locked balance — BOND_LOCK and ESCROW_LOCK UTXOs still within lock period
    int64_t locked_balance(int64_t chain_height) const;
    int64_t available_balance(int64_t chain_height) const;

    // v1.4: list bond/escrow UTXOs
    std::vector<WalletUTXO> list_bonds(int64_t chain_height = -1) const;

    // --- Genesis import ---
    bool import_genesis(const std::string& genesis_json_path, std::string* err = nullptr);

    // --- Transaction creation ---
    //
    // capsule_payload: optional. When non-null and non-empty, attached to the
    // payment output (output[0]) before signing. The caller is responsible
    // for building a valid SCPv1 capsule (use the BuildXxxPayload helpers
    // in sost/capsule.h). The wallet does NOT validate the bytes — that is
    // the job of mempool / standardness post-broadcast. Capsule attachment
    // is only meaningful at chain heights >= the activation height
    // (V12_HEIGHT in mainnet); attaching at earlier heights yields a tx
    // the validator rejects with R14_PAYLOAD_FORBIDDEN.
    //
    // mark_spent: when true (default), the selected UTXOs are marked spent
    // in the wallet's in-memory UTXO list at the end of a successful build.
    // This is fine for one-shot callers, but breaks any caller that builds
    // the tx more than once (e.g. fee-estimation passes), because pass 1
    // will silently consume UTXOs that pass 2 still needs. Such callers
    // must pass mark_spent=false on every pass and call
    // mark_tx_inputs_spent(tx) themselves after the broadcast succeeds —
    // mirroring what create_transaction_many already does.
    //
    // from_pkh: when non-null, restricts UTXO selection to outputs that pay
    // exactly this pubkey-hash. The change output is also returned to this
    // same pkh (instead of the first input's pkh). Use this when the wallet
    // file contains more than one key and the caller wants to spend from a
    // specific source — sost-cli's --from-label / --from-address resolve to
    // a pkh and pass it here. nullptr (default) preserves the original
    // "spend any UTXO whose key we hold" behaviour.
    // popc_carrier_payload: optional. When non-null and non-empty, an extra
    // 0-value output to the unspendable PoPC V15 marker pkh is appended carrying
    // these bytes (a PoPC V15 carrier — testnet PoPC soak tooling). The bytes are
    // signed in alongside the rest of the tx; the wallet does NOT validate them.
    bool create_transaction(
        const std::string& to_addr,
        int64_t amount,
        int64_t fee,
        const Hash256& genesis_hash,
        Transaction& out_tx,
        int64_t chain_height = -1,       // maturity filter
        std::string* err = nullptr,
        const std::vector<Byte>* capsule_payload = nullptr,
        bool mark_spent = true,
        const PubKeyHash* from_pkh = nullptr,
        const std::vector<Byte>* popc_carrier_payload = nullptr);

    // sendmany: single TRANSFER tx with N outputs (one per recipient).
    // Caller passes a vector of (address, amount) pairs. Change (if any)
    // is appended as one extra output to the first input's address.
    // Total tx size must stay below MAX_TX_BYTES_CONSENSUS — caller is
    // responsible for sizing the recipient list (a 1MB block / 100KB tx
    // can hold ~3000 recipients). Returns false if total > balance,
    // any address invalid, or signing fails.
    struct Recipient {
        std::string address;
        int64_t     amount;   // in stocks
    };
    bool create_transaction_many(
        const std::vector<Recipient>& recipients,
        int64_t fee,
        const Hash256& genesis_hash,
        Transaction& out_tx,
        int64_t chain_height = -1,
        std::string* err = nullptr);

    // Mark every input of `tx` as spent in this wallet's UTXO list. Use
    // after a tx built via create_transaction_many has been successfully
    // broadcast — that function intentionally does NOT auto-mark so the
    // CLI can run multiple fee-estimation passes without losing UTXOs.
    void mark_tx_inputs_spent(const Transaction& tx);

    // v1.4: create BOND_LOCK transaction (locks funds until lock_until height)
    bool create_bond_transaction(
        int64_t amount,
        int64_t fee,
        uint64_t lock_until,
        const Hash256& genesis_hash,
        Transaction& out_tx,
        int64_t chain_height = -1,
        std::string* err = nullptr);

    // v1.4: create ESCROW_LOCK transaction (locks funds with beneficiary)
    bool create_escrow_transaction(
        int64_t amount,
        int64_t fee,
        uint64_t lock_until,
        const PubKeyHash& beneficiary_pkh,
        const Hash256& genesis_hash,
        Transaction& out_tx,
        int64_t chain_height = -1,
        std::string* err = nullptr);

    // --- Persistence ---
    // Plaintext (v1)
    bool save(const std::string& path, std::string* err = nullptr) const;
    bool load(const std::string& path, std::string* err = nullptr);
    // Encrypted (v2) — AES-256-GCM + scrypt
    bool save_encrypted(const std::string& path, const std::string& passphrase,
                        std::string* err = nullptr) const;
    bool load_encrypted(const std::string& path, const std::string& passphrase,
                        std::string* err = nullptr);

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
