// test_hd_wallet.cpp — BIP39 HD Wallet Tests (20+ tests)
//
// HD01-HD07: Entropy and mnemonic
// HD08-HD10: Validation
// HD11-HD14: Seed derivation
// HD15-HD20: Address and roundtrip

#include <sost/hd_wallet.h>
#include <sost/bip39_wordlist.h>
#include <cstdio>
#include <cstring>
#include <set>
#include <algorithm>

using namespace sost;
using namespace sost::bip39;

static int g_pass = 0, g_fail = 0;

#define RUN(name) do { \
    printf("  %-52s", #name " ..."); fflush(stdout); \
    bool ok_ = name(); \
    printf("%s\n", ok_ ? "PASS" : "*** FAIL ***"); \
    ok_ ? ++g_pass : ++g_fail; \
} while (0)

#define EXPECT(cond) do { if (!(cond)) { \
    printf("\n    EXPECT failed: %s  [%s:%d]\n", #cond, __FILE__, __LINE__); \
    return false; \
}} while (0)

static std::string to_hex(const uint8_t* data, size_t len) {
    std::string r;
    r.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        char buf[3];
        snprintf(buf, sizeof(buf), "%02x", data[i]);
        r += buf;
    }
    return r;
}

// HD01: generate_entropy produces 16 bytes of non-zero data
static bool HD01_generate_entropy() {
    std::array<uint8_t, 16> e1{}, e2{};
    std::string err;
    EXPECT(generate_entropy(e1, &err));
    EXPECT(generate_entropy(e2, &err));
    // Two random outputs should differ
    EXPECT(e1 != e2);
    // At least some bytes should be non-zero
    bool all_zero = true;
    for (auto b : e1) if (b != 0) { all_zero = false; break; }
    EXPECT(!all_zero);
    return true;
}

// HD02: entropy_to_mnemonic produces 12 words
static bool HD02_entropy_to_mnemonic_12_words() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    EXPECT(words.size() == 12);
    return true;
}

// HD03: all mnemonic words are in BIP39 dictionary
static bool HD03_words_in_dictionary() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    for (const auto& w : words) {
        EXPECT(word_index(w) >= 0);
        EXPECT(word_index(w) < 2048);
    }
    return true;
}

// HD04: mnemonic_to_entropy roundtrips correctly
static bool HD04_mnemonic_roundtrip() {
    std::array<uint8_t, 16> entropy_in{}, entropy_out{};
    generate_entropy(entropy_in);
    auto words = entropy_to_mnemonic(entropy_in);
    std::string err;
    EXPECT(mnemonic_to_entropy(words, entropy_out, &err));
    EXPECT(entropy_in == entropy_out);
    return true;
}

// HD05: mnemonic_to_entropy rejects invalid checksum
static bool HD05_reject_bad_checksum() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    // Swap last word to corrupt checksum
    words[11] = (words[11] == "abandon") ? "ability" : "abandon";
    std::array<uint8_t, 16> out{};
    std::string err;
    // May or may not fail depending on whether the swap creates a valid checksum
    // But swapping to a random word almost certainly breaks it
    bool ok = mnemonic_to_entropy(words, out, &err);
    // If it passed, the swapped word happened to have valid checksum (very rare)
    // For robustness, test with a known-bad case
    std::vector<std::string> bad = {"abandon","abandon","abandon","abandon","abandon",
                                     "abandon","abandon","abandon","abandon","abandon",
                                     "abandon","abandon"};
    ok = mnemonic_to_entropy(bad, out, &err);
    EXPECT(!ok); // "abandon" x12 has invalid checksum
    return true;
}

// HD06: mnemonic_to_entropy rejects wrong word count
static bool HD06_reject_wrong_count() {
    std::vector<std::string> too_few = {"abandon","abandon","abandon"};
    std::array<uint8_t, 16> out{};
    std::string err;
    EXPECT(!mnemonic_to_entropy(too_few, out, &err));
    EXPECT(err.find("12") != std::string::npos);
    return true;
}

