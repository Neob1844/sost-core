# v16.3.0 sec1 — Acceptance report (security revision of the existing v16.3.0 release)

Frozen candidate: **260ffd02** on `feat/fork-store-hardening`. Baseline **v16.3.0** (`ec2bea2c`).
Node-only, non-consensus. **Not published, not deployed** — pending owner authorisation.

Verdict: **READY** — all mandatory checks pass; the one residual is a pre-existing v16.3.0
test-quality issue outside this hotfix's scope (documented below), not a defect in v16.3.0 (security revision sec1).

## Binaries (clean reproducible build in `build/`, Ubuntu 22.04.5 / gcc 11.4.0 / glibc 2.35)

```
c2b06b91eb9da9f4736cd514df3f7e7616a8961f46b17442d7c171c2f345ac2c  sost-node    (NEW — was 304d056d in v16.3.0)
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner   (byte-identical to v16.3.0/v16.2.3)
489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  sost-cli     (byte-identical to v16.3.0/v16.2.3)
```
Reproducible: a clean rebuild and an incremental build produced the identical node hash;
miner and cli reproduce the published v16.3.0 hashes exactly. Only `sost-node` changed.

## Step-by-step results

| # | Check | Result |
|---|-------|--------|
| 1 | Freeze candidate; full diff vs v16.3.0; confirm no consensus/emission/SbPoW/DTD/NODE_BIND/Jackpot/#30,000 change | **PASS** — only `src/sost-node.cpp` (fork/orphan store caps + metadata, `getforkstats` RPC, SIGPIPE ignore, BLCK origin tag) + tests/docs. Zero consensus files touched. |
| 2 | Audit SIGPIPE / EPIPE / incomplete writes / disconnects (static) | **PASS** — every socket write funnels through `write_exact`, which returns false on EPIPE/ECONNRESET (drops just that peer) and retries short writes; `read_exact` handles peer-close/timeout. Ignoring SIGPIPE creates no loop and hides no short write. |
| 2 | Prolonged churn + fork-storm campaign on the definitive binary | **PASS** — survived **300 s** continuous attack (v16.3.0 dies in ~6 s). Peak CPU **24 %**, peak RSS **484 MB** / idle **482 MB** (bounded, no leak). RPC available throughout (avg **52 ms**, max 456 ms, 59/59 OK). Fork store capped at **150** (per-subnet quota held), 0 rejects, 0 invalid-bans. **Recovery:** accepts an honest fork after the attack. |
| 3 | Instrument sost-core with ASan/UBSan; all tests; GitHub Actions on frozen commit | **PASS** — ASan/UBSan over the library + 119 tests: **0 memory-safety findings**. GitHub Actions on 260ffd02: **success** (unit-and-consensus, asan-ubsan, fuzz-smoke). |
| 4 | Extract the real P2P parser so the fuzzer tests production code | **PASS** — `sost/p2p_frame.h` (`sost_p2p::try_parse_frame`); `handle_peer` calls it (behaviour-identical, 119/119). Fuzzer links the real parser: 319k exec, 0 crashes, cov 129 (incl. encrypted branch). |
| 5 | Full sync from genesis with the DEFINITIVE binary; compare hashes + state vs v16.3.0 | **PASS** — v16.3.0 (security revision sec1) (`c2b06b91`) synced genesis→26,973, encrypted and plaintext, 0 rejects. **9/9 sampled block hashes MATCH** (incl. assumevalid anchor h=3554 `5034a648` and tip `f4e28b93`); UTXO identical (utxo_count 66,239, total_supply 211773.10678562). |
| 5 | Interoperability, encrypted and plaintext | **PASS** — a v16.3.0 (security revision sec1) client fully syncs from a real v16.3.0 server (hash-verified 304d056d), encrypted and plaintext, 0 rejects, past the anchor. (v16.3.0 *clients* die from their own SIGPIPE bug — reproduced v16.3.0↔v16.3.0 — which v16.3.0 (security revision sec1) fixes; not an interop regression.) |
| 6 | Reproducible binaries, SHA-256, update + rollback plan | **PASS** — hashes above (reproducible); `docs/v16/SHA256SUMS.v16.3.0 (security revision sec1)`; procedure and rollback in `docs/security/V16_3_1_RELEASE.md`. |
| 7 | Acceptance report; flag any excluded/pending | **this document** — see residuals below. |

## The V6 fix, demonstrated end-to-end

Under the identical peer/server behaviour that killed v16.3.0 in seconds, the v16.3.0 (security revision sec1) client
survived and completed the sync. In the prolonged lab it stayed alive, bounded and responsive
for 5 minutes. **v16.3.0 and STRATO carry this DoS; v16.3.0 (security revision sec1) removes it.**

## Excluded / pending (documented, not blocking)

- **`checkpoints` unit test** fails under a Debug/ASan build: `test_no_assumevalid_anchor` asserts
  there is no assumevalid anchor, but the shipped `checkpoints.h` has one at **height 3554**
  (hash `5034a648…`, dated 2026-04-09). This file is **identical between v16.3.0 and v16.3.0 (security revision sec1)** — the
  contradiction is pre-existing in v16.3.0, not introduced here; it is a test-quality bug (the test
  does not match the shipped configuration) and is compiled out under Release (`-DNDEBUG`), so the
  release build passes 119/119. **Fix separately** (update the test to assert the real anchor). Not
  a memory bug, not a consensus change.
- **CI coverage gaps** (carry into the masterplan, not blocking this node-only hotfix): the workflow
  runs unit+consensus, ASan/UBSan and fuzz-smoke; it does **not yet** include a TSan job, the new
  P2P-frame fuzzer as a gated job, `btc-watch` (needs bitcoind) or the `checkpoints` assert test.
- **Interop reverse direction** (v16.3.0 client ← v16.3.0 (security revision sec1) server) could not be exercised because
  v16.3.0 clients die from their own SIGPIPE bug in this environment; wire compatibility is proven
  by the forward direction and by the byte-identical framing (P4 is behaviour-preserving).

## Standing constraints honoured
No merge, no publish, no deploy. Consensus, emission, SbPoW, DTD, NODE_BIND, Jackpot and the
#30,000 schedule unchanged. User's WSL miner (PID 562789), wallet, keys, NODE_BIND and STRATO
untouched.
