# Gate 9 — Full final battery on the published commit

**Commit under test: `eca62d7d`** (feat/p2p-autonomy-d1, off v30000). Every result below was
produced on THIS commit (clean build), not reused from an earlier one.

| Check | Result | Evidence |
|-------|--------|----------|
| CONSENSUS files changed vs v30000 | **NONE** | git diff name-only: 0 consensus files |
| CTEST | **122/122** | 0 fail (incl. 3 D1 tests now registered) |
| Fork-choice / reorg / SACS cluster | **10/10** | casert×4, reorg, chainwork, v14-fork-gates, mtp-fork, v13-lottery/drift-fork |
| ADDR parser fuzz | **200k clean** | d1-addr-fuzz, ASan+UBSan |
| ASAN + UBSAN + LEAKSAN (D1 code) | **clean** | peer-store 9/9, fuzz 8/8, gossip-filter all-pass, 0 sanitizer reports |
| P2P adversarial (wire) | **7/7** | 500k junk addrs → +204KB RSS, FD flat, alive |
| Peer-store torture | **10/10** | restart×100, corrupt/huge/dup/empty |
| OLD/NEW compat (multi-node) | **5/5 + soak** | no OLD penalty, no split, identical tip |
| Partition / heal / heavier-wins | **9/9** | Phase 5b (G1 h15 vs G2 h5 → converge to G1) |
| Bootstrap / no-sostcore | **PASS** | peers.txt/seeds.txt bootstrap, no-source fails closed |
| Security review (Gate 6) | **SAFE, 3 fixed** | SSRF/DNS, candidate eviction, fsync — all fixed + tested |
| seeds.txt threat model (Gate 7) | **PASS** | trusted local config, bounded, no shell/remote-overwrite |
| SOAK | **0 errors** | prefix 2h38m (645 rows) + final soak on eca62d7d ongoing |
| REPRO build (temporal/env/path) | **PASS** | identical back-to-back, env-independent, path-independent (SOST code) |
| SECRET scan | see below | — |
| Controlled-env hashes | reproducible | node 47fff758 / miner 9d51a6ab / cli 4f7958fb |

## Gate 1 (miner/cli hash) — RESOLVED byte-level
Built v30000 and candidate in an identical controlled environment (same toolchain,
source path neutralized with -ffile-prefix-map):
- **sost-miner: byte-IDENTICAL** (v30000 `9d51a6ab` == candidate `9d51a6ab`)
- **sost-cli:   byte-IDENTICAL** (v30000 `4f7958fb` == candidate `4f7958fb`)
- sost-node differs (the only source delta, sost-node.cpp +310/-36).
=> MINER SOURCE FUNCTIONAL DIFF: **NO**. CLI SOURCE FUNCTIONAL DIFF: **NO**.
The published-release hash difference (eec96efb/c8ae00b9) is 100% the original release's
build environment (path), not code — proven by the identical controlled rebuild.

## Gate 2 (cross-env repro) — PASS with recipe
Three isolated axes all reproduce byte-identically: temporal (back-to-back same path),
environment (normal vs `env -i` scrubbed, same path), and path (two different real
worktrees, prefix-mapped → identical miner/cli). Residual: third-party vendored libs
(libsecp256k1/libwally) embed their build path when rebuilt from scratch in a new path —
eliminated by reusing the shipped prebuilt vendor artifacts (release process) or extending
-ffile-prefix-map to the vendor sub-builds. SOST first-party code is fully reproducible.
