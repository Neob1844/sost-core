#pragma once
#include <cstdint>

namespace sost {

// One-shot RELIEF-PREDICT gate, keyed by mining height.
//
// The miner's block monitor predicts the relief valve locally when the
// last block has been pending for longer than CASERT_RELIEF_VALVE_THRESHOLD.
// Without this gate, a thread-local flag would reset every time the monitor
// thread restarted (which happens on every mine_one_block restart). With the
// scratchpad cache making restarts <1 ms, the predict would fire every
// poll cycle and trap the miner in a profile-flip loop.
//
// This module owns a single atomic<int64_t> remembering the last height for
// which RELIEF-PREDICT already fired. Calls with the same height return
// false (don't fire again). Calls with a different height — i.e. a new
// block arrived and the miner moved to height+1 — return true and mark.
//
// Returns true exactly once per height. Thread-safe.
bool relief_predict_check_and_mark(int64_t height);

// Test / debug helpers.
void relief_predict_reset();
int64_t relief_predict_last_marked();

} // namespace sost
