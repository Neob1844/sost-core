// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// tx_send.cpp — CLI tool to send SOST transactions
// Usage: ./tx_send --from ADDR --to ADDR --amount AMOUNT --wallet WALLET.json
//        --rpc HOST:PORT --rpc-user USER --rpc-pass PASS

#include "sost/types.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include "sost/address.h"
#include "sost/serialize.h"

#include <fstream>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <unistd.h>

using namespace sost;

// ============================================================================
// Helpers
// ============================================================================

static std::string to_hex_str(const uint8_t* data, size_t len) {
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        char buf[3];
        snprintf(buf, sizeof(buf), "%02x", data[i]);
        out += buf;
    }
    return out;
}

static bool hex_to_bytes(const std::string& hex, std::vector<uint8_t>& out) {
    if (hex.size() % 2 != 0) return false;
    out.resize(hex.size() / 2);
    for (size_t i = 0; i < out.size(); ++i) {
        unsigned int byte;
        if (sscanf(hex.c_str() + i * 2, "%02x", &byte) != 1) return false;
        out[i] = (uint8_t)byte;
    }
    return true;
}

// Simple JSON string extraction
static std::string jstr(const std::string& json, const std::string& key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return "";
    pos = json.find("\"", pos + key.size() + 2);
    if (pos == std::string::npos) return "";
    auto end = json.find("\"", pos + 1);
    if (end == std::string::npos) return "";
    return json.substr(pos + 1, end - pos - 1);
}

static int64_t jint(const std::string& json, const std::string& key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return 0;
    pos = json.find(":", pos);
    if (pos == std::string::npos) return 0;
    return atoll(json.c_str() + pos + 1);
}

// ============================================================================
// RPC client
// ============================================================================

static std::string g_rpc_url;
static std::string g_rpc_user;
static std::string g_rpc_pass;

static std::string base64_encode(const std::string& in) {
    static const char* chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val = 0, valb = -6;
    for (uint8_t c : in) {
        val = (val << 8) + c;
        valb += 8;
        while (valb >= 0) {
            out.push_back(chars[(val >> valb) & 0x3F]);
            valb -= 6;
        }
    }
    if (valb > -6) out.push_back(chars[((val << 8) >> (valb + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

static std::string rpc_call(const std::string& method, const std::string& params = "[]") {
    // Parse host:port
    auto colon = g_rpc_url.rfind(':');
    std::string host = g_rpc_url.substr(0, colon);
    int port = atoi(g_rpc_url.substr(colon + 1).c_str());

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";

    struct hostent* he = gethostbyname(host.c_str());
    if (!he) { close(fd); return ""; }

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    memcpy(&addr.sin_addr, he->h_addr_list[0], he->h_length);

    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) { close(fd); return ""; }

    std::string body = "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"" + method + "\",\"params\":" + params + "}";
    std::string auth = base64_encode(g_rpc_user + ":" + g_rpc_pass);
    std::string req = "POST / HTTP/1.1\r\nHost: " + host + "\r\n"
                      "Authorization: Basic " + auth + "\r\n"
                      "Content-Type: application/json\r\n"
                      "Content-Length: " + std::to_string(body.size()) + "\r\n"
                      "Connection: close\r\n\r\n" + body;

    write(fd, req.c_str(), req.size());

    std::string response;
    char buf[4096];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf))) > 0) response.append(buf, n);
    close(fd);

    auto hdr_end = response.find("\r\n\r\n");
    if (hdr_end != std::string::npos) response = response.substr(hdr_end + 4);
    return response;
}

// ============================================================================
// Wallet loader
// ============================================================================

struct WalletKey {
    PrivKey privkey;
    PubKey pubkey;
    PubKeyHash pkh;
    std::string address;
};

