// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC counterparty — minimal redeem script builder (Phase 4A-0)
// =============================================================================
//
// THIS IS THE SAFE SUBSET ONLY.
//
// Pure byte-assembly of the BIP-199-style HTLC redeem script that the
// wallet wraps into a P2WSH UTXO on the Bitcoin side of a SOST<->BTC
// atomic swap. NO signing. NO transaction construction. NO address
// derivation (Bech32 lives in a future module). NO private key handling.
// NO network. NO file I/O.
//
// The full design rationale and the scope boundary (why signing is NOT
// in this commit) are documented in:
//   docs/design/ATOMIC_SWAP_BTC_IMPLEMENTATION_DECISION.md
//
// Wire format of the script produced (113-115 bytes typical):
//
//   OP_IF                              (0x63)
//     OP_SHA256                        (0xa8)
//     OP_PUSHBYTES_32 <hashlock>       (0x20 + 32 bytes)
//     OP_EQUALVERIFY                   (0x88)
//     OP_PUSHBYTES_33 <claim_pubkey>   (0x21 + 33 bytes)
//     OP_CHECKSIG                      (0xac)
//   OP_ELSE                            (0x67)
//     OP_PUSHBYTES_N  <refund_height>  (N-byte ScriptNum minimal encoding)
//     OP_CHECKLOCKTIMEVERIFY           (0xb1)
//     OP_DROP                          (0x75)
//     OP_PUSHBYTES_33 <refund_pubkey>  (0x21 + 33 bytes)
//     OP_CHECKSIG                      (0xac)
//   OP_ENDIF                           (0x68)
//
// SHA-256 of this byte sequence is the 32-byte P2WSH witness program.
// The Bech32 address derivation is a separate, future module.
//
// All branches gated by atomic_swap_htlc_active_at(spend_height) on the
// SOST side. This BTC builder is gate-agnostic on its own (it is pure
// computation), but its only caller — the wallet layer — refuses to act
// while the activation gate is INT64_MAX.
// =============================================================================
#pragma once

#include "sost/types.h"
#include <array>
#include <cstdint>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace btc {

// Bitcoin opcode constants used by the HTLC script.
inline constexpr uint8_t OP_IF                  = 0x63;
inline constexpr uint8_t OP_ELSE                = 0x67;
inline constexpr uint8_t OP_ENDIF               = 0x68;
inline constexpr uint8_t OP_DROP                = 0x75;
inline constexpr uint8_t OP_EQUALVERIFY         = 0x88;
inline constexpr uint8_t OP_SHA256              = 0xa8;
inline constexpr uint8_t OP_CHECKSIG            = 0xac;
inline constexpr uint8_t OP_CHECKLOCKTIMEVERIFY = 0xb1;
inline constexpr uint8_t OP_PUSHDATA1           = 0x4c;

// Encode a non-negative integer as a Bitcoin ScriptNum (minimal
// canonical encoding, little-endian, with the high-bit sign-extension
// rule). `value` must be >= 0; the HTLC refund_height is always a
// future block height and therefore non-negative.
std::vector<uint8_t> EncodeScriptNumMinimal(int64_t value);

// Encode `data` with the Bitcoin pushdata convention:
//   length 1..75      -> single length byte
//   length 76..255    -> OP_PUSHDATA1 + 1 length byte
//   length 256..65535 -> OP_PUSHDATA2 + 2 length bytes (little-endian)
//   length > 65535    -> OP_PUSHDATA4 + 4 length bytes (little-endian)
// The HTLC builder never produces pushes larger than 33 bytes, but
// the helper is general so the future signing module can reuse it.
std::vector<uint8_t> EncodePushdata(const std::vector<uint8_t>& data);
std::vector<uint8_t> EncodePushdata(const uint8_t* data, size_t len);

// Build the HTLC redeem script. `claim_pubkey` and `refund_pubkey` MUST
// each be exactly 33 bytes (compressed secp256k1 public keys, prefix
// 0x02 or 0x03). The function does NOT verify the prefix — that is the
// caller's responsibility because the script does not require the
// pubkey to be on-curve until spend time.
std::vector<uint8_t> BuildBtcHtlcRedeemScript(
    const std::array<uint8_t, 32>& hashlock,
    int64_t refund_height,
    const std::array<uint8_t, 33>& claim_pubkey,
    const std::array<uint8_t, 33>& refund_pubkey);

// Compute the future P2WSH witness program: sha256(redeem_script). This
// is the 32-byte value that goes into the BIP-141 SegWit v0 scriptPubKey
// `OP_0 <32 bytes>`. The wallet wraps this into a Bech32 address
// (segwit v0, mainnet "bc1q...", testnet "tb1q...") using a separate
// future module.
Bytes32 BtcHtlcWitnessProgram(const std::vector<uint8_t>& redeem_script);

} // namespace btc
} // namespace atomic_swap
} // namespace sost
