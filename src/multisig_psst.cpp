// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// multisig_psst.cpp — offline multisig workflow (NON-CONSENSUS). See multisig_psst.h.

#include "sost/multisig_psst.h"
#include "sost/address.h"
#include "sost/capsule.h"
#include "sost/json_rpc.h"
#include "sost/params.h"

#include <openssl/sha.h>

#include <algorithm>
#include <cstring>
#include <set>

namespace sost::psst {

namespace {

std::string Hex(const Byte* d, size_t n) { return HexStr(d, n); }
template <size_t N> std::string Hex(const std::array<Byte, N>& a) { return HexStr(a.data(), N); }

bool Unhex(const std::string& h, std::vector<Byte>& out) {
    out.clear();
    if (h.size() % 2) return false;
    for (size_t i = 0; i < h.size(); i += 2) {
        auto nib = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            return -1;                                    // lowercase only
        };
        int a = nib(h[i]), b = nib(h[i + 1]);
        if (a < 0 || b < 0) return false;
        out.push_back((Byte)((a << 4) | b));
    }
    return true;
}
template <size_t N> bool UnhexA(const std::string& h, std::array<Byte, N>& out) {
    std::vector<Byte> v;
    if (!Unhex(h, v) || v.size() != N) return false;
    std::memcpy(out.data(), v.data(), N);
    return true;
}

std::string JsonEsc(const std::string& s) {
    std::string o;
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
        else if (c < 32 || c > 126) o += '.';
        else o += (char)c;
    }
    return o;
}

class SpentView : public IUtxoView {
public:
    std::map<OutPoint, UTXOEntry> m;
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        auto it = m.find(op);
        if (it == m.end()) return std::nullopt;
        return it->second;
    }
};

std::string AddressFor(const TxOutput& o, MsNetwork net) {
    if (o.type == OUT_MULTISIG) return MultisigAddressEncode(o.pubkey_hash, net);
    return address_encode(o.pubkey_hash);
}

std::string OutputTypeName(uint8_t t) {
    switch (t) {
        case OUT_TRANSFER: return "transfer";
        case OUT_MULTISIG: return "multisig";
        case OUT_COINBASE_MINER: return "coinbase_miner";
        case OUT_COINBASE_LOTTERY: return "coinbase_lottery";
        case OUT_HTLC_LOCK: return "htlc_lock";
        default: return "type_0x" + HexStr(&t, 1);
    }
}

} // namespace

// ---------------------------------------------------------------------------
// policy
// ---------------------------------------------------------------------------
bool MakePolicy(MsNetwork net, uint8_t m, const std::vector<PubKey33>& keys, Policy& out, std::string* err) {
    std::vector<PubKey33> sorted;
    if (!MakeCanonicalPolicy(m, keys, sorted, err)) return false;
    out.net = net; out.m = m; out.keys = sorted;
    out.msh = ComputeMultisigPolicyHash(m, sorted);
    out.address = MultisigAddressEncode(out.msh, net);
    return true;
}

std::string PolicyToJson(const Policy& p) {
    std::string j = "{\n  \"format\": \"" + std::string(POLICY_FORMAT) + "\",\n";
    j += "  \"network\": \"" + std::string(MsNetworkName(p.net)) + "\",\n";
    j += "  \"m\": " + std::to_string((int)p.m) + ",\n  \"n\": " + std::to_string(p.keys.size()) + ",\n";
    j += "  \"keys\": [";
    for (size_t i = 0; i < p.keys.size(); ++i) j += std::string(i ? ", " : "") + "\"" + Hex(p.keys[i]) + "\"";
    j += "],\n  \"policy_hex\": \"";
    auto pol = SerializeMultisigPolicy(p.m, p.keys);
    j += Hex(pol.data(), pol.size()) + "\",\n";
    j += "  \"msh\": \"" + Hex(p.msh) + "\",\n";
    j += "  \"address\": \"" + p.address + "\",\n";
    // ceremony (spec §4): commit-then-reveal commitments, SHA256(pubkey) per signer
    j += "  \"ceremony_commitments\": [";
    for (size_t i = 0; i < p.keys.size(); ++i) {
        Hash256 h{}; SHA256(p.keys[i].data(), 33, h.data());
        j += std::string(i ? ", " : "") + "\"" + Hex(h) + "\"";
    }
    j += "]\n}\n";
    return j;
}

