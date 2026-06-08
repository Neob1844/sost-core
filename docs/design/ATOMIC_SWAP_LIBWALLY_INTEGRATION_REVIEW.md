# Atomic Swap — libwally-core integration review

**Status:** PLAN ONLY. No real signing code is enabled by this document
or the companion CMake skeleton. `SOST_BTC_HTLC_SIGNING` stays `OFF` by
default. `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` stays `INT64_MAX`. The
backend is still a closed stub returning `disabled_result()` from every
function in `src/atomic_swap_btc_signing.cpp`.

**Scope:** evaluate the four candidate integration paths for adding
real BTC HTLC signing to SOST, recommend one, and define the CMake
contract that any future implementation must satisfy. This document
itself activates nothing — it is the preparation needed before Phase C
(real signing with vendored library) is even attempted.

**Companion artifact:** `docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md`
(the original "do not implement from scratch" report) remains in force.
This document supersedes its open-ended "decide later" section with a
concrete integration plan.

---

## 1. Why libwally-core specifically

The STOP REPORT evaluated four candidate libraries (see its §3). For
quick reference:

| candidate | size | audit | fuzz | recommendation |
|---|---|---|---|---|
| libbitcoin-system | ~30 MB + Boost | partial | no | rejected (too heavy, Boost) |
| **libwally-core** | **~3 MB**, no Boost | **OSS-Fuzz integrated** | **continuously** | **RECOMMENDED** |
| Bitcoin Core src/script | ~5 MB | most reviewed code in crypto | yes | runner-up (vendoring difficulty) |
| from scratch | n/a | n/a | n/a | rejected (single-point-of-failure surface) |

libwally-core wins on three independent axes:

1. **Audit posture.** Continuously fuzzed via Google's OSS-Fuzz since
   2019. Used in production by Blockstream Green wallet, Liquid, Jade
   hardware wallet. The exact code path we need (BIP-143 sighash +
   BIP-340 Schnorr + Bech32 encoding) is the hot path for every
   Liquid swap and every Green transaction.
2. **Surface size.** ~3 MB of C source, no Boost dependency, builds
   cleanly under autotools. The full library compiles in under 30
   seconds on a modest VPS.
3. **API stability.** The `wally_*` C API is versioned and has not
   broken backward compatibility since v0.8 (2020). Pinning a
   specific release tag does not require carrying patches.

The only reason to prefer Bitcoin Core's `src/script` subset would be
"maximal review attention." That gain is real but the operational
cost of pulling a subset of a 100 MB+ tree, keeping it in sync, and
adapting our own makefile to its `crypto/` + `script/` subdirectories
is high. libwally is the better engineering trade-off for an L1
project of SOST's size.

---

## 2. Reproducible integration — four options

The integration MUST be reproducible: an operator who clones the SOST
repo and runs `cmake -DSOST_BTC_HTLC_SIGNING=ON` must get a
bit-identical libwally build, not "whatever the apt cache has today."

Four candidate paths in increasing order of reproducibility guarantee:

### 2.1 (REJECTED) Distro package via `apt install libwally-core-dev`

* Pro: zero changes to the SOST repo.
* Con: not bit-reproducible. Debian/Ubuntu may carry different patch
  levels at different points in time. The same `cmake` invocation on
  two different days yields two different binaries.
* Con: not all distros package libwally (Alpine, RHEL, Arch require
  manual builds anyway).
* **Verdict:** disqualified by the reproducibility requirement.

### 2.2 (REJECTED) CMake `FetchContent_Declare` without commit pin

* Pro: zero developer setup (CMake fetches the source on configure).
* Con: VIOLATES the master-command rule "Prohibido: descarga no
  pineada durante build normal." The default behaviour of
  `FetchContent` is to fetch the tip of a branch, which is not
  reproducible.
* **Verdict:** disqualified.

### 2.3 (ACCEPTABLE) CMake `FetchContent` with hardcoded git commit hash

* Pro: reproducible (`GIT_TAG <40-hex commit>` pins exactly).
* Pro: requires no submodule maintenance — the CMake hash IS the
  pin.
* Con: requires network access during build. CI and disconnected
  builds need a local cache or mirror.
* Con: every clean build re-downloads ~3 MB unless `FETCHCONTENT_BASE_DIR`
  points to a persistent cache.
* **Verdict:** acceptable fallback. Documented but not the
  recommended path.

### 2.4 (RECOMMENDED) Git submodule pinned to an audited release tag

