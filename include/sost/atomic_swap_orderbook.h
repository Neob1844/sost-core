// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap — off-chain maker/taker order board (OTC-2)
// =============================================================================
//
// Pure, non-consensus, non-custodial. This module models a P2P swap OFFER and
// validates it BEFORE any HTLC is built. It NEVER holds funds, NEVER signs,
// NEVER broadcasts, NEVER contacts a chain, and adds NO consensus rule. It is a
// userspace helper so a wallet/UI can describe and sanity-check a swap.
//
// Two safety jobs:
//   1. Timeout ordering — reuse the atomic-swap discipline (the responder's
//      refund window must open FIRST, the initiator's LAST, with a margin).
//      A mis-ordered offer is rejected so a wallet never locks into a swap the
//      counterparty could grief.
//   2. Issuer-freeze honesty — flag assets whose central issuer can freeze /
//      blacklist an address (USDT, USDC, PAXG, XAUT). For those, perfect HTLC
//      atomicity is NOT guaranteed (the issuer can freeze a leg after lock), so
//      the offer carries an explicit warning. BTC/ETH/BNB have no asset-level
//      issuer freeze.
// =============================================================================
#pragma once

#include "sost/atomic_swap_coordinator.h"  // Role
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {

using coordinator::Role;  // Initiator / Responder (from atomic_swap_coordinator.h)

// Supported swap assets. SOST is always one leg; the other is a supported
// crypto/issuer asset. (Asset transfer itself is out of scope — only metadata.)
enum class Asset : uint8_t { SOST, BTC, ETH, BNB, USDT, USDC, PAXG, XAUT };

const char* AssetName(Asset a);
bool        AssetParse(const std::string& s, Asset& out);  // case-insensitive

// Issuer-freeze: a centrally-issued token whose issuer can freeze/blacklist an
// address, breaking HTLC atomicity at the asset level. True for USDT, USDC,
// PAXG, XAUT. False for SOST, BTC, ETH, BNB.
bool        AssetHasIssuerFreeze(Asset a);
// Human-facing warning string for a freezable asset; "" for non-freezable.
std::string IssuerFreezeWarning(Asset a);

enum class OfferStatus : uint8_t {
    Open, Taken, Locked, Claimed, Refunded, Cancelled, Expired
};
const char* OfferStatusName(OfferStatus s);

// An off-chain P2P offer. The maker is conventionally the swap INITIATOR (knows
// the secret behind `hashlock`). Refund heights are stated on a common
// normalised axis (the wallet normalises across chains before filling these).
struct Offer {
    std::string id;                              // opaque maker-chosen id
    Role        maker_role = Role::Initiator;
    Asset       give = Asset::SOST;              // asset the maker gives
    Asset       want = Asset::BTC;               // asset the maker wants
    int64_t     give_amount = 0;                 // base units of `give`
    int64_t     want_amount = 0;                 // base units of `want` (price = want/give)
    std::array<uint8_t, 32> hashlock{};          // sha256(secret); maker holds secret
    int64_t     initiator_refund_height = 0;     // T1 — opens LAST
    int64_t     responder_refund_height = 0;     // T2 — opens FIRST (< T1 - margin)
    int64_t     safety_margin_min_blocks = 6;    // required T1 - T2 minimum
    OfferStatus status = OfferStatus::Open;
};

struct OfferValidation {
    bool                     ok = false;
    std::vector<std::string> errors;    // hard failures (offer must be rejected)
    std::vector<std::string> warnings;  // non-fatal (issuer-freeze, etc.)
};

// Validate an offer's structure, timeout ordering and asset honesty. ok==true
// iff there are no errors; warnings may still be present (e.g. issuer-freeze).
OfferValidation ValidateOffer(const Offer& o);

}  // namespace atomic_swap
}  // namespace sost