static bool load_wallet(const std::string& path, std::vector<WalletKey>& keys) {
    std::ifstream f(path);
    if (!f) return false;
    std::string json((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());

    // Parse keys array - simple extraction of hex private keys
    size_t pos = 0;
    while (true) {
        pos = json.find("\"privkey\"", pos);
        if (pos == std::string::npos) break;
        pos = json.find("\"", pos + 9);
        if (pos == std::string::npos) break;
        auto end = json.find("\"", pos + 1);
        if (end == std::string::npos) break;
        std::string hex = json.substr(pos + 1, end - pos - 1);
        pos = end + 1;

        if (hex.size() != 64) continue;

        WalletKey wk{};
        std::vector<uint8_t> raw;
        if (!hex_to_bytes(hex, raw) || raw.size() != 32) continue;
        memcpy(wk.privkey.data(), raw.data(), 32);

        std::string derr;
        if (!DerivePublicKey(wk.privkey, wk.pubkey, &derr)) continue;
        wk.pkh = ComputePubKeyHash(wk.pubkey);
        wk.address = "sost1" + to_hex_str(wk.pkh.data(), 20);
        keys.push_back(wk);
    }
    return !keys.empty();
}

// ============================================================================
// UTXO fetching
// ============================================================================

struct UTXO {
    Hash256 txid;
    uint32_t vout;
    int64_t amount; // stocks
    std::string txid_hex;
};

static bool fetch_utxos(const std::string& address, std::vector<UTXO>& utxos) {
    std::string resp = rpc_call("getaddressutxos", "[\"" + address + "\"]");
    if (resp.empty()) return false;

    // Parse result array of UTXOs
    auto rp = resp.find("\"result\":");
    if (rp == std::string::npos) return false;

    // Simple parser: find each utxo object
    size_t pos = rp;
    while (true) {
        pos = resp.find("\"txid\"", pos);
        if (pos == std::string::npos) break;

        UTXO u{};
        // Extract txid
        auto tstart = resp.find("\"", pos + 6);
        auto tend = resp.find("\"", tstart + 1);
        if (tstart == std::string::npos || tend == std::string::npos) break;
        u.txid_hex = resp.substr(tstart + 1, tend - tstart - 1);

        std::vector<uint8_t> txid_raw;
        if (u.txid_hex.size() == 64 && hex_to_bytes(u.txid_hex, txid_raw)) {
            memcpy(u.txid.data(), txid_raw.data(), 32);
        }

        // Extract vout
        auto vp = resp.find("\"vout\"", tend);
        if (vp != std::string::npos && vp < tend + 200) {
            auto cp = resp.find(":", vp);
            if (cp != std::string::npos) u.vout = (uint32_t)atoi(resp.c_str() + cp + 1);
        }

        // Extract amount
        auto ap = resp.find("\"amount\"", tend);
        if (ap != std::string::npos && ap < tend + 300) {
            auto cp = resp.find(":", ap);
            if (cp != std::string::npos) u.amount = atoll(resp.c_str() + cp + 1);
        }

        if (u.amount > 0) utxos.push_back(u);
        pos = tend + 1;
    }
    return true;
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char** argv) {
    std::string from_addr, to_addr, wallet_path;
    double amount = 0;
    int64_t fee_rate = 1; // stocks per byte

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--from") && i + 1 < argc) from_addr = argv[++i];
        else if (!strcmp(argv[i], "--to") && i + 1 < argc) to_addr = argv[++i];
        else if (!strcmp(argv[i], "--amount") && i + 1 < argc) amount = atof(argv[++i]);
        else if (!strcmp(argv[i], "--wallet") && i + 1 < argc) wallet_path = argv[++i];
        else if (!strcmp(argv[i], "--rpc") && i + 1 < argc) g_rpc_url = argv[++i];
        else if (!strcmp(argv[i], "--rpc-user") && i + 1 < argc) g_rpc_user = argv[++i];
        else if (!strcmp(argv[i], "--rpc-pass") && i + 1 < argc) g_rpc_pass = argv[++i];
        else if (!strcmp(argv[i], "--fee-rate") && i + 1 < argc) fee_rate = atoll(argv[++i]);
        else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
            printf("=== SOST Transaction Sender ===\n\n");
            printf("Usage:\n");
            printf("  ./tx_send --from ADDRESS --to ADDRESS --amount SOST\n");
            printf("            --wallet WALLET.json\n");
            printf("            --rpc HOST:PORT --rpc-user USER --rpc-pass PASS\n\n");
            printf("Options:\n");
            printf("  --from        Sender sost1... address\n");
            printf("  --to          Recipient sost1... address\n");
            printf("  --amount      Amount in SOST (e.g. 50 or 0.5)\n");
            printf("  --wallet      Path to wallet JSON with private keys\n");
            printf("  --rpc         Node RPC endpoint (e.g. 127.0.0.1:18232)\n");
            printf("  --rpc-user    RPC username\n");
            printf("  --rpc-pass    RPC password\n");
            printf("  --fee-rate    Fee rate in stocks/byte (default: 1)\n");
            printf("  --help        Show this help\n\n");
            printf("Example:\n");
            printf("  ./tx_send --from sost1abc... --to sost1def... --amount 50 \\\n");
            printf("    --wallet wallet.json --rpc 127.0.0.1:18232 \\\n");
            printf("    --rpc-user myuser --rpc-pass mypass\n");
            return 0;
        }
    }

    // Validate inputs
    if (from_addr.empty() || to_addr.empty() || amount <= 0 || wallet_path.empty() || g_rpc_url.empty()) {
        fprintf(stderr, "Error: missing required arguments. Use --help for usage.\n");
        return 1;
    }

    int64_t send_amount = (int64_t)(amount * 1e8 + 0.5); // SOST to stocks
    printf("=== SOST Transaction ===\n");
    printf("From:   %s\n", from_addr.c_str());
    printf("To:     %s\n", to_addr.c_str());
    printf("Amount: %.8f SOST (%lld stocks)\n", amount, (long long)send_amount);
    printf("Fee:    %lld stocks/byte\n\n", (long long)fee_rate);

    // Load wallet
    std::vector<WalletKey> keys;
    if (!load_wallet(wallet_path, keys)) {
        fprintf(stderr, "Error: cannot load wallet from %s\n", wallet_path.c_str());
        return 1;
    }
    printf("Wallet: %zu keys loaded\n", keys.size());

    // Find key for from_addr
    WalletKey* sender = nullptr;
    for (auto& k : keys) {
        if (k.address == from_addr) { sender = &k; break; }
    }
    if (!sender) {
        fprintf(stderr, "Error: sender address %s not found in wallet\n", from_addr.c_str());
        return 1;
    }
    printf("Sender key found: %s\n\n", from_addr.c_str());

    // Fetch UTXOs
    std::vector<UTXO> utxos;
    if (!fetch_utxos(from_addr, utxos) || utxos.empty()) {
        fprintf(stderr, "Error: no UTXOs found for %s (or RPC failed)\n", from_addr.c_str());
        return 1;
    }
    printf("UTXOs: %zu available\n", utxos.size());

    // Sort by amount descending for efficient selection
    std::sort(utxos.begin(), utxos.end(), [](const UTXO& a, const UTXO& b) { return a.amount > b.amount; });

    // Estimate fee (rough: 250 bytes per input + 100 base)
    int64_t est_fee = fee_rate * (100 + 250); // 1 input estimate
    int64_t needed = send_amount + est_fee;

    // Select UTXOs
    std::vector<UTXO> selected;
    int64_t total_in = 0;
    for (const auto& u : utxos) {
        selected.push_back(u);
        total_in += u.amount;
        // Update fee estimate with more inputs
        est_fee = fee_rate * (100 + 250 * (int64_t)selected.size());
        needed = send_amount + est_fee;
        if (total_in >= needed) break;
    }

    if (total_in < needed) {
        fprintf(stderr, "Error: insufficient funds. Have %lld stocks, need %lld\n",
                (long long)total_in, (long long)needed);
        return 1;
    }

    int64_t change = total_in - send_amount - est_fee;
    printf("Selected: %zu UTXOs, total=%lld stocks\n", selected.size(), (long long)total_in);
    printf("Send: %lld, Fee: %lld, Change: %lld\n\n", (long long)send_amount, (long long)est_fee, (long long)change);

    // Build transaction
    Transaction tx{};
    tx.version = 1;

    // Inputs
    for (const auto& u : selected) {
        TxInput inp{};
        inp.prev_txid = u.txid;
        inp.prev_index = u.vout;
        // signature and pubkey set during signing
        tx.inputs.push_back(inp);
    }

    // Parse recipient PKH from address
    PubKeyHash to_pkh{};
    if (to_addr.size() >= 45 && to_addr.substr(0, 5) == "sost1") {
        std::vector<uint8_t> pkh_raw;
        if (hex_to_bytes(to_addr.substr(5), pkh_raw) && pkh_raw.size() == 20) {
            memcpy(to_pkh.data(), pkh_raw.data(), 20);
        }
    }

    // Output: send amount
    TxOutput out_send{};
    out_send.amount = send_amount;
    out_send.type = OUT_TRANSFER;
    out_send.pubkey_hash = to_pkh;
    tx.outputs.push_back(out_send);

    // Output: change (if any)
    if (change > 0) {
        TxOutput out_change{};
        out_change.amount = change;
        out_change.type = OUT_TRANSFER;
        out_change.pubkey_hash = sender->pkh;
        tx.outputs.push_back(out_change);
    }

    // SOST transactions have no locktime field

    // Get genesis hash for sighash computation
    Hash256 genesis_hash{};
    {
        std::string resp = rpc_call("getblockhash", "[0]");
        auto rp = resp.find("\"result\":\"");
        if (rp != std::string::npos) {
            std::string gh = resp.substr(rp + 10, 64);
            std::vector<uint8_t> gh_raw;
            if (gh.size() == 64 && hex_to_bytes(gh, gh_raw))
                memcpy(genesis_hash.data(), gh_raw.data(), 32);
        }
    }

    // Sign each input
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        SpentOutput spent{};
        spent.amount = selected[i].amount;
        spent.type = OUT_TRANSFER;

        std::string serr;
        if (!SignTransactionInput(tx, i, spent, genesis_hash, sender->privkey, &serr)) {
            fprintf(stderr, "Error signing input %zu: %s\n", i, serr.c_str());
            return 1;
        }
    }

    printf("Transaction signed (%zu inputs, %zu outputs)\n", tx.inputs.size(), tx.outputs.size());

    // Serialize
    std::vector<Byte> raw;
    std::string ser_err;
    if (!tx.Serialize(raw, &ser_err)) {
        fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
        return 1;
    }

    std::string tx_hex = to_hex_str(raw.data(), raw.size());
    printf("TX hex: %s\n", tx_hex.substr(0, 64).c_str());
    printf("TX size: %zu bytes\n\n", raw.size());

    // Compute txid
    Hash256 txid{};
    tx.ComputeTxId(txid, nullptr);
    printf("TXID: %s\n\n", to_hex_str(txid.data(), 32).c_str());

    // Send via RPC
    printf("Sending to node...\n");
    std::string resp = rpc_call("sendrawtransaction", "[\"" + tx_hex + "\"]");
    if (resp.find("\"result\"") != std::string::npos && resp.find("\"error\":null") != std::string::npos) {
        printf("SUCCESS! Transaction broadcast.\n");
        printf("TXID: %s\n", to_hex_str(txid.data(), 32).c_str());
    } else {
        fprintf(stderr, "Node response: %s\n", resp.c_str());
    }

    return 0;
}
