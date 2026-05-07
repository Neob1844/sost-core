// SOST Beacon Phase II-A — local signed-notice channel implementation.
// See include/sost/beacon.h for the public contract and hard invariants.

#include "sost/beacon.h"
#include "sost/crypto.h"
#include "sost/params.h"

#include <secp256k1.h>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <fstream>
#include <mutex>
#include <sstream>

namespace sost::beacon {

// ---------------------------------------------------------------------------
// Hardcoded Beacon public key — placeholder, fail-closed.
//
// Format: 65-byte uncompressed point in hex. Starts with `04` followed by
// two 32-byte coordinates. The placeholder below is the generator-x-axis
// point variant `(1, sqrt(8))` which is a syntactically valid curve
// point owned by no one — verification against any real signature will
// fail, which is the safe default for a freshly cloned tree. The
// operator replaces this constant after running `beacon-keygen.sh`.
// ---------------------------------------------------------------------------
const std::string BEACON_PUBKEY_HEX =
    "04"
    "0000000000000000000000000000000000000000000000000000000000000001"
    "b7c52588d95c3b9aa25b0403f1eef75702e84bb7597aabe663b82f6f04ef2777";

// ---------------------------------------------------------------------------
// File-size cap: defensive against an oversized notices.json (e.g. a
// rogue or buggy operator dropping a multi-MB file). 256 KB is well
// above any realistic Phase II-A workload — a single notice is ~1 KB.
// ---------------------------------------------------------------------------
static constexpr size_t BEACON_FILE_MAX_BYTES = 256 * 1024;

// ===========================================================================
// secp256k1 context — Beacon-private. Distinct from the Schnorr context in
// sbpow.cpp and the ECDSA context in tx_signer.cpp; using a private context
// avoids unintended coupling between unrelated subsystems.
// ===========================================================================
namespace {

secp256k1_context* GetBeaconCtx() {
    static std::once_flag init_flag;
    static secp256k1_context* ctx = nullptr;
    std::call_once(init_flag, []() {
        ctx = secp256k1_context_create(SECP256K1_CONTEXT_VERIFY);
    });
    return ctx;
}

// ---------------------------------------------------------------------------
// Hex decoding. Returns false on any malformed input (odd length, bad
// nibble). Output bytes pre-allocated by caller.
// ---------------------------------------------------------------------------
bool hex_decode(const std::string& hex, std::vector<uint8_t>& out) {
    if (hex.size() % 2 != 0) return false;
    out.clear();
    out.reserve(hex.size() / 2);
    auto nibble = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < hex.size(); i += 2) {
        int hi = nibble(hex[i]);
        int lo = nibble(hex[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back((uint8_t)((hi << 4) | lo));
    }
    return true;
}

// ---------------------------------------------------------------------------
// Base64 decode. Standard base64 alphabet, no URL-safe variants. Returns
// false on any non-base64 character. Padding optional but tolerated.
// ---------------------------------------------------------------------------
inline int b64_value(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

bool b64_decode(const std::string& b64, std::vector<uint8_t>& out) {
    out.clear();
    out.reserve(b64.size() * 3 / 4);
    int val = 0, bits = 0;
    for (char c : b64) {
        if (c == '=') break;
        if (c == ' ' || c == '\n' || c == '\r' || c == '\t') continue;
        int v = b64_value(c);
        if (v < 0) return false;
        val = (val << 6) | v;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out.push_back((uint8_t)((val >> bits) & 0xFF));
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// JSON tokenizer state. Walks the input from a current position. Skips
// whitespace, recognises strings, integers, arrays and the literal nulls
// the Beacon schema does NOT use. Strings are unescaped. Errors are
// reported by returning false from any consumer; the caller propagates.
// ---------------------------------------------------------------------------
struct Cursor {
    const std::string& s;
    size_t             i;
    explicit Cursor(const std::string& src) : s(src), i(0) {}
    void skip_ws() {
        while (i < s.size() && (s[i] == ' ' || s[i] == '\t'
                              || s[i] == '\n' || s[i] == '\r')) ++i;
    }
    bool eof() const { return i >= s.size(); }
    bool peek(char c) { skip_ws(); return !eof() && s[i] == c; }
    bool eat(char c) { skip_ws(); if (eof() || s[i] != c) return false; ++i; return true; }
};

// Parse a JSON string literal at the cursor (consume opening and closing
// quotes). Stores the unescaped UTF-8 result. Recognises \" \\ \/ \n \r
// \t \b \f and \uXXXX (kept as the literal six-byte sequence for any
// payload field — Beacon doesn't introspect inside title_en/message_en).
bool parse_string(Cursor& c, std::string& out) {
    c.skip_ws();
    if (c.eof() || c.s[c.i] != '"') return false;
    ++c.i;
    out.clear();
    while (c.i < c.s.size()) {
        char ch = c.s[c.i++];
        if (ch == '"') return true;
        if (ch == '\\') {
            if (c.i >= c.s.size()) return false;
            char esc = c.s[c.i++];
            switch (esc) {
                case '"': out.push_back('"');  break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/');  break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                case 'u': {
                    // Keep the literal \uXXXX form. We don't decode to
                    // UTF-8 because canonical_payload re-emits the same
                    // form; round-tripping the raw escape is sufficient.
                    if (c.i + 4 > c.s.size()) return false;
                    out.push_back('\\'); out.push_back('u');
                    for (int k = 0; k < 4; ++k) out.push_back(c.s[c.i++]);
                    break;
                }
                default: return false;
            }
        } else {
            out.push_back(ch);
        }
    }
    return false; // unterminated
}

bool parse_int64(Cursor& c, int64_t& out) {
    c.skip_ws();
    if (c.eof()) return false;
    bool neg = false;
    if (c.s[c.i] == '-') { neg = true; ++c.i; }
    if (c.eof() || !std::isdigit((unsigned char)c.s[c.i])) return false;
    int64_t v = 0;
    while (c.i < c.s.size() && std::isdigit((unsigned char)c.s[c.i])) {
        v = v * 10 + (c.s[c.i++] - '0');
    }
    out = neg ? -v : v;
    return true;
}

bool parse_string_array(Cursor& c, std::vector<std::string>& out) {
    out.clear();
    if (!c.eat('[')) return false;
    c.skip_ws();
    if (c.peek(']')) { c.eat(']'); return true; }
    while (true) {
        std::string s;
        if (!parse_string(c, s)) return false;
        out.push_back(std::move(s));
        c.skip_ws();
        if (c.peek(',')) { c.eat(','); continue; }
        if (c.peek(']')) { c.eat(']'); return true; }
        return false;
    }
}

// ---------------------------------------------------------------------------
// Parse a single notice object. Cursor must be positioned at the opening
// '{'. On success, consumes through the matching '}' and populates `n`.
// ---------------------------------------------------------------------------
bool parse_notice_object(Cursor& c, Notice& n) {
    if (!c.eat('{')) return false;
    n = {};
    bool got_id = false, got_net = false, got_sev = false, got_t = false;
    bool got_msg = false, got_ah = false, got_eh = false, got_ca = false;
    bool got_cmd = false, got_sig = false;

    while (true) {
        c.skip_ws();
        if (c.peek('}')) { c.eat('}'); break; }
        std::string key;
        if (!parse_string(c, key)) return false;
        if (!c.eat(':')) return false;
        c.skip_ws();

        if      (key == "notice_id")         { if (!parse_string(c, n.notice_id))  return false; got_id  = true; }
        else if (key == "network")           { if (!parse_string(c, n.network_str)) return false; got_net = true; }
        else if (key == "severity")          { if (!parse_string(c, n.severity))   return false; got_sev = true; }
        else if (key == "title_en")          { if (!parse_string(c, n.title_en))   return false; got_t   = true; }
        else if (key == "message_en")        { if (!parse_string(c, n.message_en)) return false; got_msg = true; }
        else if (key == "activation_height") { if (!parse_int64(c, n.activation_height)) return false; got_ah = true; }
        else if (key == "expires_height")    { if (!parse_int64(c, n.expires_height))    return false; got_eh = true; }
        else if (key == "created_at")        { if (!parse_string(c, n.created_at)) return false; got_ca  = true; }
        else if (key == "commands")          { if (!parse_string_array(c, n.commands)) return false; got_cmd = true; }
        else if (key == "signature")         { if (!parse_string(c, n.signature_b64)) return false; got_sig = true; }
        else {
            // Unknown key: skip the value defensively. Beacon only
            // verifies the canonical form built from KNOWN fields, so
            // any extra key is ignored at the schema layer (and would
            // cause the signature to fail verification anyway because
            // the canonical form omits it — which is intended).
            std::string scratch_str;
            int64_t     scratch_int;
            std::vector<std::string> scratch_arr;
            if      (parse_string(c, scratch_str))         {}
            else if (parse_int64(c, scratch_int))          {}
            else if (parse_string_array(c, scratch_arr))   {}
            else                                            { return false; }
        }
        c.skip_ws();
        if (c.peek(',')) { c.eat(','); continue; }
        if (c.peek('}')) { c.eat('}'); break; }
        return false;
    }
    if (!(got_id && got_net && got_sev && got_t && got_msg
          && got_ah && got_eh && got_ca && got_cmd && got_sig)) {
        return false;
    }
    n.network = parse_network(n.network_str);
    return true;
}

} // namespace (anonymous)

// ===========================================================================
// Public API
// ===========================================================================

Network parse_network(const std::string& s) {
    if (s == "mainnet") return Network::MAINNET;
    if (s == "testnet") return Network::TESTNET;
    return Network::OTHER;
}

bool parse_notices_array(const std::string& json,
                         std::vector<Notice>& out,
                         std::string* err) {
    out.clear();
    Cursor c(json);
    c.skip_ws();
    if (!c.eat('[')) { if (err) *err = "expected top-level '['"; return false; }
    c.skip_ws();
    if (c.peek(']')) { c.eat(']'); return true; }
    while (true) {
        Notice n;
        if (!parse_notice_object(c, n)) {
            if (err) *err = "malformed notice object";
            out.clear();
            return false;
        }
        out.push_back(std::move(n));
        c.skip_ws();
        if (c.peek(',')) { c.eat(','); continue; }
        if (c.peek(']')) { c.eat(']'); return true; }
        if (err) *err = "expected ',' or ']' between notices";
        out.clear();
        return false;
    }
}

// ---------------------------------------------------------------------------
// canonical_payload — re-emit the signed JSON object with the same byte
// stream `jq -cSj 'del(.signature)' <signed.json>` produces:
//   - keys in lexicographic order
//   - compact form (no whitespace, no trailing newline)
//   - signature field DROPPED
//   - strings JSON-escaped with the same minimal subset jq uses
// ---------------------------------------------------------------------------
namespace {

// JSON-escape a string for canonical output. jq's compact emitter
// escapes only the structural subset (\\ \" and the C0 controls);
// non-ASCII bytes pass through unchanged. We mirror that behaviour
// here. Note: parse_string left \uXXXX sequences as the literal
// six-character escape, so they round-trip unchanged.
std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 2);
    out.push_back('"');
    for (unsigned char ch : s) {
        switch (ch) {
            case '"':  out.append("\\\""); break;
            case '\\': out.append("\\\\"); break;
            case '\b': out.append("\\b");  break;
            case '\f': out.append("\\f");  break;
            case '\n': out.append("\\n");  break;
            case '\r': out.append("\\r");  break;
            case '\t': out.append("\\t");  break;
            default:
                if (ch < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", (unsigned)ch);
                    out.append(buf);
                } else {
                    out.push_back((char)ch);
                }
        }
    }
    out.push_back('"');
    return out;
}

std::string render_string_array(const std::vector<std::string>& v) {
    std::string out = "[";
    for (size_t i = 0; i < v.size(); ++i) {
        if (i) out.push_back(',');
        out.append(json_escape(v[i]));
    }
    out.push_back(']');
    return out;
}

} // namespace (anonymous)

std::string canonical_payload(const Notice& n) {
    // Keys in lexicographic order, signature dropped:
    //   activation_height, commands, created_at, expires_height,
    //   message_en, network, notice_id, severity, title_en
    std::ostringstream o;
    o << "{";
    o << "\"activation_height\":" << n.activation_height;
    o << ",\"commands\":" << render_string_array(n.commands);
    o << ",\"created_at\":" << json_escape(n.created_at);
    o << ",\"expires_height\":" << n.expires_height;
    o << ",\"message_en\":" << json_escape(n.message_en);
    o << ",\"network\":" << json_escape(n.network_str);
    o << ",\"notice_id\":" << json_escape(n.notice_id);
    o << ",\"severity\":" << json_escape(n.severity);
    o << ",\"title_en\":" << json_escape(n.title_en);
    o << "}";
    return o.str();
}

bool verify_signature(const Notice& n,
                      const std::string& pubkey_hex_uncompressed) {
    secp256k1_context* ctx = GetBeaconCtx();
    if (!ctx) return false;

    // Parse pubkey hex → secp256k1_pubkey.
    std::vector<uint8_t> pub_bytes;
    if (!hex_decode(pubkey_hex_uncompressed, pub_bytes)) return false;
    if (pub_bytes.size() != 33 && pub_bytes.size() != 65) return false;
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &pk, pub_bytes.data(), pub_bytes.size())) {
        return false;
    }

