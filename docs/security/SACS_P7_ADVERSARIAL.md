# SACS P7 — Adversarial / DoS Resistance of the SACS Monitor + RPC

**Status:** EXECUTED — DoS fuzz PASS, ASan/UBSan PASS. TSan and restart-mid-reorg not
run (noted below).

## Threat: SACS must never become a DoS surface
The monitor is a fixed 512-entry ring (cannot grow), and the RPC is read-only with
server-side clamps. This test attacks both.

## 1) Malformed / injection RPC (`tests/sacs_p7_fuzz.sh`)
11 hostile inputs to `getsacsevents` / `getsacsstatus`: negative, 24-digit and
5000-digit integers, non-numeric, an SQL-ish injection string (`"0; DROP TABLE"`),
20 000-char argument, extra/garbage params, raw non-JSON body, and a missing-params call.
Result: **every one returned a valid JSON-RPC response** (clean `-8` validation error or a
bounded result), the injection string was parsed as harmless data (there is no query
engine), and **the node stayed alive**. No crash, no hang.

## 2) Responses are bounded (cannot be forced unbounded)
`getsacsevents [0,100000000]` → server clamps to the ring page: `returned:12`, ~5.8 KB.
A caller cannot make the node emit an unbounded response.

## 3) High-rate load + concurrency
- 2000 sequential `getsacsstatus` completed with the node alive (per-call ~10 ms; the
  wall time is dominated by curl process-spawn overhead in WSL, not the node).
- 8× parallel × 300 `getsacsevents` storm: during the storm a direct call still returned
  in **10 ms** — no deadlock, no serialization stall in the node.

## 4) Memory / ring bound
Node RSS after the full barrage: **~10.7 MB, flat** (no growth). `ring_size` stayed at
**12** against `ring_max` 512 — the ring cap holds; event floods cannot exhaust memory.

## 5) ASan + UBSan (`tests/sacs_p7_asan.sh`, `build-sacs-asan`)
Built with `-fsanitize=address,undefined`. Exercised the full reorg path (converge
A=5→B=4, B reorged to height 5, `REORG_COMPLETED`) plus the SACS monitor emission and the
malformed-RPC fuzz, all under the sanitizers. **0 ASan report lines, 0 UBSan report
lines** — no memory errors, no undefined behaviour in the new monitor/RPC code or the
reorg engine it hooks.

## Not run (honest)
- **ThreadSanitizer (TSan):** a separate instrumented build; not run here (memory-hard
  PoW under sanitizers is very slow — the ASan run alone took several minutes). The
  monitor's shared state is guarded by a single `std::mutex` around the ring and counters;
  the empirical concurrency storm showed no deadlock, but a TSan data-race pass is still
  future work.
- **Restart-during-reorg** (kill the node mid-`try_reorganize`): not exercised as an
  isolated adversarial case; P2 covered restart-after-reorg persistence.
