// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
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
#include "sost/hd_wallet.h"
#include "sost/addressbook.h"
#include "sost/wallet_policy.h"
#include "sost/types.h"
#include "sost/params.h"
#include "sost/address.h"
#include "sost/tx_signer.h"
#include "sost/capsule.h"
#include "sost/crypto.h"          // sha256(file bytes) for --capsule-file

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

// Fee policy. MIN_FEE_STOCKS is a flat dust floor (total fee cannot be
// lower than this even for tiny txs); FEE_RATE_DEFAULT is the per-byte
// rate used for normal tx sizing. Consensus S8 requires ≥1 stock/byte,
// so FEE_RATE_DEFAULT=1 is already valid. The 100-stock flat floor is
// a dust-protection safety margin, not a per-byte multiplier.
static const int64_t MIN_FEE_STOCKS   = 100;    // flat floor: 0.000001 SOST
static const int64_t FEE_RATE_DEFAULT  = 1;     // 1 stock/byte (consensus min S8)

// RPC auth credentials (empty = no auth header sent)
static std::string g_rpc_user = "";
static std::string g_rpc_pass = "";

// v1.3: global node address and fee rate
static std::string g_node_host = "127.0.0.1";
static int         g_node_port = 18232;
static int64_t     g_fee_rate  = FEE_RATE_DEFAULT;
static bool        g_yes_flag  = false;  // --yes skips confirmation prompts
static bool        g_skip_warning = false;  // --skip-warning for cooldown
static std::string g_send_to = "";         // --to ADDRESS
static std::string g_send_amount = "";     // --amount AMOUNT
static std::string g_sost_dir;     // ~/.sost directory
static std::string g_addressbook_path;
static std::string g_policy_path;

// V13 capsule wiring (B2). Public-mode capsule attachment for the `send`
// command. Sealed-* modes are intentionally not wired here yet — they
// require ECIES which has its own commit. Public modes accepted:
//   none, open-note, doc-ref, structured, cert
static std::string g_capsule_mode     = "none";  // --capsule-mode
static std::string g_capsule_text     = "";       // --capsule-text   (mode-dependent)
static std::string g_capsule_template = "";       // --capsule-template id name (structured only)
static std::string g_capsule_locator  = "";       // --capsule-locator (doc-ref only)
static std::string g_capsule_file     = "";       // --capsule-file <path> (doc-ref: hashed)

// Multi-key wallets: explicit source-account selection. When unset, send /
// createtx use Wallet::default_address() (pre-existing behaviour). Mutually
// exclusive — both set is an error.
static std::string g_from_label   = "";  // --from-label <label>
static std::string g_from_address = "";  // --from-address <sost1...>

static void init_sost_dir() {
    const char* home = getenv("HOME");
    if (!home) home = "/tmp";
    g_sost_dir = std::string(home) + "/.sost";
    g_addressbook_path = g_sost_dir + "/trusted_addresses.json";
    g_policy_path = g_sost_dir + "/wallet_policy.json";
}

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
    if (s.empty() || (s[0] != '-' && !isdigit(s[0]) && s[0] != '.')) {
        fprintf(stderr, "Error: invalid amount '%s' — must be a number (e.g. 10 or 1.5)\n", str);
        exit(1);
    }
    try {
        auto dot = s.find('.');
        if (dot == std::string::npos) {
            return std::stoll(s) * STOCKS_PER_SOST;
        }
        std::string whole_str = s.substr(0, dot);
        std::string frac_str = s.substr(dot + 1);
        while (frac_str.size() < 8) frac_str += '0';
        frac_str = frac_str.substr(0, 8);

        int64_t whole = whole_str.empty() ? 0 : std::stoll(whole_str);
        int64_t frac = std::stoll(frac_str);
        return whole * STOCKS_PER_SOST + frac;
    } catch (const std::exception& e) {
        fprintf(stderr, "Error: cannot parse amount '%s' — %s\n", str, e.what());
        exit(1);
    }
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

    // Read full response
    std::string resp;
    char buf[8192];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf) - 1)) > 0) {
        buf[n] = 0;
        resp += buf;
        // Check if we have complete HTTP response with JSON body
        auto hdr_end = resp.find("\r\n\r\n");
        if (hdr_end != std::string::npos) {
            // Check Content-Length if present
            auto cl_pos = resp.find("Content-Length: ");
            if (cl_pos != std::string::npos && cl_pos < hdr_end) {
                int64_t cl = std::stoll(resp.substr(cl_pos + 16));
                int64_t body_received = (int64_t)(resp.size() - hdr_end - 4);
                if (body_received >= cl) break;
            } else if (resp.size() > hdr_end + 4 && resp.back() == '}') {
                break;
            }
        }
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
// resolve_source_address — pick the source key for spending
//
// Reads the global g_from_label / g_from_address flags and resolves them
// against the loaded wallet. Returns true and fills (out_addr, out_pkh)
// when a valid source can be determined; false (with an error printed
// to stderr) when the flags conflict, point at an unknown label, or
// reference an address the wallet does not control.
//
// When both flags are empty, falls back to wallet.default_address() —
// preserves the pre-V13 behaviour for callers that have not opted in.
//
// Multi-key wallets (more than one key, no flag set) are accepted as
// "use the default" because that is the historical contract; a one-line
// notice points users at --from-label / --from-address.
// =============================================================================
static bool resolve_source_address(const sost::Wallet& w,
                                   std::string& out_addr,
                                   sost::PubKeyHash& out_pkh) {
    if (!g_from_label.empty() && !g_from_address.empty()) {
        fprintf(stderr,
            "Error: --from-label and --from-address are mutually exclusive. "
            "Pick one and retry.\n");
        return false;
    }

    if (!g_from_label.empty()) {
        const sost::WalletKey* k = w.find_key_by_label(g_from_label);
        if (!k) {
            fprintf(stderr,
                "Error: --from-label %s not found in this wallet.\n",
                g_from_label.c_str());
            fprintf(stderr, "Available keys:\n");
            for (const auto& kk : w.keys()) {
                fprintf(stderr, "  label=%-16s  address=%s\n",
                        kk.label.empty() ? "(none)" : kk.label.c_str(),
                        sost::address_encode(kk.pkh).c_str());
            }
            return false;
        }
        out_addr = sost::address_encode(k->pkh);
        out_pkh  = k->pkh;
        return true;
    }

    if (!g_from_address.empty()) {
        sost::PubKeyHash pkh{};
        if (!sost::address_decode(g_from_address, pkh)) {
            fprintf(stderr, "Error: --from-address %s is not a valid SOST address.\n",
                    g_from_address.c_str());
            return false;
        }
        if (!w.find_key_by_pkh(pkh)) {
            fprintf(stderr,
                "Error: --from-address %s is not in this wallet.\n",
                g_from_address.c_str());
            fprintf(stderr, "Available keys:\n");
            for (const auto& kk : w.keys()) {
                fprintf(stderr, "  label=%-16s  address=%s\n",
                        kk.label.empty() ? "(none)" : kk.label.c_str(),
                        sost::address_encode(kk.pkh).c_str());
            }
            return false;
        }
        out_addr = g_from_address;
        out_pkh  = pkh;
        return true;
    }

    // Neither flag set — historic default.
    out_addr = w.default_address();
    if (out_addr.empty()) {
        fprintf(stderr, "Error: wallet has no addresses.\n");
        return false;
    }
    if (!sost::address_decode(out_addr, out_pkh)) {
        fprintf(stderr, "Error: failed to decode default address %s\n",
                out_addr.c_str());
        return false;
    }
    if (w.keys().size() > 1) {
        fprintf(stderr,
            "Notice: wallet has %zu keys; using default %s. "
            "Use --from-label or --from-address to pick a different source.\n",
            w.keys().size(), out_addr.c_str());
    }
    return true;
}

// =============================================================================
// v1.4: Fetch UTXOs from node for any address the wallet controls
//       Uses getaddressutxos RPC to get UTXOs directly from the chain
//
// When `addr_override` is non-empty, query that address instead of the
// wallet's default. Used by --from-label / --from-address so multi-key
// wallets can spend from a non-default account.
// =============================================================================
static int sync_wallet_utxos_from_node(sost::Wallet& w,
                                       const std::string& addr_override = "") {
    std::string addr = !addr_override.empty() ? addr_override : w.default_address();
    printf("[DEBUG] Wallet source address: %s\n", addr.empty() ? "(empty)" : addr.c_str());
    if (addr.empty()) {
        fprintf(stderr, "Warning: wallet has no addresses\n");
        return 0;
    }

    int total_imported = 0;
    {   // Fetch UTXOs for wallet's default address
        printf("[DEBUG] Querying node for UTXOs of %s...\n", addr.c_str());
        std::string resp = rpc_call("getaddressutxos", "[\"" + addr + "\"]");
        printf("[DEBUG] RPC response length: %zu bytes\n", resp.size());
        if (resp.empty()) { printf("[DEBUG] Empty response — RPC failed\n"); return 0; }

        // Extract JSON body from HTTP response, then find "result" array
        auto body_start = resp.find("\r\n\r\n");
        std::string json_body = (body_start != std::string::npos) ? resp.substr(body_start + 4) : resp;

        // Look for "result":[ in the JSON-RPC response
        auto result_pos = json_body.find("\"result\":");
        if (result_pos != std::string::npos) {
            json_body = json_body.substr(result_pos + 9);  // Skip past "result":
        }

        auto arr_start = json_body.find('[');
        auto arr_end = json_body.rfind(']');
        if (arr_start == std::string::npos || arr_end == std::string::npos) {
            printf("[DEBUG] No JSON array found. Body: %.300s\n", json_body.c_str());
            return 0;
        }
        // Use json_body instead of resp for parsing
        std::string arr = json_body.substr(arr_start, arr_end - arr_start + 1);
        printf("[DEBUG] Parsed UTXO array: %zu chars\n", arr.size());

        // Simple JSON array parsing — find each {...} object
        size_t pos = 0;
        while (pos < arr.size()) {
            auto obj_start = arr.find('{', pos);
            if (obj_start == std::string::npos) break;
            auto obj_end = arr.find('}', obj_start);
            if (obj_end == std::string::npos) break;
            std::string obj = arr.substr(obj_start, obj_end - obj_start + 1);

            // Extract fields
            auto get_str = [&](const std::string& key) -> std::string {
                auto p = obj.find("\"" + key + "\":\"");
                if (p == std::string::npos) return "";
                p += key.size() + 4;
                auto e = obj.find('"', p);
                return e != std::string::npos ? obj.substr(p, e - p) : "";
            };
            auto get_int = [&](const std::string& key) -> int64_t {
                auto p = obj.find("\"" + key + "\":");
                if (p == std::string::npos) return 0;
                p += key.size() + 3;
                try { return std::stoll(obj.substr(p)); } catch (...) { return 0; }
            };
            auto get_bool = [&](const std::string& key) -> bool {
                auto p = obj.find("\"" + key + "\":");
                if (p == std::string::npos) return false;
                return obj.substr(p + key.size() + 3, 4) == "true";
            };

            std::string txid_hex = get_str("txid");
            int64_t vout = get_int("vout");
            int64_t amount_stocks = get_int("amount_stocks");
            int64_t height = get_int("height");
            int64_t output_type = get_int("output_type");
            bool is_coinbase = get_bool("coinbase");
            bool spendable = get_bool("spendable");

            if (!txid_hex.empty() && amount_stocks > 0 && spendable) {
                sost::WalletUTXO utxo{};
                utxo.txid = sost::from_hex(txid_hex);
                utxo.vout = (uint32_t)vout;
                utxo.amount = amount_stocks;
                utxo.height = height;
                utxo.spent = false;
                // Determine output type: use explicit field if present, else infer from coinbase flag + vout
                if (output_type > 0) {
                    utxo.output_type = (uint8_t)output_type;
                } else if (is_coinbase) {
                    // Coinbase outputs: vout=0 → miner (0x01), vout=1 → gold (0x02), vout=2 → popc (0x03)
                    if (vout == 0) utxo.output_type = 0x01;       // OUT_COINBASE_MINER
                    else if (vout == 1) utxo.output_type = 0x02;  // OUT_COINBASE_GOLD
                    else if (vout == 2) utxo.output_type = 0x03;  // OUT_COINBASE_POPC
                    else utxo.output_type = 0x01;                 // fallback
                } else {
                    utxo.output_type = 0x00;  // TRANSFER
                }
                // Decode address to pubkey hash
                sost::address_decode(addr, utxo.pkh);
                w.add_utxo(utxo);
                total_imported++;
                printf("[DEBUG] Imported UTXO: %lld stocks, type=0x%02x (coinbase=%d, vout=%d, parsed_type=%lld) height=%lld\n",
                       (long long)utxo.amount, utxo.output_type, is_coinbase, (int)vout, (long long)output_type, (long long)utxo.height);
                // TEMP REMOVE NEXT LINE AFTER FIX:
                printf("[DEBUG-OLD] Imported UTXO: %lld stocks (%.8f SOST) height=%lld\n",
                       (long long)utxo.amount,
                       (double)utxo.amount / 100000000.0,
                       (long long)utxo.height);
            }

            pos = obj_end + 1;
        }
    }
    printf("[DEBUG] Total UTXOs imported from node: %d\n", total_imported);
    return total_imported;
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
// =============================================================================
// V13 capsule helpers (B2)
// =============================================================================
// Build the SCPv1 payload bytes for the requested public mode.
// Returns true on success and fills `out`. On any error returns false and
// writes a human-readable message to stderr.
//
// Mode interpretation:
//   none           → out left empty; caller treats as "no capsule".
//   open-note      → --capsule-text becomes the body. Max 80 chars.
//   doc-ref        → --capsule-file is hashed (SHA-256) for file_hash.
//                    --capsule-locator (optional) becomes the locator,
//                    treated as IPFS_CID if it starts with "ipfs://" or
//                    "Qm"/"baf", otherwise HTTPS_URL.
//   structured     → --capsule-text becomes the fields blob (max 128 B).
//                    --capsule-template selects the template_id by name,
//                    default = custom_kv_v1.
//   cert           → --capsule-text becomes short_note (max 64 B).
//                    Default cert_kind=1, instr_kind=1.
//   sealed-*       → returns false with clear "not yet wired" error.

static uint8_t parse_template_id_or_default(const std::string& name) {
    if (name.empty() || name == "custom_kv" || name == "custom_kv_v1")
        return (uint8_t)sost::TemplateId::CUSTOM_KV_V1;
    if (name == "invoice" || name == "invoice_v1")
        return (uint8_t)sost::TemplateId::INVOICE_V1;
    if (name == "payment_receipt" || name == "payment_receipt_v1")
        return (uint8_t)sost::TemplateId::PAYMENT_RECEIPT_V1;
    if (name == "transfer_instruction" || name == "transfer_instruction_v1")
        return (uint8_t)sost::TemplateId::TRANSFER_INSTRUCTION_V1;
    if (name == "compliance_record" || name == "compliance_record_v1")
        return (uint8_t)sost::TemplateId::COMPLIANCE_RECORD_V1;
    if (name == "warranty_record" || name == "warranty_record_v1")
        return (uint8_t)sost::TemplateId::WARRANTY_RECORD_V1;
    if (name == "shipment_record" || name == "shipment_record_v1")
        return (uint8_t)sost::TemplateId::SHIPMENT_RECORD_V1;
    if (name == "gold_cert_note" || name == "gold_cert_note_v1")
        return (uint8_t)sost::TemplateId::GOLD_CERT_NOTE_V1;
    if (name == "contract_ref" || name == "contract_ref_v1")
        return (uint8_t)sost::TemplateId::CONTRACT_REF_V1;
    if (name == "escrow_note" || name == "escrow_note_v1")
        return (uint8_t)sost::TemplateId::ESCROW_NOTE_V1;
    return 0;  // 0 = unknown; caller will reject
}

static bool read_file_into_vec(const std::string& path,
                                std::vector<sost::Byte>& out,
                                std::string* err) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) {
        if (err) *err = "cannot open --capsule-file '" + path + "'";
        return false;
    }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    if (sz < 0) { fclose(f); if (err) *err = "stat failed on " + path; return false; }
    fseek(f, 0, SEEK_SET);
    out.resize((size_t)sz);
    size_t got = sz > 0 ? fread(out.data(), 1, (size_t)sz, f) : 0;
    fclose(f);
    if ((long)got != sz) {
        if (err) *err = "short read on " + path;
        return false;
    }
    return true;
}

