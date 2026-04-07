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
// Dynamic checkpoint override — loaded from checkpoint.json at startup
// Falls back to hardcoded values above if file doesn't exist.
// ═══════════════════════════════════════════════════════════════════
struct DynamicCheckpoints {
    bool loaded{false};
    std::string assumevalid_hash;
    uint32_t assumevalid_height{0};
    std::vector<HardCheckpoint> extra_checkpoints;
};

// Global dynamic state (set once at startup by load_dynamic_checkpoints)
inline DynamicCheckpoints& get_dynamic() {
    static DynamicCheckpoints dc;
    return dc;
}

// Load checkpoint.json from working directory or /etc/sost/checkpoint.json
// Format: {"assumevalid_height":3225,"assumevalid_hash":"41cd3f...","checkpoints":[{"height":3200,"hash":"1af5..."}]}
// Returns true if file was loaded, false if using hardcoded fallback.
inline bool load_dynamic_checkpoints(const std::string& path = "") {
    auto& dc = get_dynamic();
    std::vector<std::string> paths;
    if (!path.empty()) paths.push_back(path);
    paths.push_back("checkpoint.json");
    paths.push_back("/etc/sost/checkpoint.json");

    for (const auto& p : paths) {
        FILE* f = fopen(p.c_str(), "r");
        if (!f) continue;
        std::string data;
        char buf[4096];
        while (size_t n = fread(buf, 1, sizeof(buf), f)) data.append(buf, n);
        fclose(f);

        // Simple JSON parsing (no dependency) — find assumevalid_height and hash
        auto find_str = [&](const std::string& key) -> std::string {
            auto pos = data.find("\"" + key + "\"");
            if (pos == std::string::npos) return "";
            pos = data.find("\"", pos + key.size() + 2);
            if (pos == std::string::npos) return "";
            auto end = data.find("\"", pos + 1);
            if (end == std::string::npos) return "";
            return data.substr(pos + 1, end - pos - 1);
        };
        auto find_int = [&](const std::string& key) -> uint32_t {
            auto pos = data.find("\"" + key + "\"");
            if (pos == std::string::npos) return 0;
            pos = data.find(":", pos);
            if (pos == std::string::npos) return 0;
            return (uint32_t)atoi(data.c_str() + pos + 1);
        };

        uint32_t h = find_int("assumevalid_height");
        std::string hash = find_str("assumevalid_hash");
        if (h > 0 && hash.size() == 64) {
            dc.assumevalid_height = h;
            dc.assumevalid_hash = hash;
            dc.loaded = true;
            printf("[CHECKPOINT] Loaded dynamic checkpoint from %s: height=%u hash=%s\n",
                   p.c_str(), h, hash.substr(0, 16).c_str());
            return true;
        }
    }
    return false; // use hardcoded fallback
}

// ═══════════════════════════════════════════════════════════════════
// Functions — use dynamic override if loaded, else hardcoded
// ═══════════════════════════════════════════════════════════════════

inline uint32_t get_assumevalid_height() {
    auto& dc = get_dynamic();
    return dc.loaded ? dc.assumevalid_height : ASSUMEVALID_HEIGHT;
}

inline const std::string& get_assumevalid_hash() {
    auto& dc = get_dynamic();
    return dc.loaded ? dc.assumevalid_hash : ASSUMEVALID_BLOCK_HASH;
}

inline bool is_hard_checkpoint(uint32_t height, const std::string& hash) {
    // Check hardcoded first
    if (height <= LAST_HARD_CHECKPOINT_HEIGHT) {
        for (const auto& cp : HARD_CHECKPOINTS) {
            if (cp.height == height && cp.block_hash == hash) return true;
        }
    }
    // Check dynamic extras
    auto& dc = get_dynamic();
    for (const auto& cp : dc.extra_checkpoints) {
        if (cp.height == height && cp.block_hash == hash) return true;
    }
    return false;
}

inline bool has_assumevalid_anchor() {
    return !get_assumevalid_hash().empty() && get_assumevalid_height() > 0;
}

inline bool is_block_under_assumevalid(uint32_t block_height,
                                        bool chain_contains_anchor) {
    if (!has_assumevalid_anchor()) return false;
    if (!chain_contains_anchor) return false;
    return block_height <= get_assumevalid_height();
}

inline bool can_skip_cx_recomputation(uint32_t block_height,
                                       const std::string& block_hash,
                                       bool chain_contains_anchor,
                                       bool full_verify_mode) {
    if (full_verify_mode) return false;
    if (is_hard_checkpoint(block_height, block_hash)) return true;
    if (is_block_under_assumevalid(block_height, chain_contains_anchor))
        return true;
    return false;
}

} // namespace sost
