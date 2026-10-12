# PRIMARY INFRASTRUCTURE INDEPENDENCE TEST

> ## STATUS: PLANNED — NOT EXECUTED
>
> This document is a **preparation-only** test plan. It has **not been run**.
> **No date is fixed.** Nothing in this file authorizes execution.
>
> This is a kill test of **INFRASTRUCTURE ONLY**. It MUST NOT touch, modify,
> pause, or risk any of the following:
> - Consensus rules or the S14 state
> - The node / miner / CLI binaries (no rebuild, no flag change, no swap)
> - The #30000 activation
> - DTD / Historical Jackpot V2
> - HTLC / atomic swap
>
> The only action this plan ever takes is **stopping one process** (the
> project-operated primary full node) and later **starting it again**. No
> consensus parameter, binary, or activation height is involved.

---

## 0. Scope and non-goals

**What this test is.** A deliberate, controlled outage of the *primary
project-operated infrastructure node* — the single node that the public
website, public RPC gateway, and block explorer happen to read from — held
down for approximately **24 hours**, to produce *evidence* that the SOST
network keeps producing and relaying blocks without it.

**What this test is NOT.**
- Not a consensus test. Consensus rules are untouched.
- Not a fork, not an activation, not a parameter change.
- Not a binary change. No node/miner/CLI is rebuilt, re-flagged, or replaced.
- Not a miner test. Independent miners keep running their own binaries with
  their own mandatory flags (`-DSOST_ENABLE_PHASE2_SBPOW=ON`,
  `-DSOST_TESTNET_FORKS=OFF`, `--realtime`). We do not start, stop, or touch
  any miner we do not already operate, and we do not stop the project miner's
  *consensus participation* as part of the infrastructure kill unless noted in
  the variant below.
- Not a destructive test. The primary node's datadir is preserved; shutdown is
  graceful.

**Two explicit variants** (decide before running which one is in scope):
- **Variant A — infrastructure-only (default/minimum):** stop only the
  public-facing services' upstream node process. If the project also runs an
  independent mining node, that mining node continues. This proves the
  *website/RPC/explorer* layer is non-consensus-critical.
- **Variant B — full primary-operator withdrawal (stronger claim):** stop the
  primary node AND pause the project's own miner, so that for ~24h the project
  contributes *nothing* to block production. This is the real decentralization
  proof and SHOULD be the eventual target, but requires more independent
  miners observed (see preconditions) before it is safe to attempt.

Run Variant A first. Only schedule Variant B once Variant A has passed and the
independent-miner precondition for B is met.

---

## 1. Objective and hypothesis

### Objective
Demonstrate, with recorded and publishable evidence, that the SOST network is
not dependent on the primary project-operated infrastructure node. Taking that
node offline for ~24 hours must not stop the chain.

### Hypothesis
With the primary node offline:

1. **Independent nodes continue.** Other full nodes stay up and keep validating.
2. **Blocks continue.** New blocks are produced by independent miners at roughly
   the normal cadence.
3. **Propagation continues.** Blocks and transactions relay peer-to-peer among
   the remaining nodes with no central relay.
4. **Peers reconnect.** The peer graph heals; nodes that used the primary node
   as a peer find and keep other peers.
5. **Chain stays consistent.** Independent observers agree on the chain tip
   (same height, same block hash) throughout, within normal propagation lag.
6. **Infrastructure failure ≠ consensus failure.** The website, public RPC
   gateway, and explorer may go dark or degrade (expected and acceptable), and
   this has **no effect** on consensus or block production.

### Falsification
The hypothesis is **falsified** (test result = negative, and a decentralization
gap is documented) if, during the outage: block production stalls beyond the
abort threshold; the independent peer set cannot sustain propagation; or
observers diverge on the tip (a real reorg beyond normal depth).

---

## 2. Preconditions (ALL must be true before running)

Do not run until every item below is satisfied and recorded.

- [ ] **Stable post-#30000 operation.** The #30000 activation has occurred and
      the network has run cleanly for a sustained settling period
      (recommended ≥ 2 weeks, ≥ ~2000 blocks) with no emergency, no stall, no
      unexpected reorg, and no open consensus incident.
- [ ] **Independent peers/miners observed.** At least **N independent full
      nodes** and **M independent miners** that are NOT operated by the project
      are observed live and producing/relaying.
      - Variant A minimum: **N ≥ 3 independent nodes**, **M ≥ 2 independent
        miners** confirmed over the prior 7 days.
      - Variant B minimum: **N ≥ 5 independent nodes**, **M ≥ 3 independent
        miners**, with no single independent miner holding a majority of recent
        blocks (sanity against a single point of production).
      - "Independent" = different operator, different host/IP range, not under
        project control. Record how independence was established (peer addrs,
        coinbase/miner tags, operator contact).
- [ ] **Backups taken and verified.** A fresh, integrity-checked backup of the
      primary node datadir exists and is restorable. A rollback snapshot of the
      VPS/service state exists (cf. prior V15/V16 rollback snapshot practice).
