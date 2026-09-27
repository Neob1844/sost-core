# SOST Autonomous Chain Safety (SACS) — Consensus Audit & Plan (read-only foundation)

Reference height at audit: **28263** (tip `a71cca80…`, 2026-09-27T22:11Z) · →#29900: **1637** · →#30000 (V16 fork): **1737**.
Scope note: NO consensus/V16/height/main/production change here — audit + plan only.

## 1. Chain selection (audited)
SOST already selects the **highest cumulative VALID chainwork**, not the longest chain
(`src/sost-node.cpp:231`, `:5793` "Fork-aware chain acceptance using cumulative work (NOT longest chain)";
`include/sost/sostcompact.h::compare_chainwork`; `cumulative_work` threaded per block; `try_reorganize()`
replays fork blocks through the FULL validation path). Result: a peer CANNOT impose a chain by announcing
height/work — each node recomputes work over independently-validated blocks. This is the correct Bitcoin-style
base for SACS; no change needed to the selection principle.

## 2. MAX_REORG_DEPTH = 500 (the key finding)
`static const int64_t MAX_REORG_DEPTH = 500;` (`src/sost-node.cpp:446`). Enforced in 3 places:
- **:7199** block-accept — rejects a block whose height < tip − 500 (won't even consider deep-fork blocks).
- **:7388** fork-storage cutoff.
- **:7479** reorg — aborts if `disconnect_count > 500`.
Because it lives in block ACCEPTANCE and reorg, it is effectively a **consensus-affecting local rule**: two
long-separated partitions (>500 blocks each) can each refuse the other's more-work chain → **persistent split**
(the scenario in the mission). It is NOT a per-profile consensus parameter and NOT gossip-driven. It also does
NOT stop a <500-block 51% reorg. → Belongs in **Delivery B (research)**: test partition/convergence at depths
1/2/6/10/100/499/500/501/550/600 with real nodes; evaluate "500 as operational ALARM, not hard accept-rule".

## 3. Checkpoints / assumevalid (§VI, audited)
`include/sost/checkpoints.h`: (a) hard checkpoints (exact height+hash), (b) assumevalid anchor (skips sig checks
below it during fast sync), (c) **dynamic** `checkpoint.json` (cwd or `/etc/sost/checkpoint.json`) → sets
`assumevalid_height/hash` + extra checkpoints at startup. `deploy/update_checkpoint.sh` (VPS, RPC 18232) writes
`assumevalid = tip − 10` whenever the chain advances >25 blocks. **Risk:** a dynamic assumevalid this close to
the tip, if trusted for chain SELECTION (not just sig-skip), could act as a soft finality authority / bias a
branch. **SACS requirement:** dynamic checkpoints must accelerate historical validation ONLY, never override
most-work selection, never be mandatory for other operators. → Delivery A: verify assumevalid is sig-skip-only
(does not gate reorg/selection); document; ensure genesis-sync still works without checkpoint.json.

## 4. Existing bases (do not re-implement)
Branches (all present, NONE merged to main): `integration/sec2-p2p-ibd`, `release/v16.3.0-sec1-rpc`,
`fix/ibd-mining-gate` (the IBD gate must use locally-validated height, never peer-announced — reuse the fixed
version only), `feat/p2p-headers-first-ibd`, `test/security-gauntlet`. SACS reuses these; it does not rebuild P2P.

## 5. Delivery split
**A — V16-COMPATIBLE (priority, no consensus change):** SACS reorg monitor (observe fork/reorg/deep-reorg,
structured events `CHAIN_HEALTHY/FORK_DETECTED/REORG_STARTED/REORG_COMPLETED/DEEP_REORG_ALERT/…`), read-only
RPC to read incident history, transaction-safety state machine (PENDING/CONFIRMED/REORGED/REENTERED_MEMPOOL/
CONFLICTED/REPLACED/UNKNOWN) for wallet/Explorer, configurable exchange-safety API (never a consensus rule),
persistence/fsync + P2P hardening reuse. Reproducible binary + SHA-256; NOT auto-deployed.
**B — CONSENSUS RESEARCH (devnet only, future fork):** MAX_REORG_DEPTH alternatives (hard limit vs pure
most-work vs 500-as-alarm) with real-node partition/convergence tests; no incompatible mainnet change; no V16.

## 6. State (honest)
Audit (this doc): **DONE (read-only)**. SACS monitor/RPC/tx-safety/exchange-API: **DESIGNED, not yet implemented**.
Real-node partition + MAX_REORG_DEPTH tests: **PENDING (executable next — devnet lab, ulimit -f unlimited unblocks node bring-up)**.
Everything else: FUTURE / BLOCKED-on-owner (deploy/SEC2).
