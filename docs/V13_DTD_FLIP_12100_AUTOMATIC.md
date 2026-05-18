# V13 DTD Flip at Block 12,100 — Automatic

**Verdict:** the lottery cadence transition from 2-of-3 (bootstrap) to 1-of-3 (permanent) at block 12,100 is **consensus-enforced**, **automatic**, and **already covered by tests on `main`**. No operator action, no node restart, no miner restart, no Beacon notice, no RPC call, no config flag is required at block 12,100. The flip happens because the next block height satisfies a pure compile-time arithmetic condition that is evaluated fresh by the validator for every block.

This doc captures the verdict, lists the load-bearing files with line numbers, documents how to re-verify locally, and explains how to spot a regression.

---

## 1. What "DTD flip at 12,100" means precisely

The V11 Phase 2 lottery is governed by a single pure function:

```cpp
// include/sost/lottery.h:126
inline bool is_lottery_block(int64_t height, int64_t phase2_height) {
    if (phase2_height == INT64_MAX) return false;
    if (height < phase2_height)     return false;
    const int64_t offset = height - phase2_height;
    if (offset < LOTTERY_HIGH_FREQ_WINDOW) {
        return (height % 3) != 0;          // Bootstrap: 2 of every 3 blocks
    }
    return (height % 3) == 0;              // Permanent:  1 of every 3 blocks
}
```

with two production constants:

```cpp
// include/sost/params.h:391
inline constexpr int64_t  V11_PHASE2_HEIGHT        = 7100;
// include/sost/params.h:419
inline constexpr int64_t  LOTTERY_HIGH_FREQ_WINDOW = 5000;
```

For every block height `h`:

| h | `offset = h - 7100` | branch | rule | fires? |
|---|---|---|---|---|
| 12,098 | 4998 | bootstrap | `(h % 3) != 0` → `(2) != 0` | **yes** |
| 12,099 | 4999 | bootstrap | `(h % 3) != 0` → `(0) != 0` | no |
| **12,100** | **5000** | **permanent (first)** | `(h % 3) == 0` → `(1) == 0` | no |
| 12,101 | 5001 | permanent | `(h % 3) == 0` → `(2) == 0` | no |
| 12,102 | 5002 | permanent | `(h % 3) == 0` → `(0) == 0` | **yes** (first 1-of-3 firing) |
| 12,103 | 5003 | permanent | `(h % 3) == 0` → `(1) == 0` | no |

At `h = 12,100` the boundary check `offset < 5000` becomes false for the first time, and the rule silently switches from `(h % 3) != 0` to `(h % 3) == 0`. There is **no separate fork constant for 12,100** — the height is implicit in the math `7100 + 5000 = 12,100`.

---

## 2. Why it is genuinely "automatic"

| # | Guarantee | Where |
|---|---|---|
| 1 | `is_lottery_block` is a pure `inline` function — no state, no I/O, no caching | `include/sost/lottery.h:126` |
| 2 | `V11_PHASE2_HEIGHT = 7100` is `inline constexpr int64_t` (compile-time, immutable, no runtime override) | `include/sost/params.h:391` |
| 3 | `LOTTERY_HIGH_FREQ_WINDOW = 5000` is `inline constexpr int64_t` | `include/sost/params.h:419` |
| 4 | Validator routes EVERY lottery decision through this function | `src/sost-node.cpp:1220, 1436, 4305` + `src/lottery.cpp:256` |
| 5 | `sost-miner` has **no parallel cadence math** — it reads the `lottery_triggered` boolean from the node's RPC response | `src/sost-miner.cpp:625, 675` |
| 6 | No env var, RPC method, config flag, or signed Beacon notice can change the cadence at runtime | (audited statically) |
| 7 | The V13 cooldown change at block 12,000 (window 5 → 6, `lottery_exclusion_window_at` at `include/sost/params.h:835`) is decoupled — it changes WHO is eligible on a lottery block, not WHICH blocks are lottery blocks | `include/sost/params.h:835` |

Together these mean: at the moment the chain reaches block 12,100, the existing running binary already returns the new cadence value because the next call to `is_lottery_block(12100, 7100)` evaluates a different branch of the same constexpr function it was always going to evaluate.

---

## 3. How to re-verify in two commands

### a) Pure-function test (header-only, no build deps)

