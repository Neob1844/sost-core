// SOST Protocol — Copyright (c) 2026 SOST Foundation
// Licensed under the Business Source License 1.1. See LICENSE file.
//
// sost-cli.cpp — SOST Wallet CLI v1.3
//
// CHANGES v1.3:
// - FIX: query node for chain height via getinfo RPC before building tx
// - FIX: pass real height to create_transaction (was -1, now actual)
//        This enables coinbase maturity filtering inside wallet
// - ADD: dynamic fee calculation: build tx → measure size → fee = size × rate
//        Consensus rule S8 requires fee >= tx_size_bytes × 1 stock/byte
// - ADD: --fee-rate <n> flag (stocks per byte, default 1)
// - ADD: --node <host:port> promoted to global option (used by fee calc + send)
// - REM: manual [fee] parameter removed from send/createtx (now automatic)
//
// CHANGES v1.2:
// - ADD: --rpc-user / --rpc-pass for RPC Basic Auth
// - FIX: fee default is now 0.00010000 SOST (10000 stocks)
//        fee parameter is in SOST (same as amount, for consistency)
//        Help text clarifies fee unit
//
// Commands:
//   sost-cli newwallet [path]           Create new wallet
//   sost-cli getnewaddress [label]      Generate new address
//   sost-cli listaddresses              Show all addresses
//   sost-cli importprivkey <hex>        Import private key
//   sost-cli importgenesis <json>       Import genesis coinbase UTXOs
//   sost-cli getbalance [address]       Show balance (stocks)
//   sost-cli listunspent [address]      Show unspent outputs
//   sost-cli createtx <to> <amount>     Create and sign transaction (auto fee)
//   sost-cli send <to> <amount>         Create, sign and broadcast (auto fee)
//   sost-cli create-bond <amt> <blocks> Create BOND_LOCK transaction
//   sost-cli create-escrow <amt> <blocks> <beneficiary>  Create ESCROW_LOCK tx
//   sost-cli list-bonds                 List bond/escrow UTXOs
//   sost-cli dumpprivkey <address>      Show private key (DANGER)
//   sost-cli info                       Wallet summary

#include "sost/wallet.h"
#include "sost/types.h"
#include "sost/params.h"
#include "sost/address.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>

static const char* DEFAULT_WALLET = "wallet.json";
static const int64_t STOCKS_PER_SOST = 100000000LL;

// v1.3: fee is now dynamic — this is only the absolute floor
static const int64_t MIN_FEE_STOCKS   = 1000;  // 0.00001 SOST floor
static const int64_t FEE_RATE_DEFAULT  = 1;     // 1 stock/byte (consensus min S8)

// RPC auth credentials (empty = no auth header sent)
static std::string g_rpc_user = "";
static std::string g_rpc_pass = "";

// v1.3: global node address and fee rate
static std::string g_node_host = "127.0.0.1";
static int         g_node_port = 18232;
static int64_t     g_fee_rate  = FEE_RATE_DEFAULT;

// Format stocks as SOST with 8 decimal places
static std::string format_sost(int64_t stocks) {
    char buf[64];
    bool neg = stocks < 0;
    int64_t abs_val = neg ? -stocks : stocks;
    int64_t whole = abs_val / STOCKS_PER_SOST;
    int64_t frac = abs_val % STOCKS_PER_SOST;
    snprintf(buf, sizeof(buf), "%s%lld.%08lld",
             neg ? "-" : "",
             (long long)whole, (long long)frac);
    return std::string(buf);
}

// Parse SOST amount string to stocks (supports decimal)
static int64_t parse_amount(const char* str) {
    std::string s(str);
    auto dot = s.find('.');
    if (dot == std::string::npos) {
        // Integer SOST
        return std::stoll(s) * STOCKS_PER_SOST;
    }
    std::string whole_str = s.substr(0, dot);
    std::string frac_str = s.substr(dot + 1);
    // Pad or truncate to 8 digits
    while (frac_str.size() < 8) frac_str += '0';
    frac_str = frac_str.substr(0, 8);

    int64_t whole = whole_str.empty() ? 0 : std::stoll(whole_str);
    int64_t frac = std::stoll(frac_str);
    return whole * STOCKS_PER_SOST + frac;
}

// Hex helper
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

