# Fast block investigation — height 6200-6310

**Date:** 2026-04-28
**Author:** NeoB
**Scope:** read-only audit. No code modified, no commits.

## A. Executive summary

Of 103 blocks in the height range 6200–6310, **18 (17.5 %) have an
inter-block interval of exactly 1 second** as declared in their block
headers. Another 2 blocks are sub-60 s (47 s and 57 s). The pattern is
strongly correlated with E7 → H profile transitions: the 1-s block
appears immediately after a long E7 block 15 of 18 times, and a second
1-s block follows the first 3 of those 15 times.

**This is not a consensus break. The blocks are valid under current
node rules.** The chain is healthy. Top miner share at the time of
audit is ~13 % over the last 288 blocks; 23 unique miners.

The root cause is **a permissive timestamp policy in `sost-node.cpp`,
not an algorithm bypass and not selfish mining**. The dedicated MTP
validator already exists in the codebase but is not wired up.

Risk classification: **timestamp policy weakness**. Not urgent. Future
fork can tighten it. No action needed for the trial.

## B. Suspicious blocks (Δs ≤ 60)

All 1-s blocks in window 6200-6310, sorted by height:

| height | profile | prev profile | Δs | nonce | extra | scale | k | margin | steps |
|---|---|---|---|---|---|---|---|---|---|
| 6202 | H11 | E7 | 1 | 7 103 851 | 9 281 | 2 | 8 | 115 | 8 |
| 6212 | H11 | E7 | 1 | 2 373 316 | 46 620 | 2 | 8 | 115 | 8 |
| 6217 | H11 | E7 | 1 | 2 938 654 | 56 302 | 2 | 8 | 115 | 8 |
| 6223 | H11 | E7 | 1 | 368 795 | 0 | 2 | 8 | 115 | 8 |
| 6226 | H11 | E7 | 1 | 325 482 | 3 377 | 2 | 8 | 115 | 8 |
| 6229 | H11 | E7 | 1 | 7 937 516 | 48 892 | 2 | 8 | 115 | 8 |
| 6241 | H11 | E7 | 1 | 4 472 239 | 47 060 | 2 | 8 | 115 | 8 |
| 6244 | H11 | E7 | 1 | 2 841 297 | 62 171 | 2 | 8 | 115 | 8 |
| 6245 | H12 | H11 | 1 | 1 634 180 | 17 963 | 2 | 8 | 115 | 9 |
| 6252 | H11 | E7 | 1 | 3 091 445 | 19 298 | 2 | 8 | 115 | 8 |
| 6256 | H11 | E7 | 1 | 1 261 463 | 23 516 | 2 | 8 | 115 | 8 |
| 6258 | H11 | E7 | 1 | 622 516 | 18 036 | 2 | 8 | 115 | 8 |
| 6263 | H11 | E7 | 1 | 283 110 | 37 231 | 2 | 8 | 115 | 8 |
| 6264 | H12 | H11 | 1 | 29 326 | 39 389 | 2 | 8 | 115 | 9 |
| 6269 | H11 | E7 | 1 | 2 064 402 | 33 080 | 2 | 8 | 115 | 8 |
| 6270 | H12 | H11 | 1 | 1 039 735 | 59 165 | 2 | 8 | 115 | 9 |
| 6299 | H11 | E7 | 1 | 998 869 | 13 798 | 2 | 8 | 115 | 8 |
| 6302 | H11 | E7 | 1 | 2 066 523 | 39 765 | 2 | 8 | 115 | 8 |

## C. Are 1-s intervals real or explorer bug?

**Real.** Verified in two ways:

1. **Direct computation** from `bootstrap-chain.json`:
   `delta_s = block.timestamp − prev.timestamp`. The 1 s interval is
   present in the actual block headers, not an artefact of the explorer.
2. **Cross-reference** with the miner's local logs (commit `90f4e34`
   running on author's hardware): the `[MINING] Starting 12 threads`
   restarts after `[LAG-ADJUST]` and the explorer-observed timestamp
   delta agree at the second-level resolution.