- [ ] **Maintenance window declared.** A ~24h window is scheduled at a low-risk
      time. Public notice posted that website/RPC/explorer may be unavailable
      or degraded during the window (framed as a planned resilience test).
- [ ] **No conflicting activity.** No pending release, no height-gated change,
      no deploy, no migration, and no scheduled fork inside or adjacent to the
      window. #30000 (and any later gated change) is NOT inside the window.
- [ ] **Independent observers ready.** At least **2 observation vantage points
      that are NOT the primary node** are prepared to record height and tip
      hash independently (e.g. an independent full node's own RPC, and a second
      independent node or a trusted third-party node). The test must never
      measure the network *through* the node it is killing.
- [ ] **Abort criteria and on-call owner agreed.** The abort thresholds in §5
      are agreed in writing, and a named operator is on-call for the full
      window with tested access (SSH key `sost_vps`, kill-by-PID procedure,
      restart procedure) ready.
- [ ] **Dry-run of restart.** The exact start/stop commands have been reviewed
      and the restart path verified on a non-production node or in a prior
      restart, so bring-back is known-good before the node is ever stopped.

---

## 3. Roles

- **Test lead** — owns go/no-go, declares start, abort, and end.
- **On-call operator** — executes stop/restart, watches abort thresholds, holds
  VPS access the entire window.
- **Independent observer(s)** — record metrics from non-primary vantage points
  at the defined intervals; at least one should be a party not operating the
  primary infrastructure.

---

## 4. Method (step by step)

All timestamps in UTC. All RPC reads during the outage come from **independent
observers**, never from the stopped primary node.

### Phase 0 — Go/No-Go (T−60 min)
1. Re-confirm every precondition checkbox in §2; abort the run if any is unmet.
2. Confirm the on-call operator has working access and the restart command in
   hand.
3. Confirm independent observers are connected and recording.

### Phase 1 — Baseline capture (T−30 min → T0)
Record from the primary node AND from each independent observer, and store the
raw outputs:

- **Height** — `getblockcount` / `getbestblockhash` (height + tip hash).
- **Peers** — `getpeerinfo` / `getconnectioncount` (count, addresses, inbound/
  outbound, which peers are independent).
- **Miners** — recent block producers over the last ~100–300 blocks (coinbase /
  miner identification), to establish who is producing and in what share.
- **Block cadence** — average inter-block time over the last ~100–300 blocks,
  and the normal expected cadence, so "roughly normal" has a number.
- **Mempool** — size/txcount, as a relay-health reference.
- **Service health** — website, public RPC gateway (`/rpc`, `/rpc/public`),
  explorer all green (so we can show the expected degradation afterwards).
- **Network view** — each independent observer records its own tip hash + height
  and its own peer list, so baseline agreement is on record.

Freeze the baseline into a signed/timestamped record. This is T0 reference.

### Phase 2 — Controlled shutdown of ONLY the primary node (T0)
1. Gracefully stop **only** the primary full node process — kill by **PID, never
   by name** (per standing ops rule), after a clean shutdown request.
   - Variant A: stop only the node serving the public services. Leave any
     project mining node and all miner binaries running.
   - Variant B (only if its precondition met): additionally pause the project's
     own miner's participation. Do NOT modify or rebuild the miner; just stop
     the process.
2. Do **not** touch: consensus config, binaries, datadir contents, activation
   state, DTD/Jackpot, HTLC, or any other node. The datadir is left intact for
   clean re-sync later.
3. Record T0 exact stop time and confirm (from an independent observer) that the
   primary node has dropped off the peer graph.
4. Expect and note: website/RPC/explorer now degrade or go dark. This is the
   intended infrastructure failure, not a fault.

### Phase 3 — Observation window (~24h)
At fixed intervals — recommended **T0+15m, +1h, +3h, +6h, +12h, +18h, +24h** —
each independent observer records:

- Current **height** and **tip hash**.
- **Blocks since last interval** and running **inter-block cadence** vs baseline.
- **Peer count and peer list** (did peers that relied on the primary node
  reconnect elsewhere? did the independent peer set stay connected?).
- **Tip agreement across observers** (all independent observers compared: same
  height within lag, same hash at matched heights).
- Any **reorg** seen (depth, at what height) and whether it is within normal
  single-block churn.
- **Mempool/relay** evidence (txs appearing and confirming without the primary
  node).

Log everything with timestamps. Do not intervene unless an abort threshold
(§5) is crossed.

### Phase 4 — Controlled restart and re-sync (≈T0+24h)
1. Start the primary node again (reviewed start command; Variant B also resumes
   the project miner process — no rebuild, no flag change).
2. Observe it **re-sync cleanly** from the network: it connects to peers,
   downloads the blocks produced during the outage, and converges to the **same
   tip** the independent observers hold. Record re-sync duration and final tip.
3. Confirm website / public RPC gateway / explorer recover and serve the current
   tip.
4. Capture a post-restart snapshot mirroring the Phase 1 baseline.

### Phase 5 — Close-out
1. Compare against §6 success criteria; mark pass/fail per criterion.
2. Assemble the evidence pack (§7).
3. Write the result up (positive or negative) and publish.

---

## 5. Rollback / abort plan

