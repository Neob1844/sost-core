# sec2 — reproducible build, SBOM, and signing (Gauntlet item G)

Lets any third party (independent operator, exchange, auditor) rebuild `sost-node-sec2` and get
the SAME hash, and verify the manifest's authenticity — a decentralization primitive, not just a
release artifact.

## Source
- Branch `release/v16.3.0-sec1-rpc`; node source at commit `30fa5a2d` (the later `91ca9ac0`
  adds only docs and does not change the binary). Base = sec1 `32cabab2` + RPC fix `ebe4f790`.

## Toolchain (as built and verified)
| component | version |
|---|---|
| OS | Ubuntu 22.04 (WSL2) |
| gcc | 11.4.0 (Ubuntu 11.4.0-1ubuntu1~22.04.3) |
| glibc | 2.35 (Ubuntu GLIBC 2.35-0ubuntu3.15) |
| cmake | 3.22.1 |

## Build command (deterministic)
```
cmake -S <src> -B <src>/build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build <src>/build --target sost-node sost-miner sost-cli -j
```
**Reproducibility invariant (verified):** the build dir must be named EXACTLY `build` AND live
INSIDE the source tree, so `-ffile-prefix-map=<src>=/sost` normalizes source AND build paths to
`/sost`. Two clean builds under this rule produced the identical node hash `5b50a448…`; a build
dir named `build2`, or an out-of-tree build dir, changes the NODE hash (miner/cli stay identical).
This is the one caveat and it is now documented so a verifier can reproduce exactly.

## SBOM — runtime dynamic dependencies of `sost-node-sec2`
```
ld-linux-x86-64.so.2      (dynamic loader)
libc.so.6                 glibc 2.35
libstdc++.so.6 / libgcc_s.so.1 / libm.so.6   (gcc 11.4.0 runtime)
libcrypto.so.3            OpenSSL 3 (find_package(OpenSSL REQUIRED))
libsecp256k1.so.0         secp256k1
```
No network/DB libraries; the P2P/RPC stack is in-tree. libwally is vendored (see submodule),
built as part of the tree; not a runtime .so dependency of the node.

## Hashes (definitive)
```
sost-node-sec2  5b50a448f3e319ef6137da61093750bd6d286cc508ff69fe994cf3532c4fa157
sost-miner      2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  (== v16.3.0)
sost-cli        489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  (== v16.3.0)
```

## Signing procedure (execute at publish time with the project key; NOT done here)
Precedent exists (`website/api/v13_rc1_SHA256SUMS.asc`). At publish:
1. GPG detached-sign the manifest: `gpg --armor --detach-sign SHA256SUMS.v16.3.0-sec2`
   → `SHA256SUMS.v16.3.0-sec2.asc`.
2. Publish the `.asc` next to the manifest on the GitHub release AND the key fingerprint on the
   official website, so a verifier does: `gpg --verify SHA256SUMS.v16.3.0-sec2.asc` then
   `sha256sum -c SHA256SUMS.v16.3.0-sec2`.
3. Until a signing key is published, the GitHub release (authenticated upload) + the in-repo
   manifest are the integrity anchor; the fingerprint step is the hardening to add.

## Status
Reproducibility PROVEN (2 clean builds identical) + SBOM captured. Signing = documented
procedure, pending the owner's release key at publish time.