The explorer's interval display is correct. `website/sost-explorer.html`
computes intervals as `block.timestamp − prev.timestamp` consistently.

## D. Timestamp validation rules — exact code references

**File: `src/block_validation.cpp:154-167`** (function
`ValidateBlockHeaderContext`):

```cpp
// Python-aligned (strictly increasing vs. parent).
// NOTE: Python uses MTP(11). We can't compute full MTP here because this function
// receives only `prev`, not the last 11 headers. Enforcing strict monotonicity
// is a safe subset that prevents accepting blocks Python would reject.
if (header.timestamp <= prev->timestamp) {
    if (err) *err = "ValidateBlockHeaderContext: timestamp not strictly increasing";
    return false;
}

// not too far in future (Python uses +600s)
if (header.timestamp > current_time + MAX_FUTURE_BLOCK_TIME) {
    if (err) *err = "ValidateBlockHeaderContext: timestamp too far in future";
    return false;
}
```

**Constants: `include/sost/block_validation.h:35-36`**:

```cpp
inline constexpr int64_t MAX_FUTURE_BLOCK_TIME = 10 * 60; // 600 seconds
```

**Stricter validator exists but is NOT wired in:** `src/block_validation.cpp:192-254`
(`ValidateBlockHeaderContextWithMTP`) computes Median Time Past over
the last 11 blocks and rejects `header.timestamp <= mtp`. The function
is fully implemented and tested but `sost-node.cpp` never calls it.

**Actual rules used by sost-node** (file `src/sost-node.cpp:3064-3074`):

```cpp
if(!g_blocks.empty() && ts64 <= g_blocks.back().timestamp){
    printf("[BLOCK] REJECTED: timestamp not increasing\n");
    return …;
}
if(ts64 > now_ts + MAX_FUTURE_DRIFT){
    printf("[BLOCK] REJECTED: timestamp too far in future\n");
    return …;
}
```

**Effective policy:**
- `ts > prev.ts` (strictly increasing, can be `prev.ts + 1`).
- `ts ≤ now + 600 s` (max future drift).
- **No MTP check.**
- **No min spacing.**

## E. cASERT / profile transition analysis

Of 18 1-s blocks:

| Pattern | Count |
|---|---|
| E7 → 1 s H11/H12 | 15 |
| H11 → 1 s H12 (immediately after a 1-s) | 3 |

**Sequences observed**:

```
6201 E7 1875s → 6202 H11 1s
6216 E7 1744s → 6217 H11 1s
6225 E7 1646s → 6226 H11 1s
6228 E7 1327s → 6229 H11 1s
6243 E7 1675s → 6244 H11 1s → 6245 H12 1s
6251 E7 1396s → 6252 H11 1s
6255 E7 1815s → 6256 H11 1s
6262 E7 1657s → 6263 H11 1s → 6264 H12 1s
6268 E7 2898s → 6269 H11 1s → 6270 H12 1s
6298 E7  831s → 6299 H11 1s
6301 E7 1596s → 6302 H11 1s
```

**Mechanism (most plausible):**

After a long E7 block, `prev.timestamp` is far ahead of most miners'
current wall-clock time (because the E7 block timestamp gets pinned
near `now + something` by whoever found it, while the next block's
miner may have a slightly older clock).

When the next miner constructs the H11/H12 candidate, the reference
miner uses `ts = now()` (`src/sost-miner.cpp:849`). Some miners may use
`ts = max(now, prev.timestamp + 1)` instead, which is **valid under the
current node rules** because the only timestamp constraint is
`ts > prev.timestamp`. The result is `ts = prev.ts + 1` and the
explorer sees a 1-s interval, **regardless of how long the miner
actually searched in wall-clock time**.

This is consistent with the data:
- `stab_*` parameters of 1-s blocks are H11/H12 (`scale=2, k=8,
  margin=115, steps=8/9`), not E7. The PoW work was real for the
  declared profile.
