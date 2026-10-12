#pragma once
// RPC-only helper: first chain index of the cASERT meta window used by
// getinfo / getblocktemplate / getblock (sost-node.cpp build_casert_meta).
//
// The 512-block window (commit 5e3a3cfa) is exact only for the V6++ bitsQ rule
// (next height >= CASERT_V6PP_HEIGHT), which reads the last 288 intervals. The
// pre-V6++ anchor rule indexes the chain vector from genesis (anchor_idx 0 =
// genesis), so a windowed vector gives a different bitsQ for next heights
// 513..5174. Block validation always uses the full chain and is unaffected;
// mainnet tip is far past 5175, where this returns exactly the old window.
#include "sost/params.h"
#include <cstddef>

namespace sost {

inline constexpr size_t CASERT_META_WINDOW = 512;

inline size_t casert_meta_window_start(size_t end_exclusive) {
    if ((int64_t)end_exclusive < CASERT_V6PP_HEIGHT) return 0;   // pre-V6++: full chain
    return (end_exclusive > CASERT_META_WINDOW) ? (end_exclusive - CASERT_META_WINDOW) : 0;
}

} // namespace sost
