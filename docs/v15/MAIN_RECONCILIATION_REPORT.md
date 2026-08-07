# V15 main reconciliation report (canonical 25000 vs old 20000)

Reconciles the divergence discovered before deploy-prep: `origin/main` had received an OLDER V15
implementation (`c37cac6e`, V15@**20000**) via PRs, while the deploy branch
`feat/v15-jackpot-explorer-card` (HEAD b7045f64) carries the CANONICAL, validated V15@**25000**.
Mainnet is already at ~20881 (past 20000), so the old V15@20000 activation is in the past and cannot
ship. Owner confirmed Option 1: canonical V15@25000 supersedes; keep main's non-consensus web work.

## Refs
- `FEATURE_HEAD` (canonical) = `b7045f64`
- `origin/main` (at reconcile) = `6f91c022`
- `merge-base` = `b822db4c`
- Reconciliation branch = `reconcile/v15-25000` (`145f9d7f`) — NOT merged to main.

## origin/main commits (b822db4c..6f91c022) — classification
| Commit(s) | Class | Action | Reason |
|-----------|-------|--------|--------|
| `c37cac6e` + merge `383f498a` "V15 Final Decentralization Fork + Historical DTD Jackpot (consensus)" | old V15 consensus (V15@20000) | **REPLACE WITH CANONICAL V15@25000** | superseded design; V15@20000 in the past; no `validate_live_jackpot`; different jackpot.h |
| 15 `explorer:` / PR commits (v385–v392: dashboard reconcile, jackpot card glow, label overflow fix, gold-reference price card, banner note, SOST-vs-Gold Chart.js card, Atomic Swap & DTD video) | web/explorer UI | **KEEP** (reconciled) | non-consensus; the only file they touch is `website/sost-explorer.html` |

## Resolution
- **CONSENSUS SOURCE = canonical V15 branch.** All of `src/`, `include/`, `tests/`, `CMakeLists.txt`
  set to exactly `b7045f64` (verified **0-line diff** vs feature). The old-V15 additions to
  `lottery.h`, `popc_v15.h`, `lottery.cpp`, `sost-miner.cpp` and the 4 old-V15 test files
  (`test_v15_jackpot.cpp`, `test_v15_decentralization.cpp`, `test_v15_jackpot_reorg.cpp`,
  `test_v15_jackpot_runtime.cpp`) were REMOVED. The 6 old-V15 spec docs (`docs/V15_*.md`, V15@20000)
  were removed (superseded; still in git history at `c37cac6e`).
- **NON-CONSENSUS SOURCE = origin/main where compatible.** `website/sost-explorer.html` = origin/main's
  newer explorer (video/charts/banner/glow/labels) with the activation heights corrected to the
  canonical values: V15 **20000→25000**, jackpot first **20286→25290**, HTLC **15000→16000** (relay
  **17000** noted). Millisecond timers (`TIMEOUT_MS=15000`, `setInterval …,15000`) and the nonce bar
  range (`BAR_MAX=20000`, "20,000 nonces") were deliberately LEFT intact.

## Post-reconciliation invariants (verified in the reconciled tree)
- `V15_HEIGHT = 25000` (mainnet), first jackpot `25290`, `EVM HTLC 16000`, `relay 17000`.
- `validate_live_jackpot` present (12 refs) — the canonical reconstruction + B-1 backstop.
- No effective V15@20000 activation in consensus; **single** jackpot implementation (no duplicate).
- BTC gate default OFF (`SOST_BTC_HTLC_SIGNING` OFF; `SOST_BTC_ATOMIC_SWAP_ENABLED` default OFF) — Option A/B model preserved.
- 0 conflict markers anywhere; reconciled tree == canonical feature except `website/sost-explorer.html`.

`main` (local `b822db4c`, remote `6f91c022`) was NOT modified. Awaiting final authorization to merge
`reconcile/v15-25000` → main.