// HD07: mnemonic_to_entropy rejects unknown words
static bool HD07_reject_unknown_words() {
    std::vector<std::string> bad = {"abandon","abandon","abandon","abandon","abandon",
                                     "abandon","abandon","abandon","abandon","abandon",
                                     "abandon","zzzznotaword"};
    std::array<uint8_t, 16> out{};
    std::string err;
    EXPECT(!mnemonic_to_entropy(bad, out, &err));
    EXPECT(err.find("unknown") != std::string::npos);
    return true;
}

// HD08: validate_mnemonic accepts valid 12 words
static bool HD08_validate_valid() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    std::string err;
    EXPECT(validate_mnemonic(words, &err));
    return true;
}

// HD09: validate_mnemonic rejects 11 words
static bool HD09_validate_rejects_11() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    words.pop_back(); // now 11 words
    std::string err;
    EXPECT(!validate_mnemonic(words, &err));
    return true;
}

// HD10: validate_mnemonic rejects garbage
static bool HD10_validate_rejects_garbage() {
    std::vector<std::string> garbage = {"hello","world","foo","bar","baz",
                                         "qux","quux","corge","grault","garply",
                                         "waldo","fred"};
    std::string err;
    EXPECT(!validate_mnemonic(garbage, &err));
    return true;
}

// HD11: mnemonic_to_seed produces 32-byte key
static bool HD11_seed_32_bytes() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    PrivKey seed{};
    std::string err;
    EXPECT(mnemonic_to_seed(words, seed, &err));
    // Should not be all zeros
    bool all_zero = true;
    for (auto b : seed) if (b != 0) { all_zero = false; break; }
    EXPECT(!all_zero);
    return true;
}

// HD12: mnemonic_to_seed is deterministic
static bool HD12_seed_deterministic() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto words = entropy_to_mnemonic(entropy);
    PrivKey seed1{}, seed2{};
    std::string err;
    EXPECT(mnemonic_to_seed(words, seed1, &err));
    EXPECT(mnemonic_to_seed(words, seed2, &err));
    EXPECT(seed1 == seed2);
    return true;
}

// HD13: create_hd_wallet produces valid address
static bool HD13_create_valid_address() {
    HDWalletResult r;
    std::string err;
    EXPECT(create_hd_wallet(r, &err));
    EXPECT(r.address.size() == 45);
    EXPECT(r.address.substr(0, 5) == "sost1");
    EXPECT(r.mnemonic.size() == 12);
    return true;
}

// HD14: restore_from_mnemonic produces same key as create
static bool HD14_restore_matches_create() {
    HDWalletResult created;
    std::string err;
    EXPECT(create_hd_wallet(created, &err));

    HDWalletResult restored;
    EXPECT(restore_from_mnemonic(created.mnemonic, restored, &err));

    EXPECT(created.privkey == restored.privkey);
    EXPECT(created.pubkey == restored.pubkey);
    EXPECT(created.address == restored.address);
    return true;
}

// HD15: address format correct
static bool HD15_address_format() {
    HDWalletResult r;
    std::string err;
    EXPECT(create_hd_wallet(r, &err));
    EXPECT(r.address.size() == 45);
    EXPECT(r.address.substr(0, 5) == "sost1");
    // Remaining 40 chars should be lowercase hex
    for (size_t i = 5; i < 45; ++i) {
        char c = r.address[i];
        EXPECT((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));
    }
    return true;
}

// HD16: BIP39 test vector — all-zero entropy
static bool HD16_bip39_test_vector_zero_entropy() {
    // Standard test: 16 zero bytes → specific mnemonic
    std::array<uint8_t, 16> zero_entropy{};
    auto words = entropy_to_mnemonic(zero_entropy);
    EXPECT(words.size() == 12);
    // 0x000...0 → "abandon" x11 + "about" (standard BIP39 test vector)
    EXPECT(words[0] == "abandon");
    EXPECT(words[1] == "abandon");
    EXPECT(words[10] == "abandon");
    EXPECT(words[11] == "about"); // checksum gives "about"
    return true;
}

