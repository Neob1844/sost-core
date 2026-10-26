# C708 — ARV reorg finality security audit

This is research only, on branch `feat/c701-automated-bridge`. Mainnet, V17, consensus and the
node binaries are unchanged. No keys were used, no funds moved, no contract was deployed and
SACS V2 was not activated.

**Question.** Can the SOST Atomic Reserve Vault keep wSOST backed 1:1 against reorganizations,
network partitions and a hashrate majority? The constraints: no custodian, no multisig, no
privileged quorum and no developer-chosen checkpoint.

The study was written, then reviewed adversarially. The review broke the first draft's
conclusion on Ethereum anchoring. §8 records what was retracted and why.

## 0. Verdict

**Under the stated constraints the problem has no solution.** Today's measured top share is
61–83 %. Against an adversary with more than half of the hashrate, no rule computed from chain
data alone can make one history canonical for every honest participant. This holds whether the
rule runs on a SOST node or on an Ethereum verifier (§5).

| measure | what it really gives |
|---|---|
| 500-block cap + 501 confirmations | LOCAL_NODE_SAFETY for nodes that were already synced. Nothing more. |
| relay mirrors the cap | the relay agrees with synced nodes. Fresh, eclipsed or partitioned nodes can still disagree. |
| conflict-proof freeze + exposure caps | detection and bounded loss, **not** prevention. It is also a shutdown switch the majority miner can trigger at will (§7). |
| Ethereum anchoring | **not a solution today** (§8). With q > 1/2 the attacker chooses the anchors. With header-only relays, anchoring breaks LOCAL_NODE_SAFETY and can halt honest nodes. It needs block-validity proofs and data availability, which do not exist for SOST, and ConvergenceX verification in the EVM is probably infeasible. |
| more independent hashrate | the only measure that restores the honest-majority assumption, and with it probabilistic finality for all four properties |

**The limit we cannot cross without changing the protocol's assumptions:**

1. **Honest majority** (q < 1/2). This is false today.
2. **Or** an external, public, final record of arrival, plus full-validity proofs and data
   availability. That is a new dependency on another chain, not just "anchoring".
3. **Or** a subjective input (weak subjectivity). It is acceptable only when each user chooses
   it, never when one author imposes it.

### Rigor criterion (applied throughout)

The reorg problem is **not** solved by any of these on its own:

* a local policy that rejects reorgs deeper than 500 blocks;
* waiting 501 confirmations;
* minimum chain work;
* a release checkpoint;
* an Ethereum relayer that copies the same policy.

Every measure is scored on four separate properties:

* `LOCAL_NODE_SAFETY`: a node that saw the deposit with ≥ K confirmations never loses it.
* `NETWORK_CONVERGENCE`: every honest node, synced or fresh, ends on the same tip.
* `GLOBAL_CANONICALITY`: one history is accepted by every honest node, fresh ones included, and
  the relay follows it.
* `BRIDGE_BACKING_SAFETY`: every minted wSOST has its deposit on the relay's chain **and** on the
  chain of every honest node. When nothing was minted it is reported as **N/A**, never as YES.

A property that only protects an already-synced node is never described as finality.

## 1. What `MAX_REORG_DEPTH = 500` guarantees (from the code; confirmed by the review)

This covers mainnet and V17 (`src/sost-node.cpp`), where `SACS_V2_ACTIVATION_HEIGHT = INT64_MAX`
and `g_checkpoints[]` is empty.

* **Step 3.** `try_reorganize` refuses a reorg when
  `disconnect_count = tip_height − fork_point > 500`. The depth is counted on the node's own
  active chain.
* **Step 4.** A reorg needs **strictly** more cumulative work.
* **Fork admission.** Fork blocks with a known parent are admitted at any depth; only an upper
  height window applies. `cleanup_old_forks()` prunes non-active entries below `tip − 500` at the
  next connect, so a synced node cannot even evaluate a branch that forks deeper than 500 blocks
  below its tip.
