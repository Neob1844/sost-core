#pragma once

#include "sost/transaction.h"
#include <array>
#include <string>
#include <vector>

namespace sost {

// -----------------------------------------------------------------------------
// Spent output info (needed for sighash: amount + type of referenced UTXO)
// -----------------------------------------------------------------------------

struct SpentOutput {
    int64_t amount{0};       // Stockshis of the UTXO being spent
    uint8_t type{0};         // Output type of the UTXO being spent
};

// -----------------------------------------------------------------------------
// Key types
// -----------------------------------------------------------------------------

using PrivKey = std::array<Byte, 32>;    // secp256k1 private key (big-endian)
using PubKey  = std::array<Byte, 33>;    // Compressed public key (02/03 prefix)
using Sig64   = std::array<Byte, 64>;    // Compact signature (r[32] || s[32])
using PubKeyHash = std::array<Byte, 20>; // RIPEMD160(SHA256(pubkey))

// -----------------------------------------------------------------------------
// Sighash computation (BIP143-simplified, Design v1.2a Section 6)
// -----------------------------------------------------------------------------

// Precomputed hash: SHA256(SHA256( prev_txid[0]||prev_index[0] || ... ))
Hash256 ComputeHashPrevouts(const Transaction& tx);

// Precomputed hash: SHA256(SHA256( amount[0]||type[0]||pkh[0]||plen[0]||payload[0] || ... ))
Hash256 ComputeHashOutputs(const Transaction& tx);

// Full sighash for input[i]:
//   SHA256(SHA256(version || tx_type || hashPrevouts || prev_txid[i] ||
//                 prev_index[i] || spent_amount[i] || spent_type[i] ||
//                 hashOutputs || genesis_hash))
Hash256 ComputeSighash(
    const Transaction& tx,
    size_t input_index,
    const SpentOutput& spent,
    const Hash256& genesis_hash);

// -----------------------------------------------------------------------------
// ECDSA operations (secp256k1, compact 64-byte, LOW-S enforced)
// -----------------------------------------------------------------------------

// Sign a sighash with a private key. Returns compact (r||s) with LOW-S.
bool SignSighash(
    const PrivKey& privkey,
    const Hash256& sighash,
    Sig64& out_sig,
    std::string* err = nullptr);

// Verify a compact signature against a sighash and compressed pubkey.
// Checks: valid point, non-zero sig, r in [1,n-1], s in [1,n/2], ECDSA verify.
bool VerifySighash(
    const PubKey& pubkey,
    const Hash256& sighash,
    const Sig64& sig,
    std::string* err = nullptr);

// Check if s <= curve_order / 2 (LOW-S rule, Design v1.2a Section 13 E5)
bool IsLowS(const Sig64& sig);

// If s > n/2, negate it: s = n - s. Returns true if negation was needed.
bool EnforceLowS(Sig64& sig);

// -----------------------------------------------------------------------------
// Key utilities
// -----------------------------------------------------------------------------

// Generate a random secp256k1 keypair (for testing / wallet)
bool GenerateKeyPair(
    PrivKey& out_privkey,
    PubKey& out_pubkey,
    std::string* err = nullptr);

// Derive compressed public key from private key
bool DerivePublicKey(
    const PrivKey& privkey,
    PubKey& out_pubkey,
    std::string* err = nullptr);

// Compute RIPEMD160(SHA256(pubkey)) — the address hash
PubKeyHash ComputePubKeyHash(const PubKey& pubkey);

// -----------------------------------------------------------------------------
// High-level: sign a full transaction input
// -----------------------------------------------------------------------------

// Signs input[input_index] of tx:
//   1. Compute sighash
//   2. ECDSA sign with LOW-S
//   3. Write signature into tx.inputs[input_index].signature
//   4. Write pubkey into tx.inputs[input_index].pubkey
bool SignTransactionInput(
    Transaction& tx,
    size_t input_index,
    const SpentOutput& spent,
    const Hash256& genesis_hash,
    const PrivKey& privkey,
    std::string* err = nullptr);

// Verify input[input_index] of tx:
//   1. Compute sighash
//   2. Check pubkey matches expected_pkh
//   3. ECDSA verify with LOW-S check
bool VerifyTransactionInput(
    const Transaction& tx,
    size_t input_index,
    const SpentOutput& spent,
    const Hash256& genesis_hash,
    const PubKeyHash& expected_pkh,
    std::string* err = nullptr);

} // namespace sost
