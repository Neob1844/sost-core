// sost-rpc.cpp — SOST JSON-RPC Daemon (Bitcoin-compatible)
//
// Provides Bitcoin-style JSON-RPC for exchange integration (TradeOgre, etc.)
//
// Supported methods:
//   getblockcount             → chain height
//   getblockhash <height>     → block hash at height
//   getblock <hash> [verbose] → block info
//   getbalance                → wallet balance
//   getnewaddress [label]     → generate new address
//   listunspent [minconf]     → list unspent outputs
//   validateaddress <addr>    → check address validity
//   sendrawtransaction <hex>  → broadcast raw tx (stub, needs P2P)
//   gettxout <txid> <vout>    → get UTXO info
//   getinfo                   → node/wallet summary
//
// Usage:
//   sost-rpc --wallet wallet.json --port 18232 --genesis genesis_block.json

#include "sost/wallet.h"
#include "sost/address.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/types.h"

#include <fstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <map>
#include <functional>

using namespace sost;

// =============================================================================
// Globals
// =============================================================================

static Wallet g_wallet;
static std::string g_wallet_path = "wallet.json";
static Hash256 g_genesis_hash{};
static int64_t g_chain_height = 0;

// Stored blocks (minimal: just genesis for now)
struct StoredBlock {
    Hash256 block_id;
    Hash256 prev_hash;
    Hash256 merkle_root;
    int64_t timestamp;
    uint32_t bits_q;
    uint64_t nonce;
    int64_t height;
    int64_t subsidy;
};
static std::vector<StoredBlock> g_blocks;

// Using sost::STOCKS_PER_SOST from consensus_constants.h

// =============================================================================
// Helpers
// =============================================================================

static std::string to_hex(const uint8_t* data, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s;
    s.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        s += hx[data[i] >> 4];
        s += hx[data[i] & 0xF];
    }
    return s;
}

static std::string format_sost(int64_t stocks) {
    char buf[64];
    bool neg = stocks < 0;
    int64_t abs_val = neg ? -stocks : stocks;
    int64_t whole = abs_val / STOCKS_PER_SOST;
    int64_t frac = abs_val % STOCKS_PER_SOST;
    snprintf(buf, sizeof(buf), "%s%lld.%08lld",
             neg ? "-" : "", (long long)whole, (long long)frac);
    return std::string(buf);
}

// Escape a string for JSON output
static std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else out += c;
    }
    return out;
}

// =============================================================================
// Minimal JSON parser (enough for JSON-RPC requests)
// =============================================================================

static std::string json_get_string(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return "";
    // Skip whitespace
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (pos >= json.size()) return "";

    if (json[pos] == '"') {
        auto end = json.find('"', pos + 1);
        if (end == std::string::npos) return "";
        return json.substr(pos + 1, end - pos - 1);
    }
    // Number or other non-string
    auto end = json.find_first_of(",}] \t\n\r", pos);
    if (end == std::string::npos) end = json.size();
    return json.substr(pos, end - pos);
}

// Extract params array as raw strings
static std::vector<std::string> json_get_params(const std::string& json) {
    std::vector<std::string> result;
    auto pos = json.find("\"params\"");
    if (pos == std::string::npos) return result;
    pos = json.find('[', pos);
    if (pos == std::string::npos) return result;
    auto end = json.find(']', pos);
    if (end == std::string::npos) return result;

    std::string inner = json.substr(pos + 1, end - pos - 1);

    // Simple parameter extraction
    size_t i = 0;
    while (i < inner.size()) {
        // Skip whitespace and commas
        while (i < inner.size() && (inner[i] == ' ' || inner[i] == ',' || inner[i] == '\t' || inner[i] == '\n')) i++;
        if (i >= inner.size()) break;

        if (inner[i] == '"') {
            // String parameter
            auto qend = inner.find('"', i + 1);
            if (qend == std::string::npos) break;
            result.push_back(inner.substr(i + 1, qend - i - 1));
            i = qend + 1;
        } else {
            // Number/bool parameter
            auto pend = inner.find_first_of(",] \t\n\r", i);
            if (pend == std::string::npos) pend = inner.size();
            result.push_back(inner.substr(i, pend - i));
            i = pend;
        }
    }
    return result;
}