bool PolicyFromJson(const std::string& text, Policy& out, std::string* err) {
    auto fail = [&](const std::string& r) { if (err) *err = r; return false; };
    json::Value d; std::string perr;
    if (text.size() > 64 * 1024 || !json::parse(text, d, &perr) || !d.is_obj()) return fail("not a JSON policy file");
    std::string fmt, net, msh, addr; int64_t m = 0;
    d.get_str("format", fmt); d.get_str("network", net); d.get_str("msh", msh); d.get_str("address", addr);
    if (fmt != POLICY_FORMAT) return fail("unknown policy format '" + fmt + "'");
    MsNetwork n;
    if (!MsNetworkFromName(net, n)) return fail("unknown network '" + net + "'");
    if (!d.get_int("m", m) || m < 1 || m > 15) return fail("bad m");
    const json::Value* ks = d.find("keys");
    if (!ks || !ks->is_arr()) return fail("missing keys");
    std::vector<PubKey33> keys;
    for (const auto& k : ks->a) { PubKey33 pk{}; if (k.type != json::Value::T::Str || !UnhexA(k.s, pk)) return fail("bad key"); keys.push_back(pk); }
    Policy p;
    if (!MakePolicy(n, (uint8_t)m, keys, p, err)) return false;
    if (p.keys != keys) return fail("keys are not in canonical (sorted) order");
    if (Hex(p.msh) != msh) return fail("msh does not match the keys");
    if (p.address != addr) return fail("address does not match the msh/network");
    out = p;
    return true;
}

// ---------------------------------------------------------------------------
// template helpers
// ---------------------------------------------------------------------------
Transaction UnsignedTx(const Psst& p) {
    Transaction tx; tx.version = TX_VERSION_V2; tx.tx_type = TX_TYPE_STANDARD;
    for (const auto& in : p.inputs) {
        TxInput ti; ti.prev_txid = in.txid; ti.prev_index = in.vout; ti.auth_kind = in.auth_kind;
        if (in.auth_kind == AUTH_MULTISIG) { ti.ms_m = in.m; ti.ms_pubkeys = in.keys; }
        tx.inputs.push_back(ti);
    }
    tx.outputs = p.outputs;
    return tx;
}

std::vector<SpentOutput> SpentList(const Psst& p) {
    std::vector<SpentOutput> s;
    for (const auto& in : p.inputs) s.push_back(in.spent);
    return s;
}

Transaction Assemble(const Psst& p, bool* complete) {
    Transaction tx = UnsignedTx(p);
    bool all = true;
    for (size_t i = 0; i < p.inputs.size(); ++i) {
        const auto& in = p.inputs[i];
        if (in.auth_kind == AUTH_MULTISIG) {
            for (const auto& kv : in.sigs) {
                if (tx.inputs[i].ms_sigs.size() >= in.m) break;           // M lowest indexes
                MsSignature s; s.key_index = kv.first; s.sig = kv.second;
                tx.inputs[i].ms_sigs.push_back(s);
            }
            if (tx.inputs[i].ms_sigs.size() < in.m) all = false;
        } else {
            if (in.single_signed) { tx.inputs[i].signature = in.single_sig; tx.inputs[i].pubkey = in.single_pub; }
            else all = false;
        }
    }
    if (complete) *complete = all;
    return tx;
}

int64_t Fee(const Psst& p) {
    int64_t in = 0, out = 0;
    for (const auto& i : p.inputs) in += i.spent.amount;
    for (const auto& o : p.outputs) out += o.amount;
    return in - out;
}

