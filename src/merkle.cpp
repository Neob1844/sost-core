// =============================================================================
// SOST — Phase 5: Merkle Tree Implementation
// =============================================================================

#include <sost/merkle.h>
#include <openssl/sha.h>

#include <cstring>

namespace sost {

// ---------------------------------------------------------------------------
// MerkleHash: SHA256(SHA256(left || right))
// ---------------------------------------------------------------------------

Hash256 MerkleHash(const Hash256& left, const Hash256& right) {
    uint8_t combined[64];
    std::memcpy(combined, left.data(), 32);
    std::memcpy(combined + 32, right.data(), 32);

    Hash256 intermediate{};
    SHA256(combined, 64, intermediate.data());

    Hash256 result{};
    SHA256(intermediate.data(), 32, result.data());
    return result;
}

// ---------------------------------------------------------------------------
// MerkleLayer: compute one level of the tree (with mutation flag)
// ---------------------------------------------------------------------------

std::vector<Hash256> MerkleLayer(const std::vector<Hash256>& nodes, bool* mutated) {
    if (nodes.empty()) return {};

    std::vector<Hash256> parent;
    parent.reserve((nodes.size() + 1) / 2);

    for (size_t i = 0; i < nodes.size(); i += 2) {
        if (i + 1 < nodes.size()) {
            // Real pair exists.
            if (mutated && nodes[i] == nodes[i + 1]) {
                // This indicates a "real" identical pair at this level.
                *mutated = true;
            }
            parent.push_back(MerkleHash(nodes[i], nodes[i + 1]));
        } else {
            // Odd count: duplicate last (Bitcoin-style). Not a "real pair".
            parent.push_back(MerkleHash(nodes[i], nodes[i]));
        }
    }

    return parent;
}

// ---------------------------------------------------------------------------
// ComputeMerkleRoot
// ---------------------------------------------------------------------------

Hash256 ComputeMerkleRoot(const std::vector<Hash256>& txids, bool* mutated) {
    if (mutated) *mutated = false;

    if (txids.empty()) {
        return Hash256{}; // 0x00*32
    }
    if (txids.size() == 1) {
        return txids[0];
    }

    std::vector<Hash256> current = txids;
    while (current.size() > 1) {
        current = MerkleLayer(current, mutated);
    }
    return current[0];
}

// ---------------------------------------------------------------------------
// ComputeMerkleRootFromTxs
// ---------------------------------------------------------------------------

bool ComputeMerkleRootFromTxs(
    const std::vector<Transaction>& txs,
    Hash256& out_root,
    bool* mutated,
    std::string* err)
{
    if (mutated) *mutated = false;

    if (txs.empty()) {
        out_root = Hash256{};
        return true;
    }

    std::vector<Hash256> txids;
    txids.reserve(txs.size());

    for (size_t i = 0; i < txs.size(); ++i) {
        Hash256 txid{};
        if (!txs[i].ComputeTxId(txid, err)) {
            if (err) *err = "ComputeMerkleRootFromTxs: tx[" +
                            std::to_string(i) + "] " + *err;
            return false;
        }
        txids.push_back(txid);
    }

    out_root = ComputeMerkleRoot(txids, mutated);
    return true;
}

} // namespace sost
