# SOST V16 — Release Manifest

**DTD Jackpot V2.** Activation **#30,000** (mainnet, owner-locked). First V2 draw **#30,186**.

| | |
|---|---|
| Version | `v16.0.0-jackpot-v2` |
| Tag | `v16.0.0-jackpot-v2` |
| Final commit | see `git rev-list -n1 v16.0.0-jackpot-v2` |
| `HIST_JACKPOT_V2_HEIGHT` | **30000** |
| First V2 jackpot | **30186** (#30,000 is not a jackpot height) |
| Last V15 jackpot | 29,898 |
| `NODE_EPOCH_LENGTH` | 288 (= jackpot cadence) |
| `JACKPOT_V2_POW_WINDOW` | 5000 |
| `JACKPOT_V2_MIN_BLOCKS` | 3 |
| `HEARTBEAT_REQUIRED` / `HEARTBEAT_MAX_WINDOW` | 3 of last 4 |

## Where the SHA256 hashes live, and why they are not in this file

A hash of a binary built *from a tag* cannot be committed *inside* that tag — the
commit would change the tag's content and therefore the binary's provenance. The
authoritative hashes are therefore published as a **release artifact** beside the
tag, in `docs/v16/SHA256SUMS`, committed **after** the tag was created and
naming the tag it belongs to. The tag itself never changes.

```
verify:  sha256sum -c docs/v16/SHA256SUMS
```

The RC hashes that previous revisions of this file carried are **withdrawn** and
must not be used to verify anything.

## Official build environment

The published hashes were produced in exactly this environment:

| | |
|---|---|
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 5.15.167.4-microsoft-standard-WSL2 |
| Arch | x86_64 |
| Compiler | g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0 |
| Linker | GNU ld (GNU Binutils for Ubuntu) 2.38 |
| CMake | 3.22.1 |
| libc | GNU libc 2.35 (Ubuntu GLIBC 2.35-0ubuntu3.15) |

Build recipe:

```bash
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
```

## Reproducibility — what has actually been tested

```
PATH-INDEPENDENT BUILD        = YES   (measured)
CROSS-MACHINE REPRODUCIBILITY = NOT PROVEN
```

Binaries used to embed their absolute build directory (36 occurrences in
`sost-node`), so the same commit built in two directories produced two different
hashes. `-ffile-prefix-map=${CMAKE_SOURCE_DIR}=/sost` removes that: the same tag
built in two different directories now produces **byte-identical** binaries, with
zero embedded build paths. That is the claim that has been measured.

It is **not** a claim that any machine reproduces these hashes. A different
compiler, linker or libc can still produce a different binary, and that has not
been tested. So:

* **Official binary you downloaded** — the SHA256 must match exactly.
* **Binary you compiled yourself** — it matches only if you build in the
  environment above. A different hash on a different toolchain is expected and is
  not, by itself, evidence of tampering.

## Frozen consensus parameters

DTD-normal is **unchanged**: same eligibility, payout, cooldown and
anti-dominance. No NODE_BIND, no heartbeats.

DTD Jackpot V2, from #30,000:

* eligibility = valid SbPoW identity **and** ≥3 valid blocks in the previous
  5,000 **and** an active NODE_BIND **and** heartbeats per the bootstrap;
* weight = number of valid SbPoW blocks in the window, **linear**, one block one
  unit — no sqrt, no log, no cap, no node multiplier;
* node participation is a **gate**, never weight: more nodes do not raise odds;
* **no** jackpot cooldown, **no** jackpot anti-dominance, by design;
* winner = deterministic weighted draw over a canonically ordered set, integer
  arithmetic only, seeded from the domain-separated `SOST_HIST_JACKPOT` plus
  chain entropy and the height;
* payout unchanged: base 100 SOST, rollover 100→200→300→400→500, cap 500 until a
  winner, paid from the existing historical reserve, **no new emission**;
* zero eligible participants → rollover, no fallback winner;
* NODE_BIND included at height H is **active at H+1**; a heartbeat in the same
  block uses the pre-block binding;
* first V2 draw #30,186 requires NODE_BIND with a heartbeat requirement of 0/0,
  ramping to the permanent 3-of-4 at #31,338.

All of the above is guarded by `static_assert` in `include/sost/params.h`.

## Upgrade window

Update **after block #29,900 and before #30,000** (~16–17 h). V16 activates by
itself at #30,000: no command, no configuration switch, no restart at the height.
A node still on V15 after #30,000 may diverge. See
`docs/v16/QUICK_UPGRADE_5MIN.md`.