// Detect locator kind from the user-supplied string.
static sost::LocatorType detect_locator_type(const std::string& s) {
    if (s.empty()) return sost::LocatorType::NONE;
    if (s.rfind("ipfs://", 0) == 0)               return sost::LocatorType::IPFS_CID;
    if (s.rfind("Qm", 0) == 0)                    return sost::LocatorType::IPFS_CID;
    if (s.rfind("baf", 0) == 0)                   return sost::LocatorType::IPFS_CID;
    if (s.rfind("https://", 0) == 0)              return sost::LocatorType::HTTPS_URL;
    if (s.rfind("http://",  0) == 0)              return sost::LocatorType::HTTPS_URL;
    return sost::LocatorType::OPAQUE_ID;
}

static bool build_capsule_for_mode(std::vector<sost::Byte>& out_payload) {
    out_payload.clear();
    if (g_capsule_mode.empty() || g_capsule_mode == "none") {
        return true;  // no payload
    }

    // Sealed modes: explicit not-wired error so the user does not waste
    // a fee constructing a tx that the node would reject.
    if (g_capsule_mode == "sealed-note"
     || g_capsule_mode == "sealed-doc-ref"
     || g_capsule_mode == "sealed-structured") {
        fprintf(stderr,
            "ERROR: --capsule-mode '%s' is not wired in this build yet "
            "(ECIES envelope is shipped in a separate commit).\n"
            "Use a public mode for now: open-note, doc-ref, structured, cert.\n",
            g_capsule_mode.c_str());
        return false;
    }

    std::string err;
    if (g_capsule_mode == "open-note") {
        if (g_capsule_text.empty()) {
            fprintf(stderr, "ERROR: --capsule-mode open-note requires --capsule-text\n");
            return false;
        }
        if (!sost::BuildOpenNotePayload(g_capsule_text, out_payload, &err)) {
            fprintf(stderr, "ERROR: build open-note: %s\n", err.c_str());
            return false;
        }
        return true;
    }

    if (g_capsule_mode == "doc-ref") {
        if (g_capsule_file.empty()) {
            fprintf(stderr, "ERROR: --capsule-mode doc-ref requires --capsule-file <path>\n");
            return false;
        }
        std::vector<sost::Byte> file_bytes;
        if (!read_file_into_vec(g_capsule_file, file_bytes, &err)) {
            fprintf(stderr, "ERROR: %s\n", err.c_str()); return false;
        }
        sost::DocRefParams p{};
        p.capsule_id      = 0;
        p.file_size_bytes = (uint32_t)file_bytes.size();
        p.file_hash       = sost::sha256(file_bytes);
        // manifest_hash left zero (not used in this MVP)
        p.locator_type = detect_locator_type(g_capsule_locator);
        p.locator_ref.assign(g_capsule_locator.begin(), g_capsule_locator.end());
        if (!sost::BuildDocRefOpenPayload(p, out_payload, &err)) {
            fprintf(stderr, "ERROR: build doc-ref: %s\n", err.c_str());
            return false;
        }
        return true;
    }

    if (g_capsule_mode == "structured") {
        if (g_capsule_text.empty()) {
            fprintf(stderr, "ERROR: --capsule-mode structured requires --capsule-text\n");
            return false;
        }
        sost::TemplateFieldsParams p{};
        p.capsule_id  = 0;
        p.template_id = parse_template_id_or_default(g_capsule_template);
        if (p.template_id == 0) {
            fprintf(stderr,
                "ERROR: unknown --capsule-template '%s'.\n"
                "  Known: custom_kv_v1, invoice_v1, payment_receipt_v1,\n"
                "         transfer_instruction_v1, compliance_record_v1,\n"
                "         warranty_record_v1, shipment_record_v1,\n"
                "         gold_cert_note_v1, contract_ref_v1, escrow_note_v1\n",
                g_capsule_template.c_str());
            return false;
        }
        p.field_codec = 0x00;  // ASCII
        p.fields.assign(g_capsule_text.begin(), g_capsule_text.end());
        if (!sost::BuildTemplateFieldsOpenPayload(p, out_payload, &err)) {
            fprintf(stderr, "ERROR: build structured: %s\n", err.c_str());
            return false;
        }
        return true;
    }

    if (g_capsule_mode == "cert") {
        sost::CertInstructionParams p{};
        p.cert_kind  = 0x01;     // generic; advanced overrides could come later
        p.instr_kind = 0x01;
        p.cert_id    = 0;
        p.ref_value  = 0;
        p.expires_at = 0;
        p.short_note = g_capsule_text;  // may be empty (validator allows note_len=0)
        if (!sost::BuildCertInstructionPayload(p, out_payload, &err)) {
            fprintf(stderr, "ERROR: build cert: %s\n", err.c_str());
            return false;
        }
        return true;
    }

    fprintf(stderr, "ERROR: unknown --capsule-mode '%s'.\n"
        "  Known: none, open-note, doc-ref, structured, cert\n"
        "  (sealed-note, sealed-doc-ref, sealed-structured: not yet wired)\n",
        g_capsule_mode.c_str());
    return false;
}

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
    printf("\nHD Wallet (BIP39):\n");
    printf("  hd create              Generate 12-word seed phrase + wallet\n");
    printf("  hd restore             Import 12-word seed phrase\n");
    printf("\nAddress Book:\n");
    printf("  addressbook add <addr> --label <name> --trust <level>\n");
    printf("  addressbook list       List all trusted addresses\n");
    printf("  addressbook remove <addr>  Remove address from book\n");
    printf("  addressbook check <addr>   Check trust level\n");
    printf("\nWallet Policy:\n");
    printf("  policy show            Show current wallet policy\n");
    printf("  policy set <key> <val> Set policy value\n");
    printf("\nOptions:\n");
    printf("  --wallet <path>        Wallet file (default: wallet.json)\n");
    printf("  --rpc-user <user>      RPC Basic Auth username\n");
    printf("  --rpc-pass <pass>      RPC Basic Auth password\n");
    printf("  --node <host:port>     Node address (default: 127.0.0.1:18232)\n");
    printf("  --fee-rate <n>         Fee rate in stocks/byte (default: 1)\n");
    printf("  --from-label <label>   Spend from the wallet key with this label\n");
    printf("  --from-address <addr>  Spend from this exact address (must be in wallet)\n");
    printf("                         (--from-label and --from-address are mutually exclusive;\n");
    printf("                          omit both to use the wallet's default key)\n");
    printf("  --yes, -y              Skip confirmation prompts\n");
    printf("  --skip-warning         Skip first-send warning for scripts\n");
    printf("\nCapsule attach (V12+ chain only — public modes wired):\n");
    printf("  --capsule-mode <mode>  none | open-note | doc-ref | structured | cert\n");
    printf("                         (sealed-note / sealed-doc-ref / sealed-structured\n");
    printf("                          return a clear 'not yet wired' error)\n");
    printf("  --capsule-text <text>  text body (open-note: <=80; structured: <=128;\n");
    printf("                                    cert: <=64; ignored for doc-ref)\n");
    printf("  --capsule-template <id>  structured: template name. Default custom_kv_v1.\n");
    printf("                           Known: custom_kv_v1, invoice_v1, payment_receipt_v1,\n");
    printf("                           transfer_instruction_v1, compliance_record_v1,\n");
    printf("                           warranty_record_v1, shipment_record_v1,\n");
    printf("                           gold_cert_note_v1, contract_ref_v1, escrow_note_v1\n");
    printf("  --capsule-locator <s>  doc-ref: optional URL or IPFS reference\n");
    printf("  --capsule-file <path>  doc-ref: file whose SHA-256 becomes file_hash\n");
    printf("\nFee calculation (v1.3 — automatic):\n");
    printf("  Fee = tx_size_bytes x fee_rate stocks/byte\n");
    printf("  Minimum: %s SOST (%lld stocks)\n",
           format_sost(MIN_FEE_STOCKS).c_str(), (long long)MIN_FEE_STOCKS);
    printf("  Consensus rule S8: fee >= tx_size x 1 stock/byte\n");
    printf("\nExamples:\n");
    printf("  sost-cli send sost1abc... 10              (auto fee, 1 stock/byte)\n");
    printf("  sost-cli --fee-rate 2 send sost1abc... 10 (priority: 2 stocks/byte)\n");
    printf("  sost-cli send sost1abc... 10 --capsule-mode open-note --capsule-text 'donation'\n");
    printf("  sost-cli send sost1abc... 10 --capsule-mode structured \\\n");
    printf("    --capsule-template payment_receipt_v1 \\\n");
    printf("    --capsule-text 'category=APP rewards distribution; ref=batch-001; period=2026-05'\n");
}

