// hd_wallet.cpp — BIP39 seed phrase implementation
// Compatible with SOST web wallet: entropy → mnemonic → PBKDF2 → privkey
#include "sost/hd_wallet.h"
#include "sost/bip39_wordlist.h"
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <openssl/evp.h>
#include <algorithm>
#include <cstring>
#include <map>
#include <sstream>

namespace sost {
namespace bip39 {

// Build reverse lookup on first use
static std::map<std::string, int>& get_word_map() {
    static std::map<std::string, int> wmap;
    if (wmap.empty()) {
        for (int i = 0; i < BIP39_WORDLIST_SIZE; ++i) {
            wmap[BIP39_WORDLIST[i]] = i;
        }
    }
    return wmap;
}

int word_index(const std::string& word) {
    auto& m = get_word_map();
    auto it = m.find(word);
    return (it != m.end()) ? it->second : -1;
}

const char* word_at(int index) {
    if (index < 0 || index >= BIP39_WORDLIST_SIZE) return nullptr;
    return BIP39_WORDLIST[index];
}

bool generate_entropy(std::array<uint8_t, 16>& out, std::string* err) {
    if (RAND_bytes(out.data(), 16) != 1) {
        if (err) *err = "RAND_bytes failed";
        return false;
    }
    return true;
}

// Helper: get bit at position from byte array (MSB-first)
static int get_bit(const uint8_t* data, int pos) {
    return (data[pos / 8] >> (7 - (pos % 8))) & 1;
}

// Helper: set bit at position in byte array (MSB-first)
static void set_bit(uint8_t* data, int pos, int val) {
    if (val) data[pos / 8] |= (1 << (7 - (pos % 8)));
}

std::vector<std::string> entropy_to_mnemonic(const std::array<uint8_t, 16>& entropy) {
    // SHA256 of entropy for checksum
    uint8_t hash[32];
    SHA256(entropy.data(), 16, hash);

    // 132 bits: 128 entropy + 4 checksum
    uint8_t all_bits[17] = {};
    std::memcpy(all_bits, entropy.data(), 16);
    // Copy top 4 bits of hash[0] into bits 128-131
    for (int i = 0; i < 4; ++i) {
        int bit_val = (hash[0] >> (7 - i)) & 1;
        set_bit(all_bits, 128 + i, bit_val);
    }

    std::vector<std::string> words;
    words.reserve(12);

    for (int w = 0; w < 12; ++w) {
        int idx = 0;
        for (int b = 0; b < 11; ++b) {
            idx = (idx << 1) | get_bit(all_bits, w * 11 + b);
        }
        words.push_back(BIP39_WORDLIST[idx]);
    }

    return words;
}

bool mnemonic_to_entropy(const std::vector<std::string>& words,
                          std::array<uint8_t, 16>& out,
                          std::string* err) {
    if (words.size() != 12) {
        if (err) *err = "expected 12 words, got " + std::to_string(words.size());
        return false;
    }

    // Convert words to 11-bit indices
    uint16_t indices[12];
    for (int i = 0; i < 12; ++i) {
        std::string lower = words[i];
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        int idx = word_index(lower);
        if (idx < 0) {
            if (err) *err = "unknown word: " + words[i];
            return false;
        }
        indices[i] = (uint16_t)idx;
    }

    // Reconstruct 132 bits from 12 x 11-bit values
    uint8_t all_bits[17] = {};
    for (int w = 0; w < 12; ++w) {
        for (int b = 0; b < 11; ++b) {
            int bit_val = (indices[w] >> (10 - b)) & 1;
            set_bit(all_bits, w * 11 + b, bit_val);
        }
    }

    // First 128 bits = entropy, bits 128-131 = checksum
    std::memcpy(out.data(), all_bits, 16);

    // Verify checksum
    uint8_t hash[32];
    SHA256(out.data(), 16, hash);
    uint8_t expected_cs = (hash[0] >> 4) & 0x0F;
    uint8_t actual_cs = 0;
    for (int i = 0; i < 4; ++i) {
        actual_cs = (actual_cs << 1) | get_bit(all_bits, 128 + i);
    }

    if (expected_cs != actual_cs) {
        if (err) *err = "invalid checksum";
        return false;
    }

    return true;
}

bool validate_mnemonic(const std::vector<std::string>& words, std::string* err) {
    std::array<uint8_t, 16> entropy;
    return mnemonic_to_entropy(words, entropy, err);
}

bool mnemonic_to_seed(const std::vector<std::string>& words,
                       PrivKey& out_seed,
                       std::string* err) {
    // Validate first
    if (!validate_mnemonic(words, err)) return false;

    // Join words with spaces
    std::string mnemonic;
    for (size_t i = 0; i < words.size(); ++i) {
        if (i > 0) mnemonic += ' ';
        // Lowercase for consistency
        std::string lower = words[i];
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        mnemonic += lower;
    }

    // PBKDF2-HMAC-SHA512, salt="mnemonic", 2048 iterations, 32 bytes output
    // Compatible with web wallet: crypto.subtle.deriveBits('PBKDF2', salt='mnemonic', iter=2048, SHA-512, 256 bits)
    const char* salt = "mnemonic";
    uint8_t derived[32];

    int rc = PKCS5_PBKDF2_HMAC(
        mnemonic.c_str(), (int)mnemonic.size(),
        (const uint8_t*)salt, 8,
        2048,
        EVP_sha512(),
        32,
        derived
    );

    if (rc != 1) {
        if (err) *err = "PBKDF2 derivation failed";
        return false;
    }

    std::memcpy(out_seed.data(), derived, 32);

    // Wipe sensitive data
    OPENSSL_cleanse(derived, sizeof(derived));
    OPENSSL_cleanse(&mnemonic[0], mnemonic.size());

    return true;
}

bool create_hd_wallet(HDWalletResult& out, std::string* err) {
    // 1. Generate entropy
    if (!generate_entropy(out.entropy, err)) return false;

    // 2. Entropy → mnemonic
    out.mnemonic = entropy_to_mnemonic(out.entropy);

    // 3. Mnemonic → seed (= private key)
    if (!mnemonic_to_seed(out.mnemonic, out.privkey, err)) return false;

    // 4. Private key → public key
    if (!DerivePublicKey(out.privkey, out.pubkey, err)) return false;

    // 5. Public key → address
    out.pkh = ComputePubKeyHash(out.pubkey);
    out.address = address_encode(out.pkh);

    return true;
}

bool restore_from_mnemonic(const std::vector<std::string>& words,
                            HDWalletResult& out,
                            std::string* err) {
    // 1. Validate and extract entropy
    if (!mnemonic_to_entropy(words, out.entropy, err)) return false;

    // 2. Store mnemonic
    out.mnemonic = words;

    // 3. Mnemonic → seed (= private key)
    if (!mnemonic_to_seed(words, out.privkey, err)) return false;

    // 4. Private key → public key
    if (!DerivePublicKey(out.privkey, out.pubkey, err)) return false;

    // 5. Public key → address
    out.pkh = ComputePubKeyHash(out.pubkey);
    out.address = address_encode(out.pkh);

    return true;
}

} // namespace bip39
} // namespace sost
