# V15 mainnet cutover plan — OPTION A (V15 + EVM, BTC OFF)

**PREPARED, NOT EXECUTED.** The cutover is a human-supervised step performed BEFORE block 25,000.
This document is the operator runbook; `artifacts/v15-final-validation/RUNBOOK_CUTOVER.md` has the
longer narrative version.

## Release identity
- **main merge commit:** `65ebb139` (merge of `reconcile/v15-25000` = canonical V15@25000).
- **New binaries** (build from main, `SOST_BTC_HTLC_SIGNING=OFF`):
  - sost-node   `f7c625fd7b203fd140f0142208ab1184fd69358187ececf36d13e9962d0e6661`
  - sost-cli    `f6c1075d22ac566269c4b40246b9d780bec6309481a885cb140001a18978a036`
  - sost-miner  `19b8b09706be8f9959740e2b584fe407c453a81e1f9c1e769e791e3f467559c5`
  - sost-signtx `ff53919b48cf3bcd6f1913ddaa609d6334c4ac26a6f6926fc7cb09aab324813f`
  - (full manifest: `artifacts/v15-final-validation/SHA256SUMS_FINAL.txt`)
- **Consensus constants (verified in main):** V15 = **25000**, first jackpot = **25290**, EVM HTLC =
  **16000**, relay = **17000**. **BTC Atomic Swap = OFF** (0 wally/BTC-signing symbols in the binary;
  `SOST_BTC_ATOMIC_SWAP_ENABLED` default OFF). Old V15@20000 REPLACED; single jackpot; `validate_live_jackpot` present.

## 0. Rollback binary (capture BEFORE swapping)
The currently deployed binary is **v0.3.2** (confirmed via `getinfo`). On the node host, BEFORE the swap:
```
PID=$(pgrep -f 'sost-node.*mainnet'); OLD=$(readlink -f /proc/$PID/exe)
sha256sum "$OLD"                       # record SHA256_OLD
cp -a "$OLD" /opt/sost/rollback/old-sost-node   # keep the exact running binary
cp -a <node-config> /opt/sost/rollback/old-config
```
Never modify the chain datadir. Keep `old-sost-node` + `old-config` until several blocks past activation.

## 1. Prechecks (GO gate)
- `sha256sum -c` the new binaries against SHA256SUMS_FINAL on EVERY host → all match.
- New binary `strings | grep -E 'devjackpotstate|inject-tx-at1|attack-jackpot|SignBtcHtlc|wally_tx'` → EMPTY.
- Node getinfo confirms current height in a safe window (well before 25,000).
- Operator + rollback ready; miner inventory known (incl. the 13-thread CEX miner + Beelink).

## 2. Cutover order (staged, atomic, hash-verified)
1. **Stop miners** cleanly (SIGINT/stop, never pkill).
2. **Node:** stop → backup chain dir → atomically swap in the new sost-node (verified) → restart.
   Confirm it LOADS the existing chain with NO rejected historical blocks and the SAME tip hash.
3. **Sync + peers:** node re-syncs, peers connect, tip advances.
4. **Canary miner:** start ONE miner on the new binary (`--realtime` MANDATORY). Watch several blocks:
   accepted, no `REJECTED`, no timestamp/fork warnings.
5. **Staged miners:** bring the rest up ONE AT A TIME on the new binary, each confirmed before the next.
6. **Version homogeneity:** every node/miner reports the same commit (65ebb139) / version.
7. **Explorer:** deploy the matching explorer (already at V15@25000 in the merged web) if part of the package.
8. **Monitor** to several blocks past — watchdog, stalls, rejects, forks.

## GO criteria
SHA correct · config correct · **BTC OFF** · node starts · loads existing chain, same tip, 0 rejected
historical blocks · peers connected · tip advances · canary + staged miners accepted, homogeneous version.

## ABORT criteria
crash · tip divergence · **unexpected rejection of pre-V15 blocks** · peers lost · chain tip stalls ·
wrong binary/config SHA · any miner split old/new near 25,000.

## Rollback (valid only BEFORE 25,000 activation)
1. Stop the affected miners.
2. Node: stop → restore `old-sost-node` (v0.3.2) + `old-config` → restart. Confirm re-convergence.
3. Miners restart on the old binary (`--realtime`). Post-mortem before re-attempting.
NOTE: after 25,000 activates, a clean rollback is NOT possible — that is why the canary + staged
restart must COMPLETE before 25,000.

## Do NOT (this phase)
No replacing the production binary, no node/miner restart, no BTC activation, no datadir change — until
the supervised window. **BTC stays OFF; do not set `SOST_BTC_ATOMIC_SWAP_ENABLED`.**
