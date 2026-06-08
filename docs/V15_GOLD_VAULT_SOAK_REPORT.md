# V15 Gold Vault governance — B3 hardening & soak report

> Status date: 2026-06-08 · Scope: **B3 only — no new features.** Validate that the
> built Gold Vault governance (W1 Slice 1, W2 G4 marker, W3 67-block window, W4 G5
> Guardian) behaves identically across validators and survives testnet/replay/reorg
> **before** any mainnet flip. Mainnet stays DEFERRED / no-op throughout. Gold Vault
> governance belongs to **V15 (block 20,000)**, never V14 (block 15,000).

## 1. Cross-validator / determinism — ✅ AUTOMATED (CI hard-gate)

`tests/test_gv_governance_determinism.cpp` (`test-gv-governance-determinism`) rebuilds
the EXACT composed verdict `process_block` computes for a Gold Vault spend — G4
67-block window (`gv_g4_count_window` + `gv_g4_window_approved`) plus the G5 grace-window
veto scan (`gv_g5_is_veto_output` + `gv_g5_verify_veto_payload`) — over a synthetic chain
of coinbases, and asserts:

| Scenario | Verdict |
|---|---|
| 67/67 approvals, no veto | accept |
| exactly 61/67 | accept (floor) |
| 60/67 | reject (G4) |
| valid Guardian veto in grace window | reject (G5) |
| expired veto | accept (ignored) |
| veto signed for another destination | accept (does not block this dest) |
| auto-disconnect (height ≥ 100,000): 67/67 + valid veto | accept (G5 off, G4 still enforced) |
| auto-disconnect: 60/67 | reject (G4 still enforced) |

Plus the determinism / cross-validator properties themselves:
- **Determinism** — two independent evaluations of the same (chain, height, dest) give
  the byte-identical verdict. Every input is a pure function of chain state, so two
  validators on the same chain necessarily agree.
- **Recompute-from-chain (no caching)** — the same height evaluated against two different
  chains (61 vs 60 approvals) yields the two correct, different verdicts, and re-evaluating
  the first chain afterwards still returns its own result. There is no surviving tally state.

Results: testnet build **16/16**, mainnet build **4/4** (pipeline is a pure no-op while the
gates are deferred). Full `ctest` **68/68** (mainnet + testnet). In the CI hard-gate.

## 2. Reorg safety — ✅ verified by construction + the recompute test

`process_block` reads the G4/G5 windows fresh from `g_blocks` (the active chain) on every
block — `gv_g4_count_window(h, approves)` and the G5 grace scan take a per-height lookup,
hold **no persistent tally**, and exclude the current block (`[h-67, h-1]` / `[h-10, h-1]`).
A reorg that replaces blocks therefore changes the inputs and the verdict is recomputed;
nothing cached can survive a reorg. The recompute test above exercises exactly this.
**Live-node E2E reorg around the window remains a manual testnet item (§4).**

## 3. Replay byte-identical (mainnet) — guarantee + command

All V15 gates ship DEFERRED on mainnet: `GV_SLICE1_ACTIVATION_HEIGHT`, `GV_G4_ACTIVATION_HEIGHT`
and `GV_G5_ACTIVATION_HEIGHT` are `INT64_MAX`, so `gv_*_active_at(h)` is false at every mainnet
height → the W1/W3/W4b code is skipped and W2's coinbase recognition is inert. This is pinned
by `test-v14-fork-gates` (constants) and means the live block-acceptance path is byte-identical.
`--dry-run-replay` replays via `ConnectBlock` (not `process_block`), so it is unaffected regardless.

Run when a chain + baseline binary are available (not present in this sandbox):
```
scripts/validate-v14-replay.sh ./build/sost-node <baseline-sost-node> chain.json [genesis.json]
# asserts identical final height + UTXO-set root (non-zero exit = DO NOT DEPLOY)
```

## 4. Pending — requires a live testnet (manual, before the flip)

Not runnable in this sandbox (no miner/chain here). Procedure for the soak:
```
cmake -S . -B build-testnet -DSOST_TESTNET_FORKS=ON && cmake --build build-testnet
# V15_HEIGHT=300 on the testnet build. Start ≥2 nodes from this commit + a miner.
```
1. Mine across V15_HEIGHT (300); confirm both nodes stay in consensus.
2. Miners emit G4 approval markers; execute a valid Gold Vault spend with ≥61/67 → accepted.
3. Negative cases on-chain: 60/67 spend rejected; a Guardian veto in the grace window rejects;
   an expired/wrong-dest veto is ignored; a spend at height ≥100,000 ignores any veto.
4. Force a short reorg around the window; confirm both nodes recompute to the same tip.
5. Soak ≥ a few thousand blocks past V15_HEIGHT; confirm no divergence.

## 5. Go / no-go for the final V15 flip

Flip `GV_SLICE1/G4/G5_ACTIVATION_HEIGHT` → `V15_HEIGHT (20000)` only when ALL hold:
- [x] determinism / cross-validator test green (this report, §1)
- [x] reorg recompute property green (§1–§2)
- [x] mainnet replay gate-off guarantee pinned (§3)
- [ ] live multi-node testnet soak across V15_HEIGHT clean (§4)
- [ ] live E2E reorg around the window clean (§4)
- [ ] full historical mainnet replay byte-identical vs baseline (§3, needs chain.json)
- [ ] coordinated point-release + beacon notice (V14_DEPLOYMENT_CHECKLIST.md)

Until the live items are checked, mainnet remains deferred. **No flip before B3 §4 is green.**