The primary node can be brought back **immediately** at any point by running the
reviewed restart command (Variant B also resumes the paused miner). Bring-back
is always available and is the first action on any abort.

**Abort immediately (restart the primary node now) if any of these is true:**

- **Block production stalls.** No new block is observed by the independent
  observers for more than a hard threshold — recommended **> 3× the normal
  expected block interval** (set the exact minutes from baseline cadence before
  the run), i.e. a genuine stall, not ordinary variance.
- **Propagation collapses.** The independent peer set can no longer relay —
  observers stop seeing new blocks/txs propagate although a miner is producing.
- **Observer divergence / real reorg.** Independent observers disagree on the
  tip beyond normal single-block propagation lag, or a **reorg deeper than the
  normal churn depth** (set a number, e.g. > 2 blocks) is observed.
- **Independent capacity drops below floor.** Independent nodes or miners fall
  below the Variant's minimum N/M during the window (the network is suddenly
  thinner than the precondition assumed).
- **Any consensus/safety anomaly** of any kind, or an external incident
  unrelated to the test that needs the primary node up.
- **On-call loss.** The on-call operator loses tested access — restart now while
  access still exists rather than risk an unattended outage.

**Abort procedure:**
1. On-call operator restarts the primary node (and resumes miner if Variant B)
   using the pre-reviewed command.
2. Record the abort reason, exact time, and the metric that tripped it.
3. Confirm the primary node re-syncs and services recover.
4. The run is recorded as **ABORTED** with the cause; a negative/aborted result
   is itself publishable evidence of a real dependency to fix.

An abort is not a failure of the process — running the primary node is always
the safe default.

---

## 6. Success criteria (measurable)

The test **passes** only if ALL of the following hold, measured from the
independent observers (never from the primary node):

1. **Blocks keep advancing.** Height strictly increases across the full window;
   number of blocks produced during ~24h is within an agreed band of the
   baseline cadence (e.g. within ±X% of expected block count — set X from
   baseline before the run). No stall beyond the §5 threshold.
2. **Independent peers keep relaying.** Blocks and transactions propagate
   peer-to-peer throughout the window with the primary node absent; at least one
   independent observer continuously sees fresh blocks from independent miners.
3. **Peers reconnect / stay connected.** The independent peer graph remains
   connected; nodes do not collapse to isolation when the primary node leaves.
4. **Tip consistent across independent observers.** At every recorded interval,
   all independent observers agree on height and tip hash (within normal
   propagation lag).
5. **No reorg beyond normal.** No reorg deeper than the agreed normal-churn
   threshold occurs during the window.
6. **Primary node re-syncs cleanly on return.** On restart the primary node
   connects, downloads the outage blocks, and converges to the exact same tip
   hash the independent observers hold, with no manual datadir surgery and no
   consensus intervention.
7. **Infrastructure failure was isolated.** Website/RPC/explorer degradation
   during the window had zero observed effect on block production or consensus —
   i.e. criteria 1–6 held regardless of the public services being down.

Any criterion failing = test does not pass; document which and why (that is a
genuine, valuable finding).

---

## 7. Evidence to publish afterwards

To make this *evidence* rather than a claim, publish a public write-up
containing (raw logs attached, timestamps intact, sources attributed to the
independent observers):

- **Window metadata** — variant run (A or B), UTC start/stop, who was on-call,
  who the independent observers were.
- **Baseline snapshot** — T0 height, tip hash, peer counts/lists, miner set and
  shares, measured cadence, service-health green.
- **Interval table** — for each recorded interval: height, tip hash, blocks
  since last, running cadence, peer count, cross-observer tip agreement,
  reorgs seen. Include it as a chart of height-over-time with the primary-node
  outage span shaded.
- **Proof of primary-node absence** — evidence the primary node was genuinely
  down for the full window (it dropped from independent peer lists; services
  degraded) — not merely idle.
- **Proof of independent production** — the blocks produced during the outage
  attributed to independent miners (coinbase/miner identification), showing the
  project did not produce them (especially required for Variant B).
- **Restart & re-sync record** — restart time, re-sync duration, final converged
  tip hash matching the independent observers, services recovered.
- **Pass/fail per §6 criterion** — each criterion marked with the number that
  backs it.
- **Result statement** — PASS / FAIL / ABORTED, with the cause if not PASS, and
  any dependency or decentralization gap discovered and the follow-up action.
- **Reproducibility note** — the exact (read-only) RPC commands used to gather
  metrics, so a third party could re-run the measurement.

Publishing rule: publish the result honestly whether positive or negative. A
negative or aborted result is published as a documented dependency to fix, not
hidden. Follow the standing practice of only labelling it a milestone when the
evidence genuinely supports the claim.

---

## 8. Reminder

Nothing in this document is to be executed now. It is written during the
pre-#30000 freeze as preparation only. Execution requires: #30000 activated and
settled, all §2 preconditions met, a declared maintenance window, and an
explicit separate go decision. This test touches **infrastructure only** and at
no point modifies consensus, S14, the node/miner/CLI binaries, the #30000
activation, DTD/Jackpot, or HTLC.
