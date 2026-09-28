# SACS P2 — Real Isolated Reorg at MAX_REORG_DEPTH = 8 (devnet)

**Status:** EXECUTED — both scenarios PASS. Branch `research/sost-autonomous-chain-safety`.
Binaries: `build-sacs` (`-DSOST_DEVNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON
-DSOST_TESTNET_FORKS=OFF`), `MAX_REORG_DEPTH=8`. Both nodes run `--noseed` (P1) so
the experiment is fully isolated from mainnet.

PASS criteria (height match alone is NOT accepted): common ancestor + tip hashes +
cumulative chainwork + exact disconnect depth + UTXO-set-root equality + restart
persistence must ALL hold.

## Delivery mechanism + a real P2P finding
The two chains are built by two isolated nodes each mining its own history from the
same genesis. The competing chain is then delivered A→B via `getrawblock` +
`submitblock` (parent-first), which drives the real consensus engine
(`process_block` → `try_reorganize`).

**Finding (P2P sync, not the reorg engine):** the node's block sync only *requests
blocks above its own tip* ("requesting H..H") and does **no orphan-parent backfill /
headers-first divergence discovery**. So over plain P2P, a node never fetches a
peer's alternative blocks that diverge at or below its own tip, and the reorg engine
never receives the competing chain. This is why the first (pure-`--connect`) attempt
produced no reorg. It is a real limitation relevant to Delivery B and the consensus
hardening backlog; it does not affect the correctness of the reorg engine itself,
which this test exercises directly via `submitblock`. Per-block `submitblock` returns
`-25` for the sub-tip fork blocks (expected — they are stored as FORK, not added to
the active chain) until the fork tip tips the cumulative work.

## Scenario A — converge_d8 (A=9 blocks, B=8 blocks) → CONVERGE
```
COMMON ANCESTOR (genesis): A=6517916b98ab9f80 B=6517916b98ab9f80 identical=YES
PRE  A: h=9 tip=337069d25fe573d5 chainwork=0x2ee2
PRE  B: h=8 tip=9e833adbaaebc181 chainwork=0x2e65
[FORK] Alternative chain has MORE cumulative work! Fork tip h=9, active tip h=8. Attempting reorg.
[REORG] Fork detected at height 0
[REORG] Disconnecting 8 blocks (h=1..8)
[REORG] Connecting 9 blocks
POST B: h=9 tip=337069d25fe573d5           (== A tip)
UTXO ROOT A=44aa6ecca07b3df4baf60f74 B=44aa6ecca07b3df4baf60f74 equal=YES
RESTART B: h=9 tip=337069d25fe573d5 stable=YES
>>> converge_d8: PASS
```
Disconnect depth **exactly 8** (fork point = genesis h0). B adopts A's chain; UTXO
sets identical (hence all address balances identical); survives restart.

## Scenario B — reject_d9 (A=10 blocks, B=9 blocks) → NON-CONVERGENCE
```
COMMON ANCESTOR (genesis): A=6517916b98ab9f80 B=6517916b98ab9f80 identical=YES
PRE  A: h=10 tip=7a82db23e469e631 chainwork=0x2f3e
PRE  B: h=9  tip=c17f8944585e6842 chainwork=0x2ee2
[FORK] Alternative chain has MORE cumulative work! Fork tip h=10, active tip h=9. Attempting reorg.
[REORG] Rejected: depth 9 exceeds REORG_LIMIT 8
POST B: h=9 tip=c17f8944585e6842           (kept its own chain)
UTXO ROOT A=16eb907703d3097ebfcbca00 B=4804412433230c05214c50c3 equal=NO
RESTART B: h=9 tip=c17f8944585e6842 stable=YES
>>> reject_d9: PASS
```
A had **more work and more blocks**, yet B refused because the reorg would disconnect
**9 > 8** blocks. This is the key safety property: the depth cap bounds reorgs even
against a higher-work chain. Chains stay split; UTXO roots differ; B survives restart
on its own chain.

## Conclusion
- Chain selection is by **cumulative verified work**, bounded by `MAX_REORG_DEPTH`.
- Convergence at fork-depth = 8; hard non-convergence at fork-depth = 9.
- Verified on hashes, chainwork, exact disconnect depth, UTXO-set root, and restart —
  not on height alone.

Harness: `tests/sacs_p2_reorg.sh` (+ `tests/sacs_feedchain.py`).
