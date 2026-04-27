# sost-miner scratchpad cache fix

**Date:** 2026-04-27
**Author:** NeoB
**Status:** miner-only optimisation. No consensus change.

## Background

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

## Fix

A small in-process cache keyed by `skey`:

- Cap = 2 entries (8 GB peak on mainnet). LRU eviction.
- First `mine_one_block` call after a fresh start or an epoch boundary
  pays the build cost once.
- Every subsequent call inside the same epoch hits the cache in <1 ms.

The cache is held as `std::shared_ptr<std::vector<uint8_t>>` so the same
allocation is reused across calls without copying.

## Diagnostic output

Three new log lines, prefix `[PRECOMP]`:

```
[PRECOMP] cache_lookup skey=<hex16> hit=<0|1> age_ms=<int>
[PRECOMP] cache_store  skey=<hex16> build_ms=<int> scratch_mb=<int> cache_size=<int>
[PRECOMP] cache_evict  skey=<hex16> reason=lru
```

In normal operation expect one `cache_store` shortly after start, then
`cache_lookup hit=1` on every subsequent restart. A second `cache_store`
should appear only at an epoch boundary (~every 53 days).

## What this is not

- Not a consensus change. Block bytes are identical to before.
- Not pre-computation of header/nonce/parent-id. The scratchpad is
  epoch-keyed; per-block pre-computation does not apply to SOST.
- Not selfish mining, withholding, fork-inducing, or anything else
  that affects other miners' blocks. Only the miner's own scheduling
  changes.

## Update path for miners

```
cd ~/SOST/sostcore/sost-core
git pull origin main
cd build && make -j$(nproc) sost-miner
# restart your miner process
```

Any miner that does not update keeps mining valid blocks the slow way.
