// wallet_policy.cpp — SOST Treasury Safety Profile
#include "sost/wallet_policy.h"
#include <fstream>
#include <cstdio>
#include <ctime>
#include <cstdlib>

namespace sost {

static int64_t current_day(int64_t t) {
    if (t == 0) t = (int64_t)std::time(nullptr);
    return t / 86400;
}

std::string WalletPolicy::CheckSend(int64_t amount, bool addr_in_book,
                                     int64_t current_time) const {
    // Per-TX limit
    if (per_tx_limit > 0 && amount > per_tx_limit) {
        char buf[256];
        snprintf(buf, sizeof(buf),
                 "Amount %lld stocks exceeds per-transaction limit of %lld stocks",
                 (long long)amount, (long long)per_tx_limit);
        return buf;
    }

    // Daily limit
    if (daily_send_limit > 0) {
        int64_t day = current_day(current_time);
        int64_t already_sent = (day == daily_reset_day) ? daily_sent_today : 0;
        if (already_sent + amount > daily_send_limit) {
            char buf[256];
            snprintf(buf, sizeof(buf),
                     "Daily send limit exceeded: already sent %lld + %lld > limit %lld stocks",
                     (long long)already_sent, (long long)amount,
                     (long long)daily_send_limit);
            return buf;
        }
    }

    // Vault mode: require address book
    if (vault_mode && !addr_in_book) {
        return "Vault mode is active: destination must be in trusted address book";
    }

    // Large TX + address book requirement
    if (require_addressbook_for_large && large_tx_threshold > 0 &&
        amount >= large_tx_threshold && !addr_in_book) {
        char buf[256];
        snprintf(buf, sizeof(buf),
                 "Amount >= %lld stocks requires destination in address book "
                 "(policy: require_addressbook_for_large)",
                 (long long)large_tx_threshold);
        return buf;
    }

    return "";  // OK
}

void WalletPolicy::RecordSend(int64_t amount, int64_t current_time) {
    int64_t day = current_day(current_time);
    if (day != daily_reset_day) {
        daily_sent_today = 0;
        daily_reset_day = day;
    }
    daily_sent_today += amount;
}

bool WalletPolicy::Set(const std::string& key, const std::string& value,
                        std::string* err) {
    if (key == "daily_limit") {
        double v = std::strtod(value.c_str(), nullptr);
        daily_send_limit = (int64_t)(v * STOCKS_PER_SOST_POLICY);
    } else if (key == "per_tx_limit") {
        double v = std::strtod(value.c_str(), nullptr);
        per_tx_limit = (int64_t)(v * STOCKS_PER_SOST_POLICY);
    } else if (key == "large_tx_threshold") {
        double v = std::strtod(value.c_str(), nullptr);
        large_tx_threshold = (int64_t)(v * STOCKS_PER_SOST_POLICY);
    } else if (key == "require_addressbook_for_large") {
        require_addressbook_for_large = (value == "true" || value == "1");
    } else if (key == "vault_mode") {
        vault_mode = (value == "true" || value == "1");
    } else {
        if (err) *err = "unknown policy key: " + key;
        return false;
    }
    return true;
}

void WalletPolicy::Print() const {
    auto fmt = [](int64_t stocks) -> std::string {
        if (stocks == 0) return "unlimited";
        char buf[64];
        snprintf(buf, sizeof(buf), "%.8f SOST", (double)stocks / STOCKS_PER_SOST_POLICY);
        return buf;
    };

    printf("SOST Wallet Policy:\n");
    printf("  daily_send_limit:              %s\n", fmt(daily_send_limit).c_str());
    printf("  per_tx_limit:                  %s\n", fmt(per_tx_limit).c_str());
    printf("  require_addressbook_for_large: %s\n",
           require_addressbook_for_large ? "true" : "false");
    printf("  large_tx_threshold:            %s\n", fmt(large_tx_threshold).c_str());
    printf("  vault_mode:                    %s\n", vault_mode ? "true" : "false");
}

// Simple JSON escape
static std::string jp_escape(const std::string& s) {
    std::string r;
    for (char c : s) {
        if (c == '"') r += "\\\"";
        else if (c == '\\') r += "\\\\";
        else r += c;
    }
    return r;
}

bool WalletPolicy::Save(const std::string& path, std::string* err) const {
    std::ofstream f(path);
    if (!f.is_open()) {
        if (err) *err = "cannot open " + path + " for writing";
        return false;
    }
    f << "{\n";
    f << "  \"daily_send_limit_stocks\": " << daily_send_limit << ",\n";
    f << "  \"per_tx_limit_stocks\": " << per_tx_limit << ",\n";
    f << "  \"require_addressbook_for_large\": " << (require_addressbook_for_large ? "true" : "false") << ",\n";
    f << "  \"large_tx_threshold_stocks\": " << large_tx_threshold << ",\n";
    f << "  \"vault_mode\": " << (vault_mode ? "true" : "false") << "\n";
    f << "}\n";
    return true;
}

static std::string find_json_value(const std::string& content, const std::string& key) {
    auto pos = content.find("\"" + key + "\"");
    if (pos == std::string::npos) return "";
    pos = content.find(':', pos);
    if (pos == std::string::npos) return "";
    pos++;
    while (pos < content.size() && (content[pos] == ' ' || content[pos] == '\t')) pos++;
    auto end = content.find_first_of(",}\n", pos);
    if (end == std::string::npos) end = content.size();
    std::string val = content.substr(pos, end - pos);
    // Trim whitespace
    while (!val.empty() && (val.back() == ' ' || val.back() == '\t' || val.back() == '\r'))
        val.pop_back();
    return val;
}

bool WalletPolicy::Load(const std::string& path, std::string* err) {
    std::ifstream f(path);
    if (!f.is_open()) {
        // Not an error — file may not exist yet (defaults apply)
        return true;
    }

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    auto v = find_json_value(content, "daily_send_limit_stocks");
    if (!v.empty()) daily_send_limit = std::strtoll(v.c_str(), nullptr, 10);

    v = find_json_value(content, "per_tx_limit_stocks");
    if (!v.empty()) per_tx_limit = std::strtoll(v.c_str(), nullptr, 10);

    v = find_json_value(content, "require_addressbook_for_large");
    if (!v.empty()) require_addressbook_for_large = (v == "true");

    v = find_json_value(content, "large_tx_threshold_stocks");
    if (!v.empty()) large_tx_threshold = std::strtoll(v.c_str(), nullptr, 10);

    v = find_json_value(content, "vault_mode");
    if (!v.empty()) vault_mode = (v == "true");

    return true;
}

} // namespace sost
