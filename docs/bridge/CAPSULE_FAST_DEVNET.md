# Capsule-fast devnet — REAL DEVNET E2E, accelerated activation height

**Label: REAL DEVNET E2E — accelerated activation height. Not a mainnet deployment validation.**

## Why it exists

The Stage 2 bridge needs Capsule v1 on real SOST transactions. Capsules activate at
**#7,350 on mainnet** (`CAPSULE_ACTIVATION_HEIGHT_MAINNET`, pinned to `V12_HEIGHT`).

The long-running DEVNET_FAST soak network crossed the #5,175 cASERT transition with zero
rejected blocks, then slowed down. **That is not a consensus failure.** The devnet produced
blocks every ~2 s against a 600 s target, and from #5,175 the V6++ rule raises difficulty
by +12.5 % per block until block times approach the target. That is the algorithm working
as designed, and it is not "fixed" to reach #7,350 sooner. That devnet keeps running untouched as
a cASERT soak test.

To test capsule features without waiting two weeks of economically realistic difficulty
adjustment, a **separate** devnet build moves only the capsule activation:

| build | capsule activation | everything else |
|---|---|---|
| mainnet / testnet / DEVNET_FAST | 7,350 (`CAPSULE_ACTIVATION_HEIGHT_MAINNET`) | unchanged |
| `SOST_DEVNET_CAPSULE_FAST` (devnet only) | **300** | identical to DEVNET_FAST |

## The change (branch `devnet/capsule-fast-300`)

- `include/sost/tx_validation.h`: new `CAPSULE_ACTIVATION_HEIGHT_BUILD`.
  - It equals `CAPSULE_ACTIVATION_HEIGHT_MAINNET` unless `SOST_DEVNET_CAPSULE_FAST` is defined; then it is 300.
  - `#error` unless `SOST_DEVNET_FORKS` is also defined.
  - `TxValidationContext::capsule_activation_height` defaults to it. The node never overrides this default, so the default *is* the node's consensus height.
- `src/sost-cli.cpp`: the two capsule-attach guards read the same constant instead of `V12_HEIGHT`. In a mainnet build the value is the same: 7,350.
- `CMakeLists.txt`: option `SOST_DEVNET_CAPSULE_FAST` (FATAL_ERROR without `SOST_DEVNET_FORKS`).
- `tests/test_capsule_activation_build.cpp` validates through a default-constructed context (the node path):
  - normal build: 7,349 REJECT (R14) / 7,350 ACCEPT; capsule at 300 is also rejected.
  - capsule-fast build: 299 REJECT / 300 ACCEPT; the mainnet constant is still 7,350.

### Mainnet-config proof
- Built from the parent commit and from the change, same source path.
- `sost-node` and `sost-miner`: `.text`, `.rodata` and `.data` are **identical**. Only DWARF line numbers move, because the header gained lines.
- `sost-cli` differs only in the reworded error string (and the addresses that shift with it).
- Full mainnet-parameter suite: 122/122.

No mainnet constant, genesis, emission, difficulty, HTLC, DTD, Jackpot, NODE_BIND or native-asset gate changes.

## Isolation
- Fresh datadir per run. Ports: RPC 18755/18756, P2P 19755/19756.
- `--connect 127.0.0.1:1`, so the network has no peers. Profile DEV + MAGIC_DEV.
- Its own wallets. The soak devnet (18655) and the mainnet miner are never touched.

## Running it

```
cmake -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=ON -DSOST_DEVNET_CAPSULE_FAST=ON ..
python3 tests/bridge/run_capsule_fast_devnet.py --bin <build> --work <new empty dir>
```

The orchestrator:
1. **Boundary with the same signed bytes.**
   - At tip 298, the CLI refuses to attach a capsule.
   - A watch-only `buildtx` has a Capsule v1 open note inserted *before* `signtx`. The node rejects it for block #299: R14, "payload forbidden before capsule activation".
   - After one block, **the identical signed bytes** are accepted and confirmed in block #300.
   - At tip 300, the CLI builds capsules, and its bytes equal the bridge encoder's bytes.
