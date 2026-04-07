// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// checkpoints.h — Hard checkpoints and assumevalid anchor for fast sync.
//
// This file is SEPARATE from params.h by design.
// These mechanisms do NOT change consensus — they only control whether
// expensive ConvergenceX recomputation is skipped for historical blocks
// during initial sync.
//
// Trust model:
//   1. Hard checkpoints: exact height + hash match required.
//      Lower height alone is NEVER sufficient.
//   2. Assumevalid anchor: if a known block hash exists on the active
//      chain, ancestors of that branch can skip expensive CX recomputation.
//      If the anchor is not on the active chain, no fast trust.
//
// What is ALWAYS verified (even during fast sync):
//   - Header structure and magic bytes
//   - Timestamp / MTP / future drift
//   - cASERT bitsQ compliance
//   - Commit <= target (PoW inequality)
//   - Coinbase split (50/25/25) and constitutional addresses
//   - Transaction structure and semantic rules
//   - UTXO set updates (ConnectBlock)
//
// What is skipped (trusted historical blocks only):
//   - Full 100,000-round ConvergenceX gradient descent recomputation
//   - 4GB scratchpad reconstruction
//   - Stability basin re-verification
#pragma once
#include <string>
#include <vector>
#include <cstdint>

namespace sost {

struct HardCheckpoint {
    uint32_t height;
    std::string block_hash;
};

// Hard checkpoints: a block is checkpoint-trusted ONLY if its height
// AND hash match exactly. Lower height alone is NOT enough.
// Empty at genesis. Updated with each source release.
static const std::vector<HardCheckpoint> HARD_CHECKPOINTS = {
    {0,    "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37"},
    {500,  "c3830001702d6bc79ff290d415c091825b2b5a78e4b4104a5ea08b3e045bb770"},
    {1000, "c7c9553b43bf48062065bac3d727fb0a03ab42eec6c8a791f4794ed26e5cd138"},
    {1500, "1d6c7d4c5594a264ab36e9436395f27cc4588a05958464d96f5acede03614c2f"},
    {2000, "53cb6ee535b798de0f1b7f71736795af5704ce52b7c98e2c77e16fc28f876322"},
    {2500, "55d131446926521673a2be5242220f69835a9c15e6d50962852d3c55cb32715c"},
    {3000, "494bd3081d9641c84a1ba71f00f3fb99a7598c8b48fe7adb3db8747539573402"},
    {3100, "c97537bf039cbc9feb8c4a4dad57745ef026a647e000dc4aa218d485b38f8290"},
    {3150, "2089540e4c08dd6fb0bd90e181c995ef53b991215e7a4a566cb82c5443731a4c"},
    {3200, "1af5229815b9df80899c32db9a809b26367b402bb8630c9dd227d1bf607be830"},
    {3225, "41cd3f888b64a9a04051f49129764b2153414685c9ad23ad902abe3e8d75a43d"},
};

// Quick range pre-check before iterating checkpoints.
// Do NOT use this alone to trust blocks.
static const uint32_t LAST_HARD_CHECKPOINT_HEIGHT = 3225;

// Assumevalid anchor: if this block hash exists on the active chain,
// ancestors of that branch can skip expensive ConvergenceX recomputation
// (but NOT cheap/semantic verification).
// This allows new nodes to sync without full CX proof data for historical blocks.
// Updated: 2026-04-07 — block 3225 verified on mainnet.
static const std::string ASSUMEVALID_BLOCK_HASH = "41cd3f888b64a9a04051f49129764b2153414685c9ad23ad902abe3e8d75a43d";
static const uint32_t ASSUMEVALID_HEIGHT = 3225;

// ═══════════════════════════════════════════════════════════════════
// Functions — explicit, non-ambiguous
// ═══════════════════════════════════════════════════════════════════

// Returns true ONLY if height matches a checkpoint AND hash matches
// exactly. Returns false for: wrong hash, lower height without exact
// match, or lower height alone.
inline bool is_hard_checkpoint(uint32_t height, const std::string& hash) {
    if (height > LAST_HARD_CHECKPOINT_HEIGHT) return false;
    for (const auto& cp : HARD_CHECKPOINTS) {
        if (cp.height == height && cp.block_hash == hash) {
            return true;
        }
    }
    return false;
}

// Returns true only if an assumevalid anchor is configured
// (non-empty hash and height > 0).
inline bool has_assumevalid_anchor() {
    return !ASSUMEVALID_BLOCK_HASH.empty() && ASSUMEVALID_HEIGHT > 0;
}

// Returns true if a block can skip expensive CX recomputation because
// it is an ancestor of the assumevalid anchor on the active chain.
//
// chain_contains_anchor: the caller MUST verify this by checking that
// the active chain at ASSUMEVALID_HEIGHT has hash == ASSUMEVALID_BLOCK_HASH.
// If the anchor is NOT on the active chain, this returns false.
inline bool is_block_under_assumevalid(uint32_t block_height,
                                        bool chain_contains_anchor) {
    if (!has_assumevalid_anchor()) return false;
    if (!chain_contains_anchor) return false;
    return block_height <= ASSUMEVALID_HEIGHT;
}

// Master decision: should we skip expensive CX recomputation?
// Returns true ONLY if one of:
//   1. Block matches a hard checkpoint exactly (height + hash)
//   2. Block is under assumevalid anchor AND anchor is on active chain
// Returns false in ALL other cases (including full-verify mode).
inline bool can_skip_cx_recomputation(uint32_t block_height,
                                       const std::string& block_hash,
                                       bool chain_contains_anchor,
                                       bool full_verify_mode) {
    // --full-verify overrides everything
    if (full_verify_mode) return false;

    // Hard checkpoint exact match
    if (is_hard_checkpoint(block_height, block_hash)) return true;

    // Assumevalid ancestor trust
    if (is_block_under_assumevalid(block_height, chain_contains_anchor))
        return true;

    return false;
}

} // namespace sost
