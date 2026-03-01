// sost-cli.cpp — SOST Wallet CLI v1.1
//
// Commands:
//   sost-cli newwallet [path]           Create new wallet
//   sost-cli getnewaddress [label]      Generate new address
//   sost-cli listaddresses              Show all addresses
//   sost-cli importprivkey <hex>        Import private key
//   sost-cli importgenesis <json>       Import genesis coinbase UTXOs
//   sost-cli getbalance [address]       Show balance (stocks)
//   sost-cli listunspent [address]      Show unspent outputs
//   sost-cli createtx <to> <amount> [fee]  Create and sign transaction
//   sost-cli send <to> <amount> [fee]   Create, sign and broadcast to node
//   sost-cli dumpprivkey <address>      Show private key (DANGER)
//   sost-cli info                       Wallet summary

#include "sost/wallet.h"
#include "sost/types.h"
#include "sost/params.h"

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

static void print_usage() {
    printf("SOST Wallet CLI v1.1\n\n");
    printf("Usage: sost-cli [--wallet <path>] <command> [args...]\n\n");
    printf("Commands:\n");
    printf("  newwallet              Create new wallet file\n");
    printf("  getnewaddress [label]  Generate new receiving address\n");
    printf("  listaddresses          List all wallet addresses\n");
    printf("  importprivkey <hex>    Import a private key\n");
    printf("  importgenesis <json>   Import genesis block coinbase UTXOs\n");
    printf("  getbalance [addr]      Show balance in SOST\n");
    printf("  listunspent [addr]     List unspent transaction outputs\n");
    printf("  createtx <to> <amt> [fee]  Create and sign a transaction\n");
    printf("  send <to> <amt> [fee]      Create, sign and broadcast to node\n");
    printf("  dumpprivkey <addr>     Reveal private key (DANGER)\n");
    printf("  info                   Wallet summary\n");
    printf("\nOptions:\n");
    printf("  --wallet <path>        Wallet file (default: wallet.json)\n");
}

