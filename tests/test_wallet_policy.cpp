// test_wallet_policy.cpp — SOST Wallet Policy Tests
#include <sost/wallet_policy.h>
#include <cstdio>
#include <cstring>
#include <unistd.h>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define RUN(name) do { \
    printf("  %-44s", #name " ..."); fflush(stdout); \
    bool ok_ = name(); \
    printf("%s\n", ok_ ? "PASS" : "*** FAIL ***"); \
    ok_ ? ++g_pass : ++g_fail; \
} while (0)

#define EXPECT(cond) do { if (!(cond)) { \
    printf("\n    EXPECT failed: %s  [%s:%d]\n", #cond, __FILE__, __LINE__); \
    return false; \
}} while (0)

static const int64_t SOST = 100000000LL;

// WP01: Default policy allows everything
static bool WP01_default_allows_all() {
    WalletPolicy p;
    EXPECT(p.CheckSend(1000 * SOST, false, 1000000).empty());
    EXPECT(p.CheckSend(1 * SOST, true, 1000000).empty());
    return true;
}

// WP02: Per-TX limit
static bool WP02_per_tx_limit() {
    WalletPolicy p;
    p.per_tx_limit = 500 * SOST;

    EXPECT(p.CheckSend(499 * SOST, false, 1000000).empty());
    EXPECT(p.CheckSend(500 * SOST, false, 1000000).empty());
    EXPECT(!p.CheckSend(501 * SOST, false, 1000000).empty());
    return true;
}

// WP03: Daily limit
static bool WP03_daily_limit() {
    WalletPolicy p;
    p.daily_send_limit = 1000 * SOST;

    int64_t t = 86400 * 20000;  // some day

    // First send: 600 SOST
    EXPECT(p.CheckSend(600 * SOST, false, t).empty());
    p.RecordSend(600 * SOST, t);

    // Second send: 300 SOST (total 900 < 1000)
    EXPECT(p.CheckSend(300 * SOST, false, t).empty());
    p.RecordSend(300 * SOST, t);

    // Third send: 200 SOST (total 1100 > 1000) — blocked
    EXPECT(!p.CheckSend(200 * SOST, false, t).empty());

    // Next day: resets
    int64_t next_day = t + 86400;
    EXPECT(p.CheckSend(900 * SOST, false, next_day).empty());
    return true;
}

// WP04: Vault mode blocks non-addressbook
static bool WP04_vault_mode() {
    WalletPolicy p;
    p.vault_mode = true;

    EXPECT(!p.CheckSend(1 * SOST, false, 1000000).empty());  // blocked
    EXPECT(p.CheckSend(1 * SOST, true, 1000000).empty());    // allowed
    return true;
}

// WP05: Large TX requires address book
static bool WP05_large_tx_addressbook() {
    WalletPolicy p;
    p.require_addressbook_for_large = true;
    p.large_tx_threshold = 100 * SOST;

    // Below threshold: always OK
    EXPECT(p.CheckSend(99 * SOST, false, 1000000).empty());

    // At/above threshold without address book: blocked
    EXPECT(!p.CheckSend(100 * SOST, false, 1000000).empty());
    EXPECT(!p.CheckSend(200 * SOST, false, 1000000).empty());

    // With address book: OK
    EXPECT(p.CheckSend(200 * SOST, true, 1000000).empty());
    return true;
}

// WP06: Set by name
static bool WP06_set_by_name() {
    WalletPolicy p;
    std::string err;

    EXPECT(p.Set("daily_limit", "500", &err));
    EXPECT(p.daily_send_limit == 500 * SOST);

    EXPECT(p.Set("per_tx_limit", "100", &err));
    EXPECT(p.per_tx_limit == 100 * SOST);

    EXPECT(p.Set("vault_mode", "true", &err));
    EXPECT(p.vault_mode == true);

    EXPECT(p.Set("require_addressbook_for_large", "true", &err));
    EXPECT(p.require_addressbook_for_large == true);

    EXPECT(p.Set("large_tx_threshold", "50", &err));
    EXPECT(p.large_tx_threshold == 50 * SOST);

    EXPECT(!p.Set("nonexistent_key", "value", &err));
    return true;
}

// WP07: Save and load
static bool WP07_save_load() {
    const char* path = "/tmp/sost_test_policy.json";

    {
        WalletPolicy p;
        p.daily_send_limit = 1000 * SOST;
        p.per_tx_limit = 500 * SOST;
        p.require_addressbook_for_large = true;
        p.large_tx_threshold = 100 * SOST;
        p.vault_mode = true;
        std::string err;
        EXPECT(p.Save(path, &err));
    }

    {
        WalletPolicy p;
        std::string err;
        EXPECT(p.Load(path, &err));
        EXPECT(p.daily_send_limit == 1000 * SOST);
        EXPECT(p.per_tx_limit == 500 * SOST);
        EXPECT(p.require_addressbook_for_large == true);
        EXPECT(p.large_tx_threshold == 100 * SOST);
        EXPECT(p.vault_mode == true);
    }

    unlink(path);
    return true;
}

// WP08: Load missing file (defaults apply)
static bool WP08_load_missing() {
    WalletPolicy p;
    p.vault_mode = true;  // set something
    std::string err;
    EXPECT(p.Load("/tmp/sost_nonexistent_policy_12345.json", &err));
    // vault_mode should remain as set (defaults don't overwrite)
    EXPECT(p.vault_mode == true);
    return true;
}

int main() {
    printf("=== SOST Wallet Policy Tests ===\n\n");

    RUN(WP01_default_allows_all);
    RUN(WP02_per_tx_limit);
    RUN(WP03_daily_limit);
    RUN(WP04_vault_mode);
    RUN(WP05_large_tx_addressbook);
    RUN(WP06_set_by_name);
    RUN(WP07_save_load);
    RUN(WP08_load_missing);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