* Pro: maximally reproducible — the submodule SHA is recorded in our
  tree exactly. No network needed at build time after the initial
  `git submodule update --init`.
* Pro: standard developer workflow. Operators who have already cloned
  SOST run a single `git submodule update --init --recursive`.
* Pro: aligns with how SOST already vendors `forge-std` under
  `contracts/atomic-swap/lib/forge-std/`.
* Con: adds ~3 MB to the SOST repo (one-time, then immutable).
* Con: requires committing a `.gitmodules` entry. Public submodules
  are sometimes seen as a maintenance burden, but libwally's
  release cadence is slow (1–2 stable releases / year) and its
  release tags are signed by the maintainer.

**Recommended path:** **2.4 (git submodule)**, with `FetchContent`
pinned to the same commit as a documented fallback for builders who
prefer not to use submodules.

---

## 3. Pin target — recommended libwally tag

**Updated 2026-05-25 during the actual vendoring ceremony. The original
values in this section (release_1.4.0 / Lawrence Nahum / key
`0xCB37F8B0`) were the upstream state at the time this plan was
written. Upstream has rotated both maintainer and signing key since
then. The companion document
[`ATOMIC_SWAP_LIBWALLY_VENDOR_CEREMONY.md`](ATOMIC_SWAP_LIBWALLY_VENDOR_CEREMONY.md)
records the verbatim ceremony output for the actual pin.**

