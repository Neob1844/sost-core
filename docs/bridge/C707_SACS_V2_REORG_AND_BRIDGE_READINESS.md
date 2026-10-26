# C707 — SACS V2, reorg security and SOST Atomic Bridge readiness for #40,000

Research only · 2026-10-26 · chain tip at the time of writing: #32,392

Nothing in this study changes V17, consensus or mainnet. No funds move. Everything below was
read from code, not from documentation:

* V17 candidate: `v17-final-candidate` @ 32a0b1d8.
* V17 P2P branch: 5672c06c.
* Current mainnet line: v16.x and the emergency V30000 candidates.
* Live chain data: the public RPC.

---

## 1. SACS V2 — what the code actually says

| Field | Finding |
|---|---|
| SACS_V2_EXISTS | YES |
| FILES | `include/sost/params.h:681-703`; `src/sost-node.cpp` block accept (≈9045), fork-store admission (≈7603) and pruning `cleanup_old_forks` (≈9422), `try_reorganize` depth check (≈9619); SACS monitor `namespace sacs` + read-only RPC `getsacsstatus` / `getsacsevents` |
| ACTIVATION_HEIGHT | DEVNET_FAST 42 · TESTNET 30000 · **MAINNET `INT64_MAX` (deferred)** |
| CURRENT_MAINNET_STATUS | **NOT ACTIVE.** The same `INT64_MAX` is in the V17 candidate, the V17 P2P branch, the emergency V30000 candidates and the current main source. v16.2.3 does not contain SACS V2 at all. |
| Why deferred | Comment of 2026-10-08 (EMERGENCY): the network majority runs v16.x with the legacy 500-block hard cap. Activating V2 on only part of the network would make chain selection differ exactly in deep-reorg cases, which means a split. V2 also lifts the cap that bounds PoW-free fork storms (audit HIGH #6). |

**The contradiction is resolved by the code.** SACS V2 was *designed* to activate at #30,000, and
that was the plan. On 2026-10-08 it was deferred on mainnet to `INT64_MAX`. It has never been active
on mainnet.

### What SACS V2 is — the important correction

**SACS V2 is not a protection against reorgs. It is the opposite: a deep-reorg recovery rule.**

Today, in every mainnet build and in V17, the rules are these:

```
"depth" = disconnect_count = blocks of THIS node's active chain above the fork point
            (not the length of the attacker's chain)

depth ≤ 500   reorg accepted IF the other chain has strictly more cumulative work
depth  > 500  reorg REFUSED in try_reorganize (Step 3)
              a fork-choice rule that depends on each node's own history, not a block-validity rule
fork blocks   admitted to the fork store at any depth (PoW and parent checked), then pruned below
              tip − 500 by cleanup_old_forks() at the next tip connect
checkpoints   14 hard checkpoints up to #3,554 + assumevalid #3,554 (include/sost/checkpoints.h):
              fast-sync trust hints enforced with --full-verify-anchored-history, not reorg
              barriers; g_checkpoints[] (reorg barrier list) is empty; no minimum chain work
IBD           a syncing node connects blocks at tip+1 and never meets the depth rule; only reorgs
              relative to its own current tip are capped
```

SACS V2 (from its activation height, for forks whose fork point is after activation) turns the
500-block cap from a **hard rejection** into an **alarm**. A deeper reorg is then accepted when the
other chain is fully valid and has strictly more cumulative work. Deep fork blocks are also exempted
from the tip − 500 pruning, so they can win later.

* **Problem it solves:** liveness and convergence. After a network partition longer than 500 blocks
  (≈ 3.5 days), the two halves would never re-merge under the legacy cap. V2 lets the heavier one
  win.
* **Price:** it removes the only finality SOST has today. With V2 active, a heavier chain can rewrite
  any amount of post-activation history.

### Cases (legacy rules = today and V17; V2 = only if activated)

| Case | Legacy (mainnet, V17) | With SACS V2 active |
|---|---|---|
| A. 1-block reorg, more work | accepted (normal orphan) | accepted |
| B. 6-block reorg, more work | accepted | accepted |
| C. 20-block reorg, more work | accepted | accepted |
| D. 100-block reorg, more work | accepted (≤ 500) | accepted |
| E. Attacker chain with more work | **accepted by every node** if it is released before the honest chain has gained 500 blocks past the fork point, *however long the private chain is*. Once a node holds more than 500 honest blocks past the fork point, that node refuses it. A node still syncing (fewer than 500 honest blocks past the fork point in its view) can take the attacker's chain, so **the network can split** | accepted by every V2 node, for fork points at or after the activation height and while the fork blocks survive the resource limits: history is rewritten |
| F. Attacker chain with less work | never accepted | never accepted |
| G. Network partition | ≤ 500 blocks: the heavier side wins on reconnect. > 500: permanent split, needs a coordinated release | the heavier side wins at any depth |
| H. Node offline for days, comes back | it is behind, not forked: it syncs forward. Same result if the network had a reorg while it was away | same |

`MAX_REORG_DEPTH` today = **500 blocks** (≈ 3.5 days at 600 s), counted on each node's own active
chain. It protects a deposit only once the node holds more than 500 blocks above it.

## 2. SOST vs Bitcoin — properties, not slogans

| Property | Bitcoin | SOST today |
|---|---|---|
| Fork choice | most cumulative work | most cumulative work (same) |
| Reorg depth limit | none in consensus | 500-block fork-choice cap, relative to each node's own tip |
| Checkpoints / minimum chain work | Bitcoin Core ships a minimum-chain-work threshold and headers pre-sync against low-work forks | 14 hard checkpoints ≤ #3,554 + assumevalid (fast-sync hints, not reorg barriers); no minimum chain work; nothing after #3,554 |
| Timestamp rules | MTP(11), +2 h future limit | MTP(11), +600 s future limit (tighter) |
| Coinbase maturity | 100 | 1000 |
| Hashrate distribution | many independent pools; largest well below 50% | concentrated; see §4 |
| Node diversity / eclipse resistance | thousands of nodes, several implementations | small node count; V17 P2P hardening (invalid-block disconnect, `--connect` exclusivity) |
| Cost of a 6-block reorg | enormous (global ASIC hashrate) | low for whoever controls the majority of SOST hashrate |

* **WHAT_BITCOIN_GETS_FROM_SCALE:** a reorg must outrun most of the world's SHA-256 hashrate. That,
  not any rule, is why 6 confirmations are safe.
* **WHAT_SOST_CAN_REPRODUCE_IN_PROTOCOL:**
  * the identical most-work fork choice;
  * tight timestamp rules;
  * a minimum-chain-work floor, and extend the existing hard-checkpoint list past #3,554 in every
    release, against fresh-node capture;
  * the 500-block finality window;
  * peer diversity and anti-eclipse rules;
  * bridge-side confirmation depth and exposure caps.
* **WHAT_SOST_CANNOT_REPRODUCE_WITHOUT_MORE_HASHRATE:** the cost of a reorg. Against an entity with
  more than half the hashrate, no confirmation count is safe: the Nakamoto catch-up probability is 1.
  Only more independent hashrate fixes that.

## 3. Does SACS V2 protect the ARV?

**SACS_V2_PREVENTS_ARV_REORG: NO.** If it were activated, it would make the ARV *less* safe, because
it removes the 500-block cap that is today the only hard bound on how old a deposit can be reversed.

* **Under the legacy cap:** a deposit buried more than 500 blocks deep cannot be reorged out on nodes
  that were online. That gives the ARV a real, rule-based finality horizon.
* **Remaining hole:** a node syncing from genesis, and the Ethereum-side SOST light client if it only
  follows most-work, would accept a heavier deep fork that the online nodes reject. To keep the two
  sides consistent:
  * the Ethereum relay must enforce the same 500-block rule against its own tip;
  * SOST should ship rolling release checkpoints (§6 D, E).
* **Partition:** the Ethereum relay sees one side only. A long partition leaves it on whichever side
  its relayers follow, which is the same split risk as for fresh nodes.

The conclusion is conditional. V2 trades finality for convergence. It weakens the horizon on synced
nodes, but it also removes the synced-versus-relay asymmetry described above. The bridge is safe under
**either** rule only if the Ethereum relay enforces its own depth horizon. Under the legacy rule that
horizon matches the nodes; under V2 it would be the bridge's only horizon.

**Recommendation for the bridge:** keep SACS V2 deferred. If it is ever re-activated, it must keep a
finality horizon for bridge deposits. Example: V2 recovery allowed only for forks whose fork point is
newer than the bridge's release depth, or a bridge freeze triggered automatically by any
`DEEP_REORG_ALERT`.

## 4. Real hashrate data (last 1,500 blocks)

Public RPC, blocks #30,893–#32,392 (read 2026-10-26):

```
window        miners   top miner share            2nd       3rd     HHI    Nakamoto coefficient
1,500 blocks     3     sost1ad01a… 61.1 %          31.9 %     6.9 %   0.48         1
  500 blocks     3     sost1ad01a… 68.8 %          20.2 %    11.0 %   0.53         1
  288 blocks     2     sost1ad01a… 83.0 %          17.0 %      —      0.72         1
longest run of consecutive blocks by one miner: 544 (more than the 500-block cap)
block interval: mean 599.9 s · median 712 s · p95 788 s · max 23,403 s · min 60 s
500 blocks ≈ 84.5 h
```

**CURRENT_SOST_REORG_RISK** has to be read off these numbers:

* One miner holds more than 50% of the hashrate, so the Nakamoto coefficient is 1. Against that
  miner, every depth up to the 500-block cap can be reorged at will; no confirmation count helps.
* The protocol-level bound is the 500-block cap. What the dominant miner cannot do is make a node
  accept a reorg that disconnects more than 500 of its blocks. (The public 544-block run reflects
  share and luck; the capacity comes from q > 0.5 itself.)
* q here is the largest **single address** observed. A real attacker could rent hashrate or form a
  coalition, so this is not an upper bound on attacker share.
* The largest address is operated by the project itself. "Security rests on that miner's honesty"
  therefore means it rests on the operator, which matters for any keyless claim.

Security therefore rests on that miner's honesty plus the cap. It does not rest on PoW economics.
Until hashrate decentralizes, any value released against SOST deposits shallower than 501 blocks is
exposed to the largest miner.

## 5. ARV confirmation policy (SOST side)

The model is the Nakamoto catch-up probability for an attacker with hashrate share q (Bitcoin
whitepaper §11). These are the depths z needed for a given risk, computed exactly:

```
attacker share q   z for P < 1e-3   z for P < 1e-6     P(z = 30)     P(z = 500)
0.10                     5              11            < 1e-12        < 1e-12
0.20                    11              21            2.9e-9         < 1e-12
0.25                    15              31            1.4e-6         < 1e-12
0.30                    24              49            1.5e-4         < 1e-12
0.35                    41              85            5.5e-3         < 1e-12
0.40                    89             184            7.7e-2         < 1e-12
0.45                   340             704            0.43           4.7e-5
q >= 0.50          no z is safe — probability 1
```

**ARV_CONFIRMATION_POLICY** (adaptive, keyless: the vault contract applies it from the amount in the
deposit):

| Tier | Amount | Required depth | Reason |
|---|---|---|---|
| small | ≤ T1 | 30 blocks (≈ 5 h) | safe against a minority attacker up to q ≈ 0.247 at P < 1e-6 |
| medium | ≤ T2 | 100 blocks (≈ 17 h) | safe up to q ≈ 0.362 at P < 1e-6 |
| large | > T2 | **501 blocks (≈ 3.5 days)** | beyond the legacy 500 cap: online nodes cannot reorg it out, **whatever** the attacker's share |

**With today's concentration** (one miner above 50%, §4), the small and medium tiers protect only
against the *minority* miners. Until the Nakamoto coefficient is at least 2, the safe launch
configuration is: **every entry uses the 501-block tier**, and T1 and T2 start at 0. The faster
tiers open only when the measured top share stays below 0.247 (30 blocks) or below 0.362 (100 blocks)
over a long window. That measurement is public chain data, so the vault can apply it from relayed
headers without anyone deciding.

The large tier is the only tier that holds against a majority miner, and only while SACS V2 stays
deferred. T1 and T2 must come from the exposure policy (§6), not from guesses.

**ETHEREUM_FINALITY_POLICY:** finalized checkpoints only (Casper FFG, 2 epochs ≈ 12.8 min), verified
through the sync committee (N2), with the domain bound to `fork_version` and `genesis_validators_root`.
There is no "X confirmations" rule. Each Ethereum hard fork needs a SOST release first; until then the
reserve freezes and nothing is lost.

## 6. Exposure limits and further improvements (all keyless)

**ARV_EXPOSURE_POLICY.** The caps are immutable in the vault, or changeable only through a SOST
consensus upgrade. There is no admin.

| Limit | Rule |
|---|---|
| GLOBAL_BRIDGE_EXPOSURE | circulating wSOST ≤ the premint inventory. The premint size is the hard maximum loss in every scenario |
| MAX_PENDING_VALUE | entries released but not yet past the 500-block horizon ≤ E_pending |
| MAX_PER_SWAP | ≤ T2 unless it takes the 501-block tier |
| MAX_PER_BLOCK / MAX_PER_WINDOW / DAILY_CAP | rolling limit on releases per SOST block and per day, so a reorg can only take what fit in its window |
| Sizing rule | E_pending ≤ the cost to the attacker of a reorg of the corresponding depth. While hashrate is concentrated this cost is low, so the caps must be small |

Exposure limits bound the loss. They do not remove the attack.

| Improvement | Verdict |
|---|---|
| A. delayed bridge finality | YES: the tiers above |
| B. adaptive confirmation depth | YES: by amount |
| C. exposure caps | YES |
| D. rolling checkpoints | YES, *in releases*: extend the existing `HARD_CHECKPOINTS` list (today it stops at #3,554 and is only a fast-sync hint) with a recent block in every release, and make those entries reorg barriers. It protects fresh nodes and the relay. It is a release-time human input, verifiable by anyone, not a runtime key |
| E. cumulative-work floor | YES: a minimum-chain-work constant per release (Bitcoin-style anti-low-work-sync) |
| F. deep-reorg rejection | ALREADY THERE: the 500 cap. **Do not activate SACS V2 without a bridge carve-out** |
| G. weak-subjectivity checkpoint (bridge only) | YES: the Ethereum relay starts from a published SOST checkpoint and refuses reorgs deeper than 500 against its own tip |
| H / I. independent relayers, many submitters | YES: permissionless, bonded on the Ethereum side |
| J. fraud / challenge delay | YES: the relay's challenge window W |
| K. proof redundancy | partial: anyone can resubmit; a single valid proof suffices |
| L. canonical-chain commitment | YES: the vault stores the relayed SOST chain tip and work; every entry commits to a block hash, and a conflicting header at the same height triggers M |
| M. automatic freeze on contradictory proofs | YES: two valid but conflicting SOST headers deeper than the release depth, or a `DEEP_REORG_ALERT` proof, freeze new releases automatically. Exits keep working. The freeze lifts only through objective conditions, never by a person |

## 7. Coherence check — with no multisig at all

Everything above composes into one design:

* N1 keyless reserve + N2 Ethereum finality;
* legacy 500-cap finality, kept deferred from SACS V2;
* adaptive depth;
* immutable caps;
* automatic freeze.

There is no admin withdrawal, no guardian, no multisig and no human approval per operation. The
bounded model of C705 already shows that the deep-reorg case is the one that breaks I1. The caps and
the 501-block tier are what keep that case bounded.

## 8. Can N1 + N2 go into V17 at #40,000?

**Calendar.** The chain is at #32,392, so 7,608 blocks × 600 s ≈ **52.8 days**, which puts #40,000 at
about **18 December 2026**. Miners need the release some weeks before. That leaves about **4 weeks**
of engineering, review and testing.

| Item | Assessment |
|---|---|
| N1_IMPLEMENTATION_COMPLEXITY | medium: 2 output types, 4 tx types, validation, mempool policy, wallet, RPC, replay invariants. Estimate 3–5 k lines of C++ plus tests |
| N2_IMPLEMENTATION_COMPLEXITY | **high**: none of BLS12-381, keccak-256, RLP, SSZ or Merkle-Patricia exists in the node today (it links OpenSSL and libsecp256k1 only). Needs a vendored pairing library inside consensus, the per-fork Ethereum container layout (Capella → Deneb → Electra and the next fork), light-client update logic and receipt proofs |
| Ethereum side | vault contract + **SOST header relay**. On-chain verification of ConvergenceX and cASERT: **gas unmeasured, the largest unknown**, plus an external audit |
| CONSENSUS_SURFACE | large: a new cryptography stack becomes consensus-critical, plus a permanent dependency on Ethereum's fork schedule |
| SECURITY_RISK | HIGH: a bug lets anyone drain the reserve, or freezes it; there is no admin to recover |
| TEST / REPLAY / DEVNET | full genesis replay, devnet PoC (100 and 500 SOST), adversarial suites (invalid / malformed / stale proofs, double release, replay, concurrency, fork-version change, relayer outage), an independent audit of the contract, the relay and N2 |

**CAN_N1_N2_FIT_V17: NO.** The reasons, each one sufficient on its own:

1. The V17 scope is owner-frozen for #40,000 (multisig, the 80/15/5 economics, DTD-F1, the node gate,
   block limits, P2P). N1 + N2 are outside it. Only its release gate is still pending (one candidate
   commit, genesis replay, sanitizers, release hashes); adding a new cryptography stack now would
   reopen the scope and restart that gate.
2. N2 plus the Ethereum relay has never been prototyped here. A comparable light-client bridge needs
   months of build and audit, not 4 weeks.
3. Keyless means no admin recovery. Shipping it under-tested is the single worst failure mode of this
   design.
4. "Dormant" code inside V17 (activation later) does not save time: it still has to be audited before
   V17 ships.

**BRIDGE_AT_40000_REALISTIC: NO** for the keyless Atomic Bridge. What can be true at #40,000 without
compromising safety:

* V17 ships its frozen scope.
* The non-custodial P2P **Atomic Swap** (native HTLC, live since #16,000) remains the operational
  cross-chain path: users swap their own funds, and nobody holds a reserve.
* The ARV gets its own fork, V18, once the devnet PoC and the audit pass.
* The fastest safe timeline is a devnet PoC of N1 + N2 + vault + relay in Q1 2027, followed by audit,
  testnet soak and a V18 activation height chosen once the code is frozen.

## 9. Delivery

```
SACS_V2_IMPLEMENTED:        YES
SACS_V2_ACTIVE:             NO (mainnet INT64_MAX since the 2026-10-08 emergency; never active)
SACS_V2_ACTIVATION_HEIGHT:  mainnet INT64_MAX · testnet 30000 · devnet 42
SACS_V2_DESCRIPTION:        deep-reorg RECOVERY: turns the 500-block hard cap into an alarm; deeper
                            reorgs allowed when the other chain is valid and has strictly more work
MAX_REORG_DEPTH:            500 blocks (≈3.5 days) of each node's own active chain (fork-choice
                            rule); hard checkpoints only ≤ #3,554 (fast-sync hints); no min chain work
DEEP_REORG_BEHAVIOUR:       a heavier chain released before the honest chain gains 500 blocks past
                            the fork point wins everywhere; later, synced nodes refuse it and
                            syncing nodes may take it (split risk)
SACS_V2_ARV_PROTECTION:     NO — activating it would weaken the ARV (removes the 500-block horizon)
CURRENT_SOST_REORG_RISK:    HIGH: one miner 61–83 % (Nakamoto coefficient 1, 3 miners in 1,500
                            blocks, longest run 544); any depth ≤ 500 is reorgable by it; beyond
                            500 bounded by the cap (online nodes)
BTC_SECURITY_PROPERTIES_RELEVANT: most-work fork choice, MTP/time limits, min-chain-work against
                            low-work sync, many independent miners, node diversity
SOST_GAPS_VS_BTC:           hashrate concentration (cost of reorg), node count, no min-chain-work /
                            checkpoints
SAFE_IMPROVEMENTS:          keep SACS V2 deferred (or bridge carve-out); release checkpoints + min
                            chain work; relay mirrors the 500 rule; adaptive depth; immutable caps;
                            automatic freeze on contradictory proofs; more independent hashrate
ARV_CONFIRMATION_POLICY:    501 blocks for every entry while one miner > 50 %; 30 / 100 tiers open
                            only when measured top share < 0.25 / 0.36; Ethereum: finalized via N2
ARV_EXPOSURE_POLICY:        premint = hard max; pending-value, per-swap, per-block, daily caps; immutable
N1_REQUIRED:                YES
N2_REQUIRED:                YES
CAN_N1_N2_FIT_V17:          NO
RISK_LEVEL:                 HIGH if forced into V17
RECOMMENDATION:             V17 ships its frozen scope; ARV = V18 after devnet PoC + audit; keep
                            SACS V2 deferred
BRIDGE_AT_40000_REALISTIC:  NO (P2P Atomic Swap remains the operational non-custodial path)
REQUIRED_WORK_BEFORE_ARV:   N1 + N2 spec freeze · gas measurement of the SOST relay · devnet PoC
                            100/500 SOST · adversarial suite · external audit · testnet soak
V17_CHANGED: NO
CONSENSUS_CHANGED: NO
MAINNET_CHANGED: NO
```
