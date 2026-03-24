// hd_wallet.h — BIP39 seed phrase support for SOST
// Compatible with web wallet: entropy → BIP39 mnemonic → PBKDF2 seed → private key
#pragma once
#include "sost/tx_signer.h"
#include "sost/address.h"
#include <array>
#include <string>
#include <vector>

namespace sost {
namespace bip39 {

// Generate 128 bits of entropy using OpenSSL RAND_bytes
bool generate_entropy(std::array<uint8_t, 16>& out, std::string* err = nullptr);

// Convert 128-bit entropy to 12-word BIP39 mnemonic
std::vector<std::string> entropy_to_mnemonic(const std::array<uint8_t, 16>& entropy);

// Convert 12-word mnemonic back to entropy (validates checksum)
bool mnemonic_to_entropy(const std::vector<std::string>& words,
                          std::array<uint8_t, 16>& out,
                          std::string* err = nullptr);

// Validate mnemonic (word count, dictionary, checksum)
bool validate_mnemonic(const std::vector<std::string>& words,
                        std::string* err = nullptr);

// Derive 32-byte seed from mnemonic via PBKDF2-HMAC-SHA512 (2048 iterations)
// Compatible with web wallet: seed IS the private key (no BIP32 derivation)
bool mnemonic_to_seed(const std::vector<std::string>& words,
                       PrivKey& out_seed,
                       std::string* err = nullptr);

// Full wallet creation result
struct HDWalletResult {
    std::array<uint8_t, 16> entropy;
    std::vector<std::string> mnemonic;
    PrivKey privkey;
    PubKey pubkey;
    PubKeyHash pkh;
    std::string address;
};

// Create new HD wallet (entropy → mnemonic → seed → keypair → address)
bool create_hd_wallet(HDWalletResult& out, std::string* err = nullptr);

// Restore from mnemonic words
bool restore_from_mnemonic(const std::vector<std::string>& words,
                            HDWalletResult& out,
                            std::string* err = nullptr);

// Lookup word index in BIP39 wordlist (-1 if not found)
int word_index(const std::string& word);

// Get word by index (0-2047)
const char* word_at(int index);

} // namespace bip39
} // namespace sost
