#include "sost/wallet.h"
#include <chrono>
#include <cstring>
#include <fstream>
#include <algorithm>
namespace sost {

std::string pubkey_to_address(const Bytes32& pub) {
    std::string a = "sost1";
    for (int i = 0; i < 20; ++i) {
        const char* hx = "0123456789abcdef";
        a += hx[pub[i] >> 4]; a += hx[pub[i] & 0xF];
    }
    return a;
}

Bytes32 sign_hash(const Bytes32& priv, const Bytes32& h) {
    std::vector<uint8_t> buf;
    append(buf, priv); append(buf, h);
    return sha256(buf);
}

bool verify_sig(const Bytes32& pub, const Bytes32& h, const Bytes32& sig) {
    (void)pub; (void)h; (void)sig;
    // Simplified: in full impl, use ed25519 or secp256k1
    // For genesis, coinbase-only model doesn't need tx verification
    return true;
}

Wallet::Wallet() : ctr_(0) {
    seed_.fill(0);
    // Random seed from time-based entropy
    auto t = std::chrono::steady_clock::now().time_since_epoch().count();
    uint8_t tb[8]; 
    for(int i=0;i<8;++i) { tb[i]=(uint8_t)(t&0xFF); t>>=8; }
    seed_ = sha256(tb, 8);
}

KeyPair Wallet::generate_key() {
    std::vector<uint8_t> buf;
    append(buf, seed_);
    uint8_t cb[4]; write_u32_le(cb, ctr_++);
    append(buf, cb, 4);
    KeyPair kp;
    kp.priv = sha256(buf);
    std::vector<uint8_t> pb; append(pb, kp.priv);
    kp.pub = sha256(pb);
    kp.addr = pubkey_to_address(kp.pub);
    keys_.push_back(kp);
    return kp;
}

KeyPair Wallet::import_key(const Bytes32& priv) {
    KeyPair kp; kp.priv = priv;
    std::vector<uint8_t> pb; append(pb, priv);
    kp.pub = sha256(pb);
    kp.addr = pubkey_to_address(kp.pub);
    keys_.push_back(kp);
    return kp;
}

std::string Wallet::default_address() const {
    if (keys_.empty()) return "";
    return keys_[0].addr;
}

std::vector<std::string> Wallet::addresses() const {
    std::vector<std::string> r;
    for (auto& k : keys_) r.push_back(k.addr);
    return r;
}

int64_t Wallet::balance() const {
    int64_t b = 0;
    for (auto& u : utxos_) if (!u.spent) b += u.amount;
    return b;
}

void Wallet::add_utxo(const UTXO& u) { utxos_.push_back(u); }

void Wallet::mark_spent(const Bytes32& txid, uint32_t vout) {
    for (auto& u : utxos_)
        if (u.txid == txid && u.vout == vout) u.spent = true;
}

std::vector<UTXO> Wallet::utxos() const {
    std::vector<UTXO> r;
    for (auto& u : utxos_) if (!u.spent) r.push_back(u);
    return r;
}

void Wallet::credit_coinbase(int64_t h, int64_t sub, const Bytes32& bid) {
    if (keys_.empty()) generate_key();
    UTXO u; u.txid = bid; u.vout = 0;
    u.amount = sub; u.addr = keys_[0].addr;
    u.height = h; u.spent = false;
    utxos_.push_back(u);
}

Tx Wallet::create_tx(const std::string& to, int64_t amt, int64_t fee) {
    Tx tx; tx.fee = fee;
    int64_t need = amt + fee, have = 0;
    for (auto& u : utxos_) {
        if (u.spent) continue;
        TxIn in; in.txid = u.txid; in.vout = u.vout;
        // Sign
        std::vector<uint8_t> sb;
        append(sb, u.txid); append_u32_le(sb, u.vout);
        append_u64_le(sb, (uint64_t)amt);
        Bytes32 h = sha256(sb);
        in.sig = sign_hash(keys_[0].priv, h);
        tx.ins.push_back(in);
        have += u.amount;
        u.spent = true;
        if (have >= need) break;
    }
    tx.outs.push_back({to, amt});
    if (have > need) {
        tx.outs.push_back({keys_[0].addr, have - need}); // change
    }
    // txid
    std::vector<uint8_t> tb;
    for (auto& i : tx.ins) { append(tb, i.txid); append_u32_le(tb, i.vout); }
    for (auto& o : tx.outs) { append(tb, o.addr.c_str(), o.addr.size()); append_u64_le(tb, (uint64_t)o.amount); }
    tx.txid = sha256(tb);
    return tx;
}

bool Wallet::save(const std::string& path) const {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    uint32_t nk = (uint32_t)keys_.size();
    f.write((char*)&nk, 4);
    for (auto& k : keys_) {
        f.write((char*)k.priv.data(), 32);
        f.write((char*)k.pub.data(), 32);
    }
    uint32_t nu = (uint32_t)utxos_.size();
    f.write((char*)&nu, 4);
    for (auto& u : utxos_) {
        f.write((char*)u.txid.data(), 32);
        f.write((char*)&u.vout, 4);
        f.write((char*)&u.amount, 8);
        f.write((char*)&u.height, 8);
        uint8_t s = u.spent ? 1 : 0; f.write((char*)&s, 1);
    }
    return true;
}

bool Wallet::load(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    keys_.clear(); utxos_.clear();
    uint32_t nk; f.read((char*)&nk, 4);
    for (uint32_t i = 0; i < nk; ++i) {
        KeyPair kp;
        f.read((char*)kp.priv.data(), 32);
        f.read((char*)kp.pub.data(), 32);
        kp.addr = pubkey_to_address(kp.pub);
        keys_.push_back(kp);
    }
    uint32_t nu; f.read((char*)&nu, 4);
    for (uint32_t i = 0; i < nu; ++i) {
        UTXO u;
        f.read((char*)u.txid.data(), 32);
        f.read((char*)&u.vout, 4);
        f.read((char*)&u.amount, 8);
        f.read((char*)&u.height, 8);
        uint8_t s; f.read((char*)&s, 1); u.spent = s;
        u.addr = keys_.empty() ? "" : keys_[0].addr;
        utxos_.push_back(u);
    }
    return true;
}
} // namespace sost
