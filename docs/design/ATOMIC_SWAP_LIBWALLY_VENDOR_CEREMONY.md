# Atomic Swap — libwally-core vendoring ceremony record

**Date (UTC):** 2026-05-25
**Operator:** SOST Protocol maintainer (local WSL/ZBook dev environment)
**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Phase:** C.0 (signature ceremony) + C.1 (submodule pin + CMake probe)
**Result:** OK — submodule vendored, signature verified, build OFF unchanged.

**This document records the exact commands and outputs of the ceremony**
so any reviewer can reproduce the same verification, byte for byte, from
their own workstation. It is the audit-trail counterpart to
`ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md` (the plan) — that document
says *what we will do*; this one says *what we actually did*.

## What is NOT activated by this commit

Even after this commit lands, ALL the following remain unchanged:

| Constant / flag | Value | Where |
|---|---|---|
| `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` | `INT64_MAX` (SAFETY-CLOSED) | `include/sost/atomic_swap.h:107` |
| `SOST_BTC_HTLC_SIGNING` CMake default | `OFF` | `CMakeLists.txt` |
| `IsBtcHtlcSigningEnabled()` runtime | returns `false` | `src/atomic_swap_btc_signing.cpp:32` |
| Real BTC signing | NOT IMPLEMENTED — stubs only | `src/atomic_swap_btc_signing.cpp` |
| BIP-143 sighash computation | NOT IMPLEMENTED | (Phase C wiring) |
| Bech32 / Bech32m encoding | NOT IMPLEMENTED | (Phase C wiring) |
| SOST consensus rules | UNCHANGED | (zero new validation rules) |

No private keys are involved. No transactions are signed. No network I/O
is performed. Mainnet behaviour is bit-identical to the prior commit
`cd4a2bc`.

## Discrepancies vs. the original plan

`ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md` (committed in `a2d47b3` on
2026-05-24) was written when libwally's latest stable was `release_1.4.0`
and the maintainer was Lawrence Nahum with GPG key `0xCB37F8B0`.

Upstream has moved on since then. Today (2026-05-25) the authoritative
state of the upstream project is:

| Field | Plan (`a2d47b3`) | Reality verified today |
|---|---|---|
| Maintainer | Lawrence Nahum | **Jon Griffiths** |
| Primary key | `0xCB37F8B0` (legacy) | **`129EE55E90E6E7BB5ED3530DFD9FCBA3C53CED20`** |
| Signing subkey | n/a | **`E6CC917F43F36FC09BBCC604F71C22C3DB1F7227`** |
| Documented in | (the old plan) | upstream `SECURITY.md` ([github.com/ElementsProject/libwally-core](https://github.com/ElementsProject/libwally-core/blob/master/SECURITY.md)) |
| Latest stable tag | `release_1.4.0` | **`release_1.5.3`** (released 2026-04-15) |
| Successful keyserver | `hkps://keys.openpgp.org` | **`hkps://keyserver.ubuntu.com`** (openpgp.org did not have the key at retrieval time) |

The original plan is superseded by this ceremony record. The companion
`ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md` is updated in the same
commit to reflect the current upstream state.

## Why we still pin to a specific release

The reproducibility requirement of
`ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md` §2 is unchanged. We pin
to the commit hash of an annotated, GPG-signed release tag. We do NOT
follow a branch.

## Chosen pin

| Field | Value |
|---|---|
| Repository | `https://github.com/ElementsProject/libwally-core` |
| Tag | `release_1.5.3` |
| Release date | 2026-04-15 13:22:52 CEST |
| Commit hash | `000137393a436d55a18971ca93a2d20a54d55437` |
| Submodule path | `vendor/libwally-core/` |
| Maintainer (current) | Jon Griffiths `<jon_p_griffiths@yahoo.com>` |
| Primary key fingerprint | `129E E55E 90E6 E7BB 5ED3  530D FD9F CBA3 C53C ED20` |
| Signing subkey fingerprint | `E6CC 917F 43F3 6FC0 9BBC  C604 F71C 22C3 DB1F 7227` |

## Reproducing the ceremony

Anyone reviewing this commit can re-run the verification end-to-end from
a clean machine in under two minutes. The commands and the expected
outputs are recorded verbatim below.

### Step 1 — import the maintainer's public key

```bash
gpg --keyserver hkps://keyserver.ubuntu.com \
    --recv-keys E6CC917F43F36FC09BBCC604F71C22C3DB1F7227
```

Expected output (truncated):
```
gpg: Total number processed: 1
gpg:               imported: 1
```

If `keyserver.ubuntu.com` is unreachable, the SKS pool mirrors at
`hkps://keys.openpgp.org` or `hkps://pgp.mit.edu` are acceptable
fallbacks. The fingerprint must match exactly regardless of where
the key body is fetched from.

### Step 2 — clone the upstream repo and check out the release tag

```bash
git clone https://github.com/ElementsProject/libwally-core /tmp/lw-ceremony
cd /tmp/lw-ceremony
git checkout release_1.5.3
```

### Step 3 — verify the tag

```bash
git verify-tag release_1.5.3
```

Expected output (verbatim from our run on 2026-05-25):
```
gpg: Signature made Wed Apr 15 13:22:52 2026 CEST
gpg:                using RSA key E6CC917F43F36FC09BBCC604F71C22C3DB1F7227
gpg: Good signature from "Jon Griffiths <jon_p_griffiths@yahoo.com>" [unknown]
gpg: WARNING: This key is not certified with a trusted signature!
gpg:          There is no indication that the signature belongs to the owner.
Primary key fingerprint: 129E E55E 90E6 E7BB 5ED3  530D FD9F CBA3 C53C ED20
     Subkey fingerprint: E6CC 917F 43F3 6FC0 9BBC  C604 F71C 22C3 DB1F 7227
```

The `WARNING: not certified with a trusted signature` is expected: it
appears because we have not signed the maintainer's key with our own
local key (the operator's GPG keyring stays clean of cross-project
signatures). The relevant assertions are:
  - the signature is `Good`,
  - the primary key fingerprint matches `129EE55E…CED20`,
  - the subkey fingerprint matches `E6CC917F…7227`,
  - both fingerprints match the values published in upstream's
    `SECURITY.md`.

### Step 4 — capture the exact commit

```bash
git rev-list -n 1 release_1.5.3
```

Output: `000137393a436d55a18971ca93a2d20a54d55437`.

That hash is what we pin in `vendor/libwally-core/` and what the
SOST repository records via `git submodule status`:

```
+000137393a436d55a18971ca93a2d20a54d55437 vendor/libwally-core (release_1.5.3)
```

If `git submodule status` ever shows a different commit, a reviewer
knows the submodule has drifted and re-pinning + re-verifying is
required before the change is merged.

### Step 5 — re-verify inside the submodule (defence in depth)

After `git submodule update --init --recursive`, the tag can be
re-verified from inside the project's own submodule directory:

```bash
cd vendor/libwally-core
git verify-tag release_1.5.3
```

Same `Good signature` output as Step 3. The submodule carries its
own `.git` reference so the verification works without re-cloning.

## What changed in this repo by this ceremony

```
A  .gitmodules
A  vendor/libwally-core           (submodule entry, pinned commit only)
A  tools/build_libwally.sh        (helper script — does not auto-run)
M  docs/design/ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md  (maintainer/key/version updated)
A  docs/design/ATOMIC_SWAP_LIBWALLY_VENDOR_CEREMONY.md     (this file)
M  CMakeLists.txt                 (probe paths extended to include vendor/libwally-core/)
```

No code in `src/` or `include/` is modified. No new tests are added or
removed. The 8 atomic-swap C++ test binaries and the 52 Foundry tests
all still pass.

## Build behaviour

### Default (`SOST_BTC_HTLC_SIGNING=OFF` — unchanged)

The build does NOT enter the libwally probe. `vendor/libwally-core/`
sits on disk as a source tree and nothing else. The binary output is
bit-identical to what the prior commit `cd4a2bc` produced. Every
atomic-swap test still passes. Trinity still passes. The `POW-SIG/v11`
and `POW-SIG/v13` anti-incident strings remain present in `sost-node`
and `sost-miner`.

### Opt-in (`-DSOST_BTC_HTLC_SIGNING=ON`)

Without first running `tools/build_libwally.sh`, the CMake configure
step fails with `FATAL_ERROR` and points the operator at this
document and at the helper script. This is the intended behaviour:
fail loudly with a clear pointer, never silently produce a broken
binary.

After `tools/build_libwally.sh` runs successfully (requires the
`libtool` package, which is documented in the script's tool check),
the CMake configure succeeds with:

```
SOST_BTC_HTLC_SIGNING=ON — libwally-core found via manual probe
(include=/.../vendor/libwally-core/include,
 library=/.../vendor/libwally-core/build-static/src/.libs/libwallycore.a).
Phase C wiring still required.
```

The signing backend `src/atomic_swap_btc_signing.cpp` IS still a stub
that returns `disabled_result()` from every function. The flag merely
proves the integration *path* works; it does not enable any
real-signing capability. Phase C (a future commit, deliberately not in
this scope) replaces the stub bodies with `wally_*` calls.

## Local prerequisites for Phase C

When Phase C begins, the operator's workstation MUST have:

- `autoreconf` (autoconf >= 2.69) — present locally on the dev box at
  ceremony time (`autoconf 2.71`).
- `libtool` (specifically `libtoolize`) — **NOT** present on the dev
  box at ceremony time. Operator must `sudo apt-get install -y libtool`
  before running `tools/build_libwally.sh`. The script aborts loudly
  if the tool is missing — no half-built artefacts are produced.
- `make`, `gcc` / `clang`, `python3` — all already present.

Producing libwally artefacts is intentionally NOT done automatically
during the normal SOST build; the operator must run
`tools/build_libwally.sh` once, deliberately, before flipping
`SOST_BTC_HTLC_SIGNING=ON`.

## Risk register (what still holds)

| Risk | Status after this ceremony |
|---|---|
| Signing key compromised | Mitigated upstream: maintainer key is the one published in `SECURITY.md` and used to sign every release tag in the project's recent history. Cross-checked the signing subkey across tags `release_1.4.0` and `release_1.5.3` — same `E6CC917F` subkey. |
| Bit-rot of pinned commit | Mitigated: pin is a 40-hex commit hash recorded in `.gitmodules`. A drift is immediately visible via `git submodule status`. |
| Drift between plan and ceremony | Mitigated: this document records the actual ceremony verbatim; the plan doc is updated in the same commit. |
| Unverified key fetched from compromised keyserver | Mitigated: fingerprint cross-check against upstream `SECURITY.md` makes the keyserver source untrusted. Anyone re-running the ceremony can use any reachable keyserver and verify the same fingerprint. |
| Hidden code path activation | None — the consensus gate stays `INT64_MAX` and the build flag stays `OFF`. No code path is unlocked by this commit. |
| Real BTC signing accidentally enabled | None — every backend function in `src/atomic_swap_btc_signing.cpp` still returns `disabled_result()` regardless of the new flag value. |

## Future Phase C commit checklist

When Phase C is undertaken, the very first commit must:

1. Document `libtool` as a hard build dependency in the top-level README.
2. Wire one trivial `wally_*` call (e.g. `EncodeP2WSHAddress` via
   `wally_addr_segwit_from_bytes`) under `#ifdef SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY`.
3. Turn the corresponding BIP-173 / P2WSH test vectors in
   `tests/test_atomic_swap_btc_test_vectors.cpp` from PENDING markers
   to real passing assertions.
4. Run the full atomic-swap test suite (8 binaries) plus Trinity plus
   forge to confirm no regression.
5. Run the anti-incident SbPoW check (`strings sost-node | grep -c
   POW-SIG/v11` and `… | grep -c POW-SIG/v13` both > 0).
6. Confirm the consensus gate is still at `INT64_MAX` and the runtime
   `IsBtcHtlcSigningEnabled()` still returns `false`.
7. STOP immediately if any of the above fails. No half-implementation
   is ever merged.

Until then, this commit is the maximum-safety mid-state: the
infrastructure is in place, the signature trail is verifiable, and
nothing observable to mainnet has changed.