- Multiple distinct miner addresses produce 1-s blocks. Not a single
  selfish-mining actor.
- Nonces in the millions with non-zero `extra_nonce` are consistent
  with miners that have been searching across many block templates
  before publishing.

## F. Miner concentration

Distinct miner addresses observed in the 1-s blocks of the 6200-6310
window (extracted from explorer's UI; coinbase parser failed due to
non-standard SOST tx serialisation order, which doesn't affect this
analysis):

```
sost123d2c…8280  — mostly E7 wins, fewer 1-s blocks
sost15a64a…46d5  — 6270, 6287
sost14754d…6975  — 6263
sost1f1181…3f92  — 6264
sost161691…4d3b  — 6269
sost1c719c…c33e  — 6202, 6212, 6258
sost186302…f803  — 6256, 6217
sost157f84…b820  — 6252
sost1d3e7f…303a  — 6299
sost1d1996…579e  — 6302
…
```

**Multiple distinct addresses produce 1-s blocks.** This is inconsistent
with selfish-mining-by-one-actor. Consistent with **a protocol-level
property** (timestamp policy + post-E7 transition behaviour) shared
across multiple miners' implementations.

## G. Probability / variance

**Naïve Poisson model** with avg block time = 596 s and uniform `λ`:
`P(Δ ≤ 1s) ≈ 0.17%`. In 103 blocks, expected: ~0.17 1-s blocks.
Observed: 18.

**Naïve model is wrong.** Observation is ~100× expected, but the model
is wrong because:

1. The observed delta is **not** the wait time between block-finds —
   it is the difference between two declared timestamps, which can be
   `prev.ts + 1` regardless of actual mining time.
2. λ is not uniform: post-E7 the network filter is laxer for one
   block, distorting the distribution.
3. Some miners likely set `ts = max(now, prev.ts + 1)` while reference
   miner uses pure `ts = now()`, biasing observed deltas downwards
   for the optimised miners.

**Conclusion: variance estimate based on 1-s deltas is meaningless
without instrumented wall-clock timestamps.** The high count of 1-s
blocks does **not** prove unusual hashrate or cheating.

## H. Risk classification

**Timestamp policy weakness** — not urgent.

- Not a consensus break. Blocks are valid by current rules.
- Not a selfish-mining attack. Multiple distinct miners produce 1-s
  blocks.
- Not an algorithm bypass. PoW commitment, stability filter, and
  difficulty are all enforced and correctly verified.
- The MTP-strict validator (`ValidateBlockHeaderContextWithMTP`) is
  already implemented in the codebase but not wired into the node's
  accept path. Wiring it would tighten the timestamp policy without a
  consensus rule change of the underlying PoW.

## I. Recommended actions

**For the trial week (next 6 days): no action.** The chain is healthy,
miners are valid, the visual oddity does not affect any consensus
guarantee.

**Post-trial roadmap items:**

1. Wire `ValidateBlockHeaderContextWithMTP` into the node's accept path
   (file `src/sost-node.cpp` near line 3064). This rejects blocks with
   `ts ≤ MTP(11)` and would force timestamps to be at least roughly
   honest.
2. Soften the explorer's "1 s" display: when `delta_s ≤ 5` and
   `prev.profile == E7`, label the block "post-relief, timestamp
   pinned" so visitors don't misread it as cheating.
3. Add a dashboard panel: count of `delta_s ≤ 60` blocks per 100-block
   window. Useful trend indicator.
4. Document the timestamp rules clearly in the public whitepaper.

These are listed in `docs/pending_post_trial.md`.

## J. Audit trail

- Source data: `https://sostcore.com/bootstrap-chain.json` snapshot
  taken 2026-04-28.
- Block range analyzed: 6200–6310 (103 blocks).
- Code references verified by `grep`/`sed` against the local checkout
  at commit `d33bc67` (= `origin/main`).
- Machine-readable extract:
  `outputs/fast_block_investigation_6200_6310.csv`.

No code modified during this audit.