    // Decode signature: openssl emits DER. libsecp256k1's DER parser
    // accepts the same bytes — no manual conversion needed.
    std::vector<uint8_t> sig_bytes;
    if (!b64_decode(n.signature_b64, sig_bytes)) return false;
    if (sig_bytes.empty()) return false;
    secp256k1_ecdsa_signature sig;
    if (!secp256k1_ecdsa_signature_parse_der(ctx, &sig,
                                              sig_bytes.data(),
                                              sig_bytes.size())) {
        return false;
    }
    // Beacon does NOT enforce lowS — openssl produces both forms and
    // the single-pinned-key trust model is malleability-insensitive.
    // Mirror by normalising to lowS before verify so we accept either.
    secp256k1_ecdsa_signature_normalize(ctx, &sig, &sig);

    // sha256(canonical_payload).
    const std::string canon = canonical_payload(n);
    sost::Bytes32 digest = sost::sha256(
        reinterpret_cast<const uint8_t*>(canon.data()), canon.size());

    return secp256k1_ecdsa_verify(ctx, &sig, digest.data(), &pk) == 1;
}

bool is_active(const Notice& n,
               int64_t current_height,
               Network current_network,
               const std::string& pubkey_hex_uncompressed) {
    if (!n.commands.empty()) return false;                        // Phase II-A invariant
    if (n.network != current_network) return false;
    if (n.activation_height > current_height) return false;       // not yet active
    if (n.expires_height   <= current_height) return false;       // expired
    if (!verify_signature(n, pubkey_hex_uncompressed)) return false;
    return true;
}

