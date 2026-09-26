# Phase-3 security closure — the three pending tests + ConvergenceX header audit + IBD residual

All on the integrated candidate `integration/sec2-p2p-ibd` (node `c0c21da0`). Simulated peers are
a Python protocol client, NOT independent real nodes.

## 2A — Real mainnet sync from genesis (integrated binary) — VERIFIED (partial-height, real)
Isolated lab node (mainnet profile, no miner, NOT STRATO), connected to the real default seeds,
synced from block 0. Measured on THE INTEGRATED BINARY:
- genesis → **height 5,587 in 121 s**; ≤ assumevalid(3554) fast-sync ~115 blk/s, post-checkpoint
  full-validation **~23 blk/s**.
- **Independent hash check vs the live mainnet public RPC: 5/5 match** (heights 1, 10, 50, ~2793,
  5586) → the integrated binary follows the REAL highest-verified-work chain.
- Full-tip extrapolation at the measured ~23 blk/s ≈ ~18 min (consistent with the prior 18.2 min).
  **NOT claimed as a measured full-chain time** — a complete genesis→tip run is the final
  confirmation (documented reference height here = 5,587, hashes verified).

## 2B — 66 historical exceptions, independent verification — PASS
Recovered the real blocks at all 66 exception heights (range 4160–5410) from the live mainnet RPC
and compared to the recorded table hashes: **66/66 match, 0 mismatches.** The exceptions are
anchored to the ACTUAL mainnet blocks (no substitution). Combined with the static assessment
(bounded ≤5410, no PoW bypass, only replays the miner's original stability params), they introduce
no trust/validation problem and cannot apply to any height > 5410 (irrelevant to #29,900/#30,000).

## 2C — ThreadSanitizer on the integrated binary — PASS
TSan build exercised SIMULTANEOUSLY: block production (miner), P2P reception (honest peer feeding
blocks), reorg/convergence (victim converged h4→h12 under TSan), and a concurrent RPC storm
(getblocktemplate/IBD gate + getblock + culprit inputs). **0 data races, 0 TSan warnings.**

## Item 5 — ConvergenceX header-verifiability audit — headers-first must NOT trust header work
`verify_cx_proof` requires the full PoW transcript — `x_bytes` (n·4), `checkpoint_leaves`,
`segment_proofs`, `round_witnesses` — which are NOT part of a block header. **Therefore a SOST
header alone cannot prove its PoW/work** (unlike Bitcoin's self-contained 80-byte header). A
headers-first / getheaders design may transfer bits_q + roots for download *ordering*, but MUST
NOT count header-announced work toward chain selection; work is only real once the full block's CX
transcript is validated. The current model (download full blocks → verify CX → select highest
VERIFIED work, as the convergence fix does) is the correct and safe one. **Conclusion: keep
headers-first OUT of the release candidate** (its benefit is limited to ordering and it carries a
work-trust foot-gun); continue it as post-fork R&D only if a safe ordering-only design is proven.

## Item 3 — IBD mining-gate residual risk
The v2 gate is attacker-independent (local checkpoint-verified tip height; T1/T2 prove a lying peer
cannot stop a healthy node's mining; T4 proves a genesis/eclipsed node refuses to mine on a stale
tip and does not present it as synced). Residual: a node synced ABOVE the checkpoint but below the
true tip may mine soon-orphaned blocks (non-catastrophic; deep-reorg protection). A tighter bound
requires either a most-recent-checkpoint or a **minimum-chainwork floor** (both LOCAL and verified,
still peer-independent) — recommended as a release-time tightening (bump the constant per release).
Fundamental limit: a node cannot KNOW it is at the network tip in isolation without some external
reference; we therefore do NOT improvise a consensus change and keep the stable, DoS-immune bound.
