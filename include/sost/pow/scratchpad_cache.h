#pragma once
#include "sost/types.h"
#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

namespace sost {

// In-process cache for ConvergenceX scratchpads, keyed by epoch_scratch_key.
//
// The scratchpad seed `skey = epoch_scratch_key(epoch, &chain)` is constant
// for an entire epoch (~131 553 blocks ≈ 53 days). The reference miner used
// to rebuild the 4 GB scratchpad on every mine_one_block() call, which is
// 8-30 s of dead time per tip change. With this cache, every call after the
// first epoch-anchor build hits in <1 ms.
//
// Cap = 2 entries so the handoff at an epoch boundary is smooth (mainnet
// 4 GB × 2 = 8 GB peak). LRU eviction.
//
// Single-caller assumption
// ------------------------
// The cache is consulted at the top of each mine_one_block() call from the
// main mining loop. Worker threads do NOT call it; they receive the
// scratchpad by const reference. If a future change introduces concurrent
// callers of mine_one_block(), switch this cache to inflight-build tracking
// (so N concurrent misses produce 1 build, not N) before going to
// production. The internal mutex serialises map access but does NOT
// prevent thundering-herd builds.
constexpr size_t SCRATCH_CACHE_CAP = 2;

// Returns the cached scratchpad data on hit, nullptr on miss.
// Emits one [PRECOMP] cache_lookup line.
std::shared_ptr<std::vector<uint8_t>> scratch_cache_get(const Bytes32& skey);

// Inserts a freshly-built scratchpad into the cache, evicting LRU if needed.
// Emits one [PRECOMP] cache_store line, and one cache_evict line per evicted
// entry. assert()s that size <= SCRATCH_CACHE_CAP afterwards.
void scratch_cache_put(const Bytes32& skey,
                       std::shared_ptr<std::vector<uint8_t>> data,
                       int32_t scratch_mb,
                       int64_t build_took_ms);

// Test / debug helpers.
size_t scratch_cache_size();
void scratch_cache_clear();

} // namespace sost