// ---------------------------------------------------------------------------
// Bounded file read with a size cap. Returns true on success and sets
// `out` to the file's bytes. Any failure (open / oversized / read error)
// returns false; the caller treats false as "no notices".
// ---------------------------------------------------------------------------
namespace {

bool read_file_bounded(const std::string& path, std::string& out,
                       size_t cap_bytes) {
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) return false;
    f.seekg(0, std::ios::end);
    std::streamsize sz = f.tellg();
    if (sz < 0) return false;
    if ((size_t)sz > cap_bytes) return false;
    f.seekg(0, std::ios::beg);
    out.resize((size_t)sz);
    if (sz > 0 && !f.read(out.data(), sz)) return false;
    return true;
}

} // namespace (anonymous)

std::vector<Notice> load_active_notices(const std::string& datadir,
                                        int64_t            current_height,
                                        Network            current_network,
                                        const std::string& pubkey_hex_uncompressed) {
    // Phase II-A dormancy: explicit silence pre-fork.
    if (current_height < BEACON_PHASE2A_ACTIVATION_HEIGHT) return {};

    std::string path = datadir;
    if (path.empty()) path = ".";
    if (path.back() != '/') path.push_back('/');
    path.append("notices.json");

    std::string body;
    if (!read_file_bounded(path, body, BEACON_FILE_MAX_BYTES)) return {};

    std::vector<Notice> all;
    if (!parse_notices_array(body, all)) return {};

    std::vector<Notice> out;
    out.reserve(all.size());
    for (auto& n : all) {
        if (is_active(n, current_height, current_network,
                      pubkey_hex_uncompressed)) {
            out.push_back(std::move(n));
        }
    }
    return out;
}

std::string serialize_notices_for_rpc(const std::vector<Notice>& notices) {
    if (notices.empty()) return "[]";
    std::string out = "[";
    for (size_t i = 0; i < notices.size(); ++i) {
        if (i) out.push_back(',');
        const Notice& n = notices[i];
        out.append("{\"notice_id\":");        out.append(json_escape(n.notice_id));
        out.append(",\"network\":");          out.append(json_escape(n.network_str));
        out.append(",\"severity\":");         out.append(json_escape(n.severity));
        out.append(",\"title_en\":");         out.append(json_escape(n.title_en));
        out.append(",\"message_en\":");       out.append(json_escape(n.message_en));
        out.append(",\"activation_height\":");
        out.append(std::to_string(n.activation_height));
        out.append(",\"expires_height\":");
        out.append(std::to_string(n.expires_height));
        out.append(",\"created_at\":");       out.append(json_escape(n.created_at));
        out.append("}");
    }
    out.push_back(']');
    return out;
}

} // namespace sost::beacon
