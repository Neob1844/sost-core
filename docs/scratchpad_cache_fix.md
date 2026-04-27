# sost-miner: scratchpad cache + RELIEF-PREDICT loop fix

**Date:** 2026-04-28
**Author:** NeoB
**Status:** miner-only optimisations. No consensus change.

This commit ships two coupled changes that must land together:

1. **Scratchpad cache** — eliminates the 8-30 s `build_scratchpad` on every
   tip change.
2. **RELIEF-PREDICT loop fix** — gates the local relief-valve prediction
   so it fires at most once per mining height, even when the block monitor
   thread restarts.

The second fix is required because the cache fix turns mine_one_block
restarts from "8-30 s slow" into "<1 ms fast", which in turn unmasks a
latent race between RELIEF-PREDICT and LAG-CHECK. The first commit of
this work (`2de1060`, since reverted) shipped only part 1 and produced
an infinite loop in mainnet logs of the form:

```
[RELIEF-PREDICT] Elapsed 607s > 605s — pre-switching to E7
[LAG-ADJUST] Profile changed: H11 -> E7. Restarting search.
[MINING] Local profile=E7, node says H11 — using node profile
[MINING] Starting 12 threads for parallel nonce search
[RELIEF-PREDICT] Elapsed 608s > 605s — pre-switching to E7   ← loops every ~1 s
...
```

Both fixes are now in. Either one without the other is unsafe to ship.

---

## Part 1 — Scratchpad cache

### Background

The miner's `mine_one_block()` was calling `build_scratchpad(skey,
cx_scratch_mb)` on every invocation. On mainnet that scratchpad is 4 GB
and takes 8-30 seconds of CPU to construct (host-dependent: 8 s on a
12-thread laptop with the work parallelised; ~30 s on a single-thread
build).

The seed key is

```
skey = epoch_scratch_key(epoch, &chain)
```

which depends only on the epoch number and an anchor block id once per
epoch. `BLOCKS_PER_EPOCH = 131 553` ≈ ~53 days. Inside an epoch the
scratchpad is constant — but the reference miner was throwing it away
and rebuilding it from scratch on every tip change.

For miners with high RTT to the rest of the network, this dead time
landed inside the E7 relief-valve window (where the next block is
decided in seconds), so the miner was effectively absent from the most
important window of every block. This was the root cause of the
"10-20 s lag" reported by `vostokzyf` in the BCT thread.

### Fix

A small in-process cache keyed by `skey`:

- Cap = 2 entries (8 GB peak on mainnet). LRU eviction.
- First `mine_one_block` call after a fresh start or an epoch boundary
  pays the build cost once.
- Every subsequent call inside the same epoch hits the cache in <1 ms.

The cache is held as `std::shared_ptr<std::vector<uint8_t>>` so the same
allocation is reused across calls without copying.

Single-caller assumption documented in
`include/sost/pow/scratchpad_cache.h`. The internal mutex serialises
map access but does NOT prevent thundering-herd builds; the cache is
designed for the current architecture where only the main mining loop
calls `mine_one_block` sequentially.

### Diagnostic output

Three new log lines, prefix `[PRECOMP]`:

```
[PRECOMP] cache_lookup skey=<hex16> hit=<0|1> age_ms=<int>
[PRECOMP] cache_store  skey=<hex16> build_ms=<int> scratch_mb=<int> cache_size=<int>
[PRECOMP] cache_evict  skey=<hex16> reason=lru
```

In normal operation expect one `cache_store` shortly after start, then
`cache_lookup hit=1` on every subsequent restart. A second `cache_store`
should appear only at an epoch boundary (~every 53 days).

---

## Part 2 — RELIEF-PREDICT loop fix

### Background

`start_block_monitor()` runs a background thread that polls the node and
predicts the relief-valve fallback locally when `elapsed > 605 s`. The
flag protecting against repeat fires (`bool relief_predicted`) was
**local to that thread**.

Each time `mine_one_block` restarts (e.g. after `g_lag_changed=true`),
the previous monitor thread exits and a fresh one is launched, with the
flag reset to `false`. With the slow `build_scratchpad` rebuild between
restarts, the node had time to acknowledge the E7 transition, so by the
next monitor tick `mining_pi == node_pi`, no disagreement, no re-fire.

After the cache fix, restarts are <1 ms, the monitor thread is recreated
immediately, the flag is reset, and `elapsed > 605 s` still holds —
so RELIEF-PREDICT fires every poll cycle (~1 s), the miner ping-pongs
between H10/H11 and E7, and never actually hashes long enough to find a
nonce.

### Fix

A new module `sost/pow/relief_predict.{h,cpp}` owns a single
`std::atomic<int64_t> g_last_marked_height{-1}`. The block monitor calls

```cpp
if (relief_predict_check_and_mark(g_monitor_height.load())) {
    /* fire RELIEF-PREDICT exactly once for this height */
}
```

`check_and_mark` uses a CAS loop: if the current marked height equals
the supplied height, return false. Otherwise atomically replace and
return true. This is correct under concurrency (verified by a 16-thread
race test).

The flag now lives outside the monitor thread, so it persists across
`stop/start` cycles. It only resets to a different value when a new
block arrives and `g_monitor_height` advances — the natural signal that
"now we can predict again, we are on a new block".

### Diagnostic output

Unchanged. The single `[RELIEF-PREDICT]` line still appears, but now
exactly once per height.

---

## What this is not

- Not a consensus change. Block bytes are identical to before.
- Not pre-computation of header / nonce / parent-id. The scratchpad is
  epoch-keyed; per-block pre-computation does not apply to SOST.
- Not selfish mining, withholding, fork-inducing, or anything else
  that affects other miners' blocks. Only the miner's own scheduling
  changes.

## Tests added

- `tests/test_scratchpad_cache.cpp` — 12 assertions covering miss/store,
  hit, size cap, LRU eviction across simulated epoch boundaries, exact
  `[PRECOMP]` event counts.
- `tests/test_relief_predict.cpp` — 15 assertions covering the
  one-shot-per-height contract, reset semantics, 16-way concurrency
  race, and the exact mainnet scenario (50 polls at the same height
  produce exactly 1 fire; height bump produces a second fire).

Both pass cleanly. Pre-existing failing tests (`bond-lock`, `popc`,
`escrow`, `dynamic-rewards`) are unrelated and unchanged.

## Update path for miners

```
cd ~/SOST/sostcore/sost-core
git pull origin main
cd build && make -j$(nproc) sost-miner
# restart your miner process
```

Any miner that does not update keeps mining valid blocks the slow way.
