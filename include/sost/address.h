// address.h — SOST address encoding (sost1 + hex(pkh))
#pragma once
#include "sost/tx_signer.h"
#include <string>

namespace sost {

// Encode PubKeyHash → "sost1" + 40 hex chars (45 chars total)
std::string address_encode(const PubKeyHash& pkh);

// Decode "sost1..." → PubKeyHash. Returns false if invalid.
bool address_decode(const std::string& addr, PubKeyHash& out_pkh);

// Validate address format (prefix + length + hex)
bool address_valid(const std::string& addr);

// Convenience: compressed pubkey → address string
std::string pubkey_to_address(const PubKey& pubkey);

} // namespace sost