// =============================================================================
// JSON-RPC response builders
// =============================================================================

static std::string rpc_result(const std::string& id, const std::string& result_json) {
    return "{\"jsonrpc\":\"2.0\",\"id\":" + id + ",\"result\":" + result_json + "}";
}

static std::string rpc_error(const std::string& id, int code, const std::string& msg) {
    return "{\"jsonrpc\":\"2.0\",\"id\":" + id +
           ",\"error\":{\"code\":" + std::to_string(code) +
           ",\"message\":\"" + json_escape(msg) + "\"}}";
}

// =============================================================================
// RPC method handlers
// =============================================================================

static std::string handle_getblockcount(const std::string& id, const std::vector<std::string>&) {
    return rpc_result(id, std::to_string(g_chain_height));
}

static std::string handle_getblockhash(const std::string& id, const std::vector<std::string>& params) {
    if (params.empty()) return rpc_error(id, -1, "missing height parameter");
    int64_t h = std::stoll(params[0]);
    if (h < 0 || h >= (int64_t)g_blocks.size()) {
        return rpc_error(id, -8, "Block height out of range");
    }
    return rpc_result(id, "\"" + to_hex(g_blocks[h].block_id.data(), 32) + "\"");
}

static std::string handle_getblock(const std::string& id, const std::vector<std::string>& params) {
    if (params.empty()) return rpc_error(id, -1, "missing blockhash parameter");

    std::string hash_hex = params[0];
    // Find block by hash
    for (const auto& b : g_blocks) {
        if (to_hex(b.block_id.data(), 32) == hash_hex) {
            std::ostringstream s;
            s << "{";
            s << "\"hash\":\"" << to_hex(b.block_id.data(), 32) << "\",";
            s << "\"height\":" << b.height << ",";
            s << "\"previousblockhash\":\"" << to_hex(b.prev_hash.data(), 32) << "\",";
            s << "\"merkleroot\":\"" << to_hex(b.merkle_root.data(), 32) << "\",";
            s << "\"time\":" << b.timestamp << ",";
            s << "\"bits_q\":" << b.bits_q << ",";
            s << "\"nonce\":" << b.nonce << ",";
            s << "\"subsidy\":" << b.subsidy;
            s << "}";
            return rpc_result(id, s.str());
        }
    }
    return rpc_error(id, -5, "Block not found");
}

static std::string handle_getinfo(const std::string& id, const std::vector<std::string>&) {
    std::ostringstream s;
    s << "{";
    s << "\"version\":\"0.2.0\",";
    s << "\"protocolversion\":1,";
    s << "\"blocks\":" << g_chain_height << ",";
    s << "\"connections\":0,";
    s << "\"difficulty\":" << (g_blocks.empty() ? 0 : g_blocks.back().bits_q) << ",";
    s << "\"testnet\":false,";
    s << "\"balance\":\"" << format_sost(g_wallet.balance()) << "\",";
    s << "\"keypoolsize\":" << g_wallet.num_keys();
    s << "}";
    return rpc_result(id, s.str());
}

static std::string handle_getbalance(const std::string& id, const std::vector<std::string>&) {
    // Return balance as decimal SOST string (Bitcoin convention)
    double bal = (double)g_wallet.balance() / (double)sost::STOCKS_PER_SOST;
    char buf[64];
    snprintf(buf, sizeof(buf), "%.8f", bal);
    return rpc_result(id, std::string(buf));
}

static std::string handle_getnewaddress(const std::string& id, const std::vector<std::string>& params) {
    std::string label;
    if (!params.empty()) label = params[0];
    auto key = g_wallet.generate_key(label);

    std::string err;
    g_wallet.save(g_wallet_path, &err);

    return rpc_result(id, "\"" + key.address + "\"");
}

