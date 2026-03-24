// psbt.h — SOST-PSBT: Offline signing format with multisig-ready inputs
// Wallet-layer only — NO consensus change.
// Format: JSON + base64 transport. Magic prefix: "sost-psbt\xff"
#pragma once
#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include "sost/address.h"
#include <string>
#include <vector>
#include <cstdint>

namespace sost {

// ---------------------------------------------------------------------------
// PSBT input type
// ---------------------------------------------------------------------------
enum class PSBTInputType : int {
    P2PKH = 0,
    REDEEMSCRIPT_HASH_MULTISIG = 1,
};

// ---------------------------------------------------------------------------
// Partial signature (pubkey + sig, both hex)
// ---------------------------------------------------------------------------
struct PSBTPartialSig {
    std::string pubkey_hex;     // 66 hex chars (33 bytes compressed)
    std::string signature_hex;  // 128 hex chars (64 bytes compact r||s)
};

// ---------------------------------------------------------------------------
// PSBT input
// ---------------------------------------------------------------------------
struct PSBTInput {
    // UTXO reference
    std::string prev_txid_hex;
    uint32_t    prev_vout{0};
    int64_t     amount{0};
    uint8_t     output_type{0};

    // Input type
    PSBTInputType input_type{PSBTInputType::P2PKH};

    // For P2PKH: owner pubkey hash (hex)
    std::string pkh_hex;

    // For multisig (redeemScript-hash)
    std::string redeem_script_hex;
    std::vector<std::string> pubkeys_hex;
    uint32_t required_sigs{1};

    // Partial signatures collected so far
    std::vector<PSBTPartialSig> partial_sigs;

    bool finalized{false};
};

// ---------------------------------------------------------------------------
// PSBT output
// ---------------------------------------------------------------------------
struct PSBTOutput {
    int64_t     amount{0};
    std::string address;
    uint8_t     output_type{0};
    std::string pkh_hex;
};

// ---------------------------------------------------------------------------
// PSBT — the top-level container
// ---------------------------------------------------------------------------
struct PSBT {
    uint32_t version{0};
    std::vector<PSBTInput>  inputs;
    std::vector<PSBTOutput> outputs;
    std::string change_address;
    int64_t     fee{0};
    bool        complete{false};
};

// ---------------------------------------------------------------------------
// UTXO reference for creating a PSBT
// ---------------------------------------------------------------------------
struct PSBTUtxoRef {
    Hash256  txid;
    uint32_t vout{0};
    int64_t  amount{0};
    uint8_t  output_type{0};
    PubKeyHash pkh{};
};

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

// Create an unsigned PSBT from inputs, outputs, and change
bool psbt_create(
    PSBT& out,
    const std::vector<PSBTUtxoRef>& utxo_refs,
    const std::string& to_address,
    int64_t send_amount,
    const std::string& change_address,
    int64_t fee,
    std::string* err = nullptr);

// Sign result
struct PSBTSignResult {
    size_t signatures_added{0};
    size_t inputs_matched{0};
    bool   complete{false};
    std::string error;
};

// Sign inputs that match the given private key
PSBTSignResult psbt_sign(
    PSBT& psbt,
    const PrivKey& privkey,
    const Hash256& genesis_hash);

// Combine multiple partially-signed PSBTs
bool psbt_combine(
    PSBT& out,
    const std::vector<PSBT>& partials,
    std::string* err = nullptr);

// Finalize: build raw TX hex if complete, else return ""
std::string psbt_finalize(
    PSBT& psbt,
    const Hash256& genesis_hash,
    std::string* err = nullptr);

// Encode to base64 transport (JSON → base64)
std::string psbt_encode(const PSBT& psbt);

// Decode from base64 transport
bool psbt_decode(const std::string& encoded, PSBT& out, std::string* err = nullptr);

// Human-readable description
std::string psbt_describe(const PSBT& psbt);

} // namespace sost
