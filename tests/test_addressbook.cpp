// test_addressbook.cpp — SOST Address Book Tests
#include <sost/addressbook.h>
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

// AB01: Add and check trust level
static bool AB01_add_and_check() {
    AddressBook ab;
    ab.Add("sost1aaa", "Gold Vault", TrustLevel::TRUSTED, 1000);
    EXPECT(ab.Check("sost1aaa") == TrustLevel::TRUSTED);
    EXPECT(ab.Check("sost1zzz") == TrustLevel::UNKNOWN);
    EXPECT(ab.Size() == 1);
    return true;
}

// AB02: Multiple entries
static bool AB02_multiple_entries() {
    AddressBook ab;
    ab.Add("sost1aaa", "Vault", TrustLevel::TRUSTED, 100);
    ab.Add("sost1bbb", "Exchange", TrustLevel::KNOWN, 200);
    ab.Add("sost1ccc", "Scammer", TrustLevel::BLOCKED, 300);
    ab.Add("sost1ddd", "New Friend", TrustLevel::NEW, 400);

    EXPECT(ab.Size() == 4);
    EXPECT(ab.Check("sost1aaa") == TrustLevel::TRUSTED);
    EXPECT(ab.Check("sost1bbb") == TrustLevel::KNOWN);
    EXPECT(ab.Check("sost1ccc") == TrustLevel::BLOCKED);
    EXPECT(ab.Check("sost1ddd") == TrustLevel::NEW);
    return true;
}

// AB03: Remove
static bool AB03_remove() {
    AddressBook ab;
    ab.Add("sost1aaa", "A", TrustLevel::TRUSTED, 100);
    ab.Add("sost1bbb", "B", TrustLevel::KNOWN, 200);
    EXPECT(ab.Size() == 2);

    EXPECT(ab.Remove("sost1aaa"));
    EXPECT(ab.Size() == 1);
    EXPECT(ab.Check("sost1aaa") == TrustLevel::UNKNOWN);
    EXPECT(ab.Check("sost1bbb") == TrustLevel::KNOWN);

    // Remove non-existent
    EXPECT(!ab.Remove("sost1zzz"));
    return true;
}

// AB04: Update existing
static bool AB04_update() {
    AddressBook ab;
    ab.Add("sost1aaa", "Old Label", TrustLevel::NEW, 100);
    EXPECT(ab.Check("sost1aaa") == TrustLevel::NEW);

    ab.Add("sost1aaa", "New Label", TrustLevel::TRUSTED, 200);
    EXPECT(ab.Check("sost1aaa") == TrustLevel::TRUSTED);
    EXPECT(ab.Size() == 1);  // no duplicate

    auto* entry = ab.Get("sost1aaa");
    EXPECT(entry != nullptr);
    EXPECT(entry->label == "New Label");
    return true;
}

// AB05: Get entry details
static bool AB05_get_entry() {
    AddressBook ab;
    ab.Add("sost1aaa", "Gold Vault", TrustLevel::TRUSTED, 1711270800,
           "Constitutional gold vault");

    auto* e = ab.Get("sost1aaa");
    EXPECT(e != nullptr);
    EXPECT(e->address == "sost1aaa");
    EXPECT(e->label == "Gold Vault");
    EXPECT(e->trust == TrustLevel::TRUSTED);
    EXPECT(e->added_time == 1711270800);
    EXPECT(e->notes == "Constitutional gold vault");

    EXPECT(ab.Get("sost1zzz") == nullptr);
    return true;
}

// AB06: Save and load
static bool AB06_save_load() {
    const char* path = "/tmp/sost_test_addressbook.json";

    {
        AddressBook ab;
        ab.Add("sost1aaa", "Vault", TrustLevel::TRUSTED, 1000, "note1");
        ab.Add("sost1bbb", "Ex", TrustLevel::KNOWN, 2000, "note2");
        ab.Add("sost1ccc", "Bad", TrustLevel::BLOCKED, 3000);
        std::string err;
        EXPECT(ab.Save(path, &err));
    }

    {
        AddressBook ab;
        std::string err;
        EXPECT(ab.Load(path, &err));
        EXPECT(ab.Size() == 3);
        EXPECT(ab.Check("sost1aaa") == TrustLevel::TRUSTED);
        EXPECT(ab.Check("sost1bbb") == TrustLevel::KNOWN);
        EXPECT(ab.Check("sost1ccc") == TrustLevel::BLOCKED);

        auto* e = ab.Get("sost1aaa");
        EXPECT(e != nullptr);
        EXPECT(e->label == "Vault");
        EXPECT(e->notes == "note1");
    }

    unlink(path);
    return true;
}

// AB07: Load non-existent file (should succeed with empty book)
static bool AB07_load_missing() {
    AddressBook ab;
    std::string err;
    EXPECT(ab.Load("/tmp/sost_nonexistent_addressbook_12345.json", &err));
    EXPECT(ab.Size() == 0);
    return true;
}

// AB08: Trust level string conversion
static bool AB08_trust_level_strings() {
    EXPECT(TrustLevelFromStr("trusted") == TrustLevel::TRUSTED);
    EXPECT(TrustLevelFromStr("known") == TrustLevel::KNOWN);
    EXPECT(TrustLevelFromStr("new") == TrustLevel::NEW);
    EXPECT(TrustLevelFromStr("blocked") == TrustLevel::BLOCKED);
    EXPECT(TrustLevelFromStr("garbage") == TrustLevel::UNKNOWN);

    EXPECT(std::string(TrustLevelStr(TrustLevel::TRUSTED)) == "trusted");
    EXPECT(std::string(TrustLevelStr(TrustLevel::BLOCKED)) == "blocked");
    return true;
}

int main() {
    printf("=== SOST Address Book Tests ===\n\n");

    RUN(AB01_add_and_check);
    RUN(AB02_multiple_entries);
    RUN(AB03_remove);
    RUN(AB04_update);
    RUN(AB05_get_entry);
    RUN(AB06_save_load);
    RUN(AB07_load_missing);
    RUN(AB08_trust_level_strings);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