static std::string handle_validateaddress(const std::string& id, const std::vector<std::string>& params) {
    if (params.empty()) return rpc_error(id, -1, "missing address");

    std::string addr = params[0];
    bool valid = address_valid(addr);
    bool is_mine = g_wallet.has_address(addr);

    std::ostringstream s;
    s << "{";
    s << "\"isvalid\":" << (valid ? "true" : "false") << ",";
    s << "\"address\":\"" << json_escape(addr) << "\",";
    s << "\"ismine\":" << (is_mine ? "true" : "false");
    if (is_mine) {
        const WalletKey* key = g_wallet.find_key(addr);
        if (key) {
            s << ",\"pubkey\":\"" << to_hex(key->pubkey.data(), 33) << "\"";
            if (!key->label.empty()) {
                s << ",\"label\":\"" << json_escape(key->label) << "\"";
            }
        }
    }
    s << "}";
    return rpc_result(id, s.str());
}

static std::string handle_listunspent(const std::string& id, const std::vector<std::string>&) {
    auto utxos = g_wallet.list_unspent();
    std::ostringstream s;
    s << "[";
    for (size_t i = 0; i < utxos.size(); ++i) {
        if (i > 0) s << ",";
        const auto& u = utxos[i];
        std::string addr = address_encode(u.pkh);
        s << "{";
        s << "\"txid\":\"" << to_hex(u.txid.data(), 32) << "\",";
        s << "\"vout\":" << u.vout << ",";
        s << "\"address\":\"" << addr << "\",";
        s << "\"amount\":" << format_sost(u.amount) << ",";
        s << "\"confirmations\":" << (g_chain_height - u.height + 1) << ",";
        s << "\"spendable\":true";
        s << "}";
    }
    s << "]";
    return rpc_result(id, s.str());
}

static std::string handle_gettxout(const std::string& id, const std::vector<std::string>& params) {
    if (params.size() < 2) return rpc_error(id, -1, "missing txid and vout");

    std::string txid_hex = params[0];
    uint32_t vout = (uint32_t)std::stoul(params[1]);

    // Search wallet UTXOs
    auto utxos = g_wallet.list_unspent();
    for (const auto& u : utxos) {
        if (to_hex(u.txid.data(), 32) == txid_hex && u.vout == vout) {
            std::ostringstream s;
            s << "{";
            s << "\"bestblock\":\"" << to_hex(g_genesis_hash.data(), 32) << "\",";
            s << "\"confirmations\":" << (g_chain_height - u.height + 1) << ",";
            s << "\"value\":" << format_sost(u.amount) << ",";
            s << "\"address\":\"" << address_encode(u.pkh) << "\",";
            s << "\"coinbase\":true";
            s << "}";
            return rpc_result(id, s.str());
        }
    }
    return rpc_result(id, "null");
}

static std::string handle_sendrawtransaction(const std::string& id, const std::vector<std::string>& params) {
    if (params.empty()) return rpc_error(id, -1, "missing hex transaction");

    // Parse hex → bytes → Transaction
    std::string hex_str = params[0];
    if (hex_str.size() % 2 != 0) return rpc_error(id, -22, "TX decode failed: odd hex length");

    std::vector<Byte> raw;
    raw.reserve(hex_str.size() / 2);
    for (size_t i = 0; i < hex_str.size(); i += 2) {
        auto hv = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return 10 + c - 'a';
            if (c >= 'A' && c <= 'F') return 10 + c - 'A';
            return -1;
        };
        int hi = hv(hex_str[i]);
        int lo = hv(hex_str[i + 1]);
        if (hi < 0 || lo < 0) return rpc_error(id, -22, "TX decode failed: invalid hex");
        raw.push_back((Byte)((hi << 4) | lo));
    }

    Transaction tx;
    std::string err;
    if (!Transaction::Deserialize(raw, tx, &err)) {
        return rpc_error(id, -22, "TX decode failed: " + err);
    }

    Hash256 txid;
    if (!tx.ComputeTxId(txid, &err)) {
        return rpc_error(id, -25, "TX rejected: " + err);
    }

    // TODO: validate transaction against UTXO set
    // TODO: add to mempool
    // TODO: broadcast to peers via P2P

    printf("[RPC] sendrawtransaction: %s (queued, P2P not yet active)\n",
           to_hex(txid.data(), 32).c_str());

    return rpc_result(id, "\"" + to_hex(txid.data(), 32) + "\"");
}