size_t FinalSize(const Psst& p) {
    Transaction tx = UnsignedTx(p);
    for (size_t i = 0; i < tx.inputs.size(); ++i)
        if (tx.inputs[i].auth_kind == AUTH_MULTISIG) tx.inputs[i].ms_sigs.resize(p.inputs[i].m);
    return TxSerializedSizeExact(tx);
}

int64_t FinalSigchecks(const Psst& p) {
    int64_t n = 0;
    for (const auto& in : p.inputs) n += (in.auth_kind == AUTH_MULTISIG) ? in.m : 1;
    return n;
}

static bool CheckSigsAgainstTemplate(const Psst& p, std::string* err) {
    Transaction tx = UnsignedTx(p);
    auto spent = SpentList(p);
    auto pre = PrecomputeSighashV2(tx, spent);
    if (!pre.ok) { if (err) *err = "sighash precompute failed"; return false; }
    for (size_t i = 0; i < p.inputs.size(); ++i) {
        const auto& in = p.inputs[i];
        Hash256 h = ComputeSighashV2(tx, i, spent[i], pre, p.chain_id, p.genesis);
        if (in.auth_kind == AUTH_MULTISIG) {
            for (const auto& kv : in.sigs) {
                if (kv.first >= in.keys.size()) { if (err) *err = "input " + std::to_string(i) + ": key index out of range"; return false; }
                if (VerifyEcdsaLowS(in.keys[kv.first], h, kv.second) != SigVerdict::OK) {
                    if (err) *err = "input " + std::to_string(i) + ": signature of key " + std::to_string((int)kv.first) +
                                    " does not verify against this template";
                    return false;
                }
            }
        } else if (in.single_signed) {
            if (ComputePubKeyHash(in.single_pub) != in.spent.pubkey_hash ||
                VerifyEcdsaLowS(in.single_pub, h, in.single_sig) != SigVerdict::OK) {
                if (err) *err = "input " + std::to_string(i) + ": single-sig signature does not verify";
                return false;
            }
        }
    }
    return true;
}

bool Build(MsNetwork net, const Hash256& genesis, const std::vector<Input>& ins,
           const std::vector<TxOutput>& outs, Psst& out, std::string* err) {
    auto fail = [&](const std::string& r) { if (err) *err = r; return false; };
    if (ins.empty() || ins.size() > 256) return fail("bad input count");
    if (outs.empty() || outs.size() > 256) return fail("bad output count");
    std::set<std::pair<Hash256, uint32_t>> seen;
    for (size_t i = 0; i < ins.size(); ++i) {
        const auto& in = ins[i];
        if (!seen.insert({in.txid, in.vout}).second) return fail("duplicate input");
        if (in.auth_kind == AUTH_MULTISIG) {
            std::string pe;
            if (!CheckMultisigPolicy(in.m, in.keys, &pe)) return fail("input " + std::to_string(i) + ": " + pe);
            if (in.spent.type != OUT_MULTISIG) return fail("input " + std::to_string(i) + ": multisig input must spend OUT_MULTISIG");
            if (ComputeMultisigPolicyHash(in.m, in.keys) != in.spent.pubkey_hash)
                return fail("input " + std::to_string(i) + ": policy does not hash to the spent output's lock");
        } else if (in.auth_kind == AUTH_SINGLE) {
            if (in.spent.type == OUT_MULTISIG || in.spent.type == OUT_HTLC_LOCK || in.spent.type == OUT_BURN)
                return fail("input " + std::to_string(i) + ": single-sig input cannot spend output type 0x" + HexStr(&in.spent.type, 1));
        } else return fail("unknown auth kind");
        if (in.spent.amount <= 0) return fail("input " + std::to_string(i) + ": bad amount");
    }
    Psst p; p.net = net; p.chain_id = ChainIdFor(net); p.genesis = genesis; p.inputs = ins; p.outputs = outs;
    for (auto& in : p.inputs) { in.sigs.clear(); in.single_signed = false; }
    if (Fee(p) < 0) return fail("outputs exceed inputs");
    std::vector<Byte> raw; std::string se;
    if (!UnsignedTx(p).Serialize(raw, &se)) return fail("cannot serialize: " + se);
    out = p;
    return true;
}

