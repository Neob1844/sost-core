# V15 static analysis report (P2)

## Tools
- **GCC static analyzer** `-fanalyzer` (g++ (Ubuntu) 11.4.0) — available with no install.
- Adversarial manual consensus audit (see SECURITY_AUDIT_REPORT.md) as the semantic complement.
- `cppcheck` / `clang-tidy` are NOT installed and this box has no passwordless sudo, so they are
  deferred to the second box (exact commands in REMAINING_GATES.md § Gate #8). `clang` 14 is present.

## Command
Mainnet profile (no `SOST_DEVNET_FORKS` / `SOST_TESTNET_FORKS` → `V15_HEIGHT=25000`):
```
g++ -Iinclude -DSOST_HAVE_SCHNORRSIG=1 -std=gnu++17 -fanalyzer -O1 -c <file> -o /dev/null
```

## Scope + results
| Target | `-fanalyzer` diagnostics | Classification |
|--------|--------------------------|----------------|
| `src/sost-node.cpp` (V15 jackpot validation, emission transition, ConnectBlock path) | 1 | **D** — pre-existing, V15-unrelated |
| `src/sost-miner.cpp` (V15 jackpot template + DEV attack flags) | 0 | clean |
| jackpot headers TU (`jackpot.h`, `jackpot_block.h`, `jackpot_reserve.h`, `params.h`, `lottery.h`) | 0 | clean |

### The one diagnostic (classified D — not a V15 issue, not fixed)
```
src/sost-node.cpp:4547:13: warning: ignoring return value of 'int pipe(int*)'
  declared with attribute 'warn_unused_result' [-Wunused-result]
      pipe(g_interrupt_pipe);
```
In `init_interrupt_pipe()` — a pre-existing signal-handling helper unrelated to V15 consensus.
No consensus impact; left untouched to avoid churn on the pre-fork branch (candidate for a future
cosmetic sweep, not a gate blocker).

## Conclusion
The V15 consensus surface (jackpot arithmetic/validation, emission transition, miner template) is
**clean under `-fanalyzer`** — no null-deref, use-after-free, uninitialised-use, leak, or
signed-overflow findings. This complements: (a) the manual consensus audit (0 exploitable, B-1
fixed), and (b) ASan+UBSan on the consensus arithmetic (361 assertions, 0 errors). The only
outstanding static-analysis work is a `cppcheck`/`clang-tidy` cross-check on the second box, which
requires installing those tools.

**Gate status: PASS for the available analyzer** (`-fanalyzer` clean on all V15 code); cppcheck/
clang-tidy cross-check = pending-tooling (2nd box).
