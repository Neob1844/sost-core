#include "sost/pow/scratchpad_cache.h"

#include <cassert>
#include <chrono>
#include <cstdio>
#include <map>
#include <mutex>
#include <string>

namespace sost {

namespace {

struct ScratchpadEntry {
    std::shared_ptr<std::vector<uint8_t>> data;  // shared, no copy
    int64_t built_ts_ms;
    int64_t last_access_ts_ms;
    int32_t scratch_mb;
};

std::mutex g_mu;
std::map<Bytes32, std::shared_ptr<ScratchpadEntry>> g_cache;

int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

std::string hex16(const Bytes32& b) { return hex(b).substr(0, 16); }

// Mutex must be held by caller.
void evict_locked() {
    while (g_cache.size() > SCRATCH_CACHE_CAP) {
        auto oldest = g_cache.begin();
        for (auto it = g_cache.begin(); it != g_cache.end(); ++it) {
            if (it->second->last_access_ts_ms < oldest->second->last_access_ts_ms) {
                oldest = it;
            }
        }
        std::printf("[PRECOMP] cache_evict skey=%s reason=lru\n",
                    hex16(oldest->first).c_str());
        g_cache.erase(oldest);
    }
}

} // namespace

std::shared_ptr<std::vector<uint8_t>> scratch_cache_get(const Bytes32& skey) {
    std::lock_guard<std::mutex> lk(g_mu);
    auto it = g_cache.find(skey);
    if (it == g_cache.end()) {
        std::printf("[PRECOMP] cache_lookup skey=%s hit=0 age_ms=-1\n",
                    hex16(skey).c_str());
        return nullptr;
    }
    int64_t now = now_ms();
    int64_t age = now - it->second->built_ts_ms;
    it->second->last_access_ts_ms = now;
    std::printf("[PRECOMP] cache_lookup skey=%s hit=1 age_ms=%lld\n",
                hex16(skey).c_str(), (long long)age);
    return it->second->data;
}

void scratch_cache_put(const Bytes32& skey,
                       std::shared_ptr<std::vector<uint8_t>> data,
                       int32_t scratch_mb,
                       int64_t build_took_ms) {
    auto entry = std::make_shared<ScratchpadEntry>();
    int64_t now = now_ms();
    entry->data = std::move(data);
    entry->built_ts_ms = now;
    entry->last_access_ts_ms = now;
    entry->scratch_mb = scratch_mb;

    std::lock_guard<std::mutex> lk(g_mu);
    g_cache[skey] = entry;
    evict_locked();
    assert(g_cache.size() <= SCRATCH_CACHE_CAP);

    std::printf("[PRECOMP] cache_store  skey=%s build_ms=%lld scratch_mb=%d cache_size=%zu\n",
                hex16(skey).c_str(), (long long)build_took_ms,
                scratch_mb, g_cache.size());
}

size_t scratch_cache_size() {
    std::lock_guard<std::mutex> lk(g_mu);
    return g_cache.size();
}

void scratch_cache_clear() {
    std::lock_guard<std::mutex> lk(g_mu);
    g_cache.clear();
}

} // namespace sost
