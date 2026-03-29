// popc.cpp — Proof of Personal Custody (PoPC) Registry
//
// Application-layer implementation. NOT consensus. PoPC logic runs on top of
// existing BOND_LOCK UTXOs. The only consensus footprint is the 25% coinbase
// allocation to the PoPC Pool (already enforced by CB-rules in block_validation).
//
// See: docs/POPC_MODEL_A_SPECIFICATION.md, Whitepaper Section 6

#include "sost/popc.h"
#include "sost/address.h"
#include <openssl/sha.h>
#include <fstream>
#include <sstream>
#include <cstring>
#include <cstdlib>
#include <algorithm>

namespace sost {

// =========================================================================
// Internal helpers
// =========================================================================

static const char HEX_CHARS_POPC[] = "0123456789abcdef";

static std::string bytes_to_hex(const uint8_t* data, size_t len) {
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        out += HEX_CHARS_POPC[data[i] >> 4];
        out += HEX_CHARS_POPC[data[i] & 0x0F];
    }
    return out;
}

static int hex_nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    return -1;
}

static bool hex_to_bytes(const std::string& hex, uint8_t* out, size_t expected_len) {
    if (hex.size() != expected_len * 2) return false;
    for (size_t i = 0; i < expected_len; ++i) {
        int hi = hex_nibble(hex[i * 2]);
        int lo = hex_nibble(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

static std::string hash256_to_hex(const Hash256& h) {
    return bytes_to_hex(h.data(), 32);
}

static Hash256 hex_to_hash256(const std::string& hex) {
    Hash256 h{};
    hex_to_bytes(hex, h.data(), 32);
    return h;
}

static std::string pkh_to_hex(const PubKeyHash& pkh) {
    return bytes_to_hex(pkh.data(), 20);
}

static PubKeyHash hex_to_pkh(const std::string& hex) {
    PubKeyHash pkh{};
    hex_to_bytes(hex, pkh.data(), 20);
    return pkh;
}

// JSON escaping (same pattern as addressbook.cpp)
static std::string json_escape(const std::string& s) {
    std::string r;
    r.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"')  r += "\\\"";
        else if (c == '\\') r += "\\\\";
        else if (c == '\n') r += "\\n";
        else if (c == '\r') r += "\\r";
        else r += c;
    }
    return r;
}

// Extract a quoted string value from a JSON fragment for a given key.
// Works on both single-line and multi-line fragments.
static std::string extract_str(const std::string& block, const std::string& key) {
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

// Extract an integer value from a JSON fragment for a given key.
static int64_t extract_int(const std::string& block, const std::string& key) {
    auto pos = block.find("\"" + key + "\"");
    if (pos == std::string::npos) return 0;
    pos = block.find(':', pos);
    if (pos == std::string::npos) return 0;
    pos++;
    while (pos < block.size() && (block[pos] == ' ' || block[pos] == '\t')) pos++;
    return std::strtoll(block.c_str() + pos, nullptr, 10);
}

// Extract a boolean value from a JSON fragment for a given key.
static bool extract_bool(const std::string& block, const std::string& key) {
    auto pos = block.find("\"" + key + "\"");
    if (pos == std::string::npos) return false;
    pos = block.find(':', pos);
    if (pos == std::string::npos) return false;
    pos++;
    while (pos < block.size() && (block[pos] == ' ' || block[pos] == '\t')) pos++;
    return block.substr(pos, 4) == "true";
}

static std::string status_to_str(PoPCStatus s) {
    switch (s) {
        case PoPCStatus::ACTIVE:    return "ACTIVE";
        case PoPCStatus::COMPLETED: return "COMPLETED";
        case PoPCStatus::SLASHED:   return "SLASHED";
        case PoPCStatus::EXPIRED:   return "EXPIRED";
    }
    return "ACTIVE";
}

static PoPCStatus status_from_str(const std::string& s) {
    if (s == "COMPLETED") return PoPCStatus::COMPLETED;
    if (s == "SLASHED")   return PoPCStatus::SLASHED;
    if (s == "EXPIRED")   return PoPCStatus::EXPIRED;
    return PoPCStatus::ACTIVE;
}

// =========================================================================
// compute_bond_pct
// Bond sizing table — Whitepaper Section 6.5
// ratio_bps = (sost_price / gold_oz_price) × 10000
// =========================================================================
uint16_t compute_bond_pct(uint64_t ratio_bps) {
    if (ratio_bps < 100)   return 2500;  // <1%   → 25%
    if (ratio_bps < 500)   return 2000;  // 1-5%  → 20%
    if (ratio_bps < 1000)  return 1500;  // 5-10% → 15%
    if (ratio_bps < 5000)  return 1200;  // 10-50%→ 12%
    return 1000;                         // ≥50%  → 10%
}

// =========================================================================
// compute_reward_pct
// Lookup in POPC_REWARD_RATES by matching POPC_DURATIONS.
// Returns 0 if duration_months is not a valid PoPC duration.
// =========================================================================
uint16_t compute_reward_pct(uint16_t duration_months) {
    static constexpr size_t N = sizeof(POPC_DURATIONS) / sizeof(POPC_DURATIONS[0]);
    for (size_t i = 0; i < N; ++i) {
        if (POPC_DURATIONS[i] == duration_months) {
            return POPC_REWARD_RATES[i];
        }
    }
    return 0;
}

// =========================================================================
// max_gold_for_reputation
// =========================================================================
int64_t max_gold_for_reputation(uint8_t stars) {
    if (stars >= POPC_STARS_VETERAN) return POPC_MAX_MG_VETERAN;
    if (stars >= POPC_STARS_TRUSTED) return POPC_MAX_MG_TRUSTED;
    if (stars >= POPC_STARS_ESTAB)   return POPC_MAX_MG_ESTAB;
    return POPC_MAX_MG_NEW;
}

// =========================================================================
// audit_probability
// =========================================================================
uint16_t audit_probability(uint8_t stars) {
    if (stars >= POPC_STARS_VETERAN) return POPC_AUDIT_PROB_VETERAN;
    if (stars >= POPC_STARS_TRUSTED) return POPC_AUDIT_PROB_TRUSTED;
    if (stars >= POPC_STARS_ESTAB)   return POPC_AUDIT_PROB_ESTAB;
    return POPC_AUDIT_PROB_NEW;
}

// =========================================================================
// compute_audit_seed
// SHA256(block_id || commit || checkpoints_root) — 96 bytes input
// =========================================================================
Hash256 compute_audit_seed(const Hash256& block_id,
                            const Hash256& commit,
                            const Hash256& checkpoints_root) {
    uint8_t buf[96];
    std::memcpy(buf,      block_id.data(),         32);
    std::memcpy(buf + 32, commit.data(),            32);
    std::memcpy(buf + 64, checkpoints_root.data(),  32);

    Hash256 out{};
    SHA256_CTX ctx;
    SHA256_Init(&ctx);
    SHA256_Update(&ctx, buf, 96);
    SHA256_Final(out.data(), &ctx);
    return out;
}

// =========================================================================
// is_audit_triggered
// SHA256(audit_seed || commitment_id || period_index_le16)
// Take first 4 bytes as uint32_le, mod 1000, compare < audit_prob_permille
// =========================================================================
bool is_audit_triggered(const Hash256& audit_seed,
                        const Hash256& commitment_id,
                        uint16_t period_index,
                        uint16_t audit_prob_permille) {
    // Build 66-byte input: 32 + 32 + 2
    uint8_t buf[66];
    std::memcpy(buf,      audit_seed.data(),     32);
    std::memcpy(buf + 32, commitment_id.data(),  32);
    // period_index as little-endian uint16
    buf[64] = (uint8_t)(period_index & 0xFF);
    buf[65] = (uint8_t)((period_index >> 8) & 0xFF);

    uint8_t digest[32];
    SHA256_CTX ctx;
    SHA256_Init(&ctx);
    SHA256_Update(&ctx, buf, 66);
    SHA256_Final(digest, &ctx);

    // First 4 bytes as little-endian uint32
    uint32_t val = (uint32_t)digest[0]
                 | ((uint32_t)digest[1] << 8)
                 | ((uint32_t)digest[2] << 16)
                 | ((uint32_t)digest[3] << 24);

    return (val % 1000) < (uint32_t)audit_prob_permille;
}

// =========================================================================
// PoPCRegistry::register_commitment
// =========================================================================
bool PoPCRegistry::register_commitment(const PoPCCommitment& c, std::string* err) {
    // Validate duration
    bool valid_duration = false;
    static constexpr size_t N = sizeof(POPC_DURATIONS) / sizeof(POPC_DURATIONS[0]);
    for (size_t i = 0; i < N; ++i) {
        if (POPC_DURATIONS[i] == c.duration_months) { valid_duration = true; break; }
    }
    if (!valid_duration) {
        if (err) *err = "invalid duration_months: must be 1, 3, 6, 9, or 12";
        return false;
    }

    if (c.bond_sost_stocks <= 0) {
        if (err) *err = "bond_sost_stocks must be > 0";
        return false;
    }

    if (c.gold_amount_mg <= 0) {
        if (err) *err = "gold_amount_mg must be > 0";
        return false;
    }

    if (c.eth_wallet.empty()) {
        if (err) *err = "eth_wallet must not be empty";
        return false;
    }

    if (c.gold_token != "XAUT" && c.gold_token != "PAXG") {
        if (err) *err = "gold_token must be 'XAUT' or 'PAXG'";
        return false;
    }

    // No duplicate commitment_id
    for (const auto& existing : commitments_) {
        if (existing.commitment_id == c.commitment_id) {
            if (err) *err = "duplicate commitment_id";
            return false;
        }
    }

    commitments_.push_back(c);
    return true;
}

// =========================================================================
// PoPCRegistry::find
// =========================================================================
const PoPCCommitment* PoPCRegistry::find(const Hash256& commitment_id) const {
    for (const auto& c : commitments_) {
        if (c.commitment_id == commitment_id) return &c;
    }
    return nullptr;
}

// =========================================================================
// PoPCRegistry::list_active
// =========================================================================
std::vector<PoPCCommitment> PoPCRegistry::list_active() const {
    std::vector<PoPCCommitment> out;
    for (const auto& c : commitments_) {
        if (c.status == PoPCStatus::ACTIVE) out.push_back(c);
    }
    return out;
}

// =========================================================================
// PoPCRegistry::list_by_user
// =========================================================================
std::vector<PoPCCommitment> PoPCRegistry::list_by_user(const PubKeyHash& pkh) const {
    std::vector<PoPCCommitment> out;
    for (const auto& c : commitments_) {
        if (c.user_pkh == pkh) out.push_back(c);
    }
    return out;
}

// =========================================================================
// PoPCRegistry::complete
// =========================================================================
bool PoPCRegistry::complete(const Hash256& commitment_id, std::string* err) {
    for (auto& c : commitments_) {
        if (c.commitment_id == commitment_id) {
            if (c.status != PoPCStatus::ACTIVE) {
                if (err) *err = "commitment is not ACTIVE";
                return false;
            }
            c.status = PoPCStatus::COMPLETED;
            update_reputation(c.user_pkh, true);
            return true;
        }
    }
    if (err) *err = "commitment_id not found";
    return false;
}

// =========================================================================
// PoPCRegistry::slash
// =========================================================================
bool PoPCRegistry::slash(const Hash256& commitment_id, const std::string& reason,
                          std::string* err) {
    (void)reason; // Stored in audit log externally; registry records the status change
    for (auto& c : commitments_) {
        if (c.commitment_id == commitment_id) {
            if (c.status != PoPCStatus::ACTIVE) {
                if (err) *err = "commitment is not ACTIVE";
                return false;
            }
            c.status = PoPCStatus::SLASHED;
            update_reputation(c.user_pkh, false);
            return true;
        }
    }
    if (err) *err = "commitment_id not found";
    return false;
}

// =========================================================================
// PoPCRegistry::get_reputation
// Returns default (0-star, not blacklisted) if no record exists.
// =========================================================================
PoPCReputation PoPCRegistry::get_reputation(const PubKeyHash& pkh) const {
    for (const auto& r : reputations_) {
        if (r.user_pkh == pkh) return r;
    }
    PoPCReputation def{};
    def.user_pkh = pkh;
    def.stars = POPC_STARS_NEW;
    def.contracts_completed = 0;
    def.contracts_slashed = 0;
    def.blacklisted = false;
    return def;
}

// =========================================================================
// PoPCRegistry::update_reputation
// Stars tier schedule:
//   0 → 1 after 1 successful completion (not slashed)
//   1 → 3 after 3 total completions
//   3 → 5 after 5 total completions
// Any slash: star tier does NOT advance. Blacklisted after 3 slashes.
// =========================================================================
void PoPCRegistry::update_reputation(const PubKeyHash& pkh, bool success) {
    // Find or create reputation record
    PoPCReputation* rep = nullptr;
    for (auto& r : reputations_) {
        if (r.user_pkh == pkh) { rep = &r; break; }
    }
    if (!rep) {
        PoPCReputation fresh{};
        fresh.user_pkh = pkh;
        fresh.stars = POPC_STARS_NEW;
        fresh.contracts_completed = 0;
        fresh.contracts_slashed = 0;
        fresh.blacklisted = false;
        reputations_.push_back(fresh);
        rep = &reputations_.back();
    }

    if (rep->blacklisted) return; // Blacklisted users receive no further updates

    if (success) {
        if (rep->contracts_completed < 0xFFFF) rep->contracts_completed++;

        // Advance star tier based on total completions.
        // Thresholds: ESTAB(1★) at 2, TRUSTED(3★) at 5, VETERAN(5★) at 10.
        // One completion is not enough to advance from NEW(0★).
        uint16_t completed = rep->contracts_completed;
        if (completed >= 10 && rep->stars < POPC_STARS_VETERAN) {
            rep->stars = POPC_STARS_VETERAN;
        } else if (completed >= 5 && rep->stars < POPC_STARS_TRUSTED) {
            rep->stars = POPC_STARS_TRUSTED;
        } else if (completed >= 2 && rep->stars < POPC_STARS_ESTAB) {
            rep->stars = POPC_STARS_ESTAB;
        }
    } else {
        if (rep->contracts_slashed < 0xFFFF) rep->contracts_slashed++;
        if (rep->contracts_slashed >= 3) {
            rep->blacklisted = true;
        }
    }
}

// =========================================================================
// PoPCRegistry::active_count
// =========================================================================
size_t PoPCRegistry::active_count() const {
    size_t n = 0;
    for (const auto& c : commitments_) {
        if (c.status == PoPCStatus::ACTIVE) n++;
    }
    return n;
}

// =========================================================================
// PoPCRegistry::total_bonded_stocks
// Sums bond_sost_stocks for all ACTIVE commitments.
// Guarded against int64 overflow (stops accumulating at INT64_MAX).
// =========================================================================
int64_t PoPCRegistry::total_bonded_stocks() const {
    int64_t total = 0;
    for (const auto& c : commitments_) {
        if (c.status == PoPCStatus::ACTIVE) {
            // Overflow guard
            if (c.bond_sost_stocks > 0 &&
                total > (int64_t)0x7FFFFFFFFFFFFFFFLL - c.bond_sost_stocks) {
                total = (int64_t)0x7FFFFFFFFFFFFFFFLL;
                break;
            }
            total += c.bond_sost_stocks;
        }
    }
    return total;
}

// =========================================================================
// PoPCRegistry::save
// Format:
// {
//   "commitments": [ { ... }, ... ],
//   "reputations": [ { ... }, ... ]
// }
// =========================================================================
bool PoPCRegistry::save(const std::string& path, std::string* err) const {
    std::ofstream f(path);
    if (!f.is_open()) {
        if (err) *err = "cannot open " + path + " for writing";
        return false;
    }

    f << "{\n";

    // --- commitments ---
    f << "  \"commitments\": [\n";
    for (size_t i = 0; i < commitments_.size(); ++i) {
        const auto& c = commitments_[i];
        f << "    {\n";
        f << "      \"commitment_id\": \""      << hash256_to_hex(c.commitment_id)   << "\",\n";
        f << "      \"user_pkh\": \""            << pkh_to_hex(c.user_pkh)            << "\",\n";
        f << "      \"eth_wallet\": \""          << json_escape(c.eth_wallet)         << "\",\n";
        f << "      \"gold_token\": \""          << json_escape(c.gold_token)         << "\",\n";
        f << "      \"gold_amount_mg\": "        << c.gold_amount_mg                  << ",\n";
        f << "      \"bond_sost_stocks\": "      << c.bond_sost_stocks                << ",\n";
        f << "      \"duration_months\": "       << (int)c.duration_months            << ",\n";
        f << "      \"start_height\": "          << c.start_height                    << ",\n";
        f << "      \"end_height\": "            << c.end_height                      << ",\n";
        f << "      \"bond_pct_bps\": "          << (int)c.bond_pct_bps               << ",\n";
        f << "      \"reward_pct_bps\": "        << (int)c.reward_pct_bps             << ",\n";
        f << "      \"status\": \""              << status_to_str(c.status)           << "\",\n";
        f << "      \"sost_price_usd_micro\": "  << c.sost_price_usd_micro            << ",\n";
        f << "      \"gold_price_usd_micro\": "  << c.gold_price_usd_micro            << "\n";
        f << "    }";
        if (i + 1 < commitments_.size()) f << ",";
        f << "\n";
    }
    f << "  ],\n";

    // --- reputations ---
    f << "  \"reputations\": [\n";
    for (size_t i = 0; i < reputations_.size(); ++i) {
        const auto& r = reputations_[i];
        f << "    {\n";
        f << "      \"user_pkh\": \""             << pkh_to_hex(r.user_pkh)          << "\",\n";
        f << "      \"stars\": "                  << (int)r.stars                    << ",\n";
        f << "      \"contracts_completed\": "    << (int)r.contracts_completed      << ",\n";
        f << "      \"contracts_slashed\": "      << (int)r.contracts_slashed        << ",\n";
        f << "      \"blacklisted\": "            << (r.blacklisted ? "true" : "false") << "\n";
        f << "    }";
        if (i + 1 < reputations_.size()) f << ",";
        f << "\n";
    }
    f << "  ]\n";

    f << "}\n";
    return true;
}

// =========================================================================
// PoPCRegistry::load
// Parses the JSON written by save(). Uses the same manual block-extraction
// approach as addressbook.cpp and wallet_policy.cpp.
//
// Strategy: scan for top-level arrays by finding '{' ... '}' blocks.
// The outer object contains two arrays. We parse each '{...}' sub-block
// and determine if it's a commitment or reputation by checking for
// distinguishing keys.
// =========================================================================
bool PoPCRegistry::load(const std::string& path, std::string* err) {
    std::ifstream f(path);
    if (!f.is_open()) {
        // Not an error — file may not exist yet
        commitments_.clear();
        reputations_.clear();
        return true;
    }

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    commitments_.clear();
    reputations_.clear();

    // Find the position of "commitments" and "reputations" arrays so we know
    // which section each '{...}' block belongs to.
    auto commitments_pos = content.find("\"commitments\"");
    auto reputations_pos = content.find("\"reputations\"");

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

        // Determine which array this block belongs to by its position vs the
        // "commitments" / "reputations" key positions.
        bool in_commitments = (commitments_pos != std::string::npos &&
                                pos > commitments_pos &&
                               (reputations_pos == std::string::npos ||
                                pos < reputations_pos));
        bool in_reputations = (reputations_pos != std::string::npos &&
                                pos > reputations_pos);

        if (in_commitments) {
            std::string cid_hex = extract_str(block, "commitment_id");
            if (cid_hex.empty()) { pos = block_end; continue; }

            PoPCCommitment c{};
            c.commitment_id      = hex_to_hash256(cid_hex);
            c.user_pkh           = hex_to_pkh(extract_str(block, "user_pkh"));
            c.eth_wallet         = extract_str(block, "eth_wallet");
            c.gold_token         = extract_str(block, "gold_token");
            c.gold_amount_mg     = extract_int(block, "gold_amount_mg");
            c.bond_sost_stocks   = extract_int(block, "bond_sost_stocks");
            c.duration_months    = (uint16_t)extract_int(block, "duration_months");
            c.start_height       = extract_int(block, "start_height");
            c.end_height         = extract_int(block, "end_height");
            c.bond_pct_bps       = (uint16_t)extract_int(block, "bond_pct_bps");
            c.reward_pct_bps     = (uint16_t)extract_int(block, "reward_pct_bps");
            c.status             = status_from_str(extract_str(block, "status"));
            c.sost_price_usd_micro = extract_int(block, "sost_price_usd_micro");
            c.gold_price_usd_micro = extract_int(block, "gold_price_usd_micro");
            commitments_.push_back(std::move(c));

        } else if (in_reputations) {
            std::string pkh_hex = extract_str(block, "user_pkh");
            if (pkh_hex.empty()) { pos = block_end; continue; }

            PoPCReputation r{};
            r.user_pkh            = hex_to_pkh(pkh_hex);
            r.stars               = (uint8_t)extract_int(block, "stars");
            r.contracts_completed = (uint16_t)extract_int(block, "contracts_completed");
            r.contracts_slashed   = (uint16_t)extract_int(block, "contracts_slashed");
            r.blacklisted         = extract_bool(block, "blacklisted");
            reputations_.push_back(std::move(r));
        }

        pos = block_end;
    }

    return true;
}

} // namespace sost
