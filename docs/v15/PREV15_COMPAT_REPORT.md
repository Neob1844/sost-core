# Pre-V15 compatibility report (P5)

Question: does the V15 candidate (NEW, `V15_HEIGHT=25000`) stay compatible with the currently
DEPLOYED mainnet binary (OLD) for all chain state STRICTLY BELOW the fork, and correctly diverge
only AT/after 25000?

Deployed binary (OLD), confirmed live via `getinfo` on the mainnet node (:18232, read-only):
**version `0.3.2`**, profile `mainnet`, height 20795, genesis
`6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37`. The `0.3.2` string was
introduced at commit `5c2277e8` and not bumped until `v0.4.0` (`d9a72675`), so the exact deployed
commit is not pinnable from the version string alone — the binary/commit is an EXTERNAL ARTIFACT
that the operator must supply for the cross-binary tests below.

## What is PROVEN here (code-level, no OLD binary needed)

**B — NEW behaves per pre-V15 rules below the fork: PROVEN.** Every V15 rule change is strictly
gated on `height >= V15_HEIGHT (25000)` or `is_hist_jackpot_height()` (first at 25290):
- emission transition (T): `src/sost-node.cpp` gates at `height >= V15_HEIGHT` (template + validator, same comparison);
- Historical Jackpot (J): `is_hist_jackpot_height()`, no jackpot in [genesis, 25289];
- `TX_TYPE_JACKPOT` is rejected below the first jackpot height.
The consensus audit (SECURITY_AUDIT_REPORT.md, class 1) independently verified NO ungated consensus
change, and `tests/test_v15_activation_boundary.cpp` (MAINNET profile, 15/15) proves the 24999/25000
boundary and that mainnet constants are byte-identical to pre-V15. Therefore, for every height the
live chain has reached (≤ 20795, far below 25000), NEW applies the identical rules OLD applied.

**D — OLD is NOT compatible after the fork: PROVEN (by design).** At height ≥ 25000 NEW enforces the
emission transition + (from 25290) the jackpot; an OLD (v0.3.2) node that lacks these rules will
disagree at/after the fork. This is precisely why the coordinated binary swap must complete BEFORE
25000 (RUNBOOK_CUTOVER.md) — reaching 25000 on OLD activates nothing and would split from upgraded nodes.

## What REQUIRES the OLD binary / a chain snapshot → WAITING_EXTERNAL_ARTIFACT

These need either the exact deployed v0.3.2 binary or a read-only snapshot of the real mainnet
chain, on the second (non-miner) box — they must NOT run against the live datadir here, and DEV
SbPoW mining is unsafe on the miner box (OOM risk, see SECURITY_AUDIT_REPORT.md operational note):

- **A — OLD-produced chain loads in NEW.** The live mainnet chain (built by v0.3.2, all pre-V15) is
  the ideal fixture. Procedure: `cp` the node's `chain.json` to an ISOLATED datadir (read-only; never
  touch the original), start NEW `sost-node --profile mainnet --chain <copy> --rpc-port <alt>`, and
  assert it validates/reindexes to the SAME tip hash with ZERO rejected historical blocks.
- **C — OLD accepts NEW's pre-V15 blocks.** Mine a few blocks < 25000 with NEW on an isolated
  mainnet-profile chain; feed them to an OLD v0.3.2 node; assert acceptance (byte-identical rules).
- **E — NEW starts on pre-V15 chainstate without corruption.** Covered by A's reindex assertion +
  a wallet/db open check on the copied datadir.

Exact commands are in REMAINING_GATES.md (§ Gate #9). Required artifact: the deployed **v0.3.2**
binary (or its build commit) + a read-only copy of the mainnet `chain.json`.

## Gate status
**PARTIAL — code-level compatibility (B, D) PROVEN; binary-level A/C/E = WAITING_EXTERNAL_ARTIFACT**
(deployed v0.3.2 binary + chain snapshot on the 2nd box). No compatibility DEFECT found; the
remaining work is producing real cross-binary evidence, not fixing a problem.
