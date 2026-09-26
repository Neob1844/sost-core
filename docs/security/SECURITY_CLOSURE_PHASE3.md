# Phase-3 security closure — the three pending tests + ConvergenceX header audit + IBD residual

All on the integrated candidate `integration/sec2-p2p-ibd` (node `c0c21da0`). Simulated peers are
a Python protocol client, NOT independent real nodes.

## 2A — Real FULL mainnet sync from genesis (integrated binary) — COMPLETE (real, hash-verified)
**Definitive run:** the integrated binary synced **genesis → tip (28,077) in 25m06s (1506 s)**; the
**tip hash matches the public mainnet RPC exactly**, and hashes at h=1/12000/20000/25000 also match
(5/5) — the binary follows the real highest-verified-work chain across every historical activation
(V11/V12/V13/V15). Emission at the V15 transition #25000 is correct (subsidy 785100863,
miner_reward = 50% split). Sync source: an available already-synced local peer (the internet seed
DNS did not resolve from the lab box); the chain content is the REAL mainnet chain (hash-verified),
so this validates the binary's sync+verification logic regardless of source.
**Honest timing correction:** the prior "18.2 min" figure (from the standalone P2P branch) does NOT
reproduce here — the real full sync is **~25 min** on this box, with the per-interval rate declining
from ~115 blk/s (fast-sync ≤ checkpoint) to ~8–15 blk/s in the 24k–28k range (heavier late blocks).
Correctness is fully verified; the 18.2 min claim is retracted for this binary/environment.

### (superseded) earlier partial note
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

## Update — negative-case exceptions, disk-full, doc fix (follow-up)

### Exceptions — positive AND negative (empirical)
- **Positive (live):** during the real genesis sync the node LOGS the exceptions being applied with
  block-id confirmation — e.g. `historic param exception at h=5038 ... block_id confirmed` and
  `historic replay exception at h=5150..5158 ... accepted`. All 66 real historical blocks validate
  through their exceptions during sync.
- **Negative:** a tampered block at an exception height (nonce-flipped, and bits_q-altered) is
  REJECTED (-25). The guard applies the historical params ONLY when the recomputed block_id equals
  the recorded hash (`historic_param_id_matches`), so a tampered block (different id) does not get
  the exception and fails full validation.
- **Doc contradiction FIXED:** the 47 PARAM exceptions reach 5038 (`HISTORIC_PARAM_MAX_HEIGHT`), but
  the 19 REPLAY/cASERT exceptions (`HISTORIC_REPLAY_EXCEPTIONS`) reach **5410**. `HISTORIC_EXCEPTIONS_ASSESSMENT.md`
  updated (max exception height = 5410, still historical, cannot apply > 5410).

### Disk-full during write — fail-safe
Simulated without privileges by making `<chain>.tmp` a directory so the save's write fails cleanly
(disk-full / ENOSPC-equivalent; the failure mode is identical to the already-proven write-interruption:
the `.tmp` write fails → the atomic rename never runs → the real file is untouched). Result: node
stays ALIVE and keeps mining in memory, logs `WARNING: chain auto-save failed!` (8×), the real
chain.json is **byte-intact**, and after freeing the "disk" a restart **recovers the last good saved
state (h=8) with no corruption**.

### V16 transition
The #30,000 activation logic (Historical Jackpot V2 rollover + first PAID node-gated weighted jackpot)
is validated on the integrated binary by `run_v16_devnet_jackpot_v2` (9/0) at scaled devnet heights —
same consensus code path as mainnet #29,900/#30,000. Mainnet heights cannot be reached in the fast
devnet; the logic (not the literal height) is what the test exercises.
