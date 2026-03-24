// script.h — Minimal script engine for SOST multisig
// Supports: OP_0, OP_1..OP_16, OP_DUP, OP_HASH160, OP_EQUAL,
//           OP_EQUALVERIFY, OP_CHECKSIG, OP_CHECKMULTISIG
#pragma once
#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include <vector>
#include <string>
#include <cstdint>

namespace sost {

// Opcodes
constexpr uint8_t OP_0              = 0x00;
constexpr uint8_t OP_PUSHDATA_MIN   = 0x01; // 1-75: push N bytes
constexpr uint8_t OP_PUSHDATA_MAX   = 0x4B;
constexpr uint8_t OP_1              = 0x51;
constexpr uint8_t OP_2              = 0x52;
constexpr uint8_t OP_3              = 0x53;
constexpr uint8_t OP_16             = 0x60;
constexpr uint8_t OP_DUP            = 0x76;
constexpr uint8_t OP_HASH160        = 0xA9;
constexpr uint8_t OP_EQUAL          = 0x87;
constexpr uint8_t OP_EQUALVERIFY    = 0x88;
constexpr uint8_t OP_CHECKSIG       = 0xAC;
constexpr uint8_t OP_CHECKMULTISIG  = 0xAE;

// New output type for script hash (P2SH-like)
constexpr uint8_t OUT_SCRIPT_HASH   = 0x30;

// Script hash address prefix
constexpr const char* SOST3_PREFIX = "sost3";

// Multisig limits
constexpr uint32_t MAX_MULTISIG_KEYS = 15;

// Activation height — current tip ~1300, +700 buffer
constexpr int64_t MULTISIG_ACTIVATION_HEIGHT = 2000;

// ---------------------------------------------------------------------------
// Script type: just a byte vector
// ---------------------------------------------------------------------------
using Script = std::vector<Byte>;

// ---------------------------------------------------------------------------
// Build standard scripts
// ---------------------------------------------------------------------------

// P2SH scriptPubKey: OP_HASH160 <20-byte hash> OP_EQUAL
Script make_p2sh_script_pubkey(const PubKeyHash& script_hash);

// Multisig redeemScript: OP_M <pk1> <pk2> ... <pkN> OP_N OP_CHECKMULTISIG
Script make_multisig_redeem_script(uint32_t m, const std::vector<PubKey>& pubkeys);

// P2SH scriptSig: OP_0 <sig1> <sig2> ... <redeemScript>
Script make_p2sh_script_sig(const std::vector<Sig64>& sigs, const Script& redeem_script);

// ---------------------------------------------------------------------------
// Script hash (HASH160 of script)
// ---------------------------------------------------------------------------
PubKeyHash hash_script(const Script& script);

// ---------------------------------------------------------------------------
// Address encoding for script hash
// ---------------------------------------------------------------------------
std::string script_hash_to_address(const PubKeyHash& script_hash);
bool address_to_script_hash(const std::string& addr, PubKeyHash& out);
bool is_script_hash_address(const std::string& addr);

// ---------------------------------------------------------------------------
// Script evaluation context
// ---------------------------------------------------------------------------
struct ScriptEvalContext {
    Hash256 sighash;          // precomputed sighash for CHECKSIG/CHECKMULTISIG
    int64_t spend_height{0};  // for activation check
};

// Evaluate a script (scriptSig + scriptPubKey concatenated, or separate)
// Returns true if script executes successfully (top of stack is truthy)
bool eval_script(
    const Script& script_sig,
    const Script& script_pubkey,
    const ScriptEvalContext& ctx,
    std::string* err = nullptr);

// Evaluate P2SH: run scriptSig, check hash, then evaluate redeemScript
bool eval_p2sh(
    const Script& script_sig,
    const PubKeyHash& expected_hash,
    const ScriptEvalContext& ctx,
    std::string* err = nullptr);

} // namespace sost
