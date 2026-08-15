# SOST V15 FINAL — release manifest

Status: **BUILT AND VALIDATED — NOT DEPLOYED.** The cutover is a separate human decision.

---

## 1. Release identity

| Field | Value |
|---|---|
| Final code commit | `16b50a4bf5e910e25862b3a54b41a9a80cf48b6c` — the binaries below were built from this tree |
| Branch head | `release/v15-final-blockers` — one commit ahead, adding only `artifacts/v15-final-validation/*` (this manifest + evidence logs). No file under `src/`, `include/` or `CMakeLists.txt` differs, so the branch head builds byte-identical binaries. |
| Base commit | `65ebb139a6d9d7405140ac60ddd050b7ed39b0ad` — "merge: V15 25000 canonical release (reconcile/v15-25000)" |
| Author | NeoB &lt;neob@sostprotocol.com&gt; |
| Profile | MAINNET (`SOST_DEVNET_FORKS` unset, `SOST_TESTNET_FORKS=OFF`) |
| Fork heights | V15_HEIGHT = **25000** (unchanged) · HIST_JACKPOT_FIRST_HEIGHT = **25290** (unchanged) |
| BTC | OFF — `SOST_BTC_HTLC_SIGNING` not set; 0 wally symbols in all four binaries |

### Why this base

`65ebb139` is the exact commit that produced the binary currently running on
mainnet (`sost-node` sha256 `f7c625fd…`). This was established by bit-identical
reproduction, not by inference — see §2. Basing the release on it makes the delta
between the deployed node and this release **exactly the two blocker fixes and
nothing else**: no BTC/OTC-6 sources, no unrelated merges.

`65ebb139` sits between the two commits the earlier audits argued about:
`0e576fe4` (the audited RC) is its ancestor, and `d95c14e2` (`main`, the Option B
merge) is its descendant.

---

## 2. Binary provenance — the live-binary contradiction, resolved

Two prior audits disagreed about whether the deployed binary corresponded to the
audited release. Resolved by reproduction:

| Question | Answer |
|---|---|
| What produced the live `f7c625fd…`? | commit `65ebb139`, built at source root `/tmp/main-merge`, build dir `build-final`, g++ 11.4.0, cmake 3.22.1, flags `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release` |
| Reproduced bit-for-bit? | **YES** — all four binaries reproduce byte-identically when rebuilt at the same absolute path with the same toolchain |
| Is the build reproducible bit-for-bit in general? | **YES, path- and toolchain-bound.** DWARF debug info embeds the absolute source and build paths, so building the same commit at a different path yields a different sha256 with identical machine code. This is what made audit (A) report a false mismatch. |
| Does the live binary contain unaudited code? | **NO.** `sost-node` links exactly 29 translation units; the set is identical for `0e576fe4`, `65ebb139` and `d95c14e2`, and contains no BTC/OTC-6 file. `0e576fe4` → `65ebb139` differs only in `src/atomic_swap_btc_signing.cpp`, which is not one of those 29 units. Builds of `0e576fe4` and `d95c14e2` at equal-length paths have **byte-identical `.text` and `.rodata`**. |

Reproduction command used (source root must be `/tmp/main-merge`):

```
git worktree add --detach /tmp/main-merge 65ebb139
cd /tmp/main-merge
cmake -S . -B build-final -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build-final --target sost-node sost-cli sost-miner sost-signtx -j$(nproc)
sha256sum build-final/sost-node   # -> f7c625fd7b203fd140f0142208ab1184fd69358187ececf36d13e9962d0e6661
```

---

## 3. What changed in this release

### BLOCKER 1 — the DTD would have become permissioned at block 30000
`include/sost/params.h:1096` (mainnet branch of `DTD_POPC_GATE_CONSENSUS_ACTIVE`)
shipped `true` while `DTD_POPC_ELIGIBILITY_HEIGHT` is a finite **30000**. V15
ships PoPC deactivated and the chain holds zero commitments, so from block 30000
`compute_lottery_eligibility_set()` would have returned an empty set: no DTD
winner ever, 50 % of the emission rolling over forever, and the Historical
Jackpot — which selects from the same set — never paying out the reserve.

