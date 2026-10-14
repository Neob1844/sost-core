// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once

// =============================================================================
// multisig.h — native M-of-N multisig (V17, activation MULTISIG_HEIGHT)
//
// Normative reference: docs/v40000/NATIVE_MULTISIG_SPEC_40000.md (r4) and
// docs/v40000/MULTISIG_OPEN_DECISIONS_CLOSED.md (D1-D13).
//
// This module holds the pure, deterministic pieces of the design:
//   * policy encoding, canonical-policy rule R26 and the policy hash MSH (§4)
//   * the byte-level capsule envelope allowed on an OUT_MULTISIG payload (§7.3)
//   * the v2 sighash (§5.2) with CHAIN_ID and the spent-output commitment
//   * the sigcheck count of a transaction (§8)
//   * bech32m multisig addresses sostms / tsostms / dsostms (§10)
//   * a detailed LOW-S ECDSA verifier that reports S4 / S5 / failure apart
//
// No script engine, no OP_CHECKMULTISIG, no trial-and-error signature matching:
// every multisig signature names the key it was made with (key_index).
// =============================================================================

#include "sost/transaction.h"
#include "sost/tx_signer.h"

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace sost {

using PubKey33 = std::array<Byte, 33>;
using ChainId  = std::array<Byte, 32>;

inline constexpr char   MS_DOMAIN[]          = "SOST-MS1";          // 8 bytes, no terminator hashed
inline constexpr size_t MS_DOMAIN_LEN        = 8;
inline constexpr char   SIGHASH_V2_TAG[]     = "SOST-SIGHASH-V2";   // 15 bytes, no terminator hashed
inline constexpr size_t SIGHASH_V2_TAG_LEN   = 15;
inline constexpr size_t SIGHASH_V2_PREIMAGE_LEN = 246;

// ---------------------------------------------------------------------------
// Networks and CHAIN_ID (frozen literals, spec §2.2). The literals live in
// params.h next to the fork heights; these helpers only select one.
// ---------------------------------------------------------------------------
enum class MsNetwork : uint8_t { MAINNET = 0, TESTNET = 1, DEVNET = 2 };

// Network of THIS build (compile-time profile: SOST_DEVNET_FORKS -> devnet,
// SOST_TESTNET_FORKS -> testnet, otherwise mainnet).
MsNetwork ActiveMsNetwork();
// "mainnet" | "testnet" | "dev" (the sost-cli --network strings). "devnet" is
// accepted as an alias of "dev".
bool MsNetworkFromName(const std::string& name, MsNetwork& out);
const char* MsNetworkName(MsNetwork n);          // "mainnet" | "testnet" | "dev"
const ChainId& ChainIdFor(MsNetwork n);
const char* MultisigHrp(MsNetwork n);            // "sostms" | "tsostms" | "dsostms"

// ---------------------------------------------------------------------------
// Policy (§4)
// ---------------------------------------------------------------------------
// policy bytes = M u8 || N u8 || PK_0 .. PK_{N-1}
std::vector<Byte> SerializeMultisigPolicy(uint8_t m, const std::vector<PubKey33>& keys);
// MSH = RIPEMD160(SHA256("SOST-MS1" || policy))
PubKeyHash ComputeMultisigPolicyHash(uint8_t m, const std::vector<PubKey33>& keys);
// R26: 1 <= M <= N <= 15, every key 33 bytes with prefix 02/03 that parses on the
// curve, keys strictly increasing (memcmp). Returns false with a reason.
bool CheckMultisigPolicy(uint8_t m, const std::vector<PubKey33>& keys, std::string* err = nullptr);
// Wallet helper: sort keys (any order) into canonical order and check the policy.
// Rejects duplicates (they cannot be made strictly increasing).
bool MakeCanonicalPolicy(uint8_t m, std::vector<PubKey33> keys,
                         std::vector<PubKey33>& out_sorted, std::string* err = nullptr);

// ---------------------------------------------------------------------------
// OUT_MULTISIG payload envelope (§7.3, D10) — consensus. A pure function of the
// payload bytes; capsule_type and the body are relay policy, not checked here.
// ---------------------------------------------------------------------------
bool MultisigOutputPayloadOk(const std::vector<Byte>& payload);

// ---------------------------------------------------------------------------
// Sighash v2 (§5.2)
// ---------------------------------------------------------------------------
// Wire encoding of one output: amount i64 || type || pkh[20] || len u16 || payload.
void SerializeOutputWire(std::vector<Byte>& out, int64_t amount, uint8_t type,
                         const std::array<Byte, 20>& pkh, const std::vector<Byte>& payload);

struct SighashV2Precomp {
    Hash256 hash_prevouts{};
    Hash256 hash_spent_outputs{};
    Hash256 hash_outputs{};
    bool    ok{false};
};
// Computes the three per-transaction hashes ONCE (linear hashing). `spent` has
// one entry per input (amount, type, pubkey_hash, payload of the spent UTXO).
SighashV2Precomp PrecomputeSighashV2(const Transaction& tx, const std::vector<SpentOutput>& spent);

// The 20-byte auth field for input i: MSH(policy_i) for auth_kind 0x01, zeros otherwise.
std::array<Byte, 20> InputAuthField(const Transaction& tx, size_t input_index);

// 246-byte preimage for input i (exposed for vectors/tests).
std::vector<Byte> BuildSighashV2Preimage(const Transaction& tx, size_t input_index,
                                         const SpentOutput& spent_i, const SighashV2Precomp& pre,
                                         const ChainId& chain_id, const Hash256& genesis_hash);
Hash256 ComputeSighashV2(const Transaction& tx, size_t input_index,
                         const SpentOutput& spent_i, const SighashV2Precomp& pre,
                         const ChainId& chain_id, const Hash256& genesis_hash);

// ---------------------------------------------------------------------------
// Detailed LOW-S ECDSA verification (no logging, no side effects)
// ---------------------------------------------------------------------------
enum class SigVerdict : uint8_t {
    OK        = 0,
    ZERO      = 1,   // all 64 bytes zero                       -> S4
    RANGE     = 2,   // r or s zero / >= n, or s > n/2 (high-S)  -> S5
    BAD_KEY   = 3,   // pubkey does not parse                    -> S3/S6
    INVALID   = 4,   // ECDSA verification failed                -> S6 / S18
};
SigVerdict VerifyEcdsaLowS(const PubKey33& pubkey, const Hash256& msg, const Sig64& sig);
bool PubKeyParses(const PubKey33& pubkey);

// ---------------------------------------------------------------------------
// Sigchecks (§8, D4) — from the parsed transaction alone.
// ---------------------------------------------------------------------------
int64_t TxSigchecks(const Transaction& tx);

// ---------------------------------------------------------------------------
// Exact serialized size (§3.6, D11). Identical to the historical 133-byte
// estimate for every version-1 transaction.
// ---------------------------------------------------------------------------
size_t TxSerializedSizeExact(const Transaction& tx);
size_t TxInputV2Size(const TxInput& in);

// ---------------------------------------------------------------------------
// Signing helpers (wallet / offline signer; not consensus)
// ---------------------------------------------------------------------------
// Sign v2 single-sig input i (auth_kind 0x00): writes signature + pubkey.
bool SignInputV2Single(Transaction& tx, size_t input_index, const std::vector<SpentOutput>& spent,
                       const ChainId& chain_id, const Hash256& genesis_hash,
                       const PrivKey& privkey, std::string* err = nullptr);
// Produce one multisig signature for input i (auth_kind 0x01) with `privkey`, whose
// public key must be in the input's policy. Returns the key index and signature;
// does NOT modify the transaction.
bool SignInputV2Multisig(const Transaction& tx, size_t input_index, const std::vector<SpentOutput>& spent,
                         const ChainId& chain_id, const Hash256& genesis_hash,
                         const PrivKey& privkey, uint8_t& out_key_index, Sig64& out_sig,
                         std::string* err = nullptr);

// ---------------------------------------------------------------------------
// bech32m multisig addresses (§10)
// ---------------------------------------------------------------------------
std::string MultisigAddressEncode(const PubKeyHash& msh, MsNetwork net);
// Strict decoder: lowercase only, HRP of `net`, valid bech32m checksum, data =
// 0x01 || MSH (21 bytes), canonical zero padding. `err` gets the reason.
bool MultisigAddressDecode(const std::string& addr, MsNetwork net, PubKeyHash& out_msh,
                           std::string* err = nullptr);
// True if `addr` starts with any multisig HRP + '1' (cheap classifier for wallets).
bool LooksLikeMultisigAddress(const std::string& addr);

// Generic bech32m (exposed for the BIP-350 checksum vectors in the tests).
std::string Bech32mEncode(const std::string& hrp, const std::vector<uint8_t>& data5);
bool Bech32mDecode(const std::string& s, std::string& hrp_out, std::vector<uint8_t>& data5_out,
                   std::string* err = nullptr);

} // namespace sost