* **Fork-store limits.** Admission is capped at `MAX_FORK_INDEX_ENTRIES = 65,536`. Below SACS V2,
  new entries are dropped when the store is full, and there is an orphan quota per source.
  `fork_block_precheck` checks PoW against the block's *own declared* bits; cASERT is checked only
  at connect. Whether low-work fork blocks can fill the store and block honest reconvergence is an
  **open test** (§9).
* **Sync.** A syncing node fetches by height (GETB, plus a walk-back of at most 4,096 blocks), and
  only from peers that advertise a higher height. Relay goes only to peers within 50 blocks.
  There is no fetch-by-hash.
* **Fast-sync hints.** The 14 hard checkpoints (≤ #3,554) and assumevalid are hints only. There
  is no minimum chain work.

| property | guaranteed by the cap? |
|---|---|
| LOCAL_NODE_SAFETY | **YES**, for an online, synced node that holds > 500 blocks above the deposit. A node that reindexes, resyncs or was offline counts as a fresh node again. |
| NETWORK_CONVERGENCE | **NO** |
| GLOBAL_CANONICALITY | **NO**: what a node accepts depends on what it saw first |
| BRIDGE_BACKING_SAFETY | **NO** (§3) |

## 2. Do 501 confirmations give anything global?

They are **necessary**: K ≤ 500 is broken outright by a majority miner (S2). They are **not
sufficient**: they protect synced nodes only.

S3 shows why. The majority attacker releases a heavier chain after the mint. A fresh node that
reaches the attacker's chain first adopts the history without the deposit, so the wSOST is
unbacked for that part of the economy.

## 3. Simulator results (`research/arv/reorg_finality_sim.py`)

The simulator reproduces 26/26 expected outcomes. Mutation checks confirm the tests can fail:
removing the cap makes S1 d = 501 erase the deposit and makes S2 K = 501 d = 501 lose backing.

The simulator applies the node rules of §1. Its limits are stated in its docstring:

* **Constant work per block.** This is *not* neutral. Under cASERT, real branches have close
  heights and different work, and a branch that is heavier but shorter cannot be expressed.
* **Idealized delivery.** The scenario chooses the order in which blocks arrive. The real node
  fetches by height from peers that advertise a higher height, and has no fetch-by-hash.

Fresh-node and partition results are therefore **reachable orderings**, not timing-faithful
predictions.

| scenario | LOCAL | CONVERGENCE | CANONICAL | BACKING |
|---|---|---|---|---|
| S1 heavier private chain, disconnect 499 / 500 / 501 | erased / erased / **kept** | — | — | — |
| S2 majority withholds, K = 499 / 500, release at d = 500 | — | — | — | **NO / NO** (minted, then erased) |
| S2 K = 501, attacker picks d = 499 / 500 | — | — | — | N/A (nothing minted) |
| S2 K = 501, attacker picks d = 501 / 505 / 700 | — | — | — | YES, **synced nodes only** |
| S3 K = 501, late release, relay `most_work` | NO (relay loses it) | NO | NO | **NO** |
| S3 same, relay `cap_mirror` | YES | NO | NO | **NO** (freeze triggers) |
| S3 same, honest-first anchors | YES | YES | YES | YES, but the bridge is frozen and the anchors were honest by construction (see S6) |
| S4 partition 300 / 200 (< cap) | YES | YES | YES | N/A |
| S4 partition 900 / 600 or 600 / 900, relay sees one side | YES | NO | NO | **NO** |
| S4 600 / 900, honest-first anchors | YES | YES | YES | YES, but it **needs fetch-by-hash**, which the real node lacks |
| S5 anchors, K < F | NO | YES | YES | **NO** |
| **S6 attacker posts its headers to the relay first, withholds the bodies** | **NO** (a node 600 deep is forced off its deposit) | YES (trivially) | NO | N/A |

What the results show:

* **K ≤ 500 is broken.** K ≥ 501 is the minimum, never the answer by itself.
* **`most_work` is the worst relay.** It is the fork choice of the C705 sketch. The relay must at
  least use `cap_mirror`.
* **`cap_mirror` adds detection, not prevention.** A heavier valid chain that contradicts a final
  deposit is objective proof of a deep fork, so the relay can freeze without any key.
* **S6 refutes the draft's anchoring result.** The anchor-aware node is truncated to the fork
  point (h = 100). It cannot follow the attacker because it never received the bodies: it halts.

## 4. Partitions, bootstrap, restart, eclipse, retention, majority miner

* **Partition shorter than the cap:** the network reconverges on the heavier side.
* **Partition longer than the cap:** permanent split. The relay follows whatever its relayers
  feed it.
* **Bootstrap, fresh, reindexed or long-offline nodes:** they follow whatever heavier chain they
  reach first. This is the core gap; no local rule closes it.
* **Restart:** the fork store is in memory. Pending fork blocks are lost, the active chain is
  kept, and no outcome above changes.
* **Eclipse:** an eclipsed node is the F2 case of S3. The V17 P2P hardening makes eclipse harder,
  not impossible.
* **Retention:** pruning below `tip − 500` stops a synced node from evaluating a deep fork. SACS
  V2 would retain those blocks; that is the convergence-versus-finality trade (C707 §3).
* **Majority miner:**
  * it can reorg anything shallower than 501 blocks on every node;
  * it can split the network deeper than that;
  * with q > 1/2 it always catches up, so more confirmations never help.

## 5. Can an Ethereum verifier recognize a final SOST history without a new trust assumption?

**No.** The argument:

1. An adversary with q > 1/2 privately mines a branch B from before the deposit, in real time,
   while the honest network mines A.
2. B satisfies every validity rule. Its timestamps pass MTP and the +600 s rule because it was
   mined in real time. B carries more work.
3. A verifier with no prior state that is given A and B sees two valid chains. The only intrinsic
   difference is that B is heavier.
4. So any deterministic rule over chain data either picks B (backing broken) or picks A by
   something B lacks: when each chain was *first seen*.
5. "First seen" is local unless it is recorded where every observer can verify it.

Escapes that look plausible and fail:

* **VDFs, beacon-linked timestamps, randomness from another chain.** They prove a block was made
  *after* some moment, never that it was *published before* some moment. Private mining satisfies
  them.
* **Timestamp penalties for late release.** Miners set timestamps, and the private chain's
  timestamps are honest.
* **An always-online relay contract.** It is a first-seen observer, but only of what relayers post
  to it. A majority miner can post first (S6).

This matches the literature:

* Nakamoto-style consistency requires an honest hashrate majority (Garay–Kiayias–Leonardos 2015;
  Pass–Seeman–Shelat 2017).
* A node offline long enough needs an external trusted input (weak subjectivity, Buterin 2014).

What remains outside the impossibility:

* **(a) Honest majority.** An assumption, false today.
* **(b) An external public final record**, plus validity proofs and data availability (§8).
* **(c) A subjective input.**
* **(d) A stake-based finality gadget.** A consensus change with a validator set; excluded by the
  owner's constraints, not by impossibility.
* **(e) Economic designs (over-collateral, insurance).** They bound the loss and give no
  canonicality.

## 6. Release checkpoints and minimum chain work

* **Release checkpoints** used as reorg barriers are a developer input. A fresh node cannot verify
  them, and that is exactly the case that matters. The release author then decides the canonical
  history. **They are rejected under the constraints.** They remain acceptable only as fast-sync
  hints (as today) or as a labelled weak-subjectivity point that each user chooses.
* **Minimum chain work** stops a low-work fake chain during bootstrap. It does nothing against a
  heavier attacker chain and provides no BRIDGE_BACKING_SAFETY.

## 7. What each ARV piece guarantees exactly

| piece | guarantees | does not guarantee |
|---|---|---|
| N1 keyless reserve | no insider can spend the reserve; spends happen only by consensus rule | that the deposit survives a reorg; that the economy follows the branch the reserve is on |
| N2 Ethereum proofs in SOST | SOST releases only against Ethereum-finalized burns. Against a **full** Ethereum verification, breaking it needs ≥ 1/3 of stake to be slashable. A **sync-committee light client** is weaker: committee signers cannot be slashed for signing wrong headers. | SOST-side finality. It also needs an Ethereum weak-subjectivity checkpoint to bootstrap. |
| SOST relay on Ethereum (optimistic, fraud proofs) | header and PoW validity, given ≥ 1 honest watcher within W | **block-body validity**. A majority miner can mine a valid header over an invalid body (a deposit spending coins that do not exist), and the Merkle inclusion still passes. SOST has no UTXO commitment to build a validity proof on. No canonicality for fresh or partitioned nodes. |
| open relayers | liveness: anyone can post | safety. They are also the attacker's channel for posting first (S6). |
| exposure caps (immutable) | worst-case unbacked wSOST ≤ the cap per window | prevention |
| conflict-proof freeze | objective, keyless detection | undoing a past mint; liveness. A majority miner can trigger it at will, so it is a **permanent shutdown switch**. No unfreeze rule exists yet. |
| more independent hashrate | q < 1/2, hence probabilistic finality (C707 table, at P < 1e-6: z = 30 safe to q ≈ 0.247, z = 100 to q ≈ 0.363) | anything while one entity holds > 50 % |

## 8. Alternatives, and what was retracted

The first draft said Ethereum anchoring gives "all four properties for blocks older than F".
**That claim is retracted.** The result came from anchors that were honest by construction. The
review broke it:

1. **The attacker chooses the anchors.** Relayers are permissionless, so a majority miner posts
   its private headers first and the relay anchors them (S6). Anchor-aware nodes must then drop a
   600-deep deposit. That breaks LOCAL_NODE_SAFETY, the one property the plain cap did give.
2. **Data withholding.** The attacker puts headers on Ethereum and never publishes the bodies.
   Anchor-aware nodes cannot follow, and they halt at the fork point (S6). That is a §9 rejection
   condition.
3. **Header-only validity.** A relay that checks only headers mints against invalid bodies. The
   fix needs validity proofs (ZK, or fraud proofs over a state commitment), and SOST has neither.
4. **Ethereum's own trust.** A SOST node that reads Ethereum finality needs an Ethereum light
   client, which itself needs a weak-subjectivity checkpoint. If anchors enter SOST as proofs
   inside SOST blocks, the 61–83 % miner can simply leave them out.
5. **Wire protocol.** The real node has no fetch-by-hash, so a node told by an anchor to switch
   branch would need a new P2P message.
6. **EVM cost.** ConvergenceX/SbPoW verification has a ~4 GB footprint per block and cannot run in
   the EVM. A fraud proof would need an interactive bisection over Merkleized memory, or a ZK
   proof; neither exists. **This is the first rejection test** for any Ethereum-side SOST
   verifier, not an "unmeasured" cost.

| alternative | new dependency | gives | status |
|---|---|---|---|
| A. honest majority + depth | q < 1/2 | probabilistic finality; all four properties with probability 1 − P(z, q) | false today (61–83 %); getting there is a decentralization goal, not code |
| B. external anchoring | another chain's finality, its light-client weak subjectivity, validity proofs, data availability, new P2P, inclusion that does not depend on SOST miners | in principle, canonicality for blocks older than F | **not viable today**: blocked by points 1–6 |
| C. user-chosen weak subjectivity (own node, several independent sources) | social: the user's chosen sources | canonicality for that user | subjective by definition, but not unilateral |
| D. caps + freeze | none new | bounded loss + detection | the only mitigation available now; shutdown switch for the majority miner; loss bounded, never zero |
| E. over-collateral / insurance | an external collateral asset | partial reimbursement | bounds the loss; not finality |

## 9. Invariants, adversarial tests and rejection conditions

Invariants for any ARV build:

1. `minted_wSOST ≤` the deposits accepted under the chosen finality rule. That rule must be one of
   §5 (a)–(e) and stated explicitly; it is never "500 confirmations".
2. Mint delay: `K ≥ 501` SOST blocks **and** the relay challenge window W has elapsed. These are
   separate units and both must hold.
3. The relay never uses uncapped `most_work`.
4. A heavier header chain that conflicts with a minted deposit freezes both mint and release.
   **Open:** an objective unfreeze rule that a majority miner cannot hold hostage forever. None is
   known.
5. Exposure caps are immutable constants.
6. No rule may make an honest SOST node halt, or abandon a deposit it holds deeper than 500. S6
   shows that anchoring violates this.

Adversarial tests required before any real funds:

* S1–S6 re-run with per-block work and height-driven sync;
* the real-node lab (§10);
* fork-store flooding with low-declared-work blocks;
* relay griefing: header spam, false fraud proofs, censorship longer than W;
* attacker-first posting with withheld bodies;
* an invalid body under a valid header;
* an Ethereum reorg before finality;
* a node restart mid-reorg.

**Drop the design if any of these holds:**

* the EVM cannot verify a SOST header at a reasonable cost (likely, §8);
* any test shows minted wSOST greater than the accepted deposits;
* any rule makes an honest node halt (S6);
* anything needs a key, a committee or an allow-listed relayer;
* the freeze has no objective unfreeze rule.

## 10. Real-node check (scaled)

**PENDING.** It runs after the V17 final gate, so it doesn't compete with that battery for the
machine. Script: `research/arv/c708_realnode_lab.sh`. It runs on devnet, where the cap is 8 and
the fork sits below the SACS V2 height 42, so the legacy rule applies as on mainnet.

* **R1, depth sweep:** depths 7 and 8 reorg, depth 9 is refused.
* **R2, fresh nodes:** three empty nodes receive the same two chains in different orders and end
  on different histories. This shows on real nodes that the cap gives LOCAL_NODE_SAFETY, not
  canonicality.

`run_deep_fork_devnet.py` in the V17 battery already covers the legacy-cap refusal on real nodes.

## 11. Delivery

```
MAX_REORG_DEPTH_500:        LOCAL_NODE_SAFETY only (online, synced, > 500 blocks above the deposit)
CONFIRMATIONS_501:          necessary (K ≤ 500 broken by a majority miner), not sufficient
GLOBAL_FINALITY_TODAY:      NONE (q > 1/2 measured; no external record)
RELAY_FORK_CHOICE:          most_work unsafe → cap_mirror minimum (detection only)
RELAY_VALIDITY:             header-only relays mint against invalid bodies → validity proofs required, none exist
ETHEREUM_ANCHORING:         RETRACTED as a solution (attacker posts first, data withholding, halts, EVM cost)
RELEASE_CHECKPOINTS:        developer authority when used as barriers → rejected under the constraints
MIN_CHAIN_WORK:             bootstrap spam protection only; no backing safety
N1 / N2 / RELAY:            custody + cross-chain verification; NOT reorg finality
FREEZE + CAPS:              detection + bounded loss; NOT prevention; a shutdown switch for the majority miner
SOLUTION_UNDER_CONSTRAINTS: NO (§5)
LIMIT:                      honest majority, OR an external final record + validity proofs + data availability,
                            OR user-chosen subjectivity: none of these is available under the constraints today
RECOMMENDATION:             do not back wSOST with SOST deposits on reorg grounds until hashrate is
                            decentralized (largest miner q < 1/2, sustained) or a validity-proof route
                            exists; any earlier pilot = caps + freeze, labelled "bounded loss, not final"
V17_CHANGED: NO · CONSENSUS_CHANGED: NO · MAINNET_CHANGED: NO · SACS_V2_ACTIVATED: NO
```