// ---------------------------------------------------------------------------
// JSON
// ---------------------------------------------------------------------------
std::string ToJson(const Psst& p) {
    Transaction utx = UnsignedTx(p);
    std::vector<Byte> raw; utx.Serialize(raw);
    bool complete = false;
    Transaction ftx = Assemble(p, &complete);
    std::string j = "{\n  \"format\": \"" + std::string(PSST_FORMAT) + "\",\n";
    j += "  \"network\": \"" + std::string(MsNetworkName(p.net)) + "\",\n";
    j += "  \"chain_id\": \"" + Hex(p.chain_id) + "\",\n";
    j += "  \"genesis\": \"" + Hex(p.genesis) + "\",\n";
    j += "  \"unsigned_hex\": \"" + Hex(raw.data(), raw.size()) + "\",\n";
    j += "  \"inputs\": [\n";
    for (size_t i = 0; i < p.inputs.size(); ++i) {
        const auto& in = p.inputs[i];
        j += "    {\"txid\": \"" + Hex(in.txid) + "\", \"vout\": " + std::to_string(in.vout) + ",\n";
        j += "     \"spent_output\": {\"amount\": " + std::to_string(in.spent.amount) + ", \"type\": " + std::to_string((int)in.spent.type) +
             ", \"pubkey_hash\": \"" + Hex(in.spent.pubkey_hash) + "\", \"payload_hex\": \"" +
             Hex(in.spent.payload.data(), in.spent.payload.size()) + "\"},\n";
        if (in.auth_kind == AUTH_MULTISIG) {
            auto pol = SerializeMultisigPolicy(in.m, in.keys);
            j += "     \"auth\": \"multisig\", \"m\": " + std::to_string((int)in.m) + ", \"n\": " + std::to_string(in.keys.size()) +
                 ", \"policy_hex\": \"" + Hex(pol.data(), pol.size()) + "\", \"msh\": \"" + Hex(ComputeMultisigPolicyHash(in.m, in.keys)) +
                 "\", \"address\": \"" + MultisigAddressEncode(in.spent.pubkey_hash, p.net) + "\",\n     \"signatures\": {";
            bool first = true;
            for (const auto& kv : in.sigs) { j += std::string(first ? "" : ", ") + "\"" + std::to_string((int)kv.first) + "\": \"" + Hex(kv.second) + "\""; first = false; }
            j += "}}";
        } else {
            j += "     \"auth\": \"single\", \"address\": \"" + address_encode(in.spent.pubkey_hash) + "\"";
            if (in.single_signed) j += ", \"signature\": \"" + Hex(in.single_sig) + "\", \"pubkey\": \"" + Hex(in.single_pub) + "\"";
            j += "}";
        }
        j += (i + 1 < p.inputs.size() ? ",\n" : "\n");
    }
    j += "  ],\n  \"outputs_decoded\": [\n";
    for (size_t k = 0; k < p.outputs.size(); ++k) {
        const auto& o = p.outputs[k];
        j += "    {\"amount\": " + std::to_string(o.amount) + ", \"type\": \"" + OutputTypeName(o.type) + "\", \"address\": \"" + AddressFor(o, p.net) +
             "\", \"payload_hex\": \"" + Hex(o.payload.data(), o.payload.size()) + "\"";
        if (!o.payload.empty()) {
            Hash256 h{}; SHA256(o.payload.data(), o.payload.size(), h.data());
            std::string text;
            for (size_t b = (o.payload.size() >= 12 ? 12 : 0); b < o.payload.size(); ++b) text += (char)o.payload[b];
            j += ", \"capsule_sha256\": \"" + Hex(h) + "\", \"capsule_text\": \"" + JsonEsc(text) + "\"";
        }
        j += (k + 1 < p.outputs.size() ? "},\n" : "}\n");
    }
    j += "  ],\n";
    j += "  \"fee\": " + std::to_string(Fee(p)) + ",\n";
    j += "  \"tx_size\": " + std::to_string(FinalSize(p)) + ",\n";
    j += "  \"sigchecks\": " + std::to_string(FinalSigchecks(p)) + ",\n";
    j += "  \"complete\": " + std::string(complete ? "true" : "false");
    if (complete) {
        std::vector<Byte> fr; ftx.Serialize(fr);
        j += ",\n  \"txid\": \"" + ftx.ComputeTxIdHex() + "\",\n  \"final_hex\": \"" + Hex(fr.data(), fr.size()) + "\"";
    }
    j += "\n}\n";
    return j;
}

