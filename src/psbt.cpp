// psbt.cpp — SOST-PSBT implementation
// Wallet-layer offline signing, no consensus change.
#include "sost/psbt.h"
#include <openssl/evp.h>
#include <openssl/crypto.h>
#include <cstring>
#include <sstream>
#include <algorithm>
#include <cstdio>

namespace sost {

// ---------------------------------------------------------------------------
// Hex helpers (local to this TU)
// ---------------------------------------------------------------------------
static std::string to_hex(const uint8_t* d, size_t n) {
    static const char* h = "0123456789abcdef";
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s += h[d[i] >> 4]; s += h[d[i] & 0xF]; }
    return s;
}

static bool from_hex(const std::string& hex, uint8_t* out, size_t len) {
    if (hex.size() != len * 2) return false;
    auto hv = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + c - 'a';
        if (c >= 'A' && c <= 'F') return 10 + c - 'A';
        return -1;
    };
    for (size_t i = 0; i < len; ++i) {
        int hi = hv(hex[i * 2]), lo = hv(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

// ---------------------------------------------------------------------------
// Base64 encode/decode
// ---------------------------------------------------------------------------
static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static std::string b64_encode(const std::string& in) {
    std::string out;
    int val = 0, valb = -6;
    for (unsigned char c : in) {
        val = (val << 8) + c;
        valb += 8;
        while (valb >= 0) { out.push_back(B64[(val >> valb) & 0x3F]); valb -= 6; }
    }
    if (valb > -6) out.push_back(B64[((val << 8) >> (valb + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

static std::string b64_decode(const std::string& in) {
    static int T[256] = {0};
    static bool init = false;
    if (!init) {
        std::memset(T, -1, sizeof(T));
        for (int i = 0; i < 64; ++i) T[(unsigned char)B64[i]] = i;
        T[(unsigned char)'='] = 0;
        init = true;
    }
    std::string out;
    int val = 0, valb = -8;
    for (unsigned char c : in) {
        if (T[c] == -1) break;
        val = (val << 6) + T[c];
        valb += 6;
        if (valb >= 0) { out.push_back((char)((val >> valb) & 0xFF)); valb -= 8; }
    }
    return out;
}

// ---------------------------------------------------------------------------
// JSON helpers (minimal, no library)
// ---------------------------------------------------------------------------
static std::string json_escape(const std::string& s) {
    std::string r;
    for (char c : s) {
        if (c == '"') r += "\\\"";
        else if (c == '\\') r += "\\\\";
        else if (c == '\n') r += "\\n";
        else r += c;
    }
    return r;
}

static std::string extract_str(const std::string& json, const std::string& key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos + key.size() + 2);
    if (pos == std::string::npos) return "";
    pos++; // skip opening quote
    auto end = json.find('"', pos);
    if (end == std::string::npos) return "";
    return json.substr(pos, end - pos);
}

static int64_t extract_int(const std::string& json, const std::string& key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return 0;
    pos = json.find(':', pos);
    if (pos == std::string::npos) return 0;
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    return std::strtoll(json.c_str() + pos, nullptr, 10);
}

static bool extract_bool(const std::string& json, const std::string& key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return false;
    pos = json.find(':', pos);
    if (pos == std::string::npos) return false;
    return json.find("true", pos) < json.find('\n', pos);
}

// ---------------------------------------------------------------------------
// psbt_create
// ---------------------------------------------------------------------------
bool psbt_create(
    PSBT& out,
    const std::vector<PSBTUtxoRef>& utxo_refs,
    const std::string& to_address,
    int64_t send_amount,
    const std::string& change_address,
    int64_t fee,
    std::string* err)
{
    if (utxo_refs.empty()) {
        if (err) *err = "no inputs";
        return false;
    }
    if (send_amount <= 0) {
        if (err) *err = "amount must be positive";
        return false;
    }
    if (fee < 0) {
        if (err) *err = "fee must be non-negative";
        return false;
    }

    PubKeyHash to_pkh{};
    if (!address_decode(to_address, to_pkh)) {
        if (err) *err = "invalid destination address";
        return false;
    }

    int64_t total_in = 0;
    for (const auto& u : utxo_refs) {
        if (u.amount <= 0) {
            if (err) *err = "input amount must be positive";
            return false;
        }
        // Overflow check
        if (total_in > 0 && u.amount > INT64_MAX - total_in) {
            if (err) *err = "input amount overflow";
            return false;
        }
        total_in += u.amount;
    }

    int64_t needed = send_amount + fee;
    if (needed < send_amount) { // overflow
        if (err) *err = "amount + fee overflow";
        return false;
    }
    if (total_in < needed) {
        if (err) *err = "insufficient inputs: have " + std::to_string(total_in) +
                         " need " + std::to_string(needed);
        return false;
    }

    int64_t change = total_in - needed;

    out = PSBT{};
    out.version = 0;
    out.fee = fee;
    out.change_address = change_address;

    // Build inputs
    for (const auto& u : utxo_refs) {
        PSBTInput inp;
        inp.prev_txid_hex = to_hex(u.txid.data(), 32);
        inp.prev_vout = u.vout;
        inp.amount = u.amount;
        inp.output_type = u.output_type;
        inp.input_type = PSBTInputType::P2PKH;
        inp.pkh_hex = to_hex(u.pkh.data(), 20);
        inp.required_sigs = 1;
        out.inputs.push_back(std::move(inp));
    }

    // Build outputs
    PSBTOutput pay;
    pay.amount = send_amount;
    pay.address = to_address;
    pay.output_type = OUT_TRANSFER;
    pay.pkh_hex = to_hex(to_pkh.data(), 20);
    out.outputs.push_back(std::move(pay));

    if (change > 0) {
        PubKeyHash change_pkh{};
        if (!change_address.empty() && address_decode(change_address, change_pkh)) {
            PSBTOutput ch;
            ch.amount = change;
            ch.address = change_address;
            ch.output_type = OUT_TRANSFER;
            ch.pkh_hex = to_hex(change_pkh.data(), 20);
            out.outputs.push_back(std::move(ch));
        }
    }

    return true;
}

// ---------------------------------------------------------------------------
// psbt_sign
// ---------------------------------------------------------------------------
PSBTSignResult psbt_sign(
    PSBT& psbt,
    const PrivKey& privkey,
    const Hash256& genesis_hash)
{
    PSBTSignResult res;

    // Derive public key from privkey
    PubKey pubkey{};
    std::string derr;
    if (!DerivePublicKey(privkey, pubkey, &derr)) {
        res.error = "cannot derive pubkey: " + derr;
        return res;
    }
    PubKeyHash pkh = ComputePubKeyHash(pubkey);
    std::string pubkey_hex = to_hex(pubkey.data(), 33);
    std::string pkh_hex = to_hex(pkh.data(), 20);

    // Build the unsigned transaction for sighash computation
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    for (const auto& inp : psbt.inputs) {
        TxInput ti;
        from_hex(inp.prev_txid_hex, ti.prev_txid.data(), 32);
        ti.prev_index = inp.prev_vout;
        tx.inputs.push_back(ti);
    }
    for (const auto& out : psbt.outputs) {
        TxOutput to;
        to.amount = out.amount;
        to.type = out.output_type;
        from_hex(out.pkh_hex, to.pubkey_hash.data(), 20);
        tx.outputs.push_back(to);
    }

    // Sign each input where our key matches
    for (size_t i = 0; i < psbt.inputs.size(); ++i) {
        auto& inp = psbt.inputs[i];
        if (inp.finalized) continue;

        bool key_matches = false;
        if (inp.input_type == PSBTInputType::P2PKH) {
            key_matches = (inp.pkh_hex == pkh_hex);
        } else if (inp.input_type == PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG) {
            for (const auto& pk : inp.pubkeys_hex) {
                if (pk == pubkey_hex) { key_matches = true; break; }
            }
        }

        if (!key_matches) continue;
        res.inputs_matched++;

        // Check for duplicate signature
        bool already_signed = false;
        for (const auto& ps : inp.partial_sigs) {
            if (ps.pubkey_hex == pubkey_hex) { already_signed = true; break; }
        }
        if (already_signed) continue;

        // Compute sighash
        SpentOutput spent;
        spent.amount = inp.amount;
        spent.type = inp.output_type;
        Hash256 sighash = ComputeSighash(tx, i, spent, genesis_hash);

        // Sign
        Sig64 sig{};
        if (!SignSighash(privkey, sighash, sig, &derr)) {
            res.error = "sign failed for input " + std::to_string(i) + ": " + derr;
            continue;
        }

        PSBTPartialSig ps;
        ps.pubkey_hex = pubkey_hex;
        ps.signature_hex = to_hex(sig.data(), 64);
        inp.partial_sigs.push_back(std::move(ps));
        res.signatures_added++;
    }

    // Check completeness
    bool all_complete = true;
    for (const auto& inp : psbt.inputs) {
        if (inp.finalized) continue;
        if (inp.partial_sigs.size() < inp.required_sigs) {
            all_complete = false;
            break;
        }
    }
    psbt.complete = all_complete;
    res.complete = all_complete;

    // Wipe privkey copy from stack (it's passed by const ref, but be safe)
    // The caller is responsible for wiping their own copy.

    return res;
}

// ---------------------------------------------------------------------------
// psbt_combine
// ---------------------------------------------------------------------------
bool psbt_combine(
    PSBT& out,
    const std::vector<PSBT>& partials,
    std::string* err)
{
    if (partials.empty()) {
        if (err) *err = "no PSBTs to combine";
        return false;
    }

    out = partials[0]; // start with first

    for (size_t p = 1; p < partials.size(); ++p) {
        const auto& other = partials[p];
        if (other.inputs.size() != out.inputs.size()) {
            if (err) *err = "incompatible PSBTs: different input count";
            return false;
        }
        if (other.outputs.size() != out.outputs.size()) {
            if (err) *err = "incompatible PSBTs: different output count";
            return false;
        }

        // Merge signatures
        for (size_t i = 0; i < out.inputs.size(); ++i) {
            for (const auto& sig : other.inputs[i].partial_sigs) {
                // Check for duplicate
                bool dup = false;
                for (const auto& existing : out.inputs[i].partial_sigs) {
                    if (existing.pubkey_hex == sig.pubkey_hex) { dup = true; break; }
                }
                if (!dup) {
                    out.inputs[i].partial_sigs.push_back(sig);
                }
            }
        }
    }

    // Check completeness
    bool all_complete = true;
    for (const auto& inp : out.inputs) {
        if (inp.partial_sigs.size() < inp.required_sigs) {
            all_complete = false;
            break;
        }
    }
    out.complete = all_complete;
    return true;
}

// ---------------------------------------------------------------------------
// psbt_finalize
// ---------------------------------------------------------------------------
std::string psbt_finalize(
    PSBT& psbt,
    const Hash256& genesis_hash,
    std::string* err)
{
    // Check all inputs have enough signatures
    for (size_t i = 0; i < psbt.inputs.size(); ++i) {
        const auto& inp = psbt.inputs[i];
        if (inp.partial_sigs.size() < inp.required_sigs) {
            if (err) *err = "input " + std::to_string(i) + ": need " +
                            std::to_string(inp.required_sigs) + " sig(s), have " +
                            std::to_string(inp.partial_sigs.size());
            return "";
        }
        if (inp.input_type == PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG &&
            inp.redeem_script_hex.empty()) {
            if (err) *err = "input " + std::to_string(i) + ": missing redeemScript";
            return "";
        }
    }

    // Build the signed transaction
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    for (size_t i = 0; i < psbt.inputs.size(); ++i) {
        const auto& inp = psbt.inputs[i];
        TxInput ti;
        from_hex(inp.prev_txid_hex, ti.prev_txid.data(), 32);
        ti.prev_index = inp.prev_vout;

        if (inp.input_type == PSBTInputType::P2PKH) {
            // P2PKH: one signature + pubkey
            if (inp.partial_sigs.empty()) {
                if (err) *err = "input " + std::to_string(i) + ": no signature";
                return "";
            }
            const auto& ps = inp.partial_sigs[0];
            from_hex(ps.signature_hex, ti.signature.data(), 64);
            from_hex(ps.pubkey_hex, ti.pubkey.data(), 33);
        }
        // Multisig finalization will be handled in TAREA 2

        tx.inputs.push_back(ti);
    }

    for (const auto& out : psbt.outputs) {
        TxOutput to;
        to.amount = out.amount;
        to.type = out.output_type;
        from_hex(out.pkh_hex, to.pubkey_hash.data(), 20);
        tx.outputs.push_back(to);
    }

    // Serialize
    std::vector<Byte> raw;
    std::string ser_err;
    if (!tx.Serialize(raw, &ser_err)) {
        if (err) *err = "serialization failed: " + ser_err;
        return "";
    }

    psbt.complete = true;
    for (auto& inp : psbt.inputs) inp.finalized = true;

    return to_hex(raw.data(), raw.size());
}

// ---------------------------------------------------------------------------
// psbt_encode — serialize to base64 transport
// ---------------------------------------------------------------------------
std::string psbt_encode(const PSBT& psbt) {
    std::ostringstream j;
    j << "{\"sost_psbt_version\":" << psbt.version
      << ",\"complete\":" << (psbt.complete ? "true" : "false")
      << ",\"fee\":" << psbt.fee
      << ",\"change_address\":\"" << json_escape(psbt.change_address) << "\"";

    j << ",\"inputs\":[";
    for (size_t i = 0; i < psbt.inputs.size(); ++i) {
        if (i > 0) j << ",";
        const auto& inp = psbt.inputs[i];
        j << "{\"prev_txid\":\"" << inp.prev_txid_hex << "\""
          << ",\"prev_vout\":" << inp.prev_vout
          << ",\"amount\":" << inp.amount
          << ",\"output_type\":" << (int)inp.output_type
          << ",\"input_type\":" << (int)inp.input_type
          << ",\"pkh\":\"" << inp.pkh_hex << "\""
          << ",\"redeem_script\":\"" << inp.redeem_script_hex << "\""
          << ",\"required_sigs\":" << inp.required_sigs
          << ",\"finalized\":" << (inp.finalized ? "true" : "false");

        j << ",\"pubkeys\":[";
        for (size_t k = 0; k < inp.pubkeys_hex.size(); ++k) {
            if (k > 0) j << ",";
            j << "\"" << inp.pubkeys_hex[k] << "\"";
        }
        j << "]";

        j << ",\"partial_sigs\":[";
        for (size_t k = 0; k < inp.partial_sigs.size(); ++k) {
            if (k > 0) j << ",";
            j << "{\"pubkey\":\"" << inp.partial_sigs[k].pubkey_hex << "\""
              << ",\"sig\":\"" << inp.partial_sigs[k].signature_hex << "\"}";
        }
        j << "]}";
    }
    j << "]";

    j << ",\"outputs\":[";
    for (size_t i = 0; i < psbt.outputs.size(); ++i) {
        if (i > 0) j << ",";
        const auto& out = psbt.outputs[i];
        j << "{\"amount\":" << out.amount
          << ",\"address\":\"" << json_escape(out.address) << "\""
          << ",\"output_type\":" << (int)out.output_type
          << ",\"pkh\":\"" << out.pkh_hex << "\"}";
    }
    j << "]}";

    // Magic prefix + JSON → base64
    std::string payload = "sost-psbt\xff" + j.str();
    return b64_encode(payload);
}

// ---------------------------------------------------------------------------
// psbt_decode — parse from base64 transport
// ---------------------------------------------------------------------------
bool psbt_decode(const std::string& encoded, PSBT& out, std::string* err) {
    std::string payload = b64_decode(encoded);
    if (payload.size() < 10 || payload.substr(0, 10) != std::string("sost-psbt\xff", 10)) {
        if (err) *err = "invalid magic prefix";
        return false;
    }

    std::string json = payload.substr(10);
    out = PSBT{};
    out.version = (uint32_t)extract_int(json, "sost_psbt_version");
    out.complete = extract_bool(json, "complete");
    out.fee = extract_int(json, "fee");
    out.change_address = extract_str(json, "change_address");

    // Parse inputs array
    auto inputs_pos = json.find("\"inputs\":[");
    if (inputs_pos != std::string::npos) {
        size_t pos = json.find('[', inputs_pos) + 1;
        while (pos < json.size()) {
            auto obj_start = json.find('{', pos);
            if (obj_start == std::string::npos || obj_start > json.find(']', inputs_pos)) break;
            auto obj_end = json.find('}', obj_start);
            // Find matching closing brace (handle nested arrays)
            int depth = 0;
            for (size_t p = obj_start; p < json.size(); ++p) {
                if (json[p] == '{') depth++;
                else if (json[p] == '}') { depth--; if (depth == 0) { obj_end = p; break; } }
            }
            if (obj_end == std::string::npos) break;

            std::string block = json.substr(obj_start, obj_end - obj_start + 1);
            PSBTInput inp;
            inp.prev_txid_hex = extract_str(block, "prev_txid");
            inp.prev_vout = (uint32_t)extract_int(block, "prev_vout");
            inp.amount = extract_int(block, "amount");
            inp.output_type = (uint8_t)extract_int(block, "output_type");
            inp.input_type = (PSBTInputType)extract_int(block, "input_type");
            inp.pkh_hex = extract_str(block, "pkh");
            inp.redeem_script_hex = extract_str(block, "redeem_script");
            inp.required_sigs = (uint32_t)extract_int(block, "required_sigs");
            inp.finalized = extract_bool(block, "finalized");

            // Parse partial_sigs
            auto sigs_pos = block.find("\"partial_sigs\":[");
            if (sigs_pos != std::string::npos) {
                size_t sp = block.find('[', sigs_pos) + 1;
                while (sp < block.size()) {
                    auto so = block.find('{', sp);
                    auto se = block.find('}', so);
                    if (so == std::string::npos || se == std::string::npos) break;
                    std::string sb = block.substr(so, se - so + 1);
                    PSBTPartialSig ps;
                    ps.pubkey_hex = extract_str(sb, "pubkey");
                    ps.signature_hex = extract_str(sb, "sig");
                    if (!ps.pubkey_hex.empty()) inp.partial_sigs.push_back(std::move(ps));
                    sp = se + 1;
                }
            }

            // Parse pubkeys array
            auto pks_pos = block.find("\"pubkeys\":[");
            if (pks_pos != std::string::npos) {
                size_t pp = block.find('[', pks_pos) + 1;
                while (pp < block.size()) {
                    auto qs = block.find('"', pp);
                    if (qs == std::string::npos) break;
                    auto qe = block.find('"', qs + 1);
                    if (qe == std::string::npos) break;
                    std::string pk = block.substr(qs + 1, qe - qs - 1);
                    if (!pk.empty()) inp.pubkeys_hex.push_back(pk);
                    pp = qe + 1;
                    if (pp < block.size() && block[pp] == ']') break;
                }
            }

            out.inputs.push_back(std::move(inp));
            pos = obj_end + 1;
        }
    }

    // Parse outputs array
    auto outputs_pos = json.find("\"outputs\":[");
    if (outputs_pos != std::string::npos) {
        size_t pos = json.find('[', outputs_pos) + 1;
        while (pos < json.size()) {
            auto obj_start = json.find('{', pos);
            auto arr_end = json.find(']', outputs_pos + 11);
            if (obj_start == std::string::npos || obj_start > arr_end) break;
            auto obj_end = json.find('}', obj_start);
            if (obj_end == std::string::npos) break;

            std::string block = json.substr(obj_start, obj_end - obj_start + 1);
            PSBTOutput outp;
            outp.amount = extract_int(block, "amount");
            outp.address = extract_str(block, "address");
            outp.output_type = (uint8_t)extract_int(block, "output_type");
            outp.pkh_hex = extract_str(block, "pkh");
            out.outputs.push_back(std::move(outp));
            pos = obj_end + 1;
        }
    }

    return true;
}

// ---------------------------------------------------------------------------
// psbt_describe
// ---------------------------------------------------------------------------
std::string psbt_describe(const PSBT& psbt) {
    std::ostringstream s;
    s << "=== SOST-PSBT ===\n";
    s << "Version: " << psbt.version << "\n";
    s << "Complete: " << (psbt.complete ? "YES" : "NO") << "\n";
    s << "Fee: " << psbt.fee << " stocks\n";
    s << "Change: " << (psbt.change_address.empty() ? "(none)" : psbt.change_address) << "\n";

    s << "\nInputs (" << psbt.inputs.size() << "):\n";
    for (size_t i = 0; i < psbt.inputs.size(); ++i) {
        const auto& inp = psbt.inputs[i];
        s << "  [" << i << "] " << inp.prev_txid_hex.substr(0, 16) << "...:" << inp.prev_vout
          << "  amount=" << inp.amount << " stocks";
        if (inp.input_type == PSBTInputType::P2PKH) {
            s << "  type=P2PKH";
        } else {
            s << "  type=MULTISIG(" << inp.required_sigs << "-of-" << inp.pubkeys_hex.size() << ")";
        }
        s << "  sigs=" << inp.partial_sigs.size() << "/" << inp.required_sigs;
        s << (inp.finalized ? " [FINALIZED]" : "") << "\n";

        for (const auto& ps : inp.partial_sigs) {
            s << "    sig by: " << ps.pubkey_hex.substr(0, 16) << "...\n";
        }
    }

    s << "\nOutputs (" << psbt.outputs.size() << "):\n";
    for (size_t i = 0; i < psbt.outputs.size(); ++i) {
        const auto& out = psbt.outputs[i];
        s << "  [" << i << "] " << out.address << "  amount=" << out.amount << " stocks\n";
    }

    return s.str();
}

} // namespace sost
