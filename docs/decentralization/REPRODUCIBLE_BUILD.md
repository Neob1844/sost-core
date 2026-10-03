# SOST V30000 — Reproducible Build

This document lets any third party **clone the published source tag, build
`sost-node`, `sost-miner` and `sost-cli`, and compare their SHA-256 hashes
against the ones published with the release** — without anyone recompiling or
replacing the binaries already running on mainnet.

> **This recipe does not touch the running mainnet binaries.** It compiles a
> fresh, independent copy in a container (or a scratch directory) purely so you
> can verify that the published hashes come from the published source. Nothing
> here is deployed, swapped, restarted, or sent to the network.

---

## 1. What you are verifying

| | |
|---|---|
| Source tag | `v30000` |
| Repository | `https://github.com/Neob1844/sost-core` |
| Activation | Historical Jackpot V2 / DTD eligibility at block **#30,000** (mainnet, owner-locked) |
| Build system | CMake (`cmake_minimum_required(VERSION 3.16)`), C++17 |
| Output binaries | `sost-node`, `sost-miner`, `sost-cli` |

### Published SHA-256 (release `v30000`, `SHA256SUMS.txt`)

```
78fefb67a15615f3df1b0a4f498239ccba07ba47ce6e333d13d5d2afdcecbb56  sost-node
eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951  sost-miner
c8ae00b9a6745f7c84cc8791b9994d32052a07d1fed12aa82c4e283fba2f691b  sost-cli
```

Your build **matches** if the three hashes it prints are identical to the three
above.

---

## 2. Honesty: what "reproducible" does and does not mean here

Read this before you conclude anything from a hash comparison.

* **Path-independent — measured and true.** The build injects
  `-ffile-prefix-map=${CMAKE_SOURCE_DIR}=/sost`, so the absolute directory you
  build in is *not* baked into the binary. The same tag built in two different
  directories produces byte-identical binaries. You do **not** need to build in
  any particular path.

* **Cross-machine bit-for-bit determinism is NOT guaranteed.** Matching the
  published hashes depends on matching the **official toolchain exactly**
  (compiler, linker, libc, and the secp256k1/OpenSSL library builds). A
  different gcc, ld, glibc or dependency build can produce a *different but
  equally valid* binary.

* Therefore:
  * **Official binary you downloaded** → the SHA-256 **must** match the table
    above exactly. If it does not, do not run it.
  * **Binary you compiled yourself** → it matches the table **only** when you
    build in the official environment (Section 3). A different hash on a
    different toolchain is expected and is **not, by itself, evidence of
    tampering**.

* **If you do match the official toolchain and still get a mismatch, please
  report it** (open an issue on the repository with your exact OS, gcc/g++, ld,
  cmake, glibc and `libsecp256k1` / `libssl` versions, plus the hashes you got).
  That is exactly the signal this recipe exists to surface.

The quickest way to remove toolchain variables from the equation is to use the
Docker path (Section 4), which pins the environment for you.

---

## 3. Official build environment

The published hashes were produced in exactly this environment:

| | |
|---|---|
| OS | Ubuntu 22.04.5 LTS |
| Arch | x86_64 |
| Compiler | `g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0` |
| Linker | GNU ld (GNU Binutils for Ubuntu) 2.38 |
| CMake | 3.22.1 (repo requires ≥ 3.16) |
| libc | GNU libc 2.35 |

### Dependencies

From `CMakeLists.txt`:

* `find_package(OpenSSL REQUIRED)` → links `OpenSSL::Crypto` (provided by
  **`libssl-dev`**).
* `find_package(Threads REQUIRED)` → pthreads (provided by **`build-essential`**).
* **`libsecp256k1`** linked as `secp256k1`, and — because the mainnet build
  enables Phase 2 SbPoW — it **must** include the BIP-340 Schnorr module. CMake
  hard-fails configure if either `secp256k1_schnorrsig.h` or the
  `secp256k1_schnorrsig_verify` symbol is missing. On Ubuntu 22.04 the stock
  **`libsecp256k1-dev`** package (`0.1~20210825-2`) already ships the schnorrsig
  module, so no source build of secp256k1 is required.

> `vendor/libwally-core/` is present in the tree (it carries its own bundled
> copy of secp256k1), but the mainnet CMake build links the **system**
> `secp256k1` from `libsecp256k1-dev`, not the vendored one.

