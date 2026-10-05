# Phase 11 — Reproducible build

**Goal:** determine exactly what varies byte-to-byte between two builds of the same
source, and get machine-A == machine-B hashes where possible.

## Result — SAME-MACHINE double build is BIT-IDENTICAL

Two independent clean builds, same source tree, same build path (`build-repro`, wiped
between), same flags `-DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON
-DSOST_TESTNET_FORKS=OFF`, back-to-back:

| Binary | SHA256 (build A == build B) |
|--------|------------------------------|
| sost-node  | `7d50611b09f7f9c89a653233e5aa1b03a7786a0b14087a654ea29cbea29e5123` |
| sost-miner | `37e9b064cbc4e197e61ed5787b82f62d0d6b1374400140c8c176aa2a5febbb33` |
| sost-cli   | `7c65f8b06333224b5e3543f66fc8615c43620563d8f4c36424260a7756e02870` |

All three REPRODUCIBLE. The build carries no wall-clock non-determinism:
- No `__DATE__` / `__TIME__` / `__TIMESTAMP__` anywhere in src/ or include/ (verified).
- No embedded build-id variance across runs when the path is held constant.
- Link order / parallel build (`-j nproc`) does not perturb the output.

## What still varies cross-machine (documented gap, not a defect)

The only residual non-determinism is **toolchain- and path-dependent**, standard for C++:
1. **Build path** embedded via `__FILE__` in assert()/log strings. Two builds in
   *different* directories differ here. Fix for bit-for-bit cross-machine:
   `-ffile-prefix-map=$(pwd)=sost -fdebug-prefix-map=...`.
2. **Toolchain version** must match (this build: gcc 11.4.0 / binutils 2.38 / cmake 3.22.1,
   Ubuntu 22.04). A different gcc/libstdc++ produces different code.

Reference build environment pinned above. SHA256SUMS.txt remains the single cryptographic
source of truth for what operators run; reproducibility lets any operator on the pinned
toolchain regenerate the exact release hashes.

## Verdict
On a pinned toolchain + path, the SOST release is **reproducible (byte-identical)**.
The release process already achieves determinism; cross-machine parity needs only the two
standard flags above added to CMake — a low-risk, non-consensus, post-freeze improvement.