// HD17: same entropy always produces same mnemonic
static bool HD17_entropy_deterministic() {
    std::array<uint8_t, 16> entropy{};
    generate_entropy(entropy);
    auto w1 = entropy_to_mnemonic(entropy);
    auto w2 = entropy_to_mnemonic(entropy);
    EXPECT(w1 == w2);
    return true;
}

// HD18: private key from seed is valid secp256k1 key
static bool HD18_valid_secp256k1_key() {
    HDWalletResult r;
    std::string err;
    EXPECT(create_hd_wallet(r, &err));
    // Verify we can derive public key (proves key is in valid range)
    PubKey pub{};
    EXPECT(DerivePublicKey(r.privkey, pub, &err));
    EXPECT(pub == r.pubkey);
    return true;
}

// HD19: public key is 33 bytes compressed
static bool HD19_compressed_pubkey() {
    HDWalletResult r;
    std::string err;
    EXPECT(create_hd_wallet(r, &err));
    // Compressed pubkey starts with 0x02 or 0x03
    EXPECT(r.pubkey[0] == 0x02 || r.pubkey[0] == 0x03);
    return true;
}

// HD20: multiple create+restore cycles all match
static bool HD20_multiple_roundtrips() {
    for (int trial = 0; trial < 5; ++trial) {
        HDWalletResult created, restored;
        std::string err;
        EXPECT(create_hd_wallet(created, &err));
        EXPECT(restore_from_mnemonic(created.mnemonic, restored, &err));
        EXPECT(created.address == restored.address);
        EXPECT(created.privkey == restored.privkey);
    }
    return true;
}

// HD21: word_index and word_at are inverses
static bool HD21_word_lookup_consistency() {
    for (int i = 0; i < 2048; ++i) {
        const char* w = word_at(i);
        EXPECT(w != nullptr);
        EXPECT(word_index(w) == i);
    }
    EXPECT(word_at(-1) == nullptr);
    EXPECT(word_at(2048) == nullptr);
    EXPECT(word_index("notaword") == -1);
    return true;
}

// HD22: different entropy → different addresses
static bool HD22_unique_addresses() {
    std::set<std::string> addrs;
    for (int i = 0; i < 10; ++i) {
        HDWalletResult r;
        std::string err;
        EXPECT(create_hd_wallet(r, &err));
        addrs.insert(r.address);
    }
    EXPECT(addrs.size() == 10); // all unique
    return true;
}

int main() {
    printf("=== SOST HD Wallet (BIP39) Tests ===\n\n");

    RUN(HD01_generate_entropy);
    RUN(HD02_entropy_to_mnemonic_12_words);
    RUN(HD03_words_in_dictionary);
    RUN(HD04_mnemonic_roundtrip);
    RUN(HD05_reject_bad_checksum);
    RUN(HD06_reject_wrong_count);
    RUN(HD07_reject_unknown_words);
    RUN(HD08_validate_valid);
    RUN(HD09_validate_rejects_11);
    RUN(HD10_validate_rejects_garbage);
    RUN(HD11_seed_32_bytes);
    RUN(HD12_seed_deterministic);
    RUN(HD13_create_valid_address);
    RUN(HD14_restore_matches_create);
    RUN(HD15_address_format);
    RUN(HD16_bip39_test_vector_zero_entropy);
    RUN(HD17_entropy_deterministic);
    RUN(HD18_valid_secp256k1_key);
    RUN(HD19_compressed_pubkey);
    RUN(HD20_multiple_roundtrips);
    RUN(HD21_word_lookup_consistency);
    RUN(HD22_unique_addresses);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