bool FromJson(const std::string& text, Psst& out, std::string* err) {
    auto fail = [&](const std::string& r) { if (err) *err = r; return false; };
    json::Value d; std::string perr;
    if (text.size() > 8 * 1024 * 1024 || !json::parse(text, d, &perr) || !d.is_obj()) return fail("not a JSON PSST file");
    std::string fmt, net, cid, gen, uhex; int64_t fee = 0;
    d.get_str("format", fmt); d.get_str("network", net); d.get_str("chain_id", cid); d.get_str("genesis", gen); d.get_str("unsigned_hex", uhex);
    if (fmt != PSST_FORMAT) return fail("unknown file format '" + fmt + "'");
    Psst p;
    if (!MsNetworkFromName(net, p.net)) return fail("unknown network '" + net + "'");
    if (!UnhexA(cid, p.chain_id)) return fail("bad chain_id");
    if (p.chain_id != ChainIdFor(p.net)) return fail("chain_id does not belong to network '" + net + "'");
    if (!UnhexA(gen, p.genesis)) return fail("bad genesis");
    std::vector<Byte> raw;
    if (!Unhex(uhex, raw)) return fail("unsigned_hex is not lowercase hex");
    Transaction tx; std::string de;
    if (!Transaction::Deserialize(raw, tx, &de)) return fail("unsigned_hex does not decode: " + de);
    if (tx.version != TX_VERSION_V2 || tx.tx_type != TX_TYPE_STANDARD) return fail("template is not a version-2 STANDARD tx");
    const json::Value* ins = d.find("inputs");
    if (!ins || !ins->is_arr() || ins->a.size() != tx.inputs.size()) return fail("input list does not match the template");
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        const auto& e = ins->a[i];
        const auto& ti = tx.inputs[i];
        Input in;
        std::string txid, auth; int64_t vout = -1;
        if (!e.get_str("txid", txid) || !e.get_int("vout", vout) || !e.get_str("auth", auth)) return fail("input " + std::to_string(i) + " incomplete");
        if (!UnhexA(txid, in.txid) || in.txid != ti.prev_txid || vout != (int64_t)ti.prev_index) return fail("input " + std::to_string(i) + " does not match the template");
        in.vout = ti.prev_index;
        const json::Value* so = e.find("spent_output");
        int64_t amt = 0, typ = -1; std::string pkh, pl;
        if (!so || !so->get_int("amount", amt) || !so->get_int("type", typ) || !so->get_str("pubkey_hash", pkh) || !so->get_str("payload_hex", pl) ||
            amt <= 0 || typ < 0 || typ > 255 || !UnhexA(pkh, in.spent.pubkey_hash) || !Unhex(pl, in.spent.payload))
            return fail("input " + std::to_string(i) + ": bad spent_output");
        in.spent.amount = amt; in.spent.type = (uint8_t)typ;
        if (auth == "multisig") {
            if (ti.auth_kind != AUTH_MULTISIG || !ti.ms_sigs.empty()) return fail("input " + std::to_string(i) + ": template is not an unsigned multisig input");
            in.auth_kind = AUTH_MULTISIG; in.m = ti.ms_m; in.keys = ti.ms_pubkeys;
            std::string polhex, msh;
            if (!e.get_str("policy_hex", polhex) || !e.get_str("msh", msh)) return fail("input " + std::to_string(i) + ": missing policy");
            auto pol = SerializeMultisigPolicy(in.m, in.keys);
            if (polhex != Hex(pol.data(), pol.size())) return fail("input " + std::to_string(i) + ": policy_hex differs from the template");
            std::string pe;
            if (!CheckMultisigPolicy(in.m, in.keys, &pe)) return fail("input " + std::to_string(i) + ": " + pe);
            auto h = ComputeMultisigPolicyHash(in.m, in.keys);
            if (Hex(h) != msh || h != in.spent.pubkey_hash || in.spent.type != OUT_MULTISIG)
                return fail("input " + std::to_string(i) + ": MSH(policy) does not match msh / the spent output");
            const json::Value* sg = e.find("signatures");
            if (sg && sg->is_obj()) {
                for (const auto& kv : sg->o) {
                    char* endp = nullptr; long idx = strtol(kv.first.c_str(), &endp, 10);
                    Sig64 s{};
                    if (!endp || *endp || idx < 0 || idx >= (long)in.keys.size() || kv.second.type != json::Value::T::Str || !UnhexA(kv.second.s, s))
                        return fail("input " + std::to_string(i) + ": bad signature entry");
                    in.sigs[(uint8_t)idx] = s;
                }
            }
        } else if (auth == "single") {
            bool zero = true;
            for (auto b : ti.signature) if (b) zero = false;
            for (auto b : ti.pubkey) if (b) zero = false;
            if (ti.auth_kind != AUTH_SINGLE || !zero) return fail("input " + std::to_string(i) + ": template is not an unsigned single-sig input");
            if (in.spent.type == OUT_MULTISIG) return fail("input " + std::to_string(i) + ": single-sig input declared on OUT_MULTISIG");
            in.auth_kind = AUTH_SINGLE;
            std::string sig, pk;
            if (e.get_str("signature", sig) && e.get_str("pubkey", pk)) {
                if (!UnhexA(sig, in.single_sig) || !UnhexA(pk, in.single_pub)) return fail("input " + std::to_string(i) + ": bad signature");
                in.single_signed = true;
            }
        } else return fail("input " + std::to_string(i) + ": unknown auth '" + auth + "'");
        p.inputs.push_back(in);
    }
    p.outputs = tx.outputs;
    if (!d.get_int("fee", fee) || fee != Fee(p)) return fail("declared fee does not match the template and spent outputs");
    if (!CheckSigsAgainstTemplate(p, err)) return false;
    out = p;
    return true;
}