int main(int argc, char** argv) {
    init_sost_dir();
    std::string wallet_path = DEFAULT_WALLET;

    // Parse global options — order-agnostic.
    //
    // Earlier versions of this parser only accepted global flags before the
    // subcommand and dropped silently anything that came after, e.g.
    //
    //   sost-cli send sost1... 0.01 --capsule-mode structured ...
    //                                ^^^^^^^^^^^^^^ ignored
    //
    // The TX would then go out without the capsule, with no warning. We now
    // walk the entire argv once: known global flags are consumed wherever
    // they appear; everything else (subcommand + its positional args + any
    // unknown flag the subcommand handles itself) is gathered into a
    // compacted argv that the rest of main() reads as before.
    std::vector<char*> positional;
    positional.push_back(argv[0]);   // keep program name in slot 0
    for (int i = 1; i < argc; /* manual */) {
        std::string flag = argv[i];
        bool needs_value = false;
        // Single-arg switches first.
        if (flag == "--yes" || flag == "-y") {
            g_yes_flag = true; i += 1; continue;
        } else if (flag == "--skip-warning") {
            g_skip_warning = true; i += 1; continue;
        } else if (flag == "--help" || flag == "-h") {
            print_usage(); return 0;
        }
        // Two-arg flags: value follows on the next argv slot.
        needs_value = (flag == "--wallet" || flag == "--from"
                    || flag == "--rpc-user" || flag == "--rpc-pass"
                    || flag == "--node" || flag == "--rpc"
                    || flag == "--fee-rate"
                    || flag == "--to" || flag == "--amount"
                    || flag == "--from-label" || flag == "--from-address"
                    || flag == "--capsule-mode" || flag == "--capsule-text"
                    || flag == "--capsule-template" || flag == "--capsule-locator"
                    || flag == "--capsule-file");
        if (needs_value) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: %s expects a value\n", flag.c_str());
                return 1;
            }
            std::string val = argv[i + 1];
            if (flag == "--wallet" || flag == "--from")          wallet_path = val;
            else if (flag == "--rpc-user")                       g_rpc_user = val;
            else if (flag == "--rpc-pass")                       g_rpc_pass = val;
            else if (flag == "--node" || flag == "--rpc") {
                auto colon = val.find(':');
                if (colon != std::string::npos) {
                    g_node_host = val.substr(0, colon);
                    g_node_port = atoi(val.substr(colon + 1).c_str());
                } else {
                    g_node_host = val;
                }
            }
            else if (flag == "--fee-rate") {
                try { g_fee_rate = std::stoll(val); }
                catch (const std::exception&) {
                    fprintf(stderr, "Error: --fee-rate must be a number, got: %s\n",
                            val.c_str());
                    return 1;
                }
                if (g_fee_rate < 1) {
                    fprintf(stderr, "Error: --fee-rate must be >= 1 (consensus minimum)\n");
                    return 1;
                }
            }
            else if (flag == "--to")                g_send_to = val;
            else if (flag == "--amount")            g_send_amount = val;
            else if (flag == "--from-label")        g_from_label = val;
            else if (flag == "--from-address")      g_from_address = val;
            else if (flag == "--capsule-mode")      g_capsule_mode = val;
            else if (flag == "--capsule-text")      g_capsule_text = val;
            else if (flag == "--capsule-template")  g_capsule_template = val;
            else if (flag == "--capsule-locator")   g_capsule_locator = val;
            else if (flag == "--capsule-file")      g_capsule_file = val;
            i += 2;
            continue;
        }
        // Unknown flag or positional — keep for subcommand dispatch.
        positional.push_back(argv[i]);
        i += 1;
    }

    // Re-point argv/argc at the compacted positional view so the rest of
    // main() — which indexes argv[arg_start + N] — reads only the
    // subcommand and its remaining args.
    argv = positional.data();
    argc = (int)positional.size();
    int arg_start = 1;

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
    //
    // No address  → wallet-local balance (sum of imported UTXOs minus locks).
    // With address → chain-truth balance via node RPC getaddressutxos.
    //               Previously called w.balance(addr), which only saw
    //               UTXOs the wallet had imported. For any address the
    //               wallet had not pre-tracked (e.g. a public lookup of a
    //               foreign address) it returned 0 even when the chain
    //               had thousands of UTXOs. Now sums getaddressutxos
    //               directly so the printed number matches the explorer.
    // =====================================================================
    if (cmd == "getbalance") {
        int64_t chain_height = query_chain_height();
        if (argc > arg_start + 1) {
            std::string addr = argv[arg_start + 1];

            std::string resp = rpc_call("getaddressutxos", "[\"" + addr + "\"]");
            if (resp.empty()) {
                fprintf(stderr, "Error: cannot reach node at %s:%d (RPC call failed)\n",
                        g_node_host.c_str(), g_node_port);
                fprintf(stderr, "  Falling back to wallet-local balance.\n");
                printf("%s SOST\n", format_sost(w.balance(addr)).c_str());
                return 1;
            }

            // Strip HTTP headers and locate the result array.
            auto body_start = resp.find("\r\n\r\n");
            std::string json_body = (body_start != std::string::npos)
                                      ? resp.substr(body_start + 4) : resp;
            auto result_pos = json_body.find("\"result\":");
            if (result_pos != std::string::npos) {
                json_body = json_body.substr(result_pos + 9);
            }
            auto arr_start = json_body.find('[');
            auto arr_end   = json_body.rfind(']');

            int64_t total_stocks    = 0;
            int64_t spendable_stocks = 0;
            int64_t mature_stocks   = 0;
            int64_t immature_stocks = 0;
            int     utxo_count      = 0;
            int     mature_count    = 0;
            int     immature_count  = 0;

            if (arr_start != std::string::npos && arr_end != std::string::npos
                && arr_end > arr_start) {
                std::string arr = json_body.substr(arr_start, arr_end - arr_start + 1);
                size_t pos = 0;
                while (pos < arr.size()) {
                    auto obj_start = arr.find('{', pos);
                    if (obj_start == std::string::npos) break;
                    auto obj_end = arr.find('}', obj_start);
                    if (obj_end == std::string::npos) break;
                    std::string obj = arr.substr(obj_start, obj_end - obj_start + 1);
                    pos = obj_end + 1;

                    auto get_int = [&](const std::string& key) -> int64_t {
                        auto p = obj.find("\"" + key + "\":");
                        if (p == std::string::npos) return 0;
                        p += key.size() + 3;
                        try { return std::stoll(obj.substr(p)); } catch (...) { return 0; }
                    };
                    auto get_bool = [&](const std::string& key) -> bool {
                        auto p = obj.find("\"" + key + "\":");
                        if (p == std::string::npos) return false;
                        return obj.substr(p + key.size() + 3, 4) == "true";
                    };

                    int64_t amt    = get_int("amount_stocks");
                    bool spendable = get_bool("spendable");
                    bool mature    = get_bool("mature");
                    if (amt <= 0) continue;

                    total_stocks += amt;
                    utxo_count++;
                    if (spendable) spendable_stocks += amt;
                    if (mature)   { mature_stocks   += amt; mature_count++; }
                    else          { immature_stocks += amt; immature_count++; }
                }
            }

            // Backward-compatible: first line is the simple SOST total so
            // any script grepping for it still works.
            printf("%s SOST\n", format_sost(total_stocks).c_str());
            printf("Total:     %s SOST  (%d UTXO%s)\n",
                   format_sost(total_stocks).c_str(),
                   utxo_count, utxo_count == 1 ? "" : "s");
            printf("Spendable: %s SOST  (%d mature)\n",
                   format_sost(mature_stocks).c_str(), mature_count);
            if (immature_stocks > 0) {
                printf("Immature:  %s SOST  (%d UTXO%s, need 1000 confirmations)\n",
                       format_sost(immature_stocks).c_str(),
                       immature_count, immature_count == 1 ? "" : "s");
            }
            return 0;
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

        // v1.4: Sync UTXOs from node before building transaction
        //       This ensures we have ALL spendable UTXOs, not just imported ones
        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Error: cannot connect to node at %s:%d\n",
                    g_node_host.c_str(), g_node_port);
            fprintf(stderr, "  Node must be running to send transactions.\n");
            return 1;
        }
        printf("Chain height: %lld\n", (long long)chain_height);

        // Resolve source account: --from-label / --from-address override the
        // wallet's default key. On multi-key wallets without either flag we
        // emit a notice but keep the historical default behaviour.
        std::string src_addr;
        sost::PubKeyHash src_pkh{};
        if (!resolve_source_address(w, src_addr, src_pkh)) return 1;
        const sost::PubKeyHash* from_pkh =
            (!g_from_label.empty() || !g_from_address.empty()) ? &src_pkh : nullptr;

        // Clear stale UTXOs (wallet file may have wrong output_type from old sessions)
        w.clear_utxos();
        // Sync fresh UTXOs from chain for the resolved source address.
        int synced = sync_wallet_utxos_from_node(w, src_addr);
        if (synced > 0) {
            printf("Synced %d UTXOs from node for %s\n", synced, src_addr.c_str());
        } else if (w.num_utxos() == 0) {
            fprintf(stderr, "Error: no spendable UTXOs found for %s\n", src_addr.c_str());
            fprintf(stderr, "  Check that the address has received funds and they are mature.\n");
            return 1;
        }

        sost::Hash256 genesis_hash = sost::from_hex(
            "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");

        // --- Pass 1: build with estimated fee to measure real size ---
        // mark_spent=false on every fee pass: each call to create_transaction
        // would otherwise mark its inputs spent before the next pass runs,
        // which on a wallet with one large UTXO causes pass 2 to fail with
        // "insufficient funds." We mark the final tx's inputs spent once,
        // after the last pass settles below.
        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction(to_addr, amount, est_fee, genesis_hash,
                                  tx, chain_height, &err,
                                  /*capsule_payload=*/nullptr,
                                  /*mark_spent=*/false,
                                  from_pkh)) {
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
                                      tx2, chain_height, &err,
                                      /*capsule_payload=*/nullptr,
                                      /*mark_spent=*/false,
                                      from_pkh)) {
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
                                          tx3, chain_height, &err,
                                          /*capsule_payload=*/nullptr,
                                          /*mark_spent=*/false,
                                          from_pkh)) {
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

        // Now that the final fee is settled, mark the chosen inputs spent
        // (preserves the previous createtx behaviour: caller sees the raw
        // hex and the wallet won't reuse those UTXOs in the next session).
        w.mark_tx_inputs_spent(tx);
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
        // Support both positional and flag-based syntax:
        //   sost-cli send ADDRESS AMOUNT
        //   sost-cli --to ADDRESS --amount AMOUNT send
        std::string to_addr = g_send_to;
        std::string amount_str = g_send_amount;

        // Positional args override flags
        if (argc >= arg_start + 2 && argv[arg_start + 1][0] != '-') {
            to_addr = argv[arg_start + 1];
        }
        if (argc >= arg_start + 3 && argv[arg_start + 2][0] != '-') {
            amount_str = argv[arg_start + 2];
        }

        if (to_addr.empty() || amount_str.empty()) {
            fprintf(stderr, "Usage: sost-cli send <to_address> <amount_sost>\n");
            fprintf(stderr, "   or: sost-cli --to <address> --amount <sost> send\n");
            fprintf(stderr, "  Fee is automatic: tx_size x %lld stock/byte\n",
                    (long long)g_fee_rate);
            fprintf(stderr, "  Use --fee-rate <n> for priority (default: 1)\n");
            fprintf(stderr, "\nExamples:\n");
            fprintf(stderr, "  sost-cli send sost1abc... 10\n");
            fprintf(stderr, "  sost-cli --to sost1abc... --amount 10 --rpc 127.0.0.1:18232 send\n");
            return 1;
        }
        int64_t amount = parse_amount(amount_str.c_str());

        // V13 capsule attach (B2): build the payload FIRST so bad
        // --capsule-* arguments fail before any network I/O. The chain-
        // height-based V12 activation check still runs below once we have
        // the actual tip; what we do here is just argument validation +
        // payload bytes assembly.
        std::vector<sost::Byte> capsule_payload;
        if (!build_capsule_for_mode(capsule_payload)) {
            return 1;
        }
        if (!capsule_payload.empty()) {
            auto v = sost::ValidateCapsulePolicy(capsule_payload);
            if (!v.ok) {
                fprintf(stderr,
                    "ERROR: capsule failed local policy validation: %s\n"
                    "  (this is what the node mempool would reject too)\n",
                    v.message.c_str());
                return 1;
            }
        }
        const std::vector<sost::Byte>* cap_ptr =
            capsule_payload.empty() ? nullptr : &capsule_payload;

        // v1.4: Sync UTXOs from node + query chain height
        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Error: cannot connect to node at %s:%d\n",
                    g_node_host.c_str(), g_node_port);
            fprintf(stderr, "  Node must be running to send transactions.\n");
            return 1;
        }
        printf("Chain height: %lld\n", (long long)chain_height);

        // Resolve source account: --from-label / --from-address override the
        // default key. Multi-key wallets without either flag get a notice
        // but keep the historical default behaviour.
        std::string src_addr;
        sost::PubKeyHash src_pkh{};
        if (!resolve_source_address(w, src_addr, src_pkh)) return 1;
        const sost::PubKeyHash* from_pkh =
            (!g_from_label.empty() || !g_from_address.empty()) ? &src_pkh : nullptr;

        // Clear stale UTXOs (wallet file may have wrong output_type from old sessions)
        w.clear_utxos();
        // Sync fresh UTXOs from chain for the resolved source address.
        int synced = sync_wallet_utxos_from_node(w, src_addr);
        if (synced > 0) {
            printf("Synced %d UTXOs from node for %s\n", synced, src_addr.c_str());
        } else if (w.num_utxos() == 0) {
            fprintf(stderr, "Error: no spendable UTXOs found for %s\n", src_addr.c_str());
            fprintf(stderr, "  Check that the address has received funds and they are mature.\n");
            return 1;
        }

        // V13 capsule attach (B2): now that we know the chain tip, enforce the
        // V12-activation-height guard. Capsules on OUT_TRANSFER outputs are
        // rejected by the validator (R14_PAYLOAD_FORBIDDEN) before V12_HEIGHT.
        if (cap_ptr) {
            if (chain_height < (int64_t)sost::V12_HEIGHT) {
                fprintf(stderr,
                    "ERROR: capsule attach requires chain height >= V12_HEIGHT "
                    "(%lld); current tip is %lld.\n"
                    "  Wait until the chain crosses V12 or omit --capsule-mode.\n",
                    (long long)sost::V12_HEIGHT, (long long)chain_height);
                return 1;
            }
            printf("Capsule attached: mode=%s, payload=%zu bytes\n",
                   g_capsule_mode.c_str(), capsule_payload.size());
        }

        // Create transaction with dynamic fee
        sost::Hash256 genesis_hash = sost::from_hex(
            "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");

        // --- Pass 1: build with estimated fee to measure real size ---
        // mark_spent=false on every fee pass: each call would otherwise mark
        // its selected UTXOs spent in the wallet before the next pass runs,
        // and on a wallet with one large UTXO pass 2 would then fail with
        // "insufficient funds." We mark the FINAL tx's inputs spent below,
        // only after the node accepts the broadcast — mirroring sendmany.
        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction(to_addr, amount, est_fee, genesis_hash,
                                  tx, chain_height, &err, cap_ptr,
                                  /*mark_spent=*/false,
                                  from_pkh)) {
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
                                      tx2, chain_height, &err, cap_ptr,
                                      /*mark_spent=*/false,
                                      from_pkh)) {
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
                                          tx3, chain_height, &err, cap_ptr,
                                          /*mark_spent=*/false,
                                          from_pkh)) {
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

        // Wallet save + mark-inputs-spent are deferred to the post-broadcast
        // block below. Marking now would leave the local UTXO list out of
        // sync with the chain if the user aborts at the confirm prompt or
        // the node rejects the tx.

        // Display tx info
        std::string raw_hex = to_hex(raw.data(), raw.size());
        sost::Hash256 txid;
        tx.ComputeTxId(txid);

        // --- Address book + policy checks ---
        sost::AddressBook ab;
        ab.Load(g_addressbook_path);
        sost::WalletPolicy pol;
        pol.Load(g_policy_path);

        auto trust = ab.Check(to_addr);
        bool addr_in_book = (trust != sost::TrustLevel::UNKNOWN);

        // BLOCKED check (hard stop)
        if (trust == sost::TrustLevel::BLOCKED) {
            fprintf(stderr, "\nERROR: Address %s is BLOCKED in your address book.\n", to_addr.c_str());
            fprintf(stderr, "Send cancelled.\n");
            return 1;
        }

        // Policy check (hard stop)
        std::string policy_err = pol.CheckSend(amount, addr_in_book);
        if (!policy_err.empty()) {
            fprintf(stderr, "\nPOLICY BLOCK: %s\n", policy_err.c_str());
            fprintf(stderr, "Send cancelled. Use 'sost-cli policy show' to see current limits.\n");
            return 1;
        }

        printf("\n========== TRANSACTION SUMMARY ==========\n");
        printf("  TXID:   %s\n", to_hex(txid.data(), 32).c_str());
        printf("  To:     %s\n", to_addr.c_str());
        if (trust == sost::TrustLevel::TRUSTED) {
            auto* entry = ab.Get(to_addr);
            printf("  Dest:   %s (trusted)\n", entry ? entry->label.c_str() : "");
        } else if (trust == sost::TrustLevel::KNOWN) {
            auto* entry = ab.Get(to_addr);
            printf("  Dest:   %s (known)\n", entry ? entry->label.c_str() : "");
        } else {
            printf("  Dest:   UNKNOWN (not in address book)\n");
        }
        printf("  Amount: %s SOST\n", format_sost(amount).c_str());
        printf("  Fee:    %s SOST (%lld stocks = %zu bytes x %lld rate)\n",
               format_sost(real_fee).c_str(), (long long)real_fee,
               raw.size(), (long long)g_fee_rate);
        printf("  Size:   %zu bytes\n", raw.size());
        printf("=========================================\n");

        // First-time send warning (new-address cooldown)
        if (!addr_in_book && !g_skip_warning && !g_yes_flag) {
            printf("\n  WARNING: Address %s is NOT in your trusted address book.\n", to_addr.c_str());
            printf("  This is the first time you send to this address.\n");
            if (amount > 10 * STOCKS_PER_SOST) {
                printf("\n  HIGH-VALUE FIRST SEND: %s SOST to unknown address.\n",
                       format_sost(amount).c_str());
                printf("  Consider adding this address to your trusted address book first:\n");
                printf("    ./sost-cli addressbook add %s --label \"name\" --trust known\n\n",
                       to_addr.c_str());
            }
        }

        // Pre-send confirmation (safety check)
        if (!g_yes_flag) {
            printf("Confirm send? [yes/no]: ");
            fflush(stdout);
            char confirm[16] = {};
            if (!fgets(confirm, sizeof(confirm), stdin) ||
                (strncmp(confirm, "yes", 3) != 0 && strncmp(confirm, "y", 1) != 0)) {
                printf("Transaction cancelled.\n");
                return 0;
            }
        }

        // Record send in policy daily tracker
        pol.RecordSend(amount);

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
            // Node accepted: now safe to mark the tx's inputs spent locally
            // and persist the wallet so the next CLI invocation does not
            // try to reuse those UTXOs before mempool propagates back.
            w.mark_tx_inputs_spent(tx);
            std::string save_err;
            if (!w.save(wallet_path, &save_err)) {
                fprintf(stderr, "Warning: failed to save wallet: %s\n",
                        save_err.c_str());
            }
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
    // sendmany <addr1>:<amount1> <addr2>:<amount2> ...
    //
    // Single TRANSFER tx with N outputs. No recipient cap — bounded only
    // by MAX_TX_BYTES_CONSENSUS (100 KB → ~3000 recipients). One signed
    // input set, one change output (if any), atomic broadcast.
    // =====================================================================
    if (cmd == "sendmany") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli sendmany <addr1>:<amount1> [<addr2>:<amount2> ...]\n");
            fprintf(stderr, "  Single tx with N outputs. Address and amount separated by ':'.\n");
            fprintf(stderr, "  Amount is SOST (decimal).\n");
            fprintf(stderr, "\nExamples:\n");
            fprintf(stderr, "  sost-cli sendmany sost1abc:5 sost1def:10\n");
            fprintf(stderr, "  sost-cli sendmany sost1abc:0.5 sost1def:0.5 sost1ghi:0.5 sost1jkl:0.5\n");
            return 1;
        }

        std::vector<sost::Wallet::Recipient> recipients;
        int64_t total_amount = 0;
        for (int i = arg_start + 1; i < argc; ++i) {
            std::string a(argv[i]);
            auto colon = a.rfind(':');
            if (colon == std::string::npos || colon == 0 || colon == a.size() - 1) {
                fprintf(stderr, "Error: recipient '%s' must be <address>:<amount>\n", argv[i]);
                return 1;
            }
            sost::Wallet::Recipient r;
            r.address = a.substr(0, colon);
            r.amount  = parse_amount(a.substr(colon + 1).c_str());
            if (r.amount <= 0) {
                fprintf(stderr, "Error: recipient %d (%s) amount must be positive\n",
                        i - arg_start, r.address.c_str());
                return 1;
            }
            recipients.push_back(r);
            total_amount += r.amount;
        }

        int64_t chain_height = query_chain_height();
        if (chain_height < 0) {
            fprintf(stderr, "Error: cannot connect to node at %s:%d\n",
                    g_node_host.c_str(), g_node_port);
            return 1;
        }
        printf("Chain height: %lld\n", (long long)chain_height);

        w.clear_utxos();
        int synced = sync_wallet_utxos_from_node(w);
        if (synced > 0) {
            printf("Synced %d UTXOs from node for %s\n", synced, w.default_address().c_str());
        } else if (w.num_utxos() == 0) {
            fprintf(stderr, "Error: no spendable UTXOs found for %s\n", w.default_address().c_str());
            return 1;
        }

        sost::Hash256 genesis_hash = sost::from_hex(
            "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");

        // Two-pass fee calculation (same as send).
        int64_t est_fee = MIN_FEE_STOCKS;
        sost::Transaction tx;
        std::string err;
        if (!w.create_transaction_many(recipients, est_fee, genesis_hash,
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
        int64_t real_fee = calculate_fee((int64_t)raw.size());
        if (real_fee != est_fee) {
            sost::Transaction tx2;
            if (!w.create_transaction_many(recipients, real_fee, genesis_hash,
                                           tx2, chain_height, &err)) {
                fprintf(stderr, "Error (fee adjustment): %s\n", err.c_str());
                return 1;
            }
            tx = tx2;
            raw.clear();
            tx.Serialize(raw, &ser_err);
            int64_t final_fee = calculate_fee((int64_t)raw.size());
            if (final_fee > real_fee) {
                sost::Transaction tx3;
                if (!w.create_transaction_many(recipients, final_fee, genesis_hash,
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

        // Refuse to broadcast a tx larger than consensus limit.
        if ((int32_t)raw.size() > sost::MAX_TX_BYTES_CONSENSUS) {
            fprintf(stderr,
                "Error: tx size %zu bytes exceeds MAX_TX_BYTES_CONSENSUS (%d). "
                "Split the recipient list into multiple sendmany calls.\n",
                raw.size(), sost::MAX_TX_BYTES_CONSENSUS);
            return 1;
        }

        // Wallet save + mark-inputs-spent are intentionally deferred until
        // after the broadcast succeeds. Marking now would leave the local
        // UTXO list out of sync with the chain if the user aborts at the
        // confirm prompt, or if the node rejects the tx.
        std::string raw_hex = to_hex(raw.data(), raw.size());
        sost::Hash256 txid;
        tx.ComputeTxId(txid);

        printf("\n========== SENDMANY SUMMARY ==========\n");
        printf("  TXID:        %s\n", to_hex(txid.data(), 32).c_str());
        printf("  Recipients:  %zu\n", recipients.size());
        for (size_t i = 0; i < recipients.size(); ++i) {
            printf("    %2zu. %s  %s SOST\n",
                   i + 1, recipients[i].address.c_str(),
                   format_sost(recipients[i].amount).c_str());
        }
        printf("  Total out:   %s SOST\n", format_sost(total_amount).c_str());
        printf("  Fee:         %s SOST (%zu bytes x %lld stock/byte)\n",
               format_sost(real_fee).c_str(), raw.size(), (long long)g_fee_rate);
        printf("  Size:        %zu bytes\n", raw.size());
        printf("======================================\n");

        if (!g_yes_flag) {
            printf("Confirm sendmany? [yes/no]: ");
            fflush(stdout);
            char confirm[16] = {};
            if (!fgets(confirm, sizeof(confirm), stdin) ||
                (strncmp(confirm, "yes", 3) != 0 && strncmp(confirm, "y", 1) != 0)) {
                printf("Transaction cancelled.\n");
                return 0;
            }
        }

        // Broadcast.
        printf("Sending to node %s:%d...\n", g_node_host.c_str(), g_node_port);
        std::string resp = rpc_call("sendrawtransaction",
                                    "[\"" + raw_hex + "\"]");
        if (resp.find("\"result\":\"") != std::string::npos) {
            // Now that the node accepted the tx, mark its inputs as spent
            // in the local UTXO list and persist the wallet so subsequent
            // CLI invocations don't try to reuse those UTXOs before the
            // node's mempool propagates back.
            w.mark_tx_inputs_spent(tx);
            std::string save_err;
            if (!w.save(wallet_path, &save_err)) {
                fprintf(stderr, "Warning: failed to save wallet: %s\n", save_err.c_str());
            }
            printf("\nTX accepted by node! Txid: %s\n",
                   to_hex(txid.data(), 32).c_str());
            printf("  Waiting for next mined block to confirm...\n");
            return 0;
        }
        if (resp.find("401") != std::string::npos) {
            fprintf(stderr, "\nTX rejected: 401 Unauthorized\n");
            fprintf(stderr, "  Use: --rpc-user <user> --rpc-pass <pass>\n");
            return 1;
        }
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

    // =====================================================================
    // cancel-tx <txid> [--fee-bump N]
    //
    // RBF replacement of a still-pending tx. Spends the SAME inputs as the
    // original tx back to this wallet's default address with a strictly
    // higher absolute fee. Requires:
    //   - tx is still in the node's mempool (not yet mined)
    //   - all inputs belong to this wallet (we need the private keys)
    // The chain's mempool enforces RBF_MIN_FEE_BUMP_PER_BYTE = 1 stock/byte;
    // we default to a 2 stock/byte bump for headroom. Override with
    // --fee-bump N (stocks per byte added on top of the original fee).
    // =====================================================================
    if (cmd == "cancel-tx") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli cancel-tx <txid> [--fee-bump <stocks_per_byte>]\n");
            fprintf(stderr, "  Replaces a pending tx with a higher-fee TX that returns\n");
            fprintf(stderr, "  all input value to your wallet address.\n");
            fprintf(stderr, "  Default fee bump: 2 stocks/byte (chain min: 1).\n");
            return 1;
        }
        std::string orig_txid = argv[arg_start + 1];
        int64_t fee_bump_per_byte = 2;
        for (int i = arg_start + 2; i < argc; ++i) {
            if (std::string(argv[i]) == "--fee-bump" && i + 1 < argc) {
                fee_bump_per_byte = std::stoll(argv[i + 1]);
                if (fee_bump_per_byte < 1) {
                    fprintf(stderr, "Error: --fee-bump must be >= 1\n");
                    return 1;
                }
                ++i;
            }
        }

        // 1) Confirm tx is still in mempool.
        std::string mp_resp = rpc_call("getrawmempool");
        if (mp_resp.find("\"" + orig_txid + "\"") == std::string::npos) {
            fprintf(stderr, "Error: tx %s is not in the mempool. It may already be\n",
                    orig_txid.c_str());
            fprintf(stderr, "  confirmed or have been dropped — RBF is no longer possible.\n");
            return 1;
        }

        // 2) Pull verbose tx with prev_value / prev_address per vin.
        std::string tx_resp = rpc_call("getrawtransaction",
                                       "[\"" + orig_txid + "\",1]");
        if (tx_resp.find("\"result\":") == std::string::npos) {
            fprintf(stderr, "Error: getrawtransaction failed.\n");
            fprintf(stderr, "  Raw response: %s\n", tx_resp.c_str());
            return 1;
        }

        // 3) Tiny field extractor for the JSON shape we control.
        auto extract_int = [&](const std::string& key, size_t pos) -> int64_t {
            std::string pat = "\"" + key + "\":";
            auto p = tx_resp.find(pat, pos);
            if (p == std::string::npos) return -1;
            p += pat.size();
            return std::stoll(tx_resp.c_str() + p);
        };
        auto extract_str = [&](const std::string& key, size_t pos) -> std::string {
            std::string pat = "\"" + key + "\":\"";
            auto p = tx_resp.find(pat, pos);
            if (p == std::string::npos) return "";
            p += pat.size();
            auto e = tx_resp.find('"', p);
            return tx_resp.substr(p, e - p);
        };

        int64_t orig_size = extract_int("size", 0);
        int64_t orig_fee  = extract_int("fee",  0);
        if (orig_size <= 0 || orig_fee < 0) {
            fprintf(stderr, "Error: malformed getrawtransaction response.\n");
            return 1;
        }

        // 4) Walk vin[] and gather inputs.
        struct VinEntry {
            std::string txid;
            uint32_t    vout{0};
            int64_t     prev_value{0};
            std::string prev_address;
            uint8_t     prev_type{0};
        };
        std::vector<VinEntry> vins;
        auto vin_start = tx_resp.find("\"vin\":[");
        auto vin_end   = tx_resp.find("],\"vout\"", vin_start);
        if (vin_start == std::string::npos || vin_end == std::string::npos) {
            fprintf(stderr, "Error: missing vin[] in response.\n");
            return 1;
        }
        size_t cur = vin_start;
        while (true) {
            auto obj = tx_resp.find('{', cur);
            if (obj == std::string::npos || obj >= vin_end) break;
            auto obj_end = tx_resp.find('}', obj);
            if (obj_end == std::string::npos || obj_end > vin_end) break;
            VinEntry v;
            v.txid         = extract_str("txid", obj);
            v.vout         = (uint32_t)extract_int("vout", obj);
            v.prev_value   = extract_int("prev_value", obj);
            v.prev_address = extract_str("prev_address", obj);
            v.prev_type    = (uint8_t)extract_int("prev_type", obj);
            if (v.txid.empty() || v.prev_value < 0 || v.prev_address.empty()) {
                fprintf(stderr, "Error: vin missing prev_value/prev_address. "
                                "Node may need redeploy of the extended RPC.\n");
                return 1;
            }
            vins.push_back(v);
            cur = obj_end + 1;
        }
        if (vins.empty()) {
            fprintf(stderr, "Error: no vin entries parsed.\n");
            return 1;
        }

        // 5) Verify wallet owns every input.
        int64_t total_in = 0;
        for (const auto& v : vins) {
            sost::PubKeyHash pkh{};
            if (!sost::address_decode(v.prev_address, pkh)) {
                fprintf(stderr, "Error: cannot decode prev_address %s\n", v.prev_address.c_str());
                return 1;
            }
            if (!w.find_key_by_pkh(pkh)) {
                fprintf(stderr, "Error: input %s:%u belongs to %s (not in this wallet).\n",
                        v.txid.c_str(), v.vout, v.prev_address.c_str());
                fprintf(stderr, "  Cannot sign a replacement for a tx whose inputs we do not own.\n");
                return 1;
            }
            total_in += v.prev_value;
        }

        // 6) Compute new fee + return amount. Replacement size will be
        //    smaller (1 output instead of N), but we conservatively reuse
        //    the original size for the bump calc — chain only requires
        //    new_fee/new_size > old_fee/old_size AND new_fee >= old_fee +
        //    new_size * RBF_MIN_FEE_BUMP_PER_BYTE.
        int64_t new_fee = orig_fee + orig_size * fee_bump_per_byte;
        if (total_in <= new_fee) {
            fprintf(stderr, "Error: replacement fee (%lld) exceeds total input value (%lld). "
                            "Original fee was already too close to inputs.\n",
                    (long long)new_fee, (long long)total_in);
            return 1;
        }
        int64_t return_amount = total_in - new_fee;
        std::string return_addr = w.default_address();
        sost::PubKeyHash return_pkh{};
        if (!sost::address_decode(return_addr, return_pkh)) {
            fprintf(stderr, "Error: cannot decode wallet default address %s\n", return_addr.c_str());
            return 1;
        }

        // 7) Build replacement: same inputs, single output to self.
        sost::Transaction rtx{};
        rtx.version = 1;
        rtx.tx_type = 0x00;
        for (const auto& v : vins) {
            if (v.txid.size() != 64) {
                fprintf(stderr, "Error: bad input txid length %zu (expected 64 hex)\n",
                        v.txid.size());
                return 1;
            }
            sost::TxInput in{};
            in.prev_txid  = sost::from_hex(v.txid);
            in.prev_index = v.vout;
            rtx.inputs.push_back(in);
        }
        sost::TxOutput out{};
        out.amount      = return_amount;
        out.type        = 0x00;
        out.pubkey_hash = return_pkh;
        rtx.outputs.push_back(out);

        // 8) Sign each input.
        sost::Hash256 genesis_hash = sost::from_hex(
            "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");
        for (size_t i = 0; i < vins.size(); ++i) {
            sost::PubKeyHash pkh{};
            sost::address_decode(vins[i].prev_address, pkh);
            const sost::WalletKey* key = w.find_key_by_pkh(pkh);
            if (!key) {
                fprintf(stderr, "Error: lost key for input %zu\n", i);
                return 1;
            }
            sost::SpentOutput spent{};
            spent.amount = vins[i].prev_value;
            spent.type   = vins[i].prev_type;
            std::string sign_err;
            if (!sost::SignTransactionInput(rtx, i, spent, genesis_hash,
                                            key->privkey, &sign_err)) {
                fprintf(stderr, "Error signing input %zu: %s\n", i, sign_err.c_str());
                return 1;
            }
        }

        std::vector<sost::Byte> raw;
        std::string ser_err;
        if (!rtx.Serialize(raw, &ser_err)) {
            fprintf(stderr, "Error serializing replacement: %s\n", ser_err.c_str());
            return 1;
        }
        sost::Hash256 new_txid;
        rtx.ComputeTxId(new_txid);
        std::string raw_hex = to_hex(raw.data(), raw.size());

        printf("\n========== CANCEL-TX (RBF) ==========\n");
        printf("  Original txid:    %s\n", orig_txid.c_str());
        printf("  Original size:    %lld bytes\n", (long long)orig_size);
        printf("  Original fee:     %s SOST\n", format_sost(orig_fee).c_str());
        printf("  Inputs spent:     %zu  (total %s SOST)\n",
               vins.size(), format_sost(total_in).c_str());
        printf("  Replacement txid: %s\n", to_hex(new_txid.data(), 32).c_str());
        printf("  Replacement size: %zu bytes\n", raw.size());
        printf("  Replacement fee:  %s SOST  (+%s SOST, +%lld stocks/byte)\n",
               format_sost(new_fee).c_str(),
               format_sost(new_fee - orig_fee).c_str(),
               (long long)fee_bump_per_byte);
        printf("  Refund to:        %s\n", return_addr.c_str());
        printf("  Refund amount:    %s SOST\n", format_sost(return_amount).c_str());
        printf("=====================================\n");

        if (!g_yes_flag) {
            printf("Confirm cancel? [yes/no]: ");
            fflush(stdout);
            char confirm[16] = {};
            if (!fgets(confirm, sizeof(confirm), stdin) ||
                (strncmp(confirm, "yes", 3) != 0 && strncmp(confirm, "y", 1) != 0)) {
                printf("Cancellation aborted.\n");
                return 0;
            }
        }

        printf("Broadcasting replacement...\n");
        std::string resp = rpc_call("sendrawtransaction", "[\"" + raw_hex + "\"]");
        if (resp.find("\"result\":\"") != std::string::npos) {
            printf("\nReplacement accepted! New txid: %s\n",
                   to_hex(new_txid.data(), 32).c_str());
            printf("  Original tx %s is now replaced.\n", orig_txid.c_str());
            return 0;
        }
        auto err_pos = resp.find("\"message\":\"");
        if (err_pos != std::string::npos) {
            auto err_end = resp.find('"', err_pos + 11);
            std::string err_msg = resp.substr(err_pos + 11, err_end - err_pos - 11);
            fprintf(stderr, "\nReplacement rejected: %s\n", err_msg.c_str());
        } else {
            fprintf(stderr, "\nReplacement rejected (unknown error)\n");
            fprintf(stderr, "  Raw response: %s\n", resp.c_str());
        }
        return 1;
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
            "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");

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
            "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");

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

    // =====================================================================
    // hd create|restore
    // =====================================================================
    if (cmd == "hd") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli hd <create|restore>\n");
            return 1;
        }
        std::string subcmd = argv[arg_start + 1];

        if (subcmd == "create") {
            sost::bip39::HDWalletResult hd;
            std::string err;
            if (!sost::bip39::create_hd_wallet(hd, &err)) {
                fprintf(stderr, "Error: %s\n", err.c_str());
                return 1;
            }

            printf("\n========== NEW HD WALLET ==========\n\n");
            printf("  Seed phrase (12 words):\n\n    ");
            for (size_t i = 0; i < hd.mnemonic.size(); ++i) {
                printf("%s", hd.mnemonic[i].c_str());
                if (i < 11) printf(" ");
            }
            printf("\n\n");
            printf("  Address:     %s\n", hd.address.c_str());
            printf("  Private key: %s\n", to_hex(hd.privkey.data(), 32).c_str());
            printf("\n===================================\n");
            printf("\n*** WRITE DOWN YOUR SEED PHRASE AND STORE IT SAFELY ***\n");
            printf("*** ANYONE WITH THESE 12 WORDS CAN ACCESS YOUR FUNDS ***\n\n");

            // Import into wallet
            try {
                w.import_privkey(hd.privkey, "hd-seed");
                std::string serr;
                if (!w.save(wallet_path, &serr)) {
                    fprintf(stderr, "Warning: failed to save wallet: %s\n", serr.c_str());
                }
                printf("Key imported into wallet: %s\n", wallet_path.c_str());
            } catch (const std::exception& e) {
                fprintf(stderr, "Warning: %s\n", e.what());
            }
            return 0;
        }

        if (subcmd == "restore") {
            printf("Enter your 12-word seed phrase (space-separated):\n> ");
            fflush(stdout);
            char buf[1024] = {};
            if (!fgets(buf, sizeof(buf), stdin)) {
                fprintf(stderr, "Error reading seed phrase\n");
                return 1;
            }
            buf[strcspn(buf, "\r\n")] = 0;

            // Parse words
            std::vector<std::string> words;
            {
                std::string s(buf);
                size_t pos = 0;
                while (pos < s.size()) {
                    while (pos < s.size() && s[pos] == ' ') pos++;
                    size_t start = pos;
                    while (pos < s.size() && s[pos] != ' ') pos++;
                    if (pos > start) words.push_back(s.substr(start, pos - start));
                }
            }

            sost::bip39::HDWalletResult hd;
            std::string err;
            if (!sost::bip39::restore_from_mnemonic(words, hd, &err)) {
                fprintf(stderr, "Error: %s\n", err.c_str());
                return 1;
            }

            printf("\nRestored wallet:\n");
            printf("  Address: %s\n", hd.address.c_str());

            // Import into wallet
            try {
                w.import_privkey(hd.privkey, "hd-restored");
                std::string serr;
                if (!w.save(wallet_path, &serr)) {
                    fprintf(stderr, "Warning: failed to save wallet: %s\n", serr.c_str());
                }
                printf("Key imported into wallet: %s\n", wallet_path.c_str());
            } catch (const std::exception& e) {
                fprintf(stderr, "Warning: %s\n", e.what());
            }
            return 0;
        }

        fprintf(stderr, "Unknown hd subcommand: %s\n", subcmd.c_str());
        return 1;
    }

    // =====================================================================
    // addressbook add|list|remove|check
    // =====================================================================
    if (cmd == "addressbook") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli addressbook <add|list|remove|check> ...\n");
            return 1;
        }
        std::string subcmd = argv[arg_start + 1];

        // Ensure ~/.sost directory exists
        std::string mkdir_cmd = "mkdir -p " + g_sost_dir;
        system(mkdir_cmd.c_str());

        sost::AddressBook ab;
        ab.Load(g_addressbook_path);

        if (subcmd == "add") {
            if (argc < arg_start + 3) {
                fprintf(stderr, "Usage: sost-cli addressbook add <address> [--label <name>] [--trust <level>] [--notes <text>]\n");
                return 1;
            }
            std::string addr = argv[arg_start + 2];
            std::string label, notes;
            sost::TrustLevel trust = sost::TrustLevel::KNOWN;

            for (int i = arg_start + 3; i < argc; ++i) {
                if (!strcmp(argv[i], "--label") && i + 1 < argc) label = argv[++i];
                else if (!strcmp(argv[i], "--trust") && i + 1 < argc) trust = sost::TrustLevelFromStr(argv[++i]);
                else if (!strcmp(argv[i], "--notes") && i + 1 < argc) notes = argv[++i];
            }

            ab.Add(addr, label, trust, 0, notes);
            std::string err;
            if (!ab.Save(g_addressbook_path, &err)) {
                fprintf(stderr, "Error saving: %s\n", err.c_str());
                return 1;
            }
            printf("Added: %s [%s] trust=%s\n", addr.c_str(), label.c_str(),
                   sost::TrustLevelStr(trust));
        } else if (subcmd == "list") {
            if (ab.Size() == 0) {
                printf("Address book is empty.\n");
                return 0;
            }
            printf("%-47s  %-20s  %-8s  %s\n", "ADDRESS", "LABEL", "TRUST", "NOTES");
            printf("%-47s  %-20s  %-8s  %s\n", "-------", "-----", "-----", "-----");
            for (const auto& e : ab.Entries()) {
                printf("%-47s  %-20s  %-8s  %s\n",
                       e.address.c_str(), e.label.c_str(),
                       sost::TrustLevelStr(e.trust),
                       e.notes.c_str());
            }
            printf("\nTotal: %zu entries\n", ab.Size());
        } else if (subcmd == "remove") {
            if (argc < arg_start + 3) {
                fprintf(stderr, "Usage: sost-cli addressbook remove <address>\n");
                return 1;
            }
            std::string addr = argv[arg_start + 2];
            if (!ab.Remove(addr)) {
                fprintf(stderr, "Address not found: %s\n", addr.c_str());
                return 1;
            }
            std::string err;
            ab.Save(g_addressbook_path, &err);
            printf("Removed: %s\n", addr.c_str());
        } else if (subcmd == "check") {
            if (argc < arg_start + 3) {
                fprintf(stderr, "Usage: sost-cli addressbook check <address>\n");
                return 1;
            }
            std::string addr = argv[arg_start + 2];
            auto trust = ab.Check(addr);
            if (trust == sost::TrustLevel::UNKNOWN) {
                printf("%s: UNKNOWN (not in address book)\n", addr.c_str());
            } else {
                auto* e = ab.Get(addr);
                printf("%s: %s", addr.c_str(), sost::TrustLevelStr(trust));
                if (e && !e->label.empty()) printf(" [%s]", e->label.c_str());
                printf("\n");
            }
        } else {
            fprintf(stderr, "Unknown addressbook subcommand: %s\n", subcmd.c_str());
            return 1;
        }
        return 0;
    }

    // =====================================================================
    // policy show|set
    // =====================================================================
    if (cmd == "policy") {
        if (argc < arg_start + 2) {
            fprintf(stderr, "Usage: sost-cli policy <show|set> ...\n");
            return 1;
        }
        std::string subcmd = argv[arg_start + 1];

        std::string mkdir_cmd = "mkdir -p " + g_sost_dir;
        system(mkdir_cmd.c_str());

        sost::WalletPolicy pol;
        pol.Load(g_policy_path);

        if (subcmd == "show") {
            pol.Print();
        } else if (subcmd == "set") {
            if (argc < arg_start + 4) {
                fprintf(stderr, "Usage: sost-cli policy set <key> <value>\n");
                fprintf(stderr, "Keys: daily_limit, per_tx_limit, vault_mode, ");
                fprintf(stderr, "require_addressbook_for_large, large_tx_threshold\n");
                return 1;
            }
            std::string key = argv[arg_start + 2];
            std::string val = argv[arg_start + 3];
            std::string err;
            if (!pol.Set(key, val, &err)) {
                fprintf(stderr, "Error: %s\n", err.c_str());
                return 1;
            }
            if (!pol.Save(g_policy_path, &err)) {
                fprintf(stderr, "Error saving: %s\n", err.c_str());
                return 1;
            }
            printf("Policy updated: %s = %s\n", key.c_str(), val.c_str());
            pol.Print();
        } else {
            fprintf(stderr, "Unknown policy subcommand: %s\n", subcmd.c_str());
            return 1;
        }
        return 0;
    }

    // ---- popc subcommand suite ----
    // Friendly wrapper over the raw JSON-RPC PoPC methods. Translates human
    // flags to the positional parameters the node expects. Read-only helpers
    // (status, check) do not require any wallet unlock.
    //
    // Usage:
    //   sost-cli popc register --sost-address sost1...
    //                          --eth-wallet 0x...
    //                          --token XAUT|PAXG
    //                          --gold-mg 31103
    //                          --duration 12
    //   sost-cli popc status
    //   sost-cli popc check <commitment_id>
    //
    // Note: --bond is accepted for forward compatibility but ignored by the
    // node today — the bond amount is computed automatically from the
    // SOST/gold price ratio in config/popc_pricing.json.
    if (cmd == "popc") {
        if (argc < 3) {
            fprintf(stderr,
                "Usage:\n"
                "  sost-cli popc register --sost-address <addr> --eth-wallet <0x...> \\\n"
                "                         --token <XAUT|PAXG> --gold-mg <amount> \\\n"
                "                         --duration <1|3|6|9|12> [--bond <sost>]\n"
                "  sost-cli popc status\n"
                "  sost-cli popc check <commitment_id>\n");
            return 1;
        }
        std::string sub = argv[2];

        if (sub == "register") {
            std::string sost_addr, eth_wallet, token;
            int64_t gold_mg = -1;
            int     duration = -1;
            int64_t bond_sost_ignored = -1; // accepted but unused

            for (int i = 3; i < argc; ++i) {
                std::string a = argv[i];
                if ((a == "--sost-address" || a == "--sost") && i + 1 < argc) {
                    sost_addr = argv[++i];
                } else if ((a == "--eth-wallet" || a == "--eth") && i + 1 < argc) {
                    eth_wallet = argv[++i];
                } else if (a == "--token" && i + 1 < argc) {
                    token = argv[++i];
                } else if ((a == "--gold-mg" || a == "--gold-amount-mg") && i + 1 < argc) {
                    gold_mg = std::stoll(argv[++i]);
                } else if (a == "--duration" && i + 1 < argc) {
                    duration = std::stoi(argv[++i]);
                } else if ((a == "--bond" || a == "--bond-sost") && i + 1 < argc) {
                    bond_sost_ignored = std::stoll(argv[++i]);
                } else {
                    fprintf(stderr, "Unknown flag for 'popc register': %s\n", a.c_str());
                    return 1;
                }
            }

            if (sost_addr.empty() || eth_wallet.empty() || token.empty()
                || gold_mg <= 0 || duration <= 0) {
                fprintf(stderr, "Missing required flags.\n");
                fprintf(stderr, "Required: --sost-address --eth-wallet --token --gold-mg --duration\n");
                return 1;
            }
            if (token != "XAUT" && token != "PAXG") {
                fprintf(stderr, "--token must be XAUT or PAXG (case sensitive)\n");
                return 1;
            }
            if (duration != 1 && duration != 3 && duration != 6 && duration != 9 && duration != 12) {
                fprintf(stderr, "--duration must be one of 1, 3, 6, 9, 12\n");
                return 1;
            }
            if (bond_sost_ignored >= 0) {
                printf("Note: --bond is accepted but ignored — the node computes\n"
                       "      the bond automatically from the current SOST/gold ratio.\n");
            }

            // Build positional JSON-RPC params: [sost, eth, token, gold_mg, duration]
            std::string params =
                "[\"" + sost_addr + "\","
                "\"" + eth_wallet + "\","
                "\"" + token + "\","
                "\"" + std::to_string(gold_mg) + "\","
                "\"" + std::to_string(duration) + "\"]";

            printf("Registering PoPC commitment:\n");
            printf("  SOST address : %s\n", sost_addr.c_str());
            printf("  ETH wallet   : %s\n", eth_wallet.c_str());
            printf("  Token        : %s\n", token.c_str());
            printf("  Gold amount  : %lld mg (%.4f oz)\n",
                   (long long)gold_mg, (double)gold_mg / 31103.4768);
            printf("  Duration     : %d months\n", duration);
            printf("\nCalling popc_register RPC...\n");

            std::string resp = rpc_call("popc_register", params);
            if (resp.empty()) {
                fprintf(stderr, "ERROR: no response from node RPC\n");
                return 1;
            }
            // Print the JSON body (everything after the HTTP headers)
            auto hdr_end = resp.find("\r\n\r\n");
            std::string body = (hdr_end != std::string::npos) ? resp.substr(hdr_end + 4) : resp;
            printf("\n%s\n", body.c_str());

            // Best-effort exit code: 0 if node returned a result, 1 if it returned an error.
            return (body.find("\"error\"") != std::string::npos && body.find("\"error\":null") == std::string::npos) ? 1 : 0;
        }

        if (sub == "status") {
            std::string resp = rpc_call("popc_status", "[]");
            if (resp.empty()) { fprintf(stderr, "ERROR: no response from node\n"); return 1; }
            auto hdr_end = resp.find("\r\n\r\n");
            std::string body = (hdr_end != std::string::npos) ? resp.substr(hdr_end + 4) : resp;
            printf("%s\n", body.c_str());
            return 0;
        }

        if (sub == "check") {
            if (argc < 4) { fprintf(stderr, "Usage: sost-cli popc check <commitment_id>\n"); return 1; }
            std::string cid = argv[3];
            std::string params = "[\"" + cid + "\"]";
            std::string resp = rpc_call("popc_check", params);
            if (resp.empty()) { fprintf(stderr, "ERROR: no response from node\n"); return 1; }
            auto hdr_end = resp.find("\r\n\r\n");
            std::string body = (hdr_end != std::string::npos) ? resp.substr(hdr_end + 4) : resp;
            printf("%s\n", body.c_str());
            return 0;
        }

        fprintf(stderr, "Unknown popc subcommand: %s\n", sub.c_str());
        fprintf(stderr, "Valid: register, status, check\n");
        return 1;
    }

    // Unknown command
    fprintf(stderr, "Unknown command: %s\n", cmd.c_str());
    print_usage();
    return 1;
}