int main(int argc, char** argv) {
    std::string wallet_path = DEFAULT_WALLET;

    // Parse --wallet flag
    int arg_start = 1;
    if (argc >= 3 && std::string(argv[1]) == "--wallet") {
        wallet_path = argv[2];
        arg_start = 3;
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
            // If file doesn't exist, suggest creating one
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
        if (argc > arg_start + 1) {
            std::string addr = argv[arg_start + 1];
            printf("%s SOST\n", format_sost(w.balance(addr)).c_str());
        } else {
            printf("%s SOST\n", format_sost(w.balance()).c_str());
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
            printf("txid: %s  vout: %u  amount: %s SOST  height: %lld\n",
                   to_hex(u.txid.data(), 32).c_str(),
                   u.vout,
                   format_sost(u.amount).c_str(),
                   (long long)u.height);
        }
        printf("\nTotal: %zu UTXOs\n", utxos.size());
        return 0;
    }

    // =====================================================================
    // createtx <to_addr> <amount> [fee]
    // =====================================================================
    if (cmd == "createtx") {
        if (argc < arg_start + 3) {
            fprintf(stderr, "Usage: sost-cli createtx <to_address> <amount_sost> [fee_sost]\n");
            return 1;
        }
        std::string to_addr = argv[arg_start + 1];
        int64_t amount = parse_amount(argv[arg_start + 2]);
        int64_t fee = 0;
        if (argc > arg_start + 3) {
            fee = parse_amount(argv[arg_start + 3]);
        }

        // For genesis hash, use the genesis block_id
        sost::Hash256 genesis_hash = sost::from_hex("0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793");

        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction(to_addr, amount, fee, genesis_hash, tx, &err)) {
            fprintf(stderr, "Error: %s\n", err.c_str());
            return 1;
        }

        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Warning: failed to save wallet: %s\n", err.c_str());
        }

        // Serialize transaction
        std::vector<sost::Byte> raw;
        std::string ser_err;
        if (!tx.Serialize(raw, &ser_err)) {
            fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
            return 1;
        }
        printf("Transaction created successfully.\n");
        printf("  Inputs:  %zu\n", tx.inputs.size());
        printf("  Outputs: %zu\n", tx.outputs.size());
        printf("  Size:    %zu bytes\n", raw.size());
        printf("  Raw hex: %s\n", to_hex(raw.data(), raw.size()).c_str());

        // Compute txid
        sost::Hash256 txid;
        if (tx.ComputeTxId(txid)) {
            printf("  Txid:    %s\n", to_hex(txid.data(), 32).c_str());
        }

        return 0;
    }

    // =====================================================================
    // send <to_addr> <amount> [fee] [--node host:port]
    // =====================================================================
    if (cmd == "send") {
        if (argc < arg_start + 3) {
            fprintf(stderr, "Usage: sost-cli send <to_address> <amount_sost> [fee_sost] [--node host:port]\n");
            return 1;
        }
        std::string to_addr = argv[arg_start + 1];
        int64_t amount = parse_amount(argv[arg_start + 2]);
        int64_t fee = 100; // default: 100 stocks = 0.00000100 SOST
        std::string node_addr = "127.0.0.1:18232";

        for (int i = arg_start + 3; i < argc; ++i) {
            if (std::string(argv[i]) == "--node" && i + 1 < argc) {
                node_addr = argv[++i];
            } else {
                fee = parse_amount(argv[i]);
            }
        }

        // Create transaction
        sost::Hash256 genesis_hash = sost::from_hex(
            "0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793");

        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction(to_addr, amount, fee, genesis_hash, tx, &err)) {
            fprintf(stderr, "Error creating tx: %s\n", err.c_str());
            return 1;
        }

        if (!w.save(wallet_path, &err)) {
            fprintf(stderr, "Warning: failed to save wallet: %s\n", err.c_str());
        }

        // Serialize
        std::vector<sost::Byte> raw;
        std::string ser_err;
        if (!tx.Serialize(raw, &ser_err)) {
            fprintf(stderr, "Error serializing: %s\n", ser_err.c_str());
            return 1;
        }
        std::string raw_hex = to_hex(raw.data(), raw.size());

        sost::Hash256 txid;
        tx.ComputeTxId(txid);
        printf("TX created: %s\n", to_hex(txid.data(), 32).c_str());
        printf("  To:     %s\n", to_addr.c_str());
        printf("  Amount: %s SOST\n", format_sost(amount).c_str());
        printf("  Fee:    %s SOST\n", format_sost(fee).c_str());
        printf("  Size:   %zu bytes\n", raw.size());

        // Send to node via HTTP RPC
        printf("Sending to node %s...\n", node_addr.c_str());

        std::string host = "127.0.0.1";
        int port = 18232;
        auto colon = node_addr.find(':');
        if (colon != std::string::npos) {
            host = node_addr.substr(0, colon);
            port = atoi(node_addr.substr(colon + 1).c_str());
        }

        // JSON-RPC: sendrawtransaction
        std::string rpc_body = "{\"method\":\"sendrawtransaction\",\"params\":[\""
            + raw_hex + "\"],\"id\":1}";

        int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) { perror("socket"); return 1; }
        struct sockaddr_in saddr{};
        saddr.sin_family = AF_INET;
        saddr.sin_port = htons(port);
        struct hostent* he = gethostbyname(host.c_str());
        if (!he) { fprintf(stderr, "Cannot resolve %s\n", host.c_str()); close(fd); return 1; }
        memcpy(&saddr.sin_addr, he->h_addr_list[0], he->h_length);
        if (connect(fd, (struct sockaddr*)&saddr, sizeof(saddr)) < 0) {
            fprintf(stderr, "Cannot connect to %s:%d\n", host.c_str(), port);
            close(fd); return 1;
        }
        std::string http_req = "POST / HTTP/1.1\r\nHost: " + host
            + "\r\nContent-Type: application/json\r\nContent-Length: "
            + std::to_string(rpc_body.size()) + "\r\n\r\n" + rpc_body;
        write(fd, http_req.c_str(), http_req.size());

        char rbuf[4096]{};
        read(fd, rbuf, sizeof(rbuf) - 1);
        close(fd);

        std::string resp(rbuf);
        if (resp.find("\"result\":\"") != std::string::npos) {
            printf("\nTX accepted by node! Txid: %s\n", to_hex(txid.data(), 32).c_str());
            printf("  Waiting for next mined block to confirm...\n");
        } else {
            // Extract error message
            auto err_pos = resp.find("\"message\":\"");
            if (err_pos != std::string::npos) {
                auto err_end = resp.find('"', err_pos + 11);
                std::string err_msg = resp.substr(err_pos + 11, err_end - err_pos - 11);
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
    // info
    // =====================================================================
    if (cmd == "info") {
        printf("SOST Wallet\n");
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
