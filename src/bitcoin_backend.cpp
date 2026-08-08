// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// bitcoin_backend.cpp — optional Bitcoin JSON-RPC backend for BTC atomic swaps.
// See include/sost/bitcoin_backend.h for the fund-safety / Option-A rules.
//
// This file has NO libwally dependency and builds in both Option A (BTC OFF)
// and Option B (BTC ON): it is a pure network/JSON layer, gated so that with
// BTC OFF the factory only ever hands back a NullBitcoinBackend.

#include "sost/bitcoin_backend.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <unistd.h>

namespace sost {
namespace atomic_swap {
namespace btc {

const char* BtcTxStateName(BtcTxState s) {
    switch (s) {
        case BtcTxState::Unknown:  return "Unknown";
        case BtcTxState::NotFound: return "NotFound";
        case BtcTxState::InMempool:return "InMempool";
        case BtcTxState::Confirmed:return "Confirmed";
    }
    return "?";
}

// ===========================================================================
// Small, dependency-free helpers (base64 + tolerant JSON field extraction).
// These mirror the hand-rolled style already used in src/tx_send.cpp so we do
// not pull in a JSON library. They are deliberately conservative: on any doubt
// they report failure rather than guessing a value.
// ===========================================================================

static std::string base64_encode(const std::string& in) {
    static const char* chars =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val = 0, valb = -6;
    for (unsigned char c : in) {
        val = (val << 8) + c;
        valb += 8;
        while (valb >= 0) { out.push_back(chars[(val >> valb) & 0x3F]); valb -= 6; }
    }
    if (valb > -6) out.push_back(chars[((val << 8) >> (valb + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

// Extract the string value of "key":"value" (first occurrence). ok=false-ish
// signalled by empty return only where the caller treats "" as absent.
static bool json_get_string(const std::string& j, const std::string& key, std::string& out) {
    auto pos = j.find("\"" + key + "\"");
    if (pos == std::string::npos) return false;
    pos = j.find(':', pos + key.size() + 2);
    if (pos == std::string::npos) return false;
    // skip whitespace
    ++pos;
    while (pos < j.size() && (j[pos] == ' ' || j[pos] == '\t')) ++pos;
    if (pos >= j.size() || j[pos] != '"') return false;
    auto start = pos + 1;
    auto end = j.find('"', start);
    if (end == std::string::npos) return false;
    out = j.substr(start, end - start);
    return true;
}

// Extract an integer "key": <int> (first occurrence).
static bool json_get_int(const std::string& j, const std::string& key, int64_t& out) {
    auto pos = j.find("\"" + key + "\"");
    if (pos == std::string::npos) return false;
    pos = j.find(':', pos + key.size() + 2);
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < j.size() && (j[pos] == ' ' || j[pos] == '\t')) ++pos;
    if (pos >= j.size()) return false;
    bool neg = false;
    if (j[pos] == '-') { neg = true; ++pos; }
    if (pos >= j.size() || !std::isdigit((unsigned char)j[pos])) return false;
    int64_t v = 0;
    while (pos < j.size() && std::isdigit((unsigned char)j[pos])) {
        v = v * 10 + (j[pos] - '0');
        ++pos;
    }
    out = neg ? -v : v;
    return true;
}

// Parse a Bitcoin decimal amount ("key": 0.12345678) into integer satoshis
// WITHOUT floating point (avoids rounding drift). Handles up to 8 decimals.
static bool json_get_btc_sats(const std::string& j, const std::string& key,
                              size_t from, int64_t& out_sats) {
    auto pos = j.find("\"" + key + "\"", from);
    if (pos == std::string::npos) return false;
    pos = j.find(':', pos + key.size() + 2);
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < j.size() && (j[pos] == ' ' || j[pos] == '\t')) ++pos;
    bool neg = false;
    if (pos < j.size() && j[pos] == '-') { neg = true; ++pos; }
    int64_t whole = 0;
    bool any = false;
    while (pos < j.size() && std::isdigit((unsigned char)j[pos])) {
        whole = whole * 10 + (j[pos] - '0'); ++pos; any = true;
    }
    int64_t frac = 0; int fracdigits = 0;
    if (pos < j.size() && j[pos] == '.') {
        ++pos;
        while (pos < j.size() && std::isdigit((unsigned char)j[pos]) && fracdigits < 8) {
            frac = frac * 10 + (j[pos] - '0'); ++pos; ++fracdigits; any = true;
        }
        // consume any extra fractional digits beyond 8 (ignored)
        while (pos < j.size() && std::isdigit((unsigned char)j[pos])) ++pos;
    }
    if (!any) return false;
    while (fracdigits < 8) { frac *= 10; ++fracdigits; }
    int64_t sats = whole * 100000000LL + frac;
    out_sats = neg ? -sats : sats;
    return true;
}

// Returns true iff the JSON-RPC response carries a non-null "error" object,
// and fills `msg` with its message.
static bool json_rpc_error(const std::string& j, std::string& msg) {
    auto pos = j.find("\"error\"");
    if (pos == std::string::npos) return false;
    pos = j.find(':', pos + 7);
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < j.size() && (j[pos] == ' ' || j[pos] == '\t')) ++pos;
    if (pos >= j.size()) return false;
    if (j.compare(pos, 4, "null") == 0) return false;  // error: null → success
    if (j[pos] != '{') return false;                    // unexpected shape
    std::string m;
    if (json_get_string(j.substr(pos), "message", m)) msg = m;
    else msg = "bitcoind RPC error";
    return true;
}

// Extract the raw substring of the top-level "result" value (string or scalar
// or object/array), best-effort, for callers that scan inside it.
static std::string json_result_region(const std::string& j) {
    auto pos = j.find("\"result\"");
    if (pos == std::string::npos) return j;
    pos = j.find(':', pos + 8);
    if (pos == std::string::npos) return j;
    return j.substr(pos + 1);
}

// ===========================================================================
// Default raw-socket HTTP transport (mirrors tx_send.cpp::rpc_call).
// ===========================================================================

std::string DefaultBtcHttpTransport(const std::string& host, int port,
                                    const std::string& auth_b64,
                                    const std::string& json_body) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";
    struct hostent* he = ::gethostbyname(host.c_str());
    if (!he) { ::close(fd); return ""; }
    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)port);
    std::memcpy(&addr.sin_addr, he->h_addr_list[0], (size_t)he->h_length);
    if (::connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) { ::close(fd); return ""; }

