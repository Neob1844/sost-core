# Production ↔ main reconciliation (2026-10-12)

Status: **candidate branch `reconcile/v30000-production-main` — NOT promoted, NOT deployed, `main` unchanged.**
Author: Neob.

## 1. Facts

| Item | Value |
|---|---|
| `main` HEAD | `83a570f4` (web v561) |
| Production consensus base | `3acd952b` = tag `v30000-final` |
| Production source base | `59a4e666` = tag `v30000-final.1` = `origin/release/v30000-final.1` (child of `3acd952b`, changes only `src/sost-node.cpp`) |
| Running production node | `/opt/sost/build/sost-node` sha256 `7ca5ea63…` = FINAL.1 |
| merge-base(main, production) | `440defe5` |
| Divergence | main +237 commits, production +82 commits → **diverged** |

Existing immutable references (tags `v30000-final`, `v30000-final.1`, branch `release/v30000-final.1`) already identify the production source; no new reference was needed.

## 2. Release reproduction

A clean worktree of `59a4e666`, built with the recorded canonical procedure (`env -i`, Release, `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`, `-ffile-prefix-map` for source and build), reproduces the published FINAL.1 hashes **bit for bit**:

```
7ca5ea630a50f45d70cedd073c1bbb239abd69ac6f2e30c316236121c601b736  sost-node   (= running production node)
53c83836bc16e32cd0b9bdda5d15e8936a217079dacde00ca7eba8302b8a1e75  sost-miner
09d9a5022b3c03dfbe85df1ea728f931f5287712739921e17138e89dad14f62b  sost-cli
```

## 3. Inventory since `440defe5`

| | production side | main side | both |
|---|---|---|---|
| files changed | 128 | 284 | 9 |
| code (include/src/CMake/tests) | 77 | 19 | 3 |
| website | 8 | 149 | 5 |

Classification:

- **A — production-only, REQUIRED (consensus):** native assets (fail-closed: mainnet `INT64_MAX`, devnet 42, testnet 30,000), NODE_BIND v2 proof of possession, jackpot v2, mempool and UTXO changes, P2P address filter, `params.h`, `transaction.h`, `tx_validation.*`, `node_participation.*`, FINAL.1 node hardening, CMake + 57 tests.
- **B — main-only, desirable, non-consensus:** unified wallet coin selection (`coin_select.h`, `wallet.h/.cpp`, CLI), checkpoint test aligned with the real assumevalid anchor (3554), web/DEX/tooling tests, CLI wallet tools tests, all website work.
- **C — main-only consensus-affecting:** **none.** `main` changes no consensus source.
- **D — obsolete/dead:** legacy `script.h` / `psbt.cpp` multisig library (present on both sides, not reachable from consensus; `OUT_SCRIPT_HASH = 0x30` collides with `OUT_NODE_PROTOCOL`) — remove before #40,000.
- **E — conflicts needing a decision:** `.gitignore` (resolved: union) and five website pages (resolved: main's live version). The three wallet/CLI files auto-merged without textual conflict and were verified by build + tests.

## 4. Candidate reconciliation (`0859b010`)

Branch `reconcile/v30000-production-main` from `59a4e666`, then `merge main` with **production as first parent** (history and authorship of both lines preserved, no rewrite, no force-push).

Evidence:

| Check | Result |
|---|---|
| consensus and node sources vs `59a4e666` | identical (`src/sost-node.cpp` identical); only `coin_select.h`, `wallet.h`, `wallet.cpp`, `sost-cli.cpp` differ |
| canonical build | OK |
| full test suite (mainnet configuration) | **125 / 125 PASS** |
| object files vs FINAL.1 build | 53 / 58 byte-identical; the 5 that differ are `wallet.o` and `sost-cli.o` (real changes) plus `sost-node.o`, `sost-miner.o`, `sbpow.o`, which only include `wallet.h` |
| machine code of `sost-node.o` (577 functions), `sost-miner.o` (101), `sbpow.o` (25) | **identical function by function** (address-normalised disassembly) |
| binary hashes | node `d9268707…`, miner `a36b0f27…`, cli `6265a1b0…` — differences fully explained by the wallet/CLI code linked in |

**Consensus identity:** every consensus object is byte-identical, and the node/miner/SbPoW code is machine-code identical, to the binaries mainnet is running. A full genesis → tip re-validation with the reconciled node has **not** been run yet; it is the remaining promotion gate (§6).

`main` is an ancestor of the candidate, so adopting it is a **fast-forward** of `main` — no history rewrite.

Website: adopting the candidate brings three production-side website files that are not live today (`website/js/tokenization-gate.js`, `website/lab/sacs/sacs-tx-safety.js` + test). Review them before the next website deploy.

## 5. Port plan for open branches (no rewrite yet)

| Branch | Forked from | Code touched | Plan |
|---|---|---|---|
| `fix/devnet-casert-meta-window` | main | `sost-node.cpp` (RPC), header, test | production has the same RPC window (`59a4e666` line 1486); re-apply as one small commit on the reconciled baseline; non-consensus |
| `feat/cli-offline-transactions` | main | `wallet.h/.cpp`, `sost-cli.cpp`, CMake, tests | depends on coin selection (now in the candidate); rebase onto the reconciled baseline after promotion, re-run 36/36 + 22/22 + full suite |
| `feat/wsost-gold-reserve-v2`, `feat/wsost-stage2-testnet`, `feat/wsost-stage2-real-e2e` | main | none (contracts, Python, docs) | rebase cleanly; re-run Stage 2 E2E on the canonical baseline before any mainnet decision |
| `design/native-multisig-40000` | main | none (docs) | rebase; implementation branch `fork/native-multisig-40000` only from the promoted baseline |

## 6. Promotion gates (before the candidate becomes canonical)

1. Owner review of this plan and of the three production-side website files.
2. Full historical re-validation genesis → current tip with the reconciled node (same accepted/rejected blocks, UTXO set, emission, DTD/Jackpot, NODE_BIND/heartbeat, HTLC; native assets fail-closed). Any divergence: stop.
3. Then fast-forward `main` through a reviewed PR.

## 7. Recommendation on branches

`main` currently mixes website deploys (several per day) with protocol source. Recommendation: **A + C** — fast-forward `main` to the reconciled candidate after the gates, then keep **protocol work on protected `release/*` and `fork/*` branches cut from tagged production commits**, while website work continues on `main`. Every release tag must be an ancestor of `main` from now on, so this divergence cannot recur.
