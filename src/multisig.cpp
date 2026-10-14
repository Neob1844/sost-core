// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// multisig.cpp — native M-of-N multisig primitives (V17). See multisig.h and
// docs/v40000/NATIVE_MULTISIG_SPEC_40000.md. Consensus-critical: policy hash,
// canonical policy, OUT_MULTISIG payload envelope, sighash v2, sigcheck count,
// exact size. Wallet-only: signing helpers and the bech32m address codec.
// =============================================================================

#include "sost/multisig.h"
#include "sost/params.h"

#include <secp256k1.h>
#include <openssl/sha.h>
#include <openssl/ripemd.h>
#include <openssl/rand.h>

#include <algorithm>
#include <cstring>

namespace sost {

// ---------------------------------------------------------------------------
// internal helpers
// ---------------------------------------------------------------------------
namespace {

secp256k1_context* Ctx() {
    static secp256k1_context* ctx = []() -> secp256k1_context* {
        secp256k1_context* c = secp256k1_context_create(SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
        if (c) {
            unsigned char seed[32];
            if (RAND_bytes(seed, 32) == 1) (void)secp256k1_context_randomize(c, seed);
        }
        return c;
    }();
    return ctx;
}

Hash256 Sha256d(const Byte* d, size_t n) {
    Hash256 a{}, b{};
    SHA256(d, n, a.data());
    SHA256(a.data(), a.size(), b.data());
    return b;
}

void PutU32(std::vector<Byte>& o, uint32_t v) { for (int i = 0; i < 4; ++i) o.push_back((Byte)((v >> (8 * i)) & 0xFF)); }
void PutI64(std::vector<Byte>& o, int64_t v) {
    uint64_t u = (uint64_t)v;
    for (int i = 0; i < 8; ++i) { o.push_back((Byte)(u & 0xFF)); u >>= 8; }
}
void PutBytes(std::vector<Byte>& o, const Byte* p, size_t n) { o.insert(o.end(), p, p + n); }

size_t CompactLen(uint64_t n) { return n < 0xFD ? 1 : n <= 0xFFFF ? 3 : n <= 0xFFFFFFFFULL ? 5 : 9; }

const char* kAlphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
constexpr uint32_t kBech32mConst = 0x2bc830a3u;

uint32_t Polymod(const std::vector<uint8_t>& v) {
    static const uint32_t G[5] = {0x3b6a57b2u, 0x26508e6du, 0x1ea119fau, 0x3d4233ddu, 0x2a1462b3u};
    uint32_t chk = 1;
    for (uint8_t x : v) {
        uint8_t top = (uint8_t)(chk >> 25);
        chk = ((chk & 0x1ffffffu) << 5) ^ x;
        for (int i = 0; i < 5; ++i) if ((top >> i) & 1) chk ^= G[i];
    }
    return chk;
}
std::vector<uint8_t> HrpExpand(const std::string& hrp) {
    std::vector<uint8_t> r;
    for (char c : hrp) r.push_back((uint8_t)c >> 5);
    r.push_back(0);
    for (char c : hrp) r.push_back((uint8_t)c & 31);
    return r;
}

} // namespace

// ---------------------------------------------------------------------------
// networks / CHAIN_ID
// ---------------------------------------------------------------------------
MsNetwork ActiveMsNetwork() {
#if defined(SOST_DEVNET_FORKS)
    return MsNetwork::DEVNET;
#elif defined(SOST_TESTNET_FORKS)
    return MsNetwork::TESTNET;
#else
    return MsNetwork::MAINNET;
#endif
}
bool MsNetworkFromName(const std::string& n, MsNetwork& out) {
    if (n == "mainnet") { out = MsNetwork::MAINNET; return true; }
    if (n == "testnet") { out = MsNetwork::TESTNET; return true; }
    if (n == "dev" || n == "devnet") { out = MsNetwork::DEVNET; return true; }
    return false;
}
const char* MsNetworkName(MsNetwork n) {
    switch (n) { case MsNetwork::TESTNET: return "testnet"; case MsNetwork::DEVNET: return "dev"; default: return "mainnet"; }
}
const ChainId& ChainIdFor(MsNetwork n) {
    switch (n) { case MsNetwork::TESTNET: return CHAIN_ID_TESTNET; case MsNetwork::DEVNET: return CHAIN_ID_DEVNET; default: return CHAIN_ID_MAINNET; }
}
const char* MultisigHrp(MsNetwork n) {
    switch (n) { case MsNetwork::TESTNET: return "tsostms"; case MsNetwork::DEVNET: return "dsostms"; default: return "sostms"; }
}

// ---------------------------------------------------------------------------
// policy
// ---------------------------------------------------------------------------
std::vector<Byte> SerializeMultisigPolicy(uint8_t m, const std::vector<PubKey33>& keys) {
    std::vector<Byte> p;
    p.reserve(2 + 33 * keys.size());
    p.push_back(m);
    p.push_back((Byte)keys.size());
    for (const auto& k : keys) PutBytes(p, k.data(), 33);
    return p;
}

PubKeyHash ComputeMultisigPolicyHash(uint8_t m, const std::vector<PubKey33>& keys) {
    std::vector<Byte> pre(MS_DOMAIN, MS_DOMAIN + MS_DOMAIN_LEN);
    auto pol = SerializeMultisigPolicy(m, keys);
    pre.insert(pre.end(), pol.begin(), pol.end());
    Hash256 sha{};
    SHA256(pre.data(), pre.size(), sha.data());
    PubKeyHash out{};
    RIPEMD160(sha.data(), sha.size(), out.data());
    return out;
}

bool PubKeyParses(const PubKey33& pk) {
    if (pk[0] != 0x02 && pk[0] != 0x03) return false;
    secp256k1_pubkey p;
    return Ctx() && secp256k1_ec_pubkey_parse(Ctx(), &p, pk.data(), 33) == 1;
}

bool CheckMultisigPolicy(uint8_t m, const std::vector<PubKey33>& keys, std::string* err) {
    auto fail = [&](const char* r) { if (err) *err = r; return false; };
    const size_t n = keys.size();
    if (n == 0 || n > MAX_MULTISIG_N) return fail("policy_n_range");
    if (m == 0) return fail("policy_m_zero");
    if (m > n) return fail("policy_m_gt_n");
    for (size_t j = 0; j < n; ++j) {
        if (keys[j][0] != 0x02 && keys[j][0] != 0x03) return fail("policy_key_prefix");
        if (!PubKeyParses(keys[j])) return fail("policy_key_off_curve");
        if (j > 0 && std::memcmp(keys[j - 1].data(), keys[j].data(), 33) >= 0)
            return fail("policy_keys_not_strictly_increasing");
    }
    return true;
}

bool MakeCanonicalPolicy(uint8_t m, std::vector<PubKey33> keys, std::vector<PubKey33>& out, std::string* err) {
    std::sort(keys.begin(), keys.end(), [](const PubKey33& a, const PubKey33& b) {
        return std::memcmp(a.data(), b.data(), 33) < 0;
    });
    if (!CheckMultisigPolicy(m, keys, err)) {
        if (err && *err == "policy_keys_not_strictly_increasing") *err = "policy_duplicate_key";
        return false;
    }
    out = std::move(keys);
    return true;
}

// ---------------------------------------------------------------------------
// OUT_MULTISIG payload envelope (§7.3)
// ---------------------------------------------------------------------------
bool MultisigOutputPayloadOk(const std::vector<Byte>& p) {
    if (p.empty()) return true;
    const size_t len = p.size();
    if (len < 12 || len > 255) return false;
    if (p[0] != 0x53 || p[1] != 0x43 || p[2] != 0x01) return false;   // "SC", capsule v1
    if ((size_t)p[9] != len - 12) return false;                       // body_len
    if (p[10] != 0x00 || p[11] != 0x00) return false;                 // reserved
    if ((p[4] & 0xC0) != 0) return false;                             // flag bits 6-7
    return true;
}

// ---------------------------------------------------------------------------
// exact size (§3.6)
// ---------------------------------------------------------------------------
size_t TxInputV2Size(const TxInput& in) {
    size_t s = 32 + 4 + 1;
    if (in.auth_kind == AUTH_MULTISIG)
        s += 1 + 1 + 33 * in.ms_pubkeys.size() + 1 + 65 * in.ms_sigs.size();
    else
        s += 64 + 33;
    return s;
}

size_t TxSerializedSizeExact(const Transaction& tx) {
    size_t size = 4 + 1 + CompactLen(tx.inputs.size());
    if (tx.version == TX_VERSION_V2) {
        for (const auto& in : tx.inputs) size += TxInputV2Size(in);
    } else {
        size += tx.inputs.size() * 133;
    }
    size += CompactLen(tx.outputs.size());
    for (const auto& o : tx.outputs) size += 31 + o.payload.size();
    return size;
}

// ---------------------------------------------------------------------------
// sigchecks (§8)
// ---------------------------------------------------------------------------
int64_t TxSigchecks(const Transaction& tx) {
    switch (tx.tx_type) {
        case TX_TYPE_COINBASE:       return 0;
        case TX_TYPE_JACKPOT:        return 0;
        case TX_TYPE_NODE_BIND:      return 2;
        case TX_TYPE_NODE_HEARTBEAT: return 1;
        default: break;
    }
    if (tx.tx_type == TX_TYPE_STANDARD && tx.version == TX_VERSION_V2) {
        int64_t n = 0;
        for (const auto& in : tx.inputs)
            n += (in.auth_kind == AUTH_MULTISIG) ? (int64_t)in.ms_sigs.size() : 1;
        return n;
    }
    return (int64_t)tx.inputs.size();
}

// ---------------------------------------------------------------------------
// sighash v2 (§5.2)
// ---------------------------------------------------------------------------
void SerializeOutputWire(std::vector<Byte>& out, int64_t amount, uint8_t type,
                         const std::array<Byte, 20>& pkh, const std::vector<Byte>& payload) {
    PutI64(out, amount);
    out.push_back(type);
    PutBytes(out, pkh.data(), 20);
    const uint16_t l = (uint16_t)payload.size();
    out.push_back((Byte)(l & 0xFF));
    out.push_back((Byte)(l >> 8));
    if (!payload.empty()) PutBytes(out, payload.data(), payload.size());
}

SighashV2Precomp PrecomputeSighashV2(const Transaction& tx, const std::vector<SpentOutput>& spent) {
    SighashV2Precomp p;
    if (spent.size() != tx.inputs.size()) return p;
    std::vector<Byte> buf;
    buf.reserve(tx.inputs.size() * 36);
    for (const auto& in : tx.inputs) { PutBytes(buf, in.prev_txid.data(), 32); PutU32(buf, in.prev_index); }
    p.hash_prevouts = Sha256d(buf.data(), buf.size());
    buf.clear();
    for (const auto& s : spent) {
        if (s.payload.size() > 0xFFFF) return p;
        SerializeOutputWire(buf, s.amount, s.type, s.pubkey_hash, s.payload);
    }
    p.hash_spent_outputs = Sha256d(buf.data(), buf.size());
    buf.clear();
    for (const auto& o : tx.outputs) {
        if (o.payload.size() > 0xFFFF) return p;
        SerializeOutputWire(buf, o.amount, o.type, o.pubkey_hash, o.payload);
    }
    p.hash_outputs = Sha256d(buf.data(), buf.size());
    p.ok = true;
    return p;
}

std::array<Byte, 20> InputAuthField(const Transaction& tx, size_t i) {
    std::array<Byte, 20> z{};
    if (tx.version != TX_VERSION_V2 || i >= tx.inputs.size()) return z;
    const auto& in = tx.inputs[i];
    if (in.auth_kind != AUTH_MULTISIG) return z;
    return ComputeMultisigPolicyHash(in.ms_m, in.ms_pubkeys);
}

std::vector<Byte> BuildSighashV2Preimage(const Transaction& tx, size_t i, const SpentOutput& s,
                                         const SighashV2Precomp& pre, const ChainId& chain_id,
                                         const Hash256& genesis) {
    std::vector<Byte> p;
    if (i >= tx.inputs.size()) return p;
    p.reserve(SIGHASH_V2_PREIMAGE_LEN);
    PutBytes(p, reinterpret_cast<const Byte*>(SIGHASH_V2_TAG), SIGHASH_V2_TAG_LEN);
    PutBytes(p, chain_id.data(), 32);
    PutU32(p, tx.version);
    p.push_back(tx.tx_type);
    PutBytes(p, pre.hash_prevouts.data(), 32);
    PutBytes(p, pre.hash_spent_outputs.data(), 32);
    PutBytes(p, tx.inputs[i].prev_txid.data(), 32);
    PutU32(p, tx.inputs[i].prev_index);
    PutI64(p, s.amount);
    p.push_back(s.type);
    const uint8_t ak = (tx.version == TX_VERSION_V2) ? tx.inputs[i].auth_kind : AUTH_SINGLE;
    p.push_back(ak);
    auto f = InputAuthField(tx, i);
    PutBytes(p, f.data(), 20);
    PutBytes(p, pre.hash_outputs.data(), 32);
    PutBytes(p, genesis.data(), 32);
    return p;
}

Hash256 ComputeSighashV2(const Transaction& tx, size_t i, const SpentOutput& s, const SighashV2Precomp& pre,
                         const ChainId& chain_id, const Hash256& genesis) {
    auto p = BuildSighashV2Preimage(tx, i, s, pre, chain_id, genesis);
    if (p.size() != SIGHASH_V2_PREIMAGE_LEN || !pre.ok) return Hash256{};
    return Sha256d(p.data(), p.size());
}

// ---------------------------------------------------------------------------
// detailed verifier
// ---------------------------------------------------------------------------
SigVerdict VerifyEcdsaLowS(const PubKey33& pubkey, const Hash256& msg, const Sig64& sig) {
    bool all_zero = true, r_zero = true, s_zero = true;
    for (int i = 0; i < 64; ++i) if (sig[i]) { all_zero = false; break; }
    if (all_zero) return SigVerdict::ZERO;
    for (int i = 0; i < 32; ++i) { if (sig[i]) r_zero = false; if (sig[32 + i]) s_zero = false; }
    if (r_zero || s_zero) return SigVerdict::RANGE;
    secp256k1_context* c = Ctx();
    if (!c) return SigVerdict::INVALID;
    secp256k1_ecdsa_signature so;
    if (!secp256k1_ecdsa_signature_parse_compact(c, &so, sig.data())) return SigVerdict::RANGE;  // r or s >= n
    if (!IsLowS(sig)) return SigVerdict::RANGE;
    secp256k1_pubkey pk;
    if (pubkey[0] != 0x02 && pubkey[0] != 0x03) return SigVerdict::BAD_KEY;
    if (!secp256k1_ec_pubkey_parse(c, &pk, pubkey.data(), 33)) return SigVerdict::BAD_KEY;
    if (!secp256k1_ecdsa_verify(c, &so, msg.data(), &pk)) return SigVerdict::INVALID;
    return SigVerdict::OK;
}

// ---------------------------------------------------------------------------
// signing helpers
// ---------------------------------------------------------------------------
bool SignInputV2Single(Transaction& tx, size_t i, const std::vector<SpentOutput>& spent,
                       const ChainId& chain_id, const Hash256& genesis, const PrivKey& priv, std::string* err) {
    if (tx.version != TX_VERSION_V2 || i >= tx.inputs.size()) { if (err) *err = "not a v2 input"; return false; }
    if (tx.inputs[i].auth_kind != AUTH_SINGLE) { if (err) *err = "input is not single-sig"; return false; }
    PubKey pk{};
    if (!DerivePublicKey(priv, pk, err)) return false;
    tx.inputs[i].pubkey = pk;   // pubkey and signature are not committed by the sighash
    auto pre = PrecomputeSighashV2(tx, spent);
    if (!pre.ok) { if (err) *err = "spent output list does not match the inputs"; return false; }
    Hash256 h = ComputeSighashV2(tx, i, spent[i], pre, chain_id, genesis);
    Sig64 sig{};
    if (!SignSighash(priv, h, sig, err)) return false;
    tx.inputs[i].signature = sig;
    return true;
}

bool SignInputV2Multisig(const Transaction& tx, size_t i, const std::vector<SpentOutput>& spent,
                         const ChainId& chain_id, const Hash256& genesis, const PrivKey& priv,
                         uint8_t& out_idx, Sig64& out_sig, std::string* err) {
    if (tx.version != TX_VERSION_V2 || i >= tx.inputs.size()) { if (err) *err = "not a v2 input"; return false; }
    const auto& in = tx.inputs[i];
    if (in.auth_kind != AUTH_MULTISIG) { if (err) *err = "input is not multisig"; return false; }
    PubKey pk{};
    if (!DerivePublicKey(priv, pk, err)) return false;
    int idx = -1;
    for (size_t j = 0; j < in.ms_pubkeys.size(); ++j) if (in.ms_pubkeys[j] == pk) { idx = (int)j; break; }
    if (idx < 0) { if (err) *err = "key is not in the input's policy"; return false; }
    auto pre = PrecomputeSighashV2(tx, spent);
    if (!pre.ok) { if (err) *err = "spent output list does not match the inputs"; return false; }
    Hash256 h = ComputeSighashV2(tx, i, spent[i], pre, chain_id, genesis);
    if (!SignSighash(priv, h, out_sig, err)) return false;
    out_idx = (uint8_t)idx;
    return true;
}

// ---------------------------------------------------------------------------
// bech32m
// ---------------------------------------------------------------------------
std::string Bech32mEncode(const std::string& hrp, const std::vector<uint8_t>& data) {
    std::vector<uint8_t> v = HrpExpand(hrp);
    v.insert(v.end(), data.begin(), data.end());
    v.insert(v.end(), 6, 0);
    uint32_t mod = Polymod(v) ^ kBech32mConst;
    std::string out = hrp + "1";
    for (uint8_t d : data) out += kAlphabet[d];
    for (int i = 0; i < 6; ++i) out += kAlphabet[(mod >> (5 * (5 - i))) & 31];
    return out;
}

bool Bech32mDecode(const std::string& s, std::string& hrp, std::vector<uint8_t>& data, std::string* err) {
    auto fail = [&](const char* r) { if (err) *err = r; return false; };
    if (s.size() > 90) return fail("too_long");
    bool lower = false, upper = false;
    for (unsigned char c : s) {
        if (c < 33 || c > 126) return fail("bad_char");
        if (c >= 'a' && c <= 'z') lower = true;
        if (c >= 'A' && c <= 'Z') upper = true;
    }
    if (lower && upper) return fail("mixed_case");
    if (upper) return fail("upper_case");
    const size_t pos = s.rfind('1');
    if (pos == std::string::npos) return fail("missing_separator");
    if (pos < 1 || pos + 7 > s.size()) return fail("bad_separator_position");
    hrp = s.substr(0, pos);
    std::vector<uint8_t> d;
    for (size_t i = pos + 1; i < s.size(); ++i) {
        const char* p = std::strchr(kAlphabet, s[i]);
        if (!p || s[i] == '\0') return fail("char_not_in_alphabet");
        d.push_back((uint8_t)(p - kAlphabet));
    }
    std::vector<uint8_t> v = HrpExpand(hrp);
    v.insert(v.end(), d.begin(), d.end());
    if (Polymod(v) != kBech32mConst) return fail("bad_checksum");
    data.assign(d.begin(), d.end() - 6);
    return true;
}

std::string MultisigAddressEncode(const PubKeyHash& msh, MsNetwork net) {
    std::vector<uint8_t> raw;
    raw.push_back(0x01);
    raw.insert(raw.end(), msh.begin(), msh.end());
    std::vector<uint8_t> d5;
    uint32_t acc = 0; int bits = 0;
    for (uint8_t b : raw) {
        acc = ((acc << 8) | b) & 0xFFFu; bits += 8;
        while (bits >= 5) { bits -= 5; d5.push_back((acc >> bits) & 31); }
    }
    if (bits) d5.push_back((acc << (5 - bits)) & 31);
    return Bech32mEncode(MultisigHrp(net), d5);
}

bool MultisigAddressDecode(const std::string& addr, MsNetwork net, PubKeyHash& out, std::string* err) {
    std::string hrp; std::vector<uint8_t> d5;
    if (!Bech32mDecode(addr, hrp, d5, err)) return false;
    auto fail = [&](const char* r) { if (err) *err = r; return false; };
    if (hrp != MultisigHrp(net)) return fail("wrong_hrp");
    std::vector<uint8_t> raw;
    uint32_t acc = 0; int bits = 0;
    for (uint8_t v : d5) {
        acc = ((acc << 5) | v) & 0xFFFu; bits += 5;
        if (bits >= 8) { bits -= 8; raw.push_back((acc >> bits) & 0xFF); }
    }
    if (bits >= 5) return fail("bad_padding");
    if ((acc & ((1u << bits) - 1)) != 0) return fail("nonzero_padding");
    if (raw.size() != 21) return fail("bad_length");
    if (raw[0] != 0x01) return fail("bad_format_byte");
    std::copy(raw.begin() + 1, raw.end(), out.begin());
    return true;
}

bool LooksLikeMultisigAddress(const std::string& a) {
    return a.rfind("sostms1", 0) == 0 || a.rfind("tsostms1", 0) == 0 || a.rfind("dsostms1", 0) == 0;
}

} // namespace sost
