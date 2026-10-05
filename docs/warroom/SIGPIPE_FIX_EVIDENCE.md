# SIGPIPE remote-DoS — finding, fix, evidence

**Found** in the final adversarial battery (disconnect-storm), pre-#30,000.

## Vulnerability (OLD behavior — rc=141)
A peer that connects and abruptly closes/RSTs while the node is writing to it raised SIGPIPE,
whose default action terminated the node. Reproduced: ~13 half-open connections → node dead,
`rc=141` (128+13 = SIGPIPE), no crash-log. Trivial remote DoS.

## Root cause
No `SIGPIPE` handler installed (only SIGSEGV/SIGABRT/SIGFPE); `write_exact()` used `write()`
without `MSG_NOSIGNAL`.

## Fix (commit 7b9ac273, minimal, non-consensus)
- `signal(SIGPIPE, SIG_IGN)` at startup (belt).
- `send(..., MSG_NOSIGNAL)` in `write_exact()` (suspenders).
→ write()/send() return EPIPE → `write_exact` returns false → peer dropped cleanly; node lives.

## Evidence (NEW behavior)
300 half-open + burst(200 parallel) + partial-handshake+close + close-during-response +
RST(SO_LINGER 0) → NODE ALIVE, RPC ALIVE, FD STABLE (7→7, no leak), 0 crash, no log flood.
Permanent regression: tests/warroom_lab/sigpipe_regression.sh → 10/10 PASS.

## BASELINE note
`78fefb67` (V30000 BASELINE) ALSO has this bug (no SIGPIPE handler; pre-existing, not from
D1/D2). It remains the historical/operational rollback target, but **must NOT be described as
a "secure fallback" against this vector** — it carries a KNOWN SIGPIPE DoS. The V30000 FINAL
CANDIDATE (7b9ac273) is the first build without it.