// =============================================================================
// RPC dispatch
// =============================================================================

using RpcHandler = std::function<std::string(const std::string& id, const std::vector<std::string>& params)>;

static std::map<std::string, RpcHandler> g_handlers = {
    {"getblockcount",       handle_getblockcount},
    {"getblockhash",        handle_getblockhash},
    {"getblock",            handle_getblock},
    {"getinfo",             handle_getinfo},
    {"getbalance",          handle_getbalance},
    {"getnewaddress",       handle_getnewaddress},
    {"validateaddress",     handle_validateaddress},
    {"listunspent",         handle_listunspent},
    {"gettxout",            handle_gettxout},
    {"sendrawtransaction",  handle_sendrawtransaction},
};

static std::string dispatch_rpc(const std::string& request) {
    std::string method = json_get_string(request, "method");
    std::string id_raw = json_get_string(request, "id");
    std::string id = id_raw.empty() ? "null" : id_raw;

    // Wrap numeric IDs, quote string IDs
    if (!id_raw.empty() && (id_raw[0] >= '0' && id_raw[0] <= '9')) {
        id = id_raw;  // numeric, keep as-is
    } else if (id_raw != "null" && !id_raw.empty()) {
        id = "\"" + id_raw + "\"";
    }

    if (method.empty()) {
        return rpc_error(id, -32600, "Invalid request: missing method");
    }

    auto it = g_handlers.find(method);
    if (it == g_handlers.end()) {
        return rpc_error(id, -32601, "Method not found: " + method);
    }

    auto params = json_get_params(request);
    return it->second(id, params);
}

// =============================================================================
// HTTP server
// =============================================================================

static void handle_connection(int client_fd) {
    char buf[65536]{};
    ssize_t n = read(client_fd, buf, sizeof(buf) - 1);
    if (n <= 0) { close(client_fd); return; }

    std::string request(buf, n);

    // Extract body from HTTP POST
    std::string body;
    auto body_pos = request.find("\r\n\r\n");
    if (body_pos != std::string::npos) {
        body = request.substr(body_pos + 4);
    } else {
        body = request;
    }

    // Handle GET requests (simple info)
    if (request.substr(0, 3) == "GET") {
        std::string path = "/";
        auto sp = request.find(' ');
        if (sp != std::string::npos) {
            auto sp2 = request.find(' ', sp + 1);
            if (sp2 != std::string::npos) path = request.substr(sp + 1, sp2 - sp - 1);
        }

        std::string result;
        if (path == "/" || path == "/info") {
            result = dispatch_rpc("{\"method\":\"getinfo\",\"id\":1}");
        } else {
            result = "{\"error\":\"Use POST with JSON-RPC\"}";
        }

        std::string resp = "HTTP/1.1 200 OK\r\n"
                           "Content-Type: application/json\r\n"
                           "Access-Control-Allow-Origin: *\r\n"
                           "Content-Length: " + std::to_string(result.size()) + "\r\n"
                           "\r\n" + result;
        write(client_fd, resp.c_str(), resp.size());
        close(client_fd);
        return;
    }

    // Handle CORS preflight
    if (request.substr(0, 7) == "OPTIONS") {
        std::string resp = "HTTP/1.1 200 OK\r\n"
                           "Access-Control-Allow-Origin: *\r\n"
                           "Access-Control-Allow-Methods: POST, GET, OPTIONS\r\n"
                           "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
                           "Content-Length: 0\r\n\r\n";
        write(client_fd, resp.c_str(), resp.size());
        close(client_fd);
        return;
    }

    // Process JSON-RPC
    std::string result = dispatch_rpc(body);

    std::string resp = "HTTP/1.1 200 OK\r\n"
                       "Content-Type: application/json\r\n"
                       "Access-Control-Allow-Origin: *\r\n"
                       "Content-Length: " + std::to_string(result.size()) + "\r\n"
                       "\r\n" + result;
    write(client_fd, resp.c_str(), resp.size());
    close(client_fd);
}

