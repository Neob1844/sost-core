#pragma once
#include "types.h"
#include "crypto.h"
#include "serialize.h"
#include <vector>
#include <string>
namespace sost {
struct KeyPair { Bytes32 priv, pub; std::string addr; };
struct UTXO { Bytes32 txid; uint32_t vout; int64_t amount; std::string addr; int64_t height; bool spent; };
struct TxOut { std::string addr; int64_t amount; };
struct TxIn { Bytes32 txid; uint32_t vout; Bytes32 sig; };
struct Tx { Bytes32 txid; std::vector<TxIn> ins; std::vector<TxOut> outs; int64_t fee; };
std::string pubkey_to_address(const Bytes32& pub);
Bytes32 sign_hash(const Bytes32& priv, const Bytes32& h);
bool verify_sig(const Bytes32& pub, const Bytes32& h, const Bytes32& sig);
class Wallet {
public:
    Wallet();
    KeyPair generate_key();
    KeyPair import_key(const Bytes32& priv);
    std::string default_address() const;
    std::vector<std::string> addresses() const;
    int64_t balance() const;
    void add_utxo(const UTXO& u);
    void mark_spent(const Bytes32& txid, uint32_t vout);
    std::vector<UTXO> utxos() const;
    void credit_coinbase(int64_t h, int64_t sub, const Bytes32& bid);
    Tx create_tx(const std::string& to, int64_t amt, int64_t fee);
    bool save(const std::string& path) const;
    bool load(const std::string& path);
private:
    std::vector<KeyPair> keys_;
    std::vector<UTXO> utxos_;
    Bytes32 seed_; uint32_t ctr_;
};
} // namespace sost
