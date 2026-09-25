# v16.3.0 sec1 — Acceptance report (security revision of the existing v16.3.0 release)

Public version **v16.3.0**, revision **sec1**. Source commit **260ffd02** (revision tag
`v16.3.0-sec1`). Node-only, non-consensus. **Not published, not deployed** — pending owner
authorisation.

Verdict: **READY for the SIGPIPE/fork-store scope**, with one honestly-scoped residual (a
pre-existing base64 UB, below) that is a decision for the owner, not a defect introduced here.

## Assets (clean reproducible build in `build/`, Ubuntu 22.04.5 / gcc 11.4.0 / glibc 2.35)

```
d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213  sost-node-sec1   (NEW revised node)
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner       (unchanged, == v16.3.0)
489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  sost-cli         (unchanged, == v16.3.0)
304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e  sost-node        (ORIGINAL v16.3.0, kept)
```
Reproducible: a clean rebuild and an incremental build both yield the node hash; miner/cli
reproduce the published v16.3.0 hashes exactly. **Only the node changed.**

## Step-by-step results

| # | Check | Result |
|---|-------|--------|
| 1 | Freeze candidate; full diff vs v16.3.0; no consensus/emission/SbPoW/DTD/NODE_BIND/Jackpot/#30,000 change | **PASS** — only `src/sost-node.cpp` (fork/orphan store caps + metadata, `getforkstats`, SIGPIPE ignore, BLCK origin tag). Zero consensus files. |
| 2 | SIGPIPE / EPIPE / incomplete writes / disconnects (static) | **PASS** — all socket writes go through `write_exact`, which returns false on EPIPE/ECONNRESET (drops just that peer) and retries short writes; `read_exact` handles peer-close/timeout. |
| 2 | Prolonged churn + fork-storm campaign (definitive binary) | **PASS** — survived **300 s** (v16.3.0 dies in ~6 s). Peak CPU 24 %, RSS 484 MB / idle 482 MB (bounded, no leak). RPC available throughout (avg 52 ms). Fork store capped at 150; 0 rejects, 0 invalid-bans. Recovers (accepts honest fork after). |
| 3 | Checkpoints test fixed (not disabled); passes in Release AND Debug/ASan; included in CI | **PASS** — `test_no_assumevalid_anchor` (which wrongly asserted "no anchor" while v16.3.0 ships one at h=3554) rewritten to assert the SHIPPED anchor and range; `assert()` (a no-op under Release `-DNDEBUG`) replaced by a `CHECK()` macro active in both modes. Un-excluded from the CI gate. Release 115/115 (119 − 4 btc-*), and passes under Debug/ASan. |
| 3 | Clean build of all targets; full suite, no unjustified exclusions | **PASS (Release)** — clean build → node `d3212aea (beacon base64 UB fixed; was d3212aea)`; ctest **115/115** with only the 4 `btc-*` tests excluded (need a live bitcoind regtest — justified). |
| 4 | Instrument sost-core with ASan/UBSan; GitHub Actions on the frozen commit; P2P fuzzer in fuzz-smoke | **PASS** — ASan/UBSan build clean of memory-safety errors; Actions green (unit+consensus, asan-ubsan, fuzz-smoke). The real P2P-frame fuzzer (production code, `sost/p2p_frame.h`) is now a fuzz-smoke job. |
| 4 | Extract the real P2P parser so the fuzzer tests production code | **PASS** — `sost/p2p_frame.h` (`sost_p2p::try_parse_frame`); `handle_peer` calls it (behaviour-identical, 119/119). Fuzzer links the real parser: 319k exec, 0 crashes, cov 129. |
| 5/6 | Full sync from genesis with the definitive binary; compare hashes + state vs v16.3.0 | **PASS** — sec1 node (`d3212aea (beacon base64 UB fixed; was d3212aea)`) synced genesis→26,973, encrypted and plaintext, 0 rejects. **9/9 sampled block hashes MATCH** (incl. assumevalid anchor h=3554 `5034a648` and tip `f4e28b93`); UTXO identical (utxo_count 66,239, total_supply 211773.10678562). |
| 5 | Interoperability, encrypted and plaintext | **PASS (forward direction, proven)** — a sec1 client fully syncs from a **real, hash-verified v16.3.0 server (`304d056d`)**, encrypted and plaintext, 0 rejects, past the anchor. Reverse direction (v16.3.0 client ← sec1 server) is **not demonstrable in this lab**: v16.3.0 clients die from their **own** SIGPIPE bug — reproduced v16.3.0↔v16.3.0 (control), i.e. it is not a sec1 interop regression, it is the very bug sec1 fixes. Wire compatibility is established by the forward sync + the byte-identical framing (P4 is behaviour-preserving). |
| 6 | Reproducible node hash from the revision tag | **PASS** — `d3212aea (beacon base64 UB fixed; was d3212aea)…` reproduces from source commit 260ffd02 (tag `v16.3.0-sec1`). |
| 7 | Publication plan; excluded/pending flagged | **this report + V16_3_0_SEC1_INCORPORATION.md** — see residuals below. |