Install on Ubuntu 22.04:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git libssl-dev libsecp256k1-dev
```

### Required CMake options (do not change these)

| Option | Value | Why |
|---|---|---|
| `-DSOST_ENABLE_PHASE2_SBPOW` | **ON** (default ON) | REQUIRED for mainnet. A binary built with `OFF` cannot verify Phase-2 Schnorr-bound PoW and silently forks itself off the network. |
| `-DSOST_TESTNET_FORKS` | **OFF** (default OFF) | REQUIRED for mainnet. `ON` lowers fork-activation heights for a private testnet and will NOT match mainnet. |
| `-DCMAKE_BUILD_TYPE` | `Release` | Matches the official build (enables `-D_FORTIFY_SOURCE=2`). |

A binary built with `SBPOW=OFF` **or** `TESTNET_FORKS=ON` will **not** match the
published hashes and is **not consensus-capable on mainnet**.

---

## 4. Build with Docker (recommended — pins the toolchain)

The `Dockerfile.reproducible` alongside this file pins Ubuntu 22.04 + the
dependency set, clones the `v30000` tag, builds with the exact flags, and prints
the three SHA-256 hashes at the end of the build log.

```bash
# Run from the repository root (the build context is only used for the Dockerfile;
# the source is cloned fresh from the tag inside the image).
docker build -f docs/decentralization/Dockerfile.reproducible \
             -t sost-repro:v30000 .
```

The final lines of the build log are the hashes to compare:

```
=== SOST V30000 reproducible build — SHA256 ===
<hash>  build/sost-node
<hash>  build/sost-miner
<hash>  build/sost-cli
```

### Extracting the binaries

```bash
# Create a container from the image without running it, copy the binaries out,
# then discard the container.
cid=$(docker create sost-repro:v30000)
docker cp "$cid":/sost/build/sost-node  ./sost-node
docker cp "$cid":/sost/build/sost-miner ./sost-miner
docker cp "$cid":/sost/build/sost-cli   ./sost-cli
docker rm "$cid"

# Verify against the published table.
sha256sum sost-node sost-miner sost-cli
```

To build a different tag or from a fork, override the build args:

```bash
docker build -f docs/decentralization/Dockerfile.reproducible \
             --build-arg SOST_TAG=v30000 \
             --build-arg SOST_REPO=https://github.com/Neob1844/sost-core.git \
             -t sost-repro:v30000 .
```

---

## 5. Build bare-metal (Ubuntu 22.04)

```bash
# 1. Dependencies
sudo apt-get update
sudo apt-get install -y build-essential cmake git libssl-dev libsecp256k1-dev

# 2. Clone the exact published tag
git clone --depth 1 --branch v30000 \
    https://github.com/Neob1844/sost-core.git sost-core-v30000
cd sost-core-v30000

# 3. (optional) record the commit and toolchain for your report
git rev-parse HEAD
gcc --version | head -1
cmake --version | head -1

# 4. Configure with the EXACT mainnet flags
cmake -S . -B build \
      -DSOST_ENABLE_PHASE2_SBPOW=ON \
      -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release

# 5. Build only the three release binaries
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"

# 6. Hash them and compare against Section 1
sha256sum build/sost-node build/sost-miner build/sost-cli
```

Output binaries are at `build/sost-node`, `build/sost-miner`, `build/sost-cli`.

---

## 6. Confirm the binary is a mainnet / Phase-2 binary

Independent of the hash, you can confirm the SbPoW code path is compiled in
(this is the path a mainnet consensus binary must have):

```bash
strings build/sost-node  | grep -c 'POW-SIG/v11'   # must be > 0
strings build/sost-miner | grep -c 'POW-SIG/v11'   # must be > 0
```

A count of `0` means the binary was built with `SOST_ENABLE_PHASE2_SBPOW=OFF`
and is **not** consensus-capable on mainnet.

---

## 7. Reporting a mismatch

If you built in the official environment (Section 3) and your hashes differ from
Section 1, please open an issue on `https://github.com/Neob1844/sost-core`
including:

* the three hashes you obtained;
* `git rev-parse HEAD` of your checkout of tag `v30000`;
* `gcc --version`, `ld --version`, `cmake --version`, `ldd --version`;
* the installed versions of `libsecp256k1-dev` and `libssl-dev`
  (`dpkg -l | grep -E 'libsecp256k1-dev|libssl-dev'`);
* whether you built via Docker or bare-metal.

This is the feedback loop the recipe exists for: more independent builders
comparing hashes is what turns "trust the maintainer" into "verify the source."
