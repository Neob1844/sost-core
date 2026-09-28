# SACS P8–P9 — Delivery B Prototype: Automatic Reconvergence Past the Depth Cap

**Status:** IMPLEMENTED + PROVEN (devnet). Research prototype — **NOT V16, NOT mainnet.**

## Idea
Delivery A (current mainnet/V16) hard-rejects any reorg deeper than `MAX_REORG_DEPTH`
(500 mainnet / 8 devnet). Two segments partitioned longer than the cap can therefore stay
**permanently split** even when one has strictly more work (see P2 `reject_d9`). Delivery B
turns the cap into an **advisory `DEEP_REORG_ALERT`** and lets the reorg PROCEED, still
selecting the chain with the highest fully-validated cumulative work and still atomically
(snapshot + rollback on any failure). This lets segments reconverge with **no operator,
checkpoint, or quorum**.

## Implementation (`src/sost-node.cpp`, flag `--sacs-recovery-mode`)
- **DEV profile only.** Enforced at startup: on TESTNET/MAINNET the flag is refused and
  reset to false, so the mainnet MAX_REORG_DEPTH=500 hard cap and V16 are untouched.
- Two sites relaxed *only when the flag is on*:
  - accept-side cutoff: deep fork blocks are stored (so the competing segment can be
    assembled) instead of rejected.
  - `try_reorganize` Step 3: `disconnect_count > MAX_REORG_DEPTH` emits a
    `DEEP_REORG_ALERT` and proceeds, instead of `REORG_REJECTED`.
- Step 4 (strictly-higher fully-validated work) and Steps 5–7 (atomic disconnect/connect
  with rollback) are UNCHANGED — recovery mode never lowers validation or the work rule;
  it only removes the depth veto.
- Sensitive-op suspension: the deep-reorg is surfaced as `DEEP_REORG_ALERT`, which the
  exchange/wallet tx-safety policy (`suspendOnDeepReorg`) consumes to suspend credits
  during the reorg (P6 tx-safety).

## Proof (`tests/sacs_p8_deliveryb.sh`, devnet, cap=8, split depth 9 > cap)
### Control — recovery mode OFF (default)
```
[REORG] Rejected: depth 9 exceeds REORG_LIMIT 8
POST B: h=9 (kept own chain)   UTXO ROOT equal=NO   restart stable=YES
=> STAYED SPLIT (permanent partition) — PASS (control)
```
### Delivery B — recovery mode ON
```
[REORG][SACS-RECOVERY] Depth 9 exceeds cap 8 — proceeding (advisory alert).
[REORG] Disconnecting 9 blocks (h=1..9)
[REORG] Connecting 10 blocks
[REORG] Success: new tip = d4c686438007e29b at height 10
POST B: h=10 tip == A tip   DEEP_REORG_ALERT:2   UTXO ROOT equal=YES   restart stable=YES
=> CONVERGED at depth 9 (> cap 8) — automatic reconvergence, no operator/checkpoint/quorum — PASS
```

## Safety
- Flag default OFF; DEV-only. The same binary with the flag OFF still hard-rejects depth-9
  (the control run proves it) — **no regression** to Delivery A / V16.
- Convergence still requires strictly higher fully-validated work; a longer-but-lower-work
  or invalid chain is still refused (Step 4 + full validation).
- The reorg remains atomic; a mid-reorg failure rolls back to the original tip
  (RECOVERY_STARTED/COMPLETED, proven in P4).

## Residual (future, before any non-devnet consideration)
Deep-recovery interacts with `cleanup_old_forks()` pruning, mempool/coinbase-maturity of a
very deep disconnect, and the P2P sub-tip backfill gap (P2 finding). These are why Delivery
B stays a devnet research prototype and is NOT proposed for V16.
