// popc_model_b.cpp — PoPC Model B (Escrow-Based) Registry
//
// Application-layer only. No consensus changes.
// Gold is held in an Ethereum escrow contract (XAUT or PAXG).
// SOST reward is calculated and paid immediately upon registration.
//
// See: popc_model_b.h, docs/POPC_MODEL_B_SPECIFICATION.md

#include "sost/popc_model_b.h"
#include "sost/popc.h"
#include <fstream>
#include <sstream>
#include <cstring>
#include <cstdlib>
#include <algorithm>

namespace sost {

// =========================================================================
// Internal helpers (same pattern as popc.cpp)
// =========================================================================

static const char HEX_CHARS_ESCROW[] = "0123456789abcdef";

static std::string bytes_to_hex_e(const uint8_t* data, size_t len) {
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        out += HEX_CHARS_ESCROW[data[i] >> 4];
        out += HEX_CHARS_ESCROW[data[i] & 0x0F];
    }
    return out;
}

static int hex_nibble_e(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    return -1;
}

static bool hex_to_bytes_e(const std::string& hex, uint8_t* out, size_t expected_len) {
    if (hex.size() != expected_len * 2) return false;
    for (size_t i = 0; i < expected_len; ++i) {
        int hi = hex_nibble_e(hex[i * 2]);
        int lo = hex_nibble_e(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

static std::string hash256_to_hex_e(const Hash256& h) {
    return bytes_to_hex_e(h.data(), 32);
}

static Hash256 hex_to_hash256_e(const std::string& hex) {
    Hash256 h{};
    hex_to_bytes_e(hex, h.data(), 32);
    return h;
}

static std::string pkh_to_hex_e(const PubKeyHash& pkh) {
    return bytes_to_hex_e(pkh.data(), 20);
}

static PubKeyHash hex_to_pkh_e(const std::string& hex) {
    PubKeyHash pkh{};
    hex_to_bytes_e(hex, pkh.data(), 20);
    return pkh;
}

static std::string json_escape_e(const std::string& s) {
    std::string r;
    r.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"')       r += "\\\"";
        else if (c == '\\') r += "\\\\";
        else if (c == '\n') r += "\\n";
        else if (c == '\r') r += "\\r";
        else r += c;
    }
    return r;
}

static std::string extract_str_e(const std::string& block, const std::string& key) {
    auto pos = block.find("\"" + key + "\"");
    if (pos == std::string::npos) return "";
    pos = block.find(':', pos);
    if (pos == std::string::npos) return "";
    pos = block.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    auto end = block.find('"', pos + 1);
    if (end == std::string::npos) return "";
    return block.substr(pos + 1, end - pos - 1);
}

static int64_t extract_int_e(const std::string& block, const std::string& key) {
    auto pos = block.find("\"" + key + "\"");
    if (pos == std::string::npos) return 0;
    pos = block.find(':', pos);
    if (pos == std::string::npos) return 0;
    pos++;
    while (pos < block.size() && (block[pos] == ' ' || block[pos] == '\t')) pos++;
    return std::strtoll(block.c_str() + pos, nullptr, 10);
}

static std::string escrow_status_to_str(EscrowStatus s) {
    switch (s) {
        case EscrowStatus::ACTIVE:    return "ACTIVE";
        case EscrowStatus::COMPLETED: return "COMPLETED";
        case EscrowStatus::FAILED:    return "FAILED";
    }
    return "ACTIVE";
}

static EscrowStatus escrow_status_from_str(const std::string& s) {
    if (s == "COMPLETED") return EscrowStatus::COMPLETED;
    if (s == "FAILED")    return EscrowStatus::FAILED;
    return EscrowStatus::ACTIVE;
}

// =========================================================================
// calculate_escrow_reward
// Same reward rates as Model A (POPC_REWARD_RATES), applied to gold_value_stocks.
// No bond required — reward is on the full gold value.
// =========================================================================
int64_t calculate_escrow_reward(int64_t gold_value_stocks, uint16_t duration_months) {
    uint16_t reward_pct_bps = compute_reward_pct(duration_months);
    if (reward_pct_bps == 0 || gold_value_stocks <= 0) return 0;
    // reward_pct_bps is in basis-points (e.g. 100 = 1%)
    return (gold_value_stocks * (int64_t)reward_pct_bps) / 10000;
}

// =========================================================================
// EscrowRegistry::register_escrow
// =========================================================================
bool EscrowRegistry::register_escrow(const EscrowCommitment& e, std::string* err) {
    // Validate duration
    bool valid_duration = false;
    static constexpr size_t N = sizeof(POPC_DURATIONS) / sizeof(POPC_DURATIONS[0]);
    for (size_t i = 0; i < N; ++i) {
        if (POPC_DURATIONS[i] == e.duration_months) { valid_duration = true; break; }
    }
    if (!valid_duration) {
        if (err) *err = "invalid duration_months: must be 1, 3, 6, 9, or 12";
        return false;
    }

    if (e.gold_amount_mg <= 0) {
        if (err) *err = "gold_amount_mg must be > 0";
        return false;
    }

    if (e.eth_escrow_address.empty()) {
        if (err) *err = "eth_escrow_address must not be empty";
        return false;
    }

    if (e.gold_token != "XAUT" && e.gold_token != "PAXG") {
        if (err) *err = "gold_token must be 'XAUT' or 'PAXG'";
        return false;
    }

    // No duplicate escrow_id
    for (const auto& existing : escrows_) {
        if (existing.escrow_id == e.escrow_id) {
            if (err) *err = "duplicate escrow_id";
            return false;
        }
    }

    escrows_.push_back(e);
    return true;
}

// =========================================================================
// EscrowRegistry::find
// =========================================================================
const EscrowCommitment* EscrowRegistry::find(const Hash256& escrow_id) const {
    for (const auto& e : escrows_) {
        if (e.escrow_id == escrow_id) return &e;
    }
    return nullptr;
}

// =========================================================================
// EscrowRegistry::list_active
// =========================================================================
std::vector<EscrowCommitment> EscrowRegistry::list_active() const {
    std::vector<EscrowCommitment> out;
    for (const auto& e : escrows_) {
        if (e.status == EscrowStatus::ACTIVE) out.push_back(e);
    }
    return out;
}

// =========================================================================
// EscrowRegistry::complete
// =========================================================================
bool EscrowRegistry::complete(const Hash256& escrow_id, std::string* err) {
    for (auto& e : escrows_) {
        if (e.escrow_id == escrow_id) {
            if (e.status != EscrowStatus::ACTIVE) {
                if (err) *err = "escrow is not ACTIVE";
                return false;
            }
            e.status = EscrowStatus::COMPLETED;
            return true;
        }
    }
    if (err) *err = "escrow_id not found";
    return false;
}

// =========================================================================
// EscrowRegistry::mark_failed
// =========================================================================
bool EscrowRegistry::mark_failed(const Hash256& escrow_id, const std::string& reason,
                                  std::string* err) {
    (void)reason; // reason is logged externally; registry records status change
    for (auto& e : escrows_) {
        if (e.escrow_id == escrow_id) {
            if (e.status != EscrowStatus::ACTIVE) {
                if (err) *err = "escrow is not ACTIVE";
                return false;
            }
            e.status = EscrowStatus::FAILED;
            return true;
        }
    }
    if (err) *err = "escrow_id not found";
    return false;
}

// =========================================================================
// EscrowRegistry::active_count
// =========================================================================
size_t EscrowRegistry::active_count() const {
    size_t n = 0;
    for (const auto& e : escrows_) {
        if (e.status == EscrowStatus::ACTIVE) n++;
    }
    return n;
}

// =========================================================================
// EscrowRegistry::save
// Format: { "escrows": [ { ... }, ... ] }
// =========================================================================
bool EscrowRegistry::save(const std::string& path, std::string* err) const {
    std::ofstream f(path);
    if (!f.is_open()) {
        if (err) *err = "cannot open " + path + " for writing";
        return false;
    }

    f << "{\n";
    f << "  \"escrows\": [\n";
    for (size_t i = 0; i < escrows_.size(); ++i) {
        const auto& e = escrows_[i];
        f << "    {\n";
        f << "      \"escrow_id\": \""           << hash256_to_hex_e(e.escrow_id)    << "\",\n";
        f << "      \"user_pkh\": \""             << pkh_to_hex_e(e.user_pkh)         << "\",\n";
        f << "      \"eth_escrow_address\": \""   << json_escape_e(e.eth_escrow_address) << "\",\n";
        f << "      \"gold_token\": \""           << json_escape_e(e.gold_token)      << "\",\n";
        f << "      \"gold_amount_mg\": "         << e.gold_amount_mg                 << ",\n";
        f << "      \"reward_stocks\": "          << e.reward_stocks                  << ",\n";
        f << "      \"duration_months\": "        << (int)e.duration_months           << ",\n";
        f << "      \"start_height\": "           << e.start_height                   << ",\n";
        f << "      \"end_height\": "             << e.end_height                     << ",\n";
        f << "      \"status\": \""               << escrow_status_to_str(e.status)   << "\"\n";
        f << "    }";
        if (i + 1 < escrows_.size()) f << ",";
        f << "\n";
    }
    f << "  ]\n";
    f << "}\n";
    return true;
}

// =========================================================================
// EscrowRegistry::load
// Parses the JSON written by save(). Same manual block-extraction approach
// as popc.cpp and addressbook.cpp.
// =========================================================================
bool EscrowRegistry::load(const std::string& path, std::string* err) {
    std::ifstream f(path);
    if (!f.is_open()) {
        // Not an error — file may not exist yet
        escrows_.clear();
        return true;
    }

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    escrows_.clear();

    auto escrows_pos = content.find("\"escrows\"");

    // Walk all '{' ... '}' sub-blocks (skip the outermost object brace at pos 0)
    size_t pos = 0;
    while (true) {
        pos = content.find('{', pos + 1);
        if (pos == std::string::npos) break;

        // Find matching closing brace (nested-brace aware)
        int depth = 1;
        size_t scan = pos + 1;
        while (scan < content.size() && depth > 0) {
            if (content[scan] == '{') depth++;
            else if (content[scan] == '}') depth--;
            scan++;
        }
        if (depth != 0) break; // malformed

        size_t block_end = scan; // exclusive
        std::string block = content.substr(pos, block_end - pos);

        bool in_escrows = (escrows_pos != std::string::npos && pos > escrows_pos);

        if (in_escrows) {
            std::string eid_hex = extract_str_e(block, "escrow_id");
            if (eid_hex.empty()) { pos = block_end; continue; }

            EscrowCommitment e{};
            e.escrow_id          = hex_to_hash256_e(eid_hex);
            e.user_pkh           = hex_to_pkh_e(extract_str_e(block, "user_pkh"));
            e.eth_escrow_address = extract_str_e(block, "eth_escrow_address");
            e.gold_token         = extract_str_e(block, "gold_token");
            e.gold_amount_mg     = extract_int_e(block, "gold_amount_mg");
            e.reward_stocks      = extract_int_e(block, "reward_stocks");
            e.duration_months    = (uint16_t)extract_int_e(block, "duration_months");
            e.start_height       = extract_int_e(block, "start_height");
            e.end_height         = extract_int_e(block, "end_height");
            e.status             = escrow_status_from_str(extract_str_e(block, "status"));
            escrows_.push_back(std::move(e));
        }

        pos = block_end;
    }

    (void)err;
    return true;
}

} // namespace sost