// =============================================================================
// Genesis loader
// =============================================================================

static bool load_genesis(const std::string& path) {
    std::ifstream f(path);
    if (!f) return false;

    std::string json((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());

    // Extract block_id
    auto extract = [&](const std::string& key) -> std::string {
        std::string needle = "\"" + key + "\"";
        auto pos = json.find(needle);
        if (pos == std::string::npos) return "";
        pos = json.find('"', pos + needle.size() + 1);
        if (pos == std::string::npos) return "";
        auto end = json.find('"', pos + 1);
        if (end == std::string::npos) return "";
        return json.substr(pos + 1, end - pos - 1);
    };

    auto extract_int = [&](const std::string& key) -> int64_t {
        std::string needle = "\"" + key + "\"";
        auto pos = json.find(needle);
        if (pos == std::string::npos) return -1;
        pos = json.find(':', pos + needle.size());
        if (pos == std::string::npos) return -1;
        pos++;
        while (pos < json.size() && json[pos] == ' ') pos++;
        return std::stoll(json.substr(pos));
    };

    StoredBlock genesis;
    std::string bid = extract("block_id");
    if (bid.size() != 64) return false;

    genesis.block_id = from_hex(bid);
    genesis.prev_hash = from_hex(extract("prev_hash"));
    genesis.merkle_root = from_hex(extract("merkle_root"));
    genesis.timestamp = extract_int("timestamp");
    genesis.bits_q = (uint32_t)extract_int("bits_q");
    genesis.nonce = (uint64_t)extract_int("nonce");
    genesis.height = 0;
    genesis.subsidy = extract_int("subsidy_stocks");

    g_genesis_hash = genesis.block_id;
    g_blocks.push_back(genesis);
    g_chain_height = 0;

    return true;
}

// =============================================================================
// main
// =============================================================================

int main(int argc, char** argv) {
    int port = 18232;
    std::string genesis_path = "genesis_block.json";

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--wallet") && i + 1 < argc)  g_wallet_path = argv[++i];
        else if (!strcmp(argv[i], "--port") && i + 1 < argc) port = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--genesis") && i + 1 < argc) genesis_path = argv[++i];
        else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
            printf("SOST RPC Daemon v0.2\n\n");
            printf("Usage: sost-rpc [options]\n");
            printf("  --wallet <path>     Wallet file (default: wallet.json)\n");
            printf("  --port <port>       RPC port (default: 18232)\n");
            printf("  --genesis <path>    Genesis block JSON (default: genesis_block.json)\n");
            return 0;
        }
    }

    printf("=== SOST RPC Daemon v0.2 ===\n");

    // Load genesis
    if (!load_genesis(genesis_path)) {
        fprintf(stderr, "Error: cannot load genesis from '%s'\n", genesis_path.c_str());
        return 1;
    }
    printf("Genesis loaded: %s\n", to_hex(g_genesis_hash.data(), 32).c_str());

    // Load wallet
    std::string err;
    if (!g_wallet.load(g_wallet_path, &err)) {
        fprintf(stderr, "Error loading wallet '%s': %s\n", g_wallet_path.c_str(), err.c_str());
        fprintf(stderr, "Use 'sost-cli newwallet' first.\n");
        return 1;
    }
    printf("Wallet loaded: %zu keys, %s SOST\n",
           g_wallet.num_keys(), format_sost(g_wallet.balance()).c_str());

    // Start server
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    if (srv < 0) { perror("socket"); return 1; }

    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);

    if (bind(srv, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }

    listen(srv, 10);
    printf("\nRPC listening on port %d\n", port);
    printf("Test: curl -s http://localhost:%d/\n", port);
    printf("JSON-RPC: curl -s -X POST -d '{\"method\":\"getinfo\",\"id\":1}' http://localhost:%d/\n\n", port);

    while (true) {
        int client = accept(srv, nullptr, nullptr);
        if (client < 0) continue;
        handle_connection(client);
    }

    close(srv);
    return 0;
}