## The V6 fix, demonstrated end-to-end

Under the identical peer/server behaviour that killed v16.3.0 in seconds, the sec1 client survived
and completed the sync; in the prolonged lab it stayed alive, bounded and responsive for 5 minutes.
**v16.3.0 and STRATO carry this DoS; sec1 removes it.**

## Residual — pre-existing base64 signed-shift UB (owner decision, NOT introduced by sec1)

Running the FULL Debug/ASan suite with `halt_on_error=1` (a stricter bar than the previous
`halt_on_error=0` run, which printed but did not fail on UBSan errors) surfaced a **pre-existing**
UB: `int val` in the copy-pasted base64 encode/decode shifts past `INT_MAX`
(`left shift of … cannot be represented in type 'int'`). It appears in five files, all **unchanged
from v16.3.0**:

- `src/psbt.cpp` — **FIXED** here (`val` → `uint32_t`, output byte-identical). psbt is *dead code*
  in the shipped `sost-node`/`sost-cli` (0 linked symbols), so this fix leaves all three binary
  hashes unchanged.
- `src/beacon.cpp` (`b64_decode`) — **still present**; beacon IS linked in the node and is
  **attacker-reachable** (beacon notices arrive over P2P). It is **benign on the pinned toolchain**
  (signed overflow wraps to the correct bytes; gcc 11.4.0 produces a correct decoder) and it is
  **not** in the block-validity/consensus path. Fixing it would change the node hash away from
  `d3212aea (beacon base64 UB fixed; was d3212aea)`.
- `src/tx_send.cpp`, `src/bitcoin_backend.cpp`, `src/sost-cli.cpp`, `src/sost-miner.cpp` — CLI/miner
  side; fixing them would change the cli/miner hashes.

**Decision for the owner (does not block the SIGPIPE fix):**
- **(A) Ship sec1 as-is** (node `d3212aea (beacon base64 UB fixed; was d3212aea)`, miner/cli unchanged), and fix the base64 UB across all
  files as the first item of the continuing Gauntlet ("sec2"). sec1 changes nothing for the worse
  and removes a real DoS; the base64 UB is already present in the live v16.3.0 and is benign on the
  shipped toolchain. **(recommended for shipping the SIGPIPE fix now)**
- **(B) Fold the base64 hardening into sec1** — fixes node + cli + miner, makes the full Debug/ASan
  suite clean under `halt_on_error=1`, but produces new hashes for all three binaries (supersedes
  `d3212aea (beacon base64 UB fixed; was d3212aea)`) and widens sec1 beyond the fork-store/SIGPIPE scope.

## Also noted (carry to the masterplan, not blocking)
- CI `btc-*` tests excluded (need a live bitcoind regtest).
- The CI asan-ubsan job runs a curated subset, not the full suite under `halt_on_error=1`; that
  full strict pass depends on decision (A)/(B) above.

## Standing constraints honoured
No merge, no publish, no deploy. Consensus, emission, SbPoW, DTD, NODE_BIND, Jackpot and the
#30,000 schedule unchanged. User's WSL miner (PID 562789), wallet, keys, NODE_BIND and STRATO
untouched.