Fix: the **mainnet** branch is now `false`. TESTNET stays `true` (soak); DEVNET
stays `false`. Chosen over `DTD_POPC_ELIGIBILITY_HEIGHT = INT64_MAX` because the
flag already short-circuits `popc_eligibility_enforced()`, needs no arithmetic on
a saturated constant, mirrors the existing DEVNET branch, and keeps the
eligibility height meaningful for a future coordinated re-activation.

### BLOCKER 2 — the reserve was protected by key custody alone
New consensus rule **`S13_RESERVE_FROZEN` (213)**: from
`jackpot::RESERVE_FREEZE_ACTIVATION_HEIGHT` (= `V15_HEIGHT` = 25000), a UTXO
matching the pre-existing `jackpot::is_reserve_output()` predicate may be spent
**only** by the canonical `TX_TYPE_JACKPOT`, which must still match the byte-exact
canonical reconstruction. Enforced at four layers:

| Layer | Location |
|---|---|
| Consensus (primary) | `src/tx_validation.cpp` → `ValidateInputs` → `S13_RESERVE_FROZEN` |
| Relay / mempool policy | `src/tx_validation.cpp` → `ValidateTransactionPolicy` → `P_RESERVE_FROZEN` (410) |
| Node block path (independent backstop) | `src/sost-node.cpp` → `process_block` per-tx loop |
| RPC edge | `src/sost-node.cpp` → `handle_sendrawtransaction` (was warning-only, now rejects) |

The jackpot's own change output re-enters the sink as `OUT_COINBASE_GOLD` and is
therefore frozen too — intended, and required for the reserve to survive between
payouts.

### Extra hardening found while proving the above
`jackpot_tx_matches_canonical()` did not compare `tx.version`, and the canonical
jackpot is exempt from R1, so the same jackpot event could be encoded with any
version value and still be accepted. `tx.version` is now pinned, making the
"byte-exact canonical reconstruction" claim actually true of all four serialized
fields.

### Interaction note — Gold Vault governance G1-G5
A governance spend is an ordinary signed spend, so the freeze supersedes it.
On **mainnet** there is no interaction at all: `GV_SLICE1_ACTIVATION_HEIGHT` is
`INT64_MAX`, so G1-G5 is completely inert and nothing that used to be possible
becomes impossible. On **testnet** G1-G5 activates at `V15_HEIGHT` and the freeze
takes precedence from that height. Any future governed outflow must be expressed
as its own canonical protocol transaction type, never as a signed sweep.

---

## 4. Final binaries

Built from `16b50a4b` in a clean `build-final` directory.

```
8c8ff89740d1b43a8c925d7d9ec398e4989a3d4de5759785aa84e3945b79bc4c  sost-node
7379d34b74a34463745ad0885c170d2ca3bbd77efadf689aef6039ae34c1dace  sost-cli
1a21a962c67b400814edde214d52176c28538c35ae67c8a366d7fde6ad34b9ab  sost-miner
ac08c347ad315d3e1fb6bbbd49ebb6079ecdf5f1e914278a9df0f295e0fa67d9  sost-signtx
```

wally symbols (`nm -a` and `strings`): **0** in all four.

### Exact build flags

```
cmake -S . -B build-final \
      -DSOST_ENABLE_PHASE2_SBPOW=ON \
      -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build-final --target sost-node sost-cli sost-miner sost-signtx -j$(nproc)
```

### Toolchain

| Component | Version |
|---|---|
| g++ | Ubuntu 11.4.0-1ubuntu1~22.04.3 (11.4.0) |
| cmake | 3.22.1 |
| GNU ld | 2.38 |
| glibc | 2.35 |
| OpenSSL | 3.0.2 |
| Kernel / arch | Linux 5.15 WSL2 x86_64 |

### Reproduction procedure

```
git clone <repo> sost-v15 && cd sost-v15
git checkout 16b50a4bf5e910e25862b3a54b41a9a80cf48b6c
cmake -S . -B build-final -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build-final --target sost-node sost-cli sost-miner sost-signtx -j$(nproc)
sha256sum build-final/sost-node build-final/sost-cli build-final/sost-miner build-final/sost-signtx
```

The four sha256 above reproduce **only** when the checkout path matches the one
used here (`/home/sost/SOST/sostcore/sost-v15-final`) and the toolchain matches,
because DWARF embeds absolute paths. For a path-independent comparison, compare
the `.text` and `.rodata` sections:

```
objcopy --dump-section .text=/dev/stdout build-final/sost-node /dev/null | sha256sum
```