2. **Real reorg of a bridge deposit.**
   - Node B syncs from A over P2P, goes offline, and mines a longer branch from before the deposit.
   - The branch is delivered to A in order through `submitblock`, so A's own `process_block` / `try_reorganize` switch chains.
   - The relayer pre-flight and the observer both refuse the stale statement.
3. **`tests/bridge/e2e_real_capsule.py`** (A–H; wrap 100 / unwrap 40; CRITICAL + mint pause).
   - EVM side: local Anvil until Sepolia is funded.

## Results (2026-10-12, clean run from genesis, `devnet/capsule-fast-300` @ ccb4adf5)

Orchestrator 30/30, `e2e_real_capsule.py` 34/34:

| check | result |
|---|---|
| FAST_DEVNET_299 — valid capsule tx for block #299 | REJECT (R14 "payload forbidden before capsule activation") |
| FAST_DEVNET_300 — the same signed bytes | ACCEPT, confirmed in block #300 |
| CLI capsule bytes == bridge encoder bytes | PASS |
| real reorg of a 5 SOST deposit (#307 replaced; tip 310) | statement refused by the relayer pre-flight and by the observers; deposit re-mined at #311 with a new block hash and the same deposit_id |
| A open note · B bridge deposit (encrypted v2 signer) · C governance vote · G offline-signed · H confirmed + parsed | PASS |
| D malformed capsule (bad magic) | rejected (node policy, offline signer flags type -1) |
| E oversize capsule (81 > 80) | refused before building |
| F capsule mutated after signing | rejected (ECDSA verification failed) |
| observer data from the real node | txid, vout, amount, recipient, block hash, height, confirmations |
| wrong recipient / stale block / duplicate / insufficient confirmations | mint reverts / pre-flight refuses / reverts / PENDING + observers refuse |
| wrap 100 → unwrap 40 (release signed offline by the vault wallet) | 60 wSOST outstanding; vault 60.00097050 SOST (60 + unused part of the 0.001 release fee allowance); BALANCED |
| unbacked mint by 2 compromised observers | CRITICAL → mintPaused; observers refuse; a further mint reverts |

The EVM side is local Anvil (chainId 31337). Sepolia is a separate gate.

## Finding: deep-fork recovery over P2P

While building the reorg test, two nodes whose branches diverged two blocks below the shorter
tip did **not** converge over P2P:
- The node asks `GETB` from its own tip+1.
- The first block it receives has an unknown parent, so it is stored as an orphan.
- The parents are never requested, and the orphan is not re-processed when its parent later arrives as a fork block.
- The node then counts "empty DONE" replies and penalises the honest peer (+50).

Delivered in order, the same blocks reorg correctly. This was observed on the `main`-derived
devnet node. The production source (`59a4e666`) has the same height-based `GETB` / empty-DONE
logic plus extra orphan handling after reorgs. It must be re-tested on the reconciled
production baseline before any conclusion. It does not affect 1-block races, where the
competing block arrives with a known parent. **Not fixed here; no consensus impact.**

Re-tested on the v40000 base in `docs/p2p/DEEP_FORK_V40000.md`: this case is fixed there by
`299cf2e6`; three remaining false-penalty / non-convergence cases were found and fixed.

## Known limitation: `buildtx` and pending transactions

`buildtx` is watch-only. It selects coins from `getaddressutxos`, which still lists outputs
spent by an unconfirmed mempool transaction. Two offline builds from the same address before
the first one confirms can pick the same input. The node then rejects the second one
("replacement fee-rate not strictly higher") — **a safe failure, never a double spend**. The
online `send` avoids this because it marks spent inputs in the wallet file. The test waits for
confirmation. A later CLI change can exclude mempool-spent outpoints.

## Status
Today's results are valid functional evidence. Final pre-mainnet Stage 2 acceptance re-runs the
critical suite on the reconciled, production-derived canonical baseline, and on Sepolia once it is funded.
