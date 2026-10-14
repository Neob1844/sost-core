// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once

// =============================================================================
// multisig_psst.h — offline multisig workflow (NON-CONSENSUS), spec §12.
//
//   createmultisig -> buildtx (watch-only) -> signtx (offline, x M, independent)
//   -> combinetx -> verifytx -> sendrawtransaction
//
// A "sost-psst-v1" file carries a version-2 transaction template plus everything
// an air-gapped signer needs to recompute the v2 sighash on its own: the network,
// its CHAIN_ID, the genesis, every spent output (amount, type, lock, payload) and
// every multisig policy. The v2 sighash commits to all of it, so a coordinator that
// lies about any spent output only obtains signatures that are invalid on chain.
//
// Rotation = spend the old policy into a new OUT_MULTISIG output (signed by the old
// threshold). No UTXO policy is ever mutated.
// =============================================================================

#include "sost/multisig.h"
#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include "sost/tx_validation.h"

#include <map>
#include <string>
#include <vector>

namespace sost::psst {

inline constexpr const char* PSST_FORMAT   = "sost-psst-v1";
inline constexpr const char* POLICY_FORMAT = "sost-ms-policy-v1";

// ---- policy file (createmultisig) ------------------------------------------
struct Policy {
    MsNetwork net{MsNetwork::MAINNET};
    uint8_t m{0};
    std::vector<PubKey33> keys;          // canonical (sorted) order
    PubKeyHash msh{};
    std::string address;                 // bech32m for `net`
};
bool MakePolicy(MsNetwork net, uint8_t m, const std::vector<PubKey33>& keys_any_order,
                Policy& out, std::string* err = nullptr);
std::string PolicyToJson(const Policy& p);
bool PolicyFromJson(const std::string& text, Policy& out, std::string* err = nullptr);

// ---- PSST ------------------------------------------------------------------
struct Input {
    Hash256  txid{};
    uint32_t vout{0};
    SpentOutput spent;                   // amount, type, pubkey_hash (lock), payload
    uint8_t  auth_kind{AUTH_SINGLE};
    // multisig
    uint8_t  m{0};
    std::vector<PubKey33> keys;
    std::map<uint8_t, Sig64> sigs;       // key_index -> signature
    // single-sig
    bool     single_signed{false};
    Sig64    single_sig{};
    PubKey33 single_pub{};
};

struct Psst {
    MsNetwork net{MsNetwork::MAINNET};
    ChainId   chain_id{};
    Hash256   genesis{};
    std::vector<Input>    inputs;
    std::vector<TxOutput> outputs;
};

// Build a template. Inputs carry no signatures. Fails on any inconsistency.
bool Build(MsNetwork net, const Hash256& genesis, const std::vector<Input>& ins,
           const std::vector<TxOutput>& outs, Psst& out, std::string* err = nullptr);

// Unsigned version-2 template (multisig inputs with K = 0, single-sig inputs zero).
Transaction UnsignedTx(const Psst& p);
// Final transaction: each multisig input takes the M LOWEST key indexes available
// (deterministic, D6). `complete` = every input has its signature(s).
Transaction Assemble(const Psst& p, bool* complete = nullptr);
std::vector<SpentOutput> SpentList(const Psst& p);

int64_t Fee(const Psst& p);                  // sum(spent) - sum(outputs)
size_t  FinalSize(const Psst& p);            // exact size once complete (K = M)
int64_t FinalSigchecks(const Psst& p);

std::string ToJson(const Psst& p);
// Parses and checks the whole file: format, network <-> CHAIN_ID, unsigned_hex
// decodes to exactly the declared inputs/outputs, MSH(policy) == msh == spent
// lock, declared fee == computed fee, and every signature present verifies.
bool FromJson(const std::string& text, Psst& out, std::string* err = nullptr);

// Add every signature the given keys can make (multisig policy keys not yet
// signed, single-sig inputs whose lock is the key's pkh). Returns the number added.
int Sign(Psst& p, const std::vector<PrivKey>& keys, std::string* err = nullptr);

// Merge PSSTs of the SAME template (identical unsigned tx, network, CHAIN_ID,
// genesis, spent outputs and policies). Signatures are unioned; each is verified.
bool Combine(const std::vector<Psst>& parts, Psst& out, std::string* err = nullptr);

struct Report {
    bool complete{false};
    bool valid{false};                 // consensus §7.2-7.5 at `height` (declared spent outputs)
    std::string reason;
    std::string txid;
    size_t size{0};
    int64_t fee{0};
    int64_t sigchecks{0};
    std::vector<std::string> input_status;   // e.g. "multisig 2-of-3: 2 signatures (complete)"
};
// Runs ValidateTransactionConsensus on the assembled tx against a view built from
// the declared spent outputs (UTXO existence is NOT checked; the node does that).
Report Verify(const Psst& p, int64_t height);

} // namespace sost::psst