* Repository:                `https://github.com/ElementsProject/libwally-core`
* Pinned tag:                **`release_1.5.3`** (latest stable, released 2026-04-15)
* Pinned commit:             **`000137393a436d55a18971ca93a2d20a54d55437`**
* Submodule path:            `vendor/libwally-core/`
* Maintainer (current):      **Jon Griffiths** `<jon_p_griffiths@yahoo.com>`
* Primary key fingerprint:   **`129EE55E90E6E7BB5ED3530DFD9FCBA3C53CED20`**
* Signing subkey fingerprint:**`E6CC917F43F36FC09BBCC604F71C22C3DB1F7227`**
* Authoritative source:      upstream [`SECURITY.md`](https://github.com/ElementsProject/libwally-core/blob/master/SECURITY.md)

The previously-named maintainer (Lawrence Nahum, key `0xCB37F8B0`) is
legacy. The maintainer rotated to Jon Griffiths and the project signs
all release tags with the fingerprint above, including both
`release_1.4.0` and the chosen `release_1.5.3`. Either tag verifies
successfully against the current maintainer key; we pin `release_1.5.3`
because it is the latest stable and includes fixes to `tx`/`psbt`
code paths that are directly relevant to our future HTLC signing
work.

The vendoring commit message quotes the `git verify-tag release_1.5.3`
output verbatim. The full ceremony reproduction commands and their
expected outputs live in `ATOMIC_SWAP_LIBWALLY_VENDOR_CEREMONY.md`.

---

## 4. CMake contract

The CMake skeleton added in this commit (companion to this document)
implements the following contract, which any future Phase C
implementation MUST satisfy:

### 4.1 Default state — `SOST_BTC_HTLC_SIGNING=OFF`

* The configure step does NOT look for libwally.
* The build proceeds normally.
* `src/atomic_swap_btc_signing.cpp` compiles to a translation unit
  that returns `disabled_result()` from every external function.
* All atomic-swap C++ tests pass:
    test-atomic-swap-htlc-lock         (37 assertions)
    test-atomic-swap-htlc-helpers      (22 assertions)
    test-atomic-swap-htlc-rpc          (16 assertions)
    test-atomic-swap-btc-script        (19 assertions)
    test-atomic-swap-btc-signing       (15 assertions — confirms disabled)
    test-atomic-swap-coordinator       (39 assertions)
* `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == INT64_MAX` (consensus gate).

This is the **operator-default reality** for the foreseeable future.
No user-facing change vs. today.

### 4.2 Opt-in state — `cmake -DSOST_BTC_HTLC_SIGNING=ON`

* The configure step probes for libwally via `pkg-config wallycore`
  AND `find_path(WALLY_INCLUDE_DIR wally_bip32.h)`.
* If EITHER probe fails AND `SOST_BTC_HTLC_SIGNING=ON`, configure
  exits with `FATAL_ERROR` and a message that points the operator
  at this document and suggests:
      1. `git submodule update --init vendor/libwally-core/`
      2. follow vendor/libwally-core/BUILDING.md to compile, then
         re-run cmake with the resulting paths via
         `-DWALLY_INCLUDE_DIR=... -DWALLY_LIBRARY=...`
* If both probes succeed, the macro `SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY=1`
  is defined PUBLIC on `sost-core`, and `${WALLY_LIBRARY}` is added to
  `sost-core`'s link list.
* `src/atomic_swap_btc_signing.cpp` IS still a stub returning
  `disabled_result()` until Phase C wires the real `wally_*` calls.
  The macro exists so that Phase C can switch at the preprocessor
  level without further CMake changes.

### 4.3 Independence from the consensus gate

The CMake flag `SOST_BTC_HTLC_SIGNING` and the C++ constant
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` are independent.

* Flipping the CMake flag changes ONLY what the wallet/CLI can do
  off-chain. It does NOT change what the SOST chain accepts.
* Flipping the consensus constant changes what the SOST chain
  accepts at the named height. It does NOT change what the wallet
  can sign.
* Both MUST be flipped in coordinated commits, with external audit
  evidence, before any mainnet activation. Either flip alone is a
  pure no-op for the chain's safety posture.

---

## 5. What Phase C will need

This document does NOT implement signing. When the project is ready
to run Phase C, the following must be in place:

1. The vendored submodule under `vendor/libwally-core/` at the pinned
   commit, with the maintainer-signed release tag verified.
2. The CMake configure passes with `SOST_BTC_HTLC_SIGNING=ON` and
   reports both probes as `OK` (no FATAL_ERROR).
3. The full BIP-143 sighash test-vector battery (added in Phase B)
   passes when libwally is the reference implementation.
4. The full BIP-173 Bech32 + BIP-350 Bech32m vector battery (added
   in Phase B) passes when libwally is the reference implementation.
5. Phase C then replaces each `disabled_result()` body in
   `src/atomic_swap_btc_signing.cpp` with the corresponding `wally_*`
   call sequence, gated under `#ifdef SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY`.
6. The disabled-stub fallback is preserved verbatim for the OFF case
   (defense in depth).
7. **STOP condition for Phase C:** if a single test vector fails or
   if any signing call could observably leak the private key (logs,
   exceptions, side channels), Phase C halts. The backend stays
   disabled and a follow-up `ATOMIC_SWAP_BTC_SIGNING_PHASE_C_HALT.md`
   documents what blocked it. No "almost-works" implementation is
   ever merged.

---

## 6. Verification that this commit changes nothing observable

Run from the repo root:

```bash
# Build the OFF default — must succeed and not look for libwally.
cmake -S . -B build-phase-a-off -DCMAKE_BUILD_TYPE=Release
cmake --build build-phase-a-off -j$(nproc)
./build-phase-a-off/test-atomic-swap-btc-signing   # 15/15 passed, all "disabled"

# Build the ON case ON A SYSTEM WITHOUT libwally — must FAIL configure
# cleanly with a clear error pointing to this document.
cmake -S . -B build-phase-a-on -DCMAKE_BUILD_TYPE=Release \
    -DSOST_BTC_HTLC_SIGNING=ON
# expected: configure exits with FATAL_ERROR, mentions
# "vendor/libwally-core/" and this document path.

# Consensus gate sanity:
grep "ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT" include/sost/atomic_swap.h
# expected: ... = INT64_MAX;
```

If any of the three behaviours above is not observed, this commit is
buggy and must NOT be merged.

---

## 7. Out of scope for this commit

* Adding the submodule under `vendor/libwally-core/` — that requires
  the maintainer signature verification ceremony and a separate
  commit.
* Writing the BIP-143 / BIP-173 / BIP-350 test vector batteries —
  that is Phase B.
* Wiring `wally_*` calls into the backend — that is Phase C.
* Flipping any consensus or build-time defaults — explicitly
  forbidden by the master command.

This is a planning artifact. It commits the CMake contract and the
integration decision into the tree so the next engineering session
has zero ambiguity about what to do next.

---

**Audit trail:**
* `docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md` — original
  "do not implement from scratch" decision.
* `include/sost/atomic_swap_btc_signing.h` — disabled API surface.
* `src/atomic_swap_btc_signing.cpp` — `disabled_result()` stubs.
* `CMakeLists.txt` — SOST_BTC_HTLC_SIGNING option (this commit
  expands the ON branch with the probe-and-fail-clean logic
  documented in §4.2).
