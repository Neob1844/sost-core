#pragma once
// =============================================================================
// SOST — Phase 5: Merkle Tree
// Bitcoin-style double-SHA256 merkle root computation.
//
// Algorithm:
//   1. If 0 leaves → return 0x00*32
//   2. If 1 leaf  → return the single txid (already double-hashed)
//   3. If odd count → duplicate last leaf
//   4. Pairwise combine: SHA256(SHA256(left || right))
//   5. Repeat until 1 node remains = merkle root
//
// SECURITY NOTE (mutation / CVE-2012-2459 style):
//   We expose a `mutated` flag (Bitcoin Core style). If any internal layer
//   combines a *real* identical pair (left == right where both existed as
//   separate nodes, not just "duplicate-last"), we set mutated=true.
//   Block validation SHOULD reject mutated blocks.
// =============================================================================

#include <sost/transaction.h>

#include <string>
#include <vector>

namespace sost {

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

/// Double-SHA256 of concatenated left||right (64 bytes → 32 bytes)
Hash256 MerkleHash(const Hash256& left, const Hash256& right);

/// Compute a single layer of the merkle tree.
/// Pairs adjacent nodes; duplicates last if odd count.
/// If `mutated` is non-null, it is set to true if a real identical pair
/// (nodes[i] == nodes[i+1]) is encountered.
std::vector<Hash256> MerkleLayer(const std::vector<Hash256>& nodes, bool* mutated = nullptr);

/// Compute the merkle root from a list of transaction IDs.
/// Returns 0x00*32 for empty input.
/// If `mutated` is non-null, it is set to true if mutation is detected.
Hash256 ComputeMerkleRoot(const std::vector<Hash256>& txids, bool* mutated = nullptr);

/// Compute the merkle root from a list of transactions.
/// Serializes each tx, computes txid, then builds merkle tree.
/// Returns false if any txid computation fails.
/// If `mutated` is non-null, it is set to true if mutation is detected.
bool ComputeMerkleRootFromTxs(
    const std::vector<Transaction>& txs,
    Hash256& out_root,
    bool* mutated,
    std::string* err = nullptr);

// Backward-compatible overload (existing callers)
inline bool ComputeMerkleRootFromTxs(
    const std::vector<Transaction>& txs,
    Hash256& out_root,
    std::string* err = nullptr)
{
    return ComputeMerkleRootFromTxs(txs, out_root, nullptr, err);
}

} // namespace sost
