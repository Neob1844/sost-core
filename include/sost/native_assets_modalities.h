// native_assets_modalities.h — Tokenization modality helpers (V30000).
//
// The four tokenization modalities (Tokenize / Auction / Draw / Project Funding)
// add NO new consensus rules. They COMPOSE primitives that are already
// consensus-validated:
//   - native asset genesis/issue/transfer/burn  (this fork, height >= 30000)
//   - OUT_ESCROW_LOCK (0x11): time-locked, beneficiary-bound escrow  (live)
//   - OUT_HTLC_LOCK  (0x12): hashlock + refund atomic-swap leg        (live)
//
// This header provides the PURE, deterministic, publicly-recomputable pieces
// that make a modality auditable — most importantly the Draw winner selection,
// whose entropy is a committed future block hash (unknown to participants at
// entry time, recomputable by anyone afterwards).
#pragma once
#include <array>
#include <cstdint>
#include <vector>
#include <string>
#include <algorithm>
#include "sost/transaction.h"   // Byte, Hash256
#include "sost/types.h"         // Bytes32
#include "sost/crypto.h"        // sha256

namespace sost {
namespace modalities {

// ---- Draw: verifiable winner selection -------------------------------------
//
// winner_index = be64( SHA256( entropy_block_hash || draw_id || count_LE ) ) % count
//
// entropy_block_hash : hash of the committed close block (unknown at entry time)
// draw_id            : 32-byte draw identifier (domain separation across draws)
// participant_count  : number of valid, canonically-ordered entries (>0)
//
// Participants are canonically ordered by entry txid ascending; the caller maps
// the returned index into that ordered list. Modulo bias is negligible for any
// practical participant_count versus 2^64 and is documented, not hidden.
inline uint64_t draw_select_index(const Hash256& entropy_block_hash,
                                  const Hash256& draw_id,
                                  uint64_t participant_count) {
    if (participant_count == 0) return 0;
    std::vector<Byte> buf;
    buf.reserve(72);
    buf.insert(buf.end(), entropy_block_hash.begin(), entropy_block_hash.end());
    buf.insert(buf.end(), draw_id.begin(), draw_id.end());
    for (int i = 0; i < 8; ++i)
        buf.push_back(static_cast<Byte>((participant_count >> (8 * i)) & 0xFF));
    Bytes32 h = sost::sha256(buf.data(), buf.size());
    uint64_t v = 0;                       // big-endian first 8 bytes
    for (int i = 0; i < 8; ++i)
        v = (v << 8) | static_cast<uint64_t>(h[i]);
    return v % participant_count;
}

// Canonical participant ordering: ascending by 32-byte entry txid.
inline void draw_canonical_order(std::vector<Hash256>& entry_txids) {
    std::sort(entry_txids.begin(), entry_txids.end(),
              [](const Hash256& a, const Hash256& b) {
                  return std::lexicographical_compare(a.begin(), a.end(),
                                                      b.begin(), b.end());
              });
}

// ---- Modality identifiers ---------------------------------------------------
// A modality instance (auction/draw/project) is identified the same way a
// native asset is: by the first funding outpoint, so the id is unforgeable and
// unique. compute_asset_id() in native_assets.h is reused by callers; this
// enum only tags the coordination record.
enum class ModalityKind : uint8_t {
    TOKENIZE        = 0,   // plain asset create/issue/transfer/burn
    AUCTION         = 1,   // asset escrow + atomic asset<->SOST settlement
    DRAW            = 2,   // entry pool + block-entropy selection + payout
    PROJECT_FUNDING = 3,   // contribution escrow + milestone release / refund
};

} // namespace modalities
} // namespace sost
