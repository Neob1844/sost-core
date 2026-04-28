# Timestamp policy hardening — MTP fork at block 6400

**Date:** 2026-04-28
**Author:** NeoB
**Status:** experimental coordinated hard fork. Activation at height 6400.

## Summary

From block **6400**, SOST consensus rejects any block whose timestamp
fails **either** of these two rules:

  1. `ts > MedianTimePast(last 11 blocks)`
  2. `ts >= prev.timestamp + 60 seconds`

Pre-fork blocks remain valid under the existing rule (`ts > prev.ts`
and `ts <= now + 600 s`).

**Why both rules.** MTP alone is not enough. Once the chain has a
strictly increasing timestamp sequence, `prev.ts` is normally above
MTP, so a candidate `ts = prev.ts + 1` would still satisfy the MTP
rule. The minimum-delta rule eliminates the artificial 1-second
deltas observed in blocks 6200–6310 (see
`docs/fast_block_investigation_6200_6310.md`).

This is **not** a PoW change. It is **not** a reward change. It is
**not** a cASERT change. It does not affect historical blocks.

## Background

Investigation `docs/fast_block_investigation_6200_6310.md` found that
~17 % of blocks in the range 6200-6310 had a header timestamp delta of
exactly 1 second. The effect was strongest immediately after long E7
relief-valve blocks. The blocks were valid under the current rules and
PoW was correctly enforced; the problem was a permissive timestamp
policy that let miners declare `ts = prev.ts + 1` regardless of the
actual wall-clock time.

The dedicated MTP validator was already implemented in the codebase
but never wired into the `submitblock` accept path. This fork wires it.

## Old rule (pre-fork)

`src/sost-node.cpp` block accept path (≈ lines 3062-3071):

```cpp
if(!g_blocks.empty() && ts64 <= g_blocks.back().timestamp){
    return REJECT("timestamp not increasing");
}
if(ts64 > now_ts + MAX_FUTURE_DRIFT){  // 600 s
    return REJECT("timestamp too far in future");
}
```

## New rule (fork active, height ≥ 6400)

The node accept path calls `ValidatePostForkTimestamp` from
`src/block_validation.cpp`, which encapsulates both rules:

```cpp
if (height >= TIMESTAMP_MTP_FORK_HEIGHT && !g_blocks.empty()) {
    if (!ValidatePostForkTimestamp(ts64, g_blocks.back().timestamp,
                                   meta_for_mtp, &err)) {
        return REJECT(err);   // MTP or min-delta failed
    }
}
```

The function checks (in order):
1. `ts > MedianTimePast(last 11 timestamps)`
2. `ts >= prev_ts + TIMESTAMP_MIN_DELTA_SECONDS`

Constants in `include/sost/params.h`:

```cpp
inline constexpr int64_t TIMESTAMP_MTP_FORK_HEIGHT  = 6400;
inline constexpr int32_t TIMESTAMP_MTP_WINDOW       = 11;
inline constexpr int64_t TIMESTAMP_MIN_DELTA_SECONDS = 60;
```

## Miner side

`src/sost-miner.cpp` computes `min_valid_ts` once per `mine_one_block`
call, then clamps every timestamp generation site to `max(now, min_valid_ts)`:

```cpp
int64_t min_valid_ts = g_chain.empty() ? 0 : (g_chain.back().time + 1);
if (h >= TIMESTAMP_MTP_FORK_HEIGHT && !g_chain.empty()) {
    // Post-fork: must clear BOTH MTP+1 and prev+min_delta
    int64_t mtp_plus_1    = MTP_of(g_chain) + 1;
    int64_t prev_plus_min = g_chain.back().time + TIMESTAMP_MIN_DELTA_SECONDS;
    min_valid_ts = max(min_valid_ts, max(mtp_plus_1, prev_plus_min));
}
```

All timestamp generation sites in the miner clamp to
`max(now, min_valid_ts)`. This guarantees a miner running this code
never produces a candidate that fails MTP after height 6400, even when
the local wall clock is briefly behind the chain.

## Compatibility

- Old miners still produce `ts = now()`. Once height crosses 6400,
  any of their candidates with `ts <= MTP` will be rejected by upgraded
  nodes. **Old miners must update.**
- Old nodes still accept `ts > prev.ts`. After block 6400, they may
  accept blocks that upgraded nodes reject, leading to a temporary
  fork on their view of the chain. **Old nodes must update.**
- The fork is **experimental** in the sense that the network is small
  (~23 unique miners, 10 visible peers as of 2026-04-28). A coordinated
  upgrade is feasible.

## Activation timeline

- 2026-04-28: code published (commit on `experimental/mtp-fork-6400`).
- After review and BCT announcement: merge to `main`, push, deploy.
- Block 6306 (current tip) → block 6400 ≈ 94 blocks ≈ 16 hours of
  wall-clock at avg 600 s/block.
- All operators must update before height 6400.

## Tests

`tests/test_mtp_fork.cpp` covers 22 assertions including:

**MTP rule alone (the existing `ValidateBlockHeaderContextWithMTP`):**
- `ts == MTP` → rejected
- `ts == MTP - 1` → rejected
- `ts = prev.ts + 1` well above MTP → accepted (this is what motivated
  adding the min-delta rule)
- post-E7 `ts = prev.ts + 1` → accepted under MTP-only

**Post-fork combined rule (`ValidatePostForkTimestamp`):**
- **`ATTACK: ts = prev+1` is REJECTED post-fork** ← key fix
- `ts = prev+30` rejected
- `ts = prev+59` rejected (boundary just below)
- `ts = prev+60` accepted (boundary at exact min)
- `ts = prev+600` (target spacing) accepted
- `ts == MTP` rejected even when above prev+60
- chain shorter than MTP window: graceful degradation

**Constants:**
- `TIMESTAMP_MTP_FORK_HEIGHT > 0`
- `TIMESTAMP_MTP_WINDOW == 11`
- `TIMESTAMP_MIN_DELTA_SECONDS == 60`

`test-mtp-fork`: 22/22 pass. Full ctest unchanged (4 preexisting
failures unrelated to the fork: `bond-lock`, `popc`, `escrow`,
`dynamic-rewards`).

## What does not change

- No supply change.
- No reward change.
- No PoW algorithm change. ConvergenceX is untouched.
- No cASERT change. avg288 still drives bitsQ.
- No coinbase or wallet change.
- No new RPC.
- Pre-fork blocks remain valid forever under the old rule.