---

## 5. Validation results (all re-run on the final commit)

| Gate | Result |
|---|---|
| Mainnet `ctest` | **105 / 105 passed, 0 failed** (was 102 before this release; +3 new suites) |
| Testnet-profile `ctest` | **105 / 105 passed, 0 failed** |
| Quick GO/NO-GO gate | **GO** — DEV isolation intact, consensus arithmetic **361 / 0** |
| Valid-PoW attack matrix (DEVNET) | **PASS** — 17 / 17 mutations rejected with zero state mutation, honest block accepted |
| Attack matrix, MAINNET parameters (new) | **45 / 45** — every mutation replayed at h=25290 |
| Blocker-1 regression, MAINNET parameters (new) | **28 / 28** |
| Reserve-freeze regression (new) | **110 / 110** |
| Integration harnesses (14) | reorg · failed_reorg · restart · reindex · rollover · rollover_cap · reserve_edges · mempool · payout · soak · attacks · multiblock M02 · M03 · M08 — **all PASS** |
| DEV soak | **18 harness runs over 3 rounds, 0 failures** |

### Historical replay — byte-identical

Full mainnet chain 0..22027 replayed with `--dry-run-replay --full-verify`,
deployed binary vs final binary:

| | deployed `f7c625fd…` | final `8c8ff897…` |
|---|---|---|
| final_height | 22027 | 22027 |
| utxo_count | 58167 | 58167 |
| utxo_set_root | `6b46fcdc38b853cfb1c2a582ef76e7a3a27dc137621dd5dba68ce4022cf9c1fe` | identical |
| tip_block_id | `1d275f91b9f8c553598085546c477a371c541e768054741348d2ee6ae852fe36` | identical |

Both consensus changes are height-gated at or after 25000, which the chain has
not reached (tip 22027 at the time of validation).

---

## 6. Replacement scope for the cutover

Read-only inspection of `212.132.108.244:/opt/sost/build`:

| Binary | Deployed sha256 | State | Action |
|---|---|---|---|
| `sost-node` | `f7c625fd…` (2026-08-07) | V15 release build, but **predates both blocker fixes** | **REPLACE** with `8c8ff897…` |
| `sost-cli` | `1a50a1cc…` (2026-07-10) | **STALE** — not even the 2026-08-07 release build (`f6c1075d…`) | **REPLACE** with `7379d34b…` |
| `sost-miner` | `fb9eecdd…` (2026-07-10) | **STALE** — not the release build (`19b8b097…`) | **REPLACE** with `1a21a962…` |
| `sost-signtx` | `3b1194de…` (2026-07-10) | **STALE** — not the release build (`ff53919b…`) | **REPLACE** with `ac08c347…` |

Note: the 2026-08-07 cutover replaced **only** `sost-node`; the other three
binaries on the VPS are still from 2026-07-10.

**Mining machine.** No `sost-miner` process was running at validation time. The
local build at `/home/sost/SOST/sostcore/sost-core/build/sost-miner` is
`d7562c93…` (2026-08-06) — neither the release build nor this one, so it must be
replaced with `1a21a962…` before mining resumes. The miner must be launched with
`--realtime`.

**Deadline.** Both fixes are consensus rules that bite at height 25000 (freeze)
and 30000 (DTD gate). The node must be replaced before block **25000**. The DTD
gate fix is what keeps the eligibility set non-empty from 30000, so a node still
running `f7c625fd…` past 30000 would fork away from upgraded nodes.

---

## 7. Not covered by this release

Honest scope statement — none of these are regressions, all are pre-existing:

- The valid-PoW **node-level** attack matrix still runs only under DEVNET_FAST
  (the mutations are compiled `#ifdef SOST_DEVNET_FORKS` and the harness needs a
  first jackpot at height 24). The MAINNET-parameter matrix added here covers the
  same mutations at the consensus-decision layer, not end-to-end PoW/submitblock
  and not node-state atomicity.
- The 14 pending multi-block scenarios listed in `attack-matrix.md` (rows 1-14)
  remain as they were.
- `tests/test_v13_helpers.cpp` still does not compile under DEVNET (pre-existing;
  the devnet harnesses build only `sost-node`/`sost-miner`/`sost-cli`/`sost-signtx`).
- BTC atomic swap remains OFF and unvalidated against a real bitcoind.