// =============================================================================
// Base64 encode (for RPC Basic Auth)
// =============================================================================
static std::string base64_encode(const std::string& in) {
    static const char* b64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val = 0, valb = -6;
    for (unsigned char c : in) {
        val = (val << 8) + c;
        valb += 8;
        while (valb >= 0) {
            out.push_back(b64[(val >> valb) & 0x3F]);
            valb -= 6;
        }
    }
    if (valb > -6) out.push_back(b64[((val << 8) >> (valb + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

static std::string rpc_auth_header() {
    if (g_rpc_user.empty() && g_rpc_pass.empty()) return "";
    std::string token = base64_encode(g_rpc_user + ":" + g_rpc_pass);
    return "Authorization: Basic " + token + "\r\n";
}

// =============================================================================
// v1.3: RPC helper — send a JSON-RPC call to the running node
//
// Used to query chain height (getinfo) before building transactions.
// This lets us pass the real height to create_transaction so it can
// filter out immature coinbase UTXOs (COINBASE_MATURITY = 1000).
// =============================================================================
static std::string rpc_call(const std::string& method,
                            const std::string& params_json = "[]")
{
    std::string body = "{\"method\":\"" + method
        + "\",\"params\":" + params_json + ",\"id\":1}";

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";

    struct sockaddr_in saddr{};
    saddr.sin_family = AF_INET;
    saddr.sin_port = htons(g_node_port);
    struct hostent* he = gethostbyname(g_node_host.c_str());
    if (!he) { close(fd); return ""; }
    memcpy(&saddr.sin_addr, he->h_addr_list[0], he->h_length);

    if (connect(fd, (struct sockaddr*)&saddr, sizeof(saddr)) < 0) {
        close(fd);
        return "";
    }

    std::string req = "POST / HTTP/1.1\r\nHost: " + g_node_host
        + "\r\nContent-Type: application/json\r\n"
        + rpc_auth_header()
        + "Content-Length: " + std::to_string(body.size())
        + "\r\n\r\n" + body;

    write(fd, req.c_str(), req.size());

    // Read response (16KB buffer — enough for getinfo)
    std::string resp;
    char buf[4096];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf) - 1)) > 0) {
        buf[n] = 0;
        resp += buf;
        if (resp.find("\r\n\r\n") != std::string::npos &&
            resp.back() == '}') break;
    }
    close(fd);
    return resp;
}

// v1.3: Extract "blocks" field from getinfo JSON response
static int64_t query_chain_height() {
    std::string resp = rpc_call("getinfo");
    if (resp.empty()) return -1;

    // Find "blocks":NNN in JSON
    auto pos = resp.find("\"blocks\":");
    if (pos == std::string::npos) return -1;
    pos += 9;  // skip past "blocks":
    return std::stoll(resp.substr(pos));
}

// =============================================================================
// v1.3: Dynamic fee calculation
//
// Bitcoin Core approach:
//   1. Build tx with initial fee estimate
//   2. Serialize to measure real byte count
//   3. fee = max(real_size × fee_rate, MIN_FEE_STOCKS)
//   4. If fee changed, rebuild tx with correct fee (change output adjusts)
//
// This guarantees S8 compliance: fee >= tx_size × 1 stock/byte
// =============================================================================
static int64_t calculate_fee(int64_t tx_size_bytes) {
    int64_t fee = tx_size_bytes * g_fee_rate;
    if (fee < MIN_FEE_STOCKS) fee = MIN_FEE_STOCKS;
    return fee;
}

static void print_usage() {
    printf("SOST Wallet CLI v1.3\n\n");
    printf("Usage: sost-cli [options] <command> [args...]\n\n");
    printf("Commands:\n");
    printf("  newwallet              Create new wallet file\n");
    printf("  getnewaddress [label]  Generate new receiving address\n");
    printf("  listaddresses          List all wallet addresses\n");
    printf("  importprivkey <hex>    Import a private key\n");
    printf("  importgenesis <json>   Import genesis block coinbase UTXOs\n");
    printf("  getbalance [addr]      Show balance in SOST\n");
    printf("  listunspent [addr]     List unspent transaction outputs\n");
    printf("  createtx <to> <amt>    Create and sign a transaction (auto fee)\n");
    printf("  send <to> <amt>        Create, sign and broadcast to node (auto fee)\n");
    printf("  create-bond <amt> <blocks>  Create BOND_LOCK (timelocked to self)\n");
    printf("  create-escrow <amt> <blocks> <beneficiary>  Create ESCROW_LOCK\n");
    printf("  list-bonds             List active bond/escrow UTXOs\n");
    printf("  dumpprivkey <addr>     Reveal private key (DANGER)\n");
    printf("  wallet-export          Export encrypted wallet backup (AES-256-GCM)\n");
    printf("  wallet-import          Import encrypted wallet backup\n");
    printf("  info                   Wallet summary\n");
    printf("\nOptions:\n");
    printf("  --wallet <path>        Wallet file (default: wallet.json)\n");
    printf("  --rpc-user <user>      RPC Basic Auth username\n");
    printf("  --rpc-pass <pass>      RPC Basic Auth password\n");
    printf("  --node <host:port>     Node address (default: 127.0.0.1:18232)\n");
    printf("  --fee-rate <n>         Fee rate in stocks/byte (default: 1)\n");
    printf("\nFee calculation (v1.3 — automatic):\n");
    printf("  Fee = tx_size_bytes x fee_rate stocks/byte\n");
    printf("  Minimum: %s SOST (%lld stocks)\n",
           format_sost(MIN_FEE_STOCKS).c_str(), (long long)MIN_FEE_STOCKS);
    printf("  Consensus rule S8: fee >= tx_size x 1 stock/byte\n");
    printf("\nExamples:\n");
    printf("  sost-cli send sost1abc... 10              (auto fee, 1 stock/byte)\n");
    printf("  sost-cli --fee-rate 2 send sost1abc... 10 (priority: 2 stocks/byte)\n");
}

int main(int argc, char** argv) {
    std::string wallet_path = DEFAULT_WALLET;

    // Parse global options
    int arg_start = 1;
    while (arg_start < argc && argv[arg_start][0] == '-') {
        std::string flag = argv[arg_start];
        if (flag == "--wallet" && arg_start + 1 < argc) {
            wallet_path = argv[arg_start + 1];
            arg_start += 2;
        } else if (flag == "--rpc-user" && arg_start + 1 < argc) {
            g_rpc_user = argv[arg_start + 1];
            arg_start += 2;
        } else if (flag == "--rpc-pass" && arg_start + 1 < argc) {
            g_rpc_pass = argv[arg_start + 1];
            arg_start += 2;
        } else if (flag == "--node" && arg_start + 1 < argc) {
            // v1.3: --node is now a global option (used by fee calc + send)
            std::string na = argv[arg_start + 1];
            auto colon = na.find(':');
            if (colon != std::string::npos) {
                g_node_host = na.substr(0, colon);
                g_node_port = atoi(na.substr(colon + 1).c_str());
            } else {
                g_node_host = na;
            }
            arg_start += 2;
        } else if (flag == "--fee-rate" && arg_start + 1 < argc) {
            // v1.3: custom fee rate (stocks per byte)
            g_fee_rate = std::stoll(argv[arg_start + 1]);
            if (g_fee_rate < 1) {
                fprintf(stderr, "Error: --fee-rate must be >= 1 (consensus minimum)\n");
                return 1;
            }
            arg_start += 2;
        } else if (flag == "--help" || flag == "-h") {
            print_usage();
            return 0;
        } else {
            break;
        }
    }

    if (argc < arg_start + 1) {
        print_usage();
        return 1;
    }

    std::string cmd = argv[arg_start];

    // =====================================================================
    // newwallet
    // =====================================================================
    if (cmd == "newwallet") {
        sost::Wallet w;
        auto key = w.generate_key("default");
        std::string err;
        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }
        printf("New wallet created: %s\n", wallet_path.c_str());
        printf("Address: %s\n", key.address.c_str());
        printf("\n*** BACKUP THIS FILE — IT CONTAINS YOUR PRIVATE KEYS ***\n");
        return 0;
    }

    // All other commands need an existing wallet (except newwallet)
    sost::Wallet w;
    {
        std::string err;
        if (!w.load(wallet_path, &err)) {
            fprintf(stderr, "Error loading wallet '%s': %s\n",
                    wallet_path.c_str(), err.c_str());
            fprintf(stderr, "Use 'sost-cli newwallet' to create a new wallet.\n");
            return 1;
        }
    }

    // =====================================================================
    // getnewaddress [label]
    // =====================================================================
    if (cmd == "getnewaddress") {
        std::string label;
        if (argc > arg_start + 1) label = argv[arg_start + 1];
        auto key = w.generate_key(label);
        std::string err;
        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Error saving wallet: %s\n", err.c_str());
            return 1;
        }
        printf("%s\n", key.address.c_str());
        return 0;
    }

    // =====================================================================
    // listaddresses
    // =====================================================================
    if (cmd == "listaddresses") {
        const auto& keys = w.keys();
        if (keys.empty()) {
            printf("No addresses in wallet.\n");
            return 0;
        }
        for (const auto& k : keys) {
            int64_t bal = w.balance(k.address);
            printf("%-47s  %s SOST", k.address.c_str(), format_sost(bal).c_str());
            if (!k.label.empty()) printf("  [%s]", k.label.c_str());
            printf("\n");
        }
        return 0;
    }

    // =====================================================================
    // importprivkey <hex>
    // =====================================================================
    if (cmd == "importprivkey") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli importprivkey <64-char-hex>\n");
            return 1;
        }
        std::string hex_str = argv[arg_start + 1];
        if (hex_str.size() != 64) {
            fprintf(stderr, "Error: private key must be 64 hex characters\n");
            return 1;
        }
        sost::PrivKey priv{};
        for (int i = 0; i < 32; ++i) {
            auto hv = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return 10 + c - 'a';
                if (c >= 'A' && c <= 'F') return 10 + c - 'A';
                return -1;
            };
            int hi = hv(hex_str[i * 2]);
            int lo = hv(hex_str[i * 2 + 1]);
            if (hi < 0 || lo < 0) {
                fprintf(stderr, "Error: invalid hex character\n");
                return 1;
            }
            priv[i] = (uint8_t)((hi << 4) | lo);
        }

        try {
            auto key = w.import_privkey(priv);
            std::string err;
            if (!w.save(wallet_path, &err)) {
                fprintf(stderr, "Error saving wallet: %s\n", err.c_str());
                return 1;
            }
            printf("Imported: %s\n", key.address.c_str());
        } catch (const std::exception& e) {
            fprintf(stderr, "Error: %s\n", e.what());
            return 1;
        }
        return 0;
    }

    // =====================================================================
    // importgenesis <json_path>
    // =====================================================================
    if (cmd == "importgenesis") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli importgenesis <genesis_block.json>\n");
            return 1;
        }
        std::string err;
        if (!w.import_genesis(argv[arg_start + 1], &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }
        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Error saving wallet: %s\n", err.c_str());
            return 1;
        }
        printf("Genesis imported. Balance: %s SOST\n",
               format_sost(w.balance()).c_str());
        printf("UTXOs: %zu\n", w.num_utxos());
        return 0;
    }

    // =====================================================================
    // getbalance [address]
    // =====================================================================
    if (cmd == "getbalance") {
        int64_t chain_height = query_chain_height();
        if (argc > arg_start + 1) {
            std::string addr = argv[arg_start + 1];
            printf("%s SOST\n", format_sost(w.balance(addr)).c_str());
        } else {
            int64_t total = w.balance(chain_height);
            int64_t locked = w.locked_balance(chain_height);
            int64_t avail = total - locked;
            printf("Total:     %s SOST\n", format_sost(total).c_str());
            if (locked > 0) {
                printf("Available: %s SOST\n", format_sost(avail).c_str());
                printf("Locked:    %s SOST (bonds/escrows)\n", format_sost(locked).c_str());
            }
        }
        return 0;
    }

    // =====================================================================
    // listunspent [address]
    // =====================================================================
    if (cmd == "listunspent") {
        std::vector<sost::WalletUTXO> utxos;
        if (argc > arg_start + 1) {
            utxos = w.list_unspent(argv[arg_start + 1]);
        } else {
            utxos = w.list_unspent();
        }
        if (utxos.empty()) {
            printf("No unspent outputs.\n");
            return 0;
        }
        for (const auto& u : utxos) {
            printf("txid: %s  vout: %u  amount: %s SOST  height: %lld",
                   to_hex(u.txid.data(), 32).c_str(),
                   u.vout,
                   format_sost(u.amount).c_str(),
                   (long long)u.height);
            if (u.output_type == 0x10) printf("  [BOND locked until %llu]", (unsigned long long)u.lock_until);
            if (u.output_type == 0x11) printf("  [ESCROW locked until %llu]", (unsigned long long)u.lock_until);
            printf("\n");
        }
        printf("\nTotal: %zu UTXOs\n", utxos.size());
        return 0;
    }

    // =====================================================================
    // createtx <to_addr> <amount_sost>
    //
    // v1.3: fee is now automatic. Two-pass build:
    //   Pass 1: build tx with MIN_FEE estimate → serialize → measure bytes
    //   Pass 2: real_fee = bytes × fee_rate → rebuild if different
    //   Pass 3: (rare) if size shifted after fee change, one more adjust
    // =====================================================================
    if (cmd == "createtx") {
        if (argc < arg_start + 3) {
            fprintf(stderr, "Usage: sost-cli createtx <to_address> <amount_sost>\n");
            fprintf(stderr, "  Fee is automatic: tx_size x %lld stock/byte\n",
                    (long long)g_fee_rate);
            return 1;
        }
        std::string to_addr = argv[arg_start + 1];
        int64_t amount = parse_amount(argv[arg_start + 2]);

        // v1.3: Query node for chain height so create_transaction can
        //       filter out immature coinbase UTXOs (need COINBASE_MATURITY confs)
        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Warning: cannot reach node at %s:%d\n",
                    g_node_host.c_str(), g_node_port);
            fprintf(stderr, "  Maturity check disabled — tx may be rejected by node.\n");
            chain_height = -1;
        } else {
            printf("Chain height: %lld\n", (long long)chain_height);
        }

        sost::Hash256 genesis_hash = sost::from_hex(
            "0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793");

        // --- Pass 1: build with estimated fee to measure real size ---
        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction(to_addr, amount, est_fee, genesis_hash,
                                  tx, chain_height, &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }

        // Serialize to get actual byte count
        std::vector<sost::Byte> raw;
        std::string ser_err;
        if (!tx.Serialize(raw, &ser_err)) {
            fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
            return 1;
        }

        // --- Pass 2: recalculate fee from real size, rebuild if needed ---
        int64_t real_fee = calculate_fee((int64_t)raw.size());
        if (real_fee != est_fee) {
            sost::Transaction tx2;
            if (!w.create_transaction(to_addr, amount, real_fee, genesis_hash,
                                      tx2, chain_height, &err)) {
                fprintf(stderr, "Error (fee adjustment): %s\n", err.c_str());
                return 1;
            }
            tx = tx2;
            raw.clear();
            if (!tx.Serialize(raw, &ser_err)) {
                fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
                return 1;
            }

            // --- Pass 3: final check (size may shift by a few bytes) ---
            int64_t final_fee = calculate_fee((int64_t)raw.size());
            if (final_fee > real_fee) {
                sost::Transaction tx3;
                if (!w.create_transaction(to_addr, amount, final_fee, genesis_hash,
                                          tx3, chain_height, &err)) {
                    fprintf(stderr, "Error (final fee pass): %s\n", err.c_str());
                    return 1;
                }
                tx = tx3;
                raw.clear();
                tx.Serialize(raw, &ser_err);
                real_fee = final_fee;
            } else {
                real_fee = final_fee;
            }
        }

        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Warning: failed to save wallet: %s\n", err.c_str());
        }

        printf("Transaction created successfully.\n");
        printf("  Inputs:  %zu\n", tx.inputs.size());
        printf("  Outputs: %zu\n", tx.outputs.size());
        printf("  Size:    %zu bytes\n", raw.size());
        printf("  Fee:     %s SOST (%lld stocks = %zu bytes x %lld rate)\n",
               format_sost(real_fee).c_str(), (long long)real_fee,
               raw.size(), (long long)g_fee_rate);
        printf("  Raw hex: %s\n", to_hex(raw.data(), raw.size()).c_str());

        sost::Hash256 txid;
        if (tx.ComputeTxId(txid)) {
            printf("  Txid:    %s\n", to_hex(txid.data(), 32).c_str());
        }

        return 0;
    }

    // =====================================================================
    // send <to_addr> <amount_sost>
    //
    // v1.3: automatic fee, queries node for height, two-pass build
    //       No more manual [fee] parameter — calculated from real tx size
    // =====================================================================
    if (cmd == "send") {
        if (argc < arg_start + 3) {
            fprintf(stderr, "Usage: sost-cli send <to_address> <amount_sost>\n");
            fprintf(stderr, "  Fee is automatic: tx_size x %lld stock/byte\n",
                    (long long)g_fee_rate);
            fprintf(stderr, "  Use --fee-rate <n> for priority (default: 1)\n");
            fprintf(stderr, "\nExamples:\n");
            fprintf(stderr, "  sost-cli send sost1abc... 10\n");
            fprintf(stderr, "  sost-cli --fee-rate 2 send sost1abc... 10\n");
            return 1;
        }
        std::string to_addr = argv[arg_start + 1];
        int64_t amount = parse_amount(argv[arg_start + 2]);

        // v1.3: Query node for current chain height
        //       Required for: maturity filter + broadcasting
        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Error: cannot connect to node at %s:%d\n",
                    g_node_host.c_str(), g_node_port);
            fprintf(stderr, "  Node must be running to check maturity and broadcast.\n");
            return 1;
        }
        printf("Chain height: %lld\n", (long long)chain_height);

        // Create transaction with dynamic fee
        sost::Hash256 genesis_hash = sost::from_hex(
            "0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793");

        // --- Pass 1: build with estimated fee to measure real size ---
        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction(to_addr, amount, est_fee, genesis_hash,
                                  tx, chain_height, &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }

        std::vector<sost::Byte> raw;
        std::string ser_err;
        if (!tx.Serialize(raw, &ser_err)) {
            fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
            return 1;
        }

        // --- Pass 2: recalculate fee from real size, rebuild if different ---
        int64_t real_fee = calculate_fee((int64_t)raw.size());
        if (real_fee != est_fee) {
            sost::Transaction tx2;
            if (!w.create_transaction(to_addr, amount, real_fee, genesis_hash,
                                      tx2, chain_height, &err)) {
                fprintf(stderr, "Error (fee adjustment): %s\n", err.c_str());
                return 1;
            }
            tx = tx2;
            raw.clear();
            if (!tx.Serialize(raw, &ser_err)) {
                fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
                return 1;
            }

            // --- Pass 3: final check ---
            int64_t final_fee = calculate_fee((int64_t)raw.size());
            if (final_fee > real_fee) {
                sost::Transaction tx3;
                if (!w.create_transaction(to_addr, amount, final_fee, genesis_hash,
                                          tx3, chain_height, &err)) {
                    fprintf(stderr, "Error (final fee pass): %s\n", err.c_str());
                    return 1;
                }
                tx = tx3;
                raw.clear();
                tx.Serialize(raw, &ser_err);
                real_fee = final_fee;
            } else {
                real_fee = final_fee;
            }
        }

        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Warning: failed to save wallet: %s\n", err.c_str());
        }

        // Display tx info
        std::string raw_hex = to_hex(raw.data(), raw.size());
        sost::Hash256 txid;
        tx.ComputeTxId(txid);

        printf("TX created: %s\n", to_hex(txid.data(), 32).c_str());
        printf("  To:     %s\n", to_addr.c_str());
        printf("  Amount: %s SOST\n", format_sost(amount).c_str());
        printf("  Fee:    %s SOST (%lld stocks = %zu bytes x %lld rate)\n",
               format_sost(real_fee).c_str(), (long long)real_fee,
               raw.size(), (long long)g_fee_rate);
        printf("  Size:   %zu bytes\n", raw.size());

        // Broadcast via JSON-RPC: sendrawtransaction
        printf("Sending to node %s:%d...\n", g_node_host.c_str(), g_node_port);

        std::string rpc_body = "{\"method\":\"sendrawtransaction\",\"params\":[\""
            + raw_hex + "\"],\"id\":1}";

        int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) { perror("socket"); return 1; }
        struct sockaddr_in saddr{};
        saddr.sin_family = AF_INET;
        saddr.sin_port = htons(g_node_port);
        struct hostent* he = gethostbyname(g_node_host.c_str());
        if (!he) {
            fprintf(stderr, "Cannot resolve %s\n", g_node_host.c_str());
            close(fd);
            return 1;
        }
        memcpy(&saddr.sin_addr, he->h_addr_list[0], he->h_length);
        if (connect(fd, (struct sockaddr*)&saddr, sizeof(saddr)) < 0) {
            fprintf(stderr, "Cannot connect to %s:%d\n",
                    g_node_host.c_str(), g_node_port);
            close(fd);
            return 1;
        }

        std::string http_req = "POST / HTTP/1.1\r\nHost: " + g_node_host
            + "\r\nContent-Type: application/json\r\n"
            + rpc_auth_header()
            + "Content-Length: " + std::to_string(rpc_body.size())
            + "\r\n\r\n" + rpc_body;

        write(fd, http_req.c_str(), http_req.size());

        char rbuf[4096]{};
        read(fd, rbuf, sizeof(rbuf) - 1);
        close(fd);

        std::string resp(rbuf);
        if (resp.find("\"result\":\"") != std::string::npos) {
            printf("\nTX accepted by node! Txid: %s\n",
                   to_hex(txid.data(), 32).c_str());
            printf("  Waiting for next mined block to confirm...\n");
        } else if (resp.find("401") != std::string::npos) {
            fprintf(stderr, "\nTX rejected: 401 Unauthorized\n");
            fprintf(stderr, "  Node requires auth. Use: --rpc-user <user> --rpc-pass <pass>\n");
            return 1;
        } else {
            auto err_pos = resp.find("\"message\":\"");
            if (err_pos != std::string::npos) {
                auto err_end = resp.find('"', err_pos + 11);
                std::string err_msg = resp.substr(err_pos + 11,
                                                   err_end - err_pos - 11);
                fprintf(stderr, "\nTX rejected: %s\n", err_msg.c_str());
            } else {
                fprintf(stderr, "\nTX rejected (unknown error)\n");
                fprintf(stderr, "  Raw response: %s\n", resp.c_str());
            }
            return 1;
        }
        return 0;
    }

    // =====================================================================
    // create-bond <amount_sost> <lock_blocks>
    // =====================================================================
    if (cmd == "create-bond") {
        if (argc < arg_start + 3) {
            fprintf(stderr, "Usage: sost-cli create-bond <amount_sost> <lock_blocks>\n");
            fprintf(stderr, "  Creates a BOND_LOCK output locked for <lock_blocks> blocks\n");
            fprintf(stderr, "  Example: sost-cli create-bond 100 1000  (lock 100 SOST for 1000 blocks)\n");
            return 1;
        }
        int64_t amount = parse_amount(argv[arg_start + 1]);
        int64_t lock_blocks = std::stoll(argv[arg_start + 2]);
        if (lock_blocks <= 0) {
            fprintf(stderr, "Error: lock_blocks must be positive\n");
            return 1;
        }

        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Error: cannot connect to node (need chain height for lock_until)\n");
            return 1;
        }
        uint64_t lock_until = (uint64_t)chain_height + (uint64_t)lock_blocks;

        sost::Hash256 genesis_hash = sost::from_hex(
            "0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793");

        // Two-pass fee calculation
        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_bond_transaction(amount, est_fee, lock_until, genesis_hash,
                                       tx, chain_height, &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }

        std::vector<sost::Byte> raw;
        std::string ser_err;
        tx.Serialize(raw, &ser_err);
        int64_t real_fee = calculate_fee((int64_t)raw.size());
        if (real_fee != est_fee) {
            sost::Transaction tx2;
            if (!w.create_bond_transaction(amount, real_fee, lock_until, genesis_hash,
                                           tx2, chain_height, &err)) {
                fprintf(stderr, "Error (fee adjustment): %s\n", err.c_str());
                return 1;
            }
            tx = tx2;
            raw.clear();
            tx.Serialize(raw, &ser_err);
        }

        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Warning: failed to save wallet: %s\n", err.c_str());
        }

        sost::Hash256 txid;
        tx.ComputeTxId(txid);
        printf("BOND_LOCK transaction created.\n");
        printf("  Amount:     %s SOST\n", format_sost(amount).c_str());
        printf("  Lock until: height %llu (current: %lld, +%lld blocks)\n",
               (unsigned long long)lock_until, (long long)chain_height, (long long)lock_blocks);
        printf("  Fee:        %s SOST (%zu bytes)\n", format_sost(real_fee).c_str(), raw.size());
        printf("  Txid:       %s\n", to_hex(txid.data(), 32).c_str());
        printf("  Raw hex:    %s\n", to_hex(raw.data(), raw.size()).c_str());
        return 0;
    }

    // =====================================================================
    // create-escrow <amount_sost> <lock_blocks> <beneficiary_address>
    // =====================================================================
    if (cmd == "create-escrow") {
        if (argc < arg_start + 4) {
            fprintf(stderr, "Usage: sost-cli create-escrow <amount_sost> <lock_blocks> <beneficiary>\n");
            fprintf(stderr, "  Creates an ESCROW_LOCK output with a beneficiary address\n");
            return 1;
        }
        int64_t amount = parse_amount(argv[arg_start + 1]);
        int64_t lock_blocks = std::stoll(argv[arg_start + 2]);
        std::string beneficiary_addr = argv[arg_start + 3];

        if (lock_blocks <= 0) {
            fprintf(stderr, "Error: lock_blocks must be positive\n");
            return 1;
        }

        sost::PubKeyHash beneficiary_pkh{};
        if (!sost::address_decode(beneficiary_addr, beneficiary_pkh)) {
            fprintf(stderr, "Error: invalid beneficiary address: %s\n", beneficiary_addr.c_str());
            return 1;
        }

        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Error: cannot connect to node (need chain height for lock_until)\n");
            return 1;
        }
        uint64_t lock_until = (uint64_t)chain_height + (uint64_t)lock_blocks;

        sost::Hash256 genesis_hash = sost::from_hex(
            "0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793");

        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_escrow_transaction(amount, est_fee, lock_until, beneficiary_pkh,
                                         genesis_hash, tx, chain_height, &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }

        std::vector<sost::Byte> raw;
        std::string ser_err;
        tx.Serialize(raw, &ser_err);
        int64_t real_fee = calculate_fee((int64_t)raw.size());
        if (real_fee != est_fee) {
            sost::Transaction tx2;
            if (!w.create_escrow_transaction(amount, real_fee, lock_until, beneficiary_pkh,
                                             genesis_hash, tx2, chain_height, &err)) {
                fprintf(stderr, "Error (fee adjustment): %s\n", err.c_str());
                return 1;
            }
            tx = tx2;
            raw.clear();
            tx.Serialize(raw, &ser_err);
        }

        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Warning: failed to save wallet: %s\n", err.c_str());
        }

        sost::Hash256 txid;
        tx.ComputeTxId(txid);
        printf("ESCROW_LOCK transaction created.\n");
        printf("  Amount:      %s SOST\n", format_sost(amount).c_str());
        printf("  Lock until:  height %llu (current: %lld, +%lld blocks)\n",
               (unsigned long long)lock_until, (long long)chain_height, (long long)lock_blocks);
        printf("  Beneficiary: %s\n", beneficiary_addr.c_str());
        printf("  Fee:         %s SOST (%zu bytes)\n", format_sost(real_fee).c_str(), raw.size());
        printf("  Txid:        %s\n", to_hex(txid.data(), 32).c_str());
        printf("  Raw hex:     %s\n", to_hex(raw.data(), raw.size()).c_str());
        return 0;
    }

    // =====================================================================
    // list-bonds
    // =====================================================================
    if (cmd == "list-bonds") {
        int64_t chain_height = query_chain_height();
        auto bonds = w.list_bonds(chain_height);
        if (bonds.empty()) {
            printf("No active bond/escrow UTXOs.\n");
            return 0;
        }
        for (const auto& u : bonds) {
            const char* type_str = (u.output_type == 0x10) ? "BOND" : "ESCROW";
            bool locked = (chain_height >= 0 && (uint64_t)chain_height < u.lock_until);
            printf("[%s] %s SOST  lock_until: %llu  status: %s\n",
                   type_str,
                   format_sost(u.amount).c_str(),
                   (unsigned long long)u.lock_until,
                   locked ? "LOCKED" : "UNLOCKED");
            printf("  txid: %s  vout: %u\n",
                   to_hex(u.txid.data(), 32).c_str(), u.vout);
            if (u.output_type == 0x11) {
                printf("  beneficiary: sost1%s\n",
                       to_hex(u.beneficiary.data(), 20).c_str());
            }
            if (locked && chain_height >= 0) {
                printf("  blocks remaining: %llu\n",
                       (unsigned long long)(u.lock_until - (uint64_t)chain_height));
            }
        }
        printf("\nTotal: %zu bond/escrow UTXOs\n", bonds.size());
        return 0;
    }

    // =====================================================================
    // dumpprivkey <address>
    // =====================================================================
    if (cmd == "dumpprivkey") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli dumpprivkey <address>\n");
            return 1;
        }
        std::string addr = argv[arg_start + 1];
        const sost::WalletKey* key = w.find_key(addr);
        if (!key) {
            fprintf(stderr, "Error: address not found in wallet\n");
            return 1;
        }
        printf("%s\n", to_hex(key->privkey.data(), 32).c_str());
        printf("\n*** KEEP THIS KEY SECRET — ANYONE WITH IT CAN SPEND YOUR SOST ***\n");
        return 0;
    }

    // =====================================================================
    // wallet-export --encrypted --output <file>
    // =====================================================================
    if (cmd == "wallet-export") {
        std::string output_path;
        bool encrypted = false;
        for (int i = arg_start + 1; i < argc; ++i) {
            if (!strcmp(argv[i], "--encrypted")) encrypted = true;
            else if (!strcmp(argv[i], "--output") && i + 1 < argc) output_path = argv[++i];
        }
        if (output_path.empty()) {
            fprintf(stderr, "Usage: sost-cli wallet-export --encrypted --output <file>\n");
            return 1;
        }
        if (!encrypted) {
            fprintf(stderr, "Error: only --encrypted export is supported (plaintext export is a security risk)\n");
            return 1;
        }

        // Prompt passphrase twice
        printf("Enter passphrase for encrypted backup: ");
        fflush(stdout);
        char pass1[256]{}, pass2[256]{};
        if (!fgets(pass1, sizeof(pass1), stdin)) { fprintf(stderr, "Error reading passphrase\n"); return 1; }
        pass1[strcspn(pass1, "\r\n")] = 0;

        printf("Confirm passphrase: ");
        fflush(stdout);
        if (!fgets(pass2, sizeof(pass2), stdin)) { fprintf(stderr, "Error reading passphrase\n"); return 1; }
        pass2[strcspn(pass2, "\r\n")] = 0;

        if (strcmp(pass1, pass2) != 0) {
            fprintf(stderr, "Error: passphrases do not match\n");
            return 1;
        }
        if (strlen(pass1) < 8) {
            fprintf(stderr, "Error: passphrase must be at least 8 characters\n");
            return 1;
        }

        std::string err;
        if (!w.save_encrypted(output_path, std::string(pass1), &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }
        printf("Encrypted wallet backup saved to: %s\n", output_path.c_str());
        printf("  Keys:    %zu\n", w.num_keys());
        printf("  UTXOs:   %zu\n", w.num_utxos());
        printf("  KDF:     scrypt (N=32768, r=8, p=1)\n");
        printf("  Cipher:  AES-256-GCM\n");
        printf("\n*** REMEMBER YOUR PASSPHRASE — IT CANNOT BE RECOVERED ***\n");

        // Zero passphrase memory
        memset(pass1, 0, sizeof(pass1));
        memset(pass2, 0, sizeof(pass2));
        return 0;
    }

    // =====================================================================
    // wallet-import --encrypted --input <file>
    // =====================================================================
    if (cmd == "wallet-import") {
        std::string input_path;
        bool encrypted = false;
        for (int i = arg_start + 1; i < argc; ++i) {
            if (!strcmp(argv[i], "--encrypted")) encrypted = true;
            else if (!strcmp(argv[i], "--input") && i + 1 < argc) input_path = argv[++i];
        }
        if (input_path.empty()) {
            fprintf(stderr, "Usage: sost-cli wallet-import --encrypted --input <file>\n");
            return 1;
        }
        if (!encrypted) {
            fprintf(stderr, "Error: only --encrypted import is supported\n");
            return 1;
        }

        printf("Enter passphrase for encrypted backup: ");
        fflush(stdout);
        char pass[256]{};
        if (!fgets(pass, sizeof(pass), stdin)) { fprintf(stderr, "Error reading passphrase\n"); return 1; }
        pass[strcspn(pass, "\r\n")] = 0;

        sost::Wallet imported;
        std::string err;
        if (!imported.load_encrypted(input_path, std::string(pass), &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            memset(pass, 0, sizeof(pass));
            return 1;
        }
        memset(pass, 0, sizeof(pass));

        // Save as the active wallet (plaintext format for node use)
        if (!imported.save(wallet_path, &err)) {
            fprintf(stderr, "Error saving wallet: %s\n", err.c_str());
            return 1;
        }
        printf("Wallet imported from: %s\n", input_path.c_str());
        printf("  Saved to:  %s\n", wallet_path.c_str());
        printf("  Keys:      %zu\n", imported.num_keys());
        printf("  UTXOs:     %zu\n", imported.num_utxos());
        printf("  Balance:   %s SOST\n", format_sost(imported.balance()).c_str());
        return 0;
    }

    // =====================================================================
    // info
    // =====================================================================
    if (cmd == "info") {
        printf("SOST Wallet v1.3\n");
        printf("  File:      %s\n", wallet_path.c_str());
        printf("  Addresses: %zu\n", w.num_keys());
        printf("  UTXOs:     %zu\n", w.num_utxos());
        printf("  Balance:   %s SOST\n", format_sost(w.balance()).c_str());
        if (w.num_keys() > 0) {
            printf("  Default:   %s\n", w.default_address().c_str());
        }
        return 0;
    }

    // Unknown command
    fprintf(stderr, "Unknown command: %s\n", cmd.c_str());
    print_usage();
    return 1;
}
