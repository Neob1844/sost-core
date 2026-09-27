// coin_select.h — unified wallet coin-selection ALGORITHM (pure, testable, wallet-only).
// NO consensus/emission/maturity/key logic. Maturity, constitutional-address, --from and lock
// filtering are done by the caller (Wallet::select_coins); this file is the selection algorithm
// over already-eligible candidate amounts. Design: docs/wallet/COIN_SELECTION_AUDIT.md.
#pragma once
#include <cstdint>
#include <vector>
#include <algorithm>
#include <numeric>
#include <functional>

namespace sost { namespace coinselect {

// Estimated serialized bytes of ONE spent input (txid 32 + vout 4 + sig ~72 + pubkey 33 +
// length/overhead). Used only for effective-value / waste; the CLI computes the EXACT fee via
// its build→measure two-pass, so this is a heuristic cost, never the consensus fee.
inline constexpr int64_t APPROX_INPUT_BYTES  = 148;
inline constexpr int64_t APPROX_CHANGE_BYTES = 34;   // one extra output if change is created

struct Result {
    std::vector<size_t> indices;  // chosen indices into the input `amounts`
    int64_t total_in = 0;
    bool     ok = false;          // true iff total_in >= needed
    bool     bnb = false;         // true iff the exact-match Branch-and-Bound path found it
};

// Branch-and-Bound: find a subset whose total is within [needed, needed + cost_window] so no (or
// negligible) change output is required. Deterministic, bounded iterations. Returns empty on miss.
// `sorted` are (amount, orig_index) sorted by amount DESC. cost_window ~ the cost of a change output.
inline std::vector<size_t> bnb(const std::vector<std::pair<int64_t,size_t>>& sorted,
                               int64_t needed, int64_t cost_window, int max_tries = 100000) {
    int64_t total_avail = 0; for (auto& p : sorted) total_avail += p.first;
    if (total_avail < needed) return {};
    const int64_t upper = needed + cost_window;
    std::vector<char> best_sel, cur_sel(sorted.size(), 0);
    bool found = false;
    int tries = 0;
    // suffix sums for pruning
    std::vector<int64_t> suffix(sorted.size()+1, 0);
    for (int i = (int)sorted.size()-1; i >= 0; --i) suffix[i] = suffix[i+1] + sorted[i].first;
    // iterative DFS
    struct Frame { int depth; int64_t sum; };
    // recursive lambda via explicit stack to bound memory
    std::vector<char> sel(sorted.size(), 0);
    std::function<bool(int,int64_t)> dfs = [&](int depth, int64_t sum) -> bool {
        if (++tries > max_tries) return false;
        if (sum > upper) return false;                      // overshoot beyond change window
        if (sum >= needed) { best_sel = sel; return true; } // exact-enough (changeless)
        if (depth >= (int)sorted.size()) return false;
        if (sum + suffix[depth] < needed) return false;     // cannot reach even taking all remaining
        // branch: include sorted[depth]
        sel[depth] = 1;
        if (dfs(depth+1, sum + sorted[depth].first)) return true;
        sel[depth] = 0;
        // branch: exclude sorted[depth]
        return dfs(depth+1, sum);
    };
    found = dfs(0, 0);
    if (!found) return {};
    std::vector<size_t> out;
    for (size_t i = 0; i < sorted.size(); ++i) if (best_sel[i]) out.push_back(sorted[i].second);
    return out;
}

// Unified selection: BnB (changeless) first, else largest-effective-value-first accumulation
// (minimizes input count for a mixed wallet — the fix over naive oldest-first). `fee_per_input` =
// APPROX_INPUT_BYTES * fee_rate; UTXOs whose effective value <= 0 are deferred (uneconomic) and only
// used if needed to reach `needed`.
inline Result select(const std::vector<int64_t>& amounts, int64_t needed, int64_t fee_rate) {
    Result r;
    if (needed <= 0) { r.ok = true; return r; }
    const int64_t fee_per_input = APPROX_INPUT_BYTES * (fee_rate > 0 ? fee_rate : 1);
    // build (amount, index), split economic (eff>0) vs uneconomic
    std::vector<std::pair<int64_t,size_t>> econ, uneco;
    for (size_t i = 0; i < amounts.size(); ++i) {
        if (amounts[i] <= 0) continue;
        if (amounts[i] - fee_per_input > 0) econ.push_back({amounts[i], i});
        else                                 uneco.push_back({amounts[i], i});
    }
    std::sort(econ.begin(), econ.end(), [](auto&a,auto&b){ return a.first > b.first; });
    std::sort(uneco.begin(), uneco.end(), [](auto&a,auto&b){ return a.first > b.first; });

    // 1) BnB over economic UTXOs for a changeless match
    auto bnb_sel = bnb(econ, needed, APPROX_CHANGE_BYTES * (fee_rate > 0 ? fee_rate : 1));
    if (!bnb_sel.empty()) {
        r.indices = bnb_sel; r.bnb = true;
        for (size_t idx : r.indices) r.total_in += amounts[idx];
        r.ok = r.total_in >= needed; return r;
    }
    // 2) Fallback: largest-effective-first accumulate; then uneconomic if still short.
    for (auto& p : econ) {
        if (r.total_in >= needed) break;
        r.indices.push_back(p.second); r.total_in += p.first;
    }
    if (r.total_in < needed) {
        for (auto& p : uneco) {
            if (r.total_in >= needed) break;
            r.indices.push_back(p.second); r.total_in += p.first;
        }
    }
    r.ok = r.total_in >= needed;
    return r;
}

}} // namespace
