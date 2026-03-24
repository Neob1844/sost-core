// wallet_policy.h — SOST Treasury Safety Profile (wallet-layer, no consensus)
#pragma once
#include <string>
#include <cstdint>
#include <map>

namespace sost {

static const int64_t STOCKS_PER_SOST_POLICY = 100000000LL;

struct WalletPolicy {
    int64_t daily_send_limit{0};           // 0 = no limit (stocks)
    int64_t per_tx_limit{0};               // 0 = no limit (stocks)
    bool    require_addressbook_for_large{false};
    int64_t large_tx_threshold{0};         // stocks
    bool    vault_mode{false};

    // Daily tracking (not persisted — resets on load)
    int64_t daily_sent_today{0};
    int64_t daily_reset_day{0};            // day number (unix_time / 86400)

    // Check if a send is allowed; returns "" if OK, or error message
    std::string CheckSend(int64_t amount, bool addr_in_book,
                          int64_t current_time = 0) const;

    // Record a send (updates daily tracking)
    void RecordSend(int64_t amount, int64_t current_time = 0);

    // Persistence
    bool Save(const std::string& path, std::string* err = nullptr) const;
    bool Load(const std::string& path, std::string* err = nullptr);

    // Helper: set a field by name
    bool Set(const std::string& key, const std::string& value, std::string* err = nullptr);

    // Display
    void Print() const;
};

} // namespace sost