    std::string req = "POST / HTTP/1.1\r\nHost: " + host + "\r\n"
                      "Authorization: Basic " + auth_b64 + "\r\n"
                      "Content-Type: application/json\r\n"
                      "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
                      "Connection: close\r\n\r\n" + json_body;
    ssize_t wr = ::write(fd, req.c_str(), req.size());
    if (wr < 0) { ::close(fd); return ""; }

    std::string response;
    char buf[4096];
    ssize_t n;
    while ((n = ::read(fd, buf, sizeof(buf))) > 0) response.append(buf, (size_t)n);
    ::close(fd);

    auto hdr_end = response.find("\r\n\r\n");
    if (hdr_end != std::string::npos) response = response.substr(hdr_end + 4);
    return response;
}

// ===========================================================================
// BitcoinRpcConfig
// ===========================================================================

static std::string env_str(const char* k) {
    const char* v = std::getenv(k);
    return v ? std::string(v) : std::string();
}

BitcoinRpcConfig BitcoinRpcConfig::FromEnv() {
    BitcoinRpcConfig c;
    c.host = env_str("BTC_RPC_HOST");
    std::string p = env_str("BTC_RPC_PORT");
    c.port = p.empty() ? 0 : std::atoi(p.c_str());
    c.user = env_str("BTC_RPC_USER");
    c.pass = env_str("BTC_RPC_PASSWORD");
    std::string net = env_str("BTC_NETWORK");
    if (!net.empty()) c.network = net;
    std::string conf = env_str("BTC_CONFIRMATIONS");
    if (!conf.empty()) c.min_confirmations = std::atoi(conf.c_str());
    if (c.min_confirmations < 1) c.min_confirmations = 1;
    // Runtime gate — same variable the signing module reads.
    std::string g = env_str("SOST_BTC_ATOMIC_SWAP_ENABLED");
    c.runtime_enabled = (g == "1" || g == "t" || g == "T" || g == "y" || g == "Y" ||
                         g == "true" || g == "TRUE");
    return c;
}

bool BitcoinRpcConfig::HasCredentials() const {
    return !host.empty() && port > 0 && !user.empty() && !pass.empty();
}

bool BitcoinRpcConfig::IsUsable() const {
    return runtime_enabled && HasCredentials();
}

// ===========================================================================
// BitcoindRpcBackend
// ===========================================================================

BitcoindRpcBackend::BitcoindRpcBackend(BitcoinRpcConfig cfg, BtcHttpTransport transport)
    : cfg_(std::move(cfg)), transport_(std::move(transport)) {
    if (!transport_) transport_ = &DefaultBtcHttpTransport;
}

std::string BitcoindRpcBackend::Rpc(const std::string& method, const std::string& params_json) {
    // bitcoind speaks JSON-RPC 1.0.
    std::string body = "{\"jsonrpc\":\"1.0\",\"id\":\"sost-swap\",\"method\":\"" +
                       method + "\",\"params\":" + params_json + "}";
    std::string auth = base64_encode(cfg_.user + ":" + cfg_.pass);
    return transport_(cfg_.host, cfg_.port, auth, body);
}

std::string BitcoindRpcBackend::CallRawForTest(const std::string& method,
                                               const std::string& params_json) {
    return Rpc(method, params_json);
}

BtcBroadcastResult BitcoindRpcBackend::BroadcastRawTransaction(const std::string& raw_tx_hex) {
    BtcBroadcastResult r;
    if (!IsConfigured()) { r.error = "BTC backend not configured"; return r; }
    std::string resp = Rpc("sendrawtransaction", "[\"" + raw_tx_hex + "\"]");
    if (resp.empty()) { r.error = "bitcoind RPC transport failure"; return r; }
    std::string emsg;
    if (json_rpc_error(resp, emsg)) { r.error = emsg; return r; }
    // result is the txid string.
    std::string txid;
    if (!json_get_string(resp, "result", txid) || txid.size() != 64) {
        r.error = "unexpected sendrawtransaction response";
        return r;
    }
    r.ok = true;
    r.txid = txid;
    return r;
}

BtcRawTxResult BitcoindRpcBackend::GetRawTransaction(const std::string& txid) {
    BtcRawTxResult r;
    if (!IsConfigured()) { r.error = "BTC backend not configured"; return r; }
    // verbose=false → result is the raw hex string.
    std::string resp = Rpc("getrawtransaction", "[\"" + txid + "\",false]");
    if (resp.empty()) { r.error = "bitcoind RPC transport failure"; return r; }
    std::string emsg;
    if (json_rpc_error(resp, emsg)) { r.error = emsg; return r; }
    std::string hex;
    if (!json_get_string(resp, "result", hex) || hex.empty()) {
        r.error = "raw tx not returned";
        return r;
    }
    r.ok = true;
    r.raw_tx_hex = hex;
    return r;
}

BtcTxStatus BitcoindRpcBackend::GetTransactionStatus(const std::string& txid) {
    BtcTxStatus r;
    if (!IsConfigured()) { r.error = "BTC backend not configured"; return r; }
    // verbose=true → result object with "confirmations" when known.
    std::string resp = Rpc("getrawtransaction", "[\"" + txid + "\",true]");
    if (resp.empty()) { r.error = "bitcoind RPC transport failure"; return r; }
    std::string emsg;
    if (json_rpc_error(resp, emsg)) {
        // A missing tx is a normal, queryable answer: the query succeeded.
        if (emsg.find("No such") != std::string::npos ||
            emsg.find("not found") != std::string::npos ||
            emsg.find("No information") != std::string::npos) {
            r.ok = true; r.state = BtcTxState::NotFound; return r;
        }
        r.error = emsg;
        return r;
    }
    r.ok = true;
    int64_t conf = 0;
    if (json_get_int(resp, "confirmations", conf) && conf > 0) {
        r.state = BtcTxState::Confirmed;
        r.confirmations = conf;
    } else {
        // Known to the node but unconfirmed.
        r.state = BtcTxState::InMempool;
        r.confirmations = 0;
    }
    return r;
}

BtcHeightResult BitcoindRpcBackend::GetBlockHeight() {
    BtcHeightResult r;
    if (!IsConfigured()) { r.error = "BTC backend not configured"; return r; }
    std::string resp = Rpc("getblockcount", "[]");
    if (resp.empty()) { r.error = "bitcoind RPC transport failure"; return r; }
    std::string emsg;
    if (json_rpc_error(resp, emsg)) { r.error = emsg; return r; }
    int64_t h = -1;
    if (!json_get_int(resp, "result", h) || h < 0) {
        r.error = "unexpected getblockcount response";
        return r;
    }
    r.ok = true;
    r.height = h;
    return r;
}

BtcFeeResult BitcoindRpcBackend::EstimateFeeRate(int confirm_target_blocks) {
    BtcFeeResult r;
    if (!IsConfigured()) { r.error = "BTC backend not configured"; return r; }
    if (confirm_target_blocks < 1) confirm_target_blocks = 6;
    std::string resp = Rpc("estimatesmartfee", "[" + std::to_string(confirm_target_blocks) + "]");
    if (resp.empty()) { r.error = "bitcoind RPC transport failure"; return r; }
    std::string emsg;
    if (json_rpc_error(resp, emsg)) { r.error = emsg; return r; }
    // result.feerate is BTC/kvB. Convert to sat/vByte = feerate*1e8/1000.
    int64_t sats_per_kvb = 0;
    if (json_get_btc_sats(resp, "feerate", 0, sats_per_kvb) && sats_per_kvb > 0) {
        int64_t sat_vb = sats_per_kvb / 1000;
        if (sat_vb < 1) sat_vb = 1;   // never below the relay floor
        r.ok = true;
        r.sat_per_vbyte = sat_vb;
        return r;
    }
    // estimatesmartfee could not produce an estimate — fail closed (caller
    // must supply an explicit fee rather than guess).
    r.error = "fee estimate unavailable";
    return r;
}

BtcListUnspentResult BitcoindRpcBackend::ListUnspent(int min_confirmations,
                                                     const std::string& address) {
    BtcListUnspentResult r;
    if (!IsConfigured()) { r.error = "BTC backend not configured"; return r; }
    if (min_confirmations < 0) min_confirmations = 0;
    std::string params = "[" + std::to_string(min_confirmations) + ",9999999";
    if (!address.empty()) params += ",[\"" + address + "\"]";
    params += "]";
    std::string resp = Rpc("listunspent", params);
    if (resp.empty()) { r.error = "bitcoind RPC transport failure"; return r; }
    std::string emsg;
    if (json_rpc_error(resp, emsg)) { r.error = emsg; return r; }

    // Walk the result array, one "txid" anchor per UTXO object.
    std::string region = json_result_region(resp);
    size_t pos = 0;
    while (true) {
        auto tp = region.find("\"txid\"", pos);
        if (tp == std::string::npos) break;
        BtcUtxo u;
        std::string sub = region.substr(tp);
        std::string txid;
        if (json_get_string(sub, "txid", txid)) u.txid = txid;
        int64_t vout = 0;
        if (json_get_int(sub, "vout", vout)) u.vout = (uint32_t)vout;
        int64_t sats = 0;
        if (json_get_btc_sats(region, "amount", tp, sats)) u.amount_sats = sats;
        std::string spk;
        if (json_get_string(sub, "scriptPubKey", spk)) u.script_pubkey_hex = spk;
        int64_t conf = 0;
        if (json_get_int(sub, "confirmations", conf)) u.confirmations = conf;
        if (!u.txid.empty() && u.amount_sats > 0) r.utxos.push_back(u);
        pos = tp + 6;
    }
    r.ok = true;
    return r;
}

// ===========================================================================
// Factories
// ===========================================================================

std::unique_ptr<BitcoinBackend> MakeBitcoinBackend(const BitcoinRpcConfig& cfg,
                                                   BtcHttpTransport transport) {
    if (!cfg.runtime_enabled) {
        return std::unique_ptr<BitcoinBackend>(
            new NullBitcoinBackend("BTC atomic swap disabled (SOST_BTC_ATOMIC_SWAP_ENABLED != 1)"));
    }
    if (!cfg.HasCredentials()) {
        return std::unique_ptr<BitcoinBackend>(
            new NullBitcoinBackend("BTC backend enabled but BTC_RPC_* incomplete"));
    }
    return std::unique_ptr<BitcoinBackend>(new BitcoindRpcBackend(cfg, std::move(transport)));
}

std::unique_ptr<BitcoinBackend> MakeBitcoinBackendFromEnv() {
    return MakeBitcoinBackend(BitcoinRpcConfig::FromEnv());
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