// ---------------------------------------------------------------------------
// sign / combine / verify
// ---------------------------------------------------------------------------
int Sign(Psst& p, const std::vector<PrivKey>& keys, std::string* err) {
    Transaction tx = UnsignedTx(p);
    auto spent = SpentList(p);
    int added = 0;
    for (const auto& k : keys) {
        PubKey pk{};
        if (!DerivePublicKey(k, pk, err)) continue;
        const PubKeyHash pkh = ComputePubKeyHash(pk);
        for (size_t i = 0; i < p.inputs.size(); ++i) {
            auto& in = p.inputs[i];
            if (in.auth_kind == AUTH_MULTISIG) {
                auto it = std::find(in.keys.begin(), in.keys.end(), pk);
                if (it == in.keys.end()) continue;
                const uint8_t idx = (uint8_t)(it - in.keys.begin());
                if (in.sigs.count(idx)) continue;
                uint8_t got = 0; Sig64 s{};
                if (!SignInputV2Multisig(tx, i, spent, p.chain_id, p.genesis, k, got, s, err)) return -1;
                in.sigs[got] = s; ++added;
            } else if (!in.single_signed && pkh == in.spent.pubkey_hash) {
                Transaction t2 = tx;
                if (!SignInputV2Single(t2, i, spent, p.chain_id, p.genesis, k, err)) return -1;
                in.single_sig = t2.inputs[i].signature; in.single_pub = t2.inputs[i].pubkey; in.single_signed = true; ++added;
            }
        }
    }
    return added;
}