```bash
cd /opt/sost
g++ -std=c++17 -I include tests/test_lottery_frequency.cpp \
    -o /tmp/test_lottery_frequency
/tmp/test_lottery_frequency
```

Last verified result on `main`:

```
=== test_lottery_frequency (V11 Phase 2 C5) ===
=== Summary: 52 passed, 0 failed ===
```

Section 7 of that test pins the production schedule against `V11_PHASE2_HEIGHT = 7100`, including:

- `last bootstrap block height=12099 (offset=4999, 12099%3==0) → false`
- `first permanent block height=12100 (offset=5000, 12100%3==1) → false`
- `permanent height=12101 (h%3==2) → false`
- `permanent height=12102 (h%3==0) → true (first permanent triggered)`
- `permanent height=12103 (h%3==1) → false`

### b) Read-only Python audit

```bash
mkdir -p /tmp/sost-v13-dtd-audit
python3 scripts/trinity/v13_dtd_flip_audit.py \
    --repo-root /opt/sost \
    --out-json  /tmp/sost-v13-dtd-audit/audit.json \
    --out-md    /tmp/sost-v13-dtd-audit/audit.md \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
```

The audit asserts six gates:

1. **G1** — constants pinned (`V11_PHASE2_HEIGHT=7100`, `LOTTERY_HIGH_FREQ_WINDOW=5000`, `V13_HEIGHT=12000`)
2. **G2** — `is_lottery_block` defined inline in `lottery.h` with the expected signature
3. **G3** — every `src/` call site passes a named constant or a variable as `phase2_height` (no numeric literal)
4. **G4** — `sost-miner.cpp` consumes the RPC `lottery_triggered` field and does not call `is_lottery_block` itself
5. **G5** — `lottery_exclusion_window_at` returns 5 pre-V13 and 6 post-V13 and is decoupled from `is_lottery_block`
6. **G6** — a pure Python re-implementation of `is_lottery_block` agrees with the documented firing pattern at heights 12,095..12,110

Exit code `0` = all gates GREEN. Exit code `1` = at least one gate RED (consensus integrity has been weakened — investigate immediately).

---

## 4. What this does NOT change

- Does not change the emission schedule.
- Does not change the 4,669,201 SOST hard cap.
- Does not change the 50/25/25 coinbase split on non-triggered blocks.
- Does not change the 50/50 miner/lottery-winner split on triggered blocks.
- Does not change the SbPoW signing contract.
- Does not change cASERT or any difficulty rule.
- Does not introduce any new transaction type.
- Does not require any miner config change.
- Does not require any node restart.
- Does not depend on Beacon (a Beacon notice MUST NOT and CANNOT change consensus rules — it is a loudspeaker, not a remote control).

---

## 5. How to spot a regression

Any of the following would be a regression and the audit script should flag it:

- `V11_PHASE2_HEIGHT` or `LOTTERY_HIGH_FREQ_WINDOW` changed in `params.h` ⇒ G1 red.
- `is_lottery_block` signature changed or removed from `lottery.h` ⇒ G2 red.
- A new call site in `src/` that passes a numeric literal (e.g. `is_lottery_block(h, 7100)`) ⇒ G3 red. A numeric literal would silently shift the cadence at that single call site.
- A new function in `sost-miner.cpp` that recomputes the cadence with its own `height % 3` math ⇒ G4 red.
- `lottery_exclusion_window_at` rewritten to call `is_lottery_block` ⇒ G5 red. Coupling these helpers would couple the V13 cooldown change to the cadence flip and break the orthogonality this doc relies on.
- A new RPC method or config flag that lets the operator override `lottery_triggered` ⇒ no automated gate yet, but easy to spot by re-running the audit after any change to `sost-node.cpp` and `sost-miner.cpp`.

If any gate goes red on `main`, the V11 Phase 2 cadence flip at block 12,100 is no longer guaranteed to be automatic. That is a release-blocker, not a documentation issue.

---

## 6. Companion files

- `scripts/trinity/v13_dtd_flip_audit.py` — the read-only audit script.
- `tests/trinity/test_v13_dtd_flip_audit.py` — functional + negative + static-safety tests for the audit script (also asserts the live tree comes up all-green).
- `tests/test_lottery_frequency.cpp` — the pre-existing C++ pure-function test that pins the production schedule. Section 7 is the load-bearing section for this verdict; Section 8 (added by this branch) walks the contiguous run 12,095..12,110.

— NeoB
