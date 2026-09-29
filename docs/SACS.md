# SOST Autonomous Chain Safety (SACS) — status

Consolidated pointer. Full research lives on branch `research/sost-autonomous-chain-safety`
(rebased onto current main 2026-09-29; backup `backup/sacs-pre-rebase-20260929`). No consensus/V16/STRATO
change; nothing deployed to mainnet.

## What SACS is
An autonomous safety layer over open PoW: every node independently follows the **highest cumulative verified
work** chain. No ChainLocks, masternodes, quorums, miner votes or developer-selected chain. **Not** absolute
finality — a valid higher-work chain cannot be excluded by software alone.

## Two separated deliverables
- **SACS Core (V16-compatible)** — fork/reorg monitor, structured events, read-only `getchainsafety` RPC,
  transaction-safety state machine (CONFIRMED→REORGED→REENTERED_MEMPOOL→CONFLICTED), wallet/Explorer/DEX/
  exchange reconciliation, recovery/persistence. **Observability + application safety, no consensus change.**
  Status: **CODE COMPLETE + LAB VERIFIED** on the research branch; **NOT deployed** (no binary swap pre-fork).
- **SACS Deep-Reorg Recovery** — research (devnet only) into making the 500-block cap an operational alert
  rather than an automatic rejection, so a valid higher-work chain can be adopted after a long partition.
  **Consensus-affecting → future coordinated upgrade, never auto-added to V16.**

## MAX_REORG_DEPTH = 500 finding (research branch, `SACS_500BLOCK_FINDING.md`)
Enforced in `src/sost-node.cpp` at 3 sites (:7199 accept, :7388 fork-storage, :7479 reorg) + checkpoint
guard (:7488). Behaviour: **≤500 → converge to most-work; ≥501 → PERSISTENT SPLIT even with more valid work**;
also does not stop a <500 51% reorg; split persists across restarts. Literal 499/500/501/550/600 at mainnet
scale is BLOCKED-ENVIRONMENT (SbPoW mining cost); tested at scaled devnet `MAX_REORG_DEPTH=8` (depths
6/7/8/9/10). Recommendation: treat 500 as an operational **alert**, separating policy from consensus — future
upgrade, not V16.

## Checkpoints (`SACS_CONSENSUS_AUDIT.md` + verified on STRATO)
- **Hard checkpoints** (≤ height 3,554): reject a contradicting chain → a trust assumption, not just an
  optimisation. **assumevalid**: skips PoW/sig recompute only; does not gate selection/subsidy/UTXO/difficulty.
- **Dynamic checkpoint updater NOT running on STRATO** (no cron / systemd timer / `checkpoint.json`) —
  verified read-only 2026-09-29. No operator is imposing a chain via checkpoints.

## Web / whitepaper
Documented as **LAB VERIFIED · RESEARCH** on `website/sost-security.html#sacs` and
`website/sost-whitepaper.html#sec-sacs`. Never labelled MAINNET LIVE until an authorised, backed-up,
reversible deployment after #30,000.

## Fresh devnet lab run — 2026-09-29 (IMPORTANT, must reconcile)
Ran the branch harness `tests/sacs_p2_reorg.sh` with the existing `build-sacs` binaries (isolated `--noseed`
nodes; competing chain delivered via `submitblock` → real `try_reorganize`; MAX_REORG_DEPTH scaled to 8):
- **converge_d8 (disconnect 8 = limit): PASS** — B adopted A's higher-work chain; UTXO root A==B (`509e23a9…`);
  restart stable.
- **reject_d9 (disconnect 9 = limit+1): the node CONVERGED instead of rejecting** — B reorged (disconnect 9,
  connect 10), UTXO root A==B (`890abdf1…`), restart stable; **no REORG_LIMIT rejection was logged**. The
  harness marks this FAIL because it *expected* a persistent split.

**This CONTRADICTS the analytical `SACS_500BLOCK_FINDING.md`** (which predicted persistent split at limit+1).
Empirically, in this build, limit+1 did NOT split — the depth guard (`:7479 disconnect_count > MAX_REORG_DEPTH`)
did not fire on this reorg path. Also `[REORG] Active work=0000… candidate work=0000…` and `Fork detected at
height 0` (two fully independent from-genesis chains) — logging/work-accounting on the fork-store→reorg path
needs review. **Conclusion: boundary behavior is UNRESOLVED and under active lab verification; no doctrinal
claim about the 500 rule until the code-path vs the analysis is reconciled.** No mainnet/consensus/V16 change.