bool Combine(const std::vector<Psst>& parts, Psst& out, std::string* err) {
    auto fail = [&](const std::string& r) { if (err) *err = r; return false; };
    if (parts.empty()) return fail("nothing to combine");
    Psst r = parts[0];
    std::vector<Byte> base; UnsignedTx(r).Serialize(base);
    for (size_t k = 1; k < parts.size(); ++k) {
        const Psst& q = parts[k];
        std::vector<Byte> b; UnsignedTx(q).Serialize(b);
        if (q.net != r.net || q.chain_id != r.chain_id || q.genesis != r.genesis) return fail("file " + std::to_string(k) + ": different network / CHAIN_ID / genesis");
        if (b != base) return fail("file " + std::to_string(k) + ": different unsigned transaction");
        if (q.inputs.size() != r.inputs.size()) return fail("file " + std::to_string(k) + ": different inputs");
        for (size_t i = 0; i < q.inputs.size(); ++i) {
            const auto& a = r.inputs[i]; const auto& c = q.inputs[i];
            if (a.auth_kind != c.auth_kind || a.m != c.m || a.keys != c.keys)
                return fail("file " + std::to_string(k) + ": input " + std::to_string(i) + " has a different policy");
            if (a.spent.amount != c.spent.amount || a.spent.type != c.spent.type || a.spent.pubkey_hash != c.spent.pubkey_hash ||
                a.spent.payload != c.spent.payload)
                return fail("file " + std::to_string(k) + ": input " + std::to_string(i) + " declares a different spent output");
        }
        for (size_t i = 0; i < q.inputs.size(); ++i) {
            for (const auto& kv : q.inputs[i].sigs) r.inputs[i].sigs.emplace(kv.first, kv.second);
            if (!r.inputs[i].single_signed && q.inputs[i].single_signed) {
                r.inputs[i].single_signed = true; r.inputs[i].single_sig = q.inputs[i].single_sig; r.inputs[i].single_pub = q.inputs[i].single_pub;
            }
        }
    }
    if (!CheckSigsAgainstTemplate(r, err)) return false;
    out = r;
    return true;
}

Report Verify(const Psst& p, int64_t height) {
    Report rep;
    bool complete = false;
    Transaction tx = Assemble(p, &complete);
    rep.complete = complete;
    rep.size = TxSerializedSizeExact(tx);
    rep.fee = Fee(p);
    rep.sigchecks = TxSigchecks(tx);
    rep.txid = tx.ComputeTxIdHex();
    for (size_t i = 0; i < p.inputs.size(); ++i) {
        const auto& in = p.inputs[i];
        if (in.auth_kind == AUTH_MULTISIG)
            rep.input_status.push_back("input " + std::to_string(i) + ": multisig " + std::to_string((int)in.m) + "-of-" +
                                       std::to_string(in.keys.size()) + ", " + std::to_string(in.sigs.size()) + " signature(s)" +
                                       (in.sigs.size() >= in.m ? " (threshold met)" : " (INCOMPLETE)"));
        else
            rep.input_status.push_back("input " + std::to_string(i) + ": single-sig " + (in.single_signed ? "(signed)" : "(UNSIGNED)"));
    }
    SpentView v;
    for (const auto& in : p.inputs) {
        UTXOEntry e; e.amount = in.spent.amount; e.type = in.spent.type; e.pubkey_hash = in.spent.pubkey_hash;
        e.payload = in.spent.payload; e.payload_len = (uint16_t)in.spent.payload.size(); e.height = 0; e.is_coinbase = false;
        v.m[OutPoint{in.txid, in.vout}] = e;
    }
    TxValidationContext ctx; ctx.genesis_hash = p.genesis; ctx.spend_height = height; ctx.chain_id = p.chain_id;
    auto r = ValidateTransactionConsensus(tx, v, ctx);
    rep.valid = r.ok && complete;
    rep.reason = complete ? (r.ok ? "ok" : std::to_string((int)r.code) + " " + r.message) : "incomplete: threshold not met";
    return rep;
}

} // namespace sost::psst
