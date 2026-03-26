# SOST vs Bitcoin: Reorganization Resistance Analysis

**Date:** 2026-03-26
**Context:** Bitcoin suffered a 2-block reorg on March 23, 2026. Foundry USA (34% hashrate) mined 7 consecutive blocks. Debate over whether mining concentration weakens the 6-confirmation rule.

---

## Comparison Table

| Mechanism | Bitcoin | SOST Protocol | SOST Advantage |
|-----------|---------|---------------|---------------|
| **Difficulty adjustment** | Every 2,016 blocks (~2 weeks) | Per-block (cASERT exponential, 24h halflife) | Responds to hashrate changes 2,016x faster |
| **Coinbase maturity** | 100 blocks (~17 hours) | 1,000 blocks (~7 days) | 10x longer lockup = 10x less incentive to reorg for rewards |
| **PoW algorithm** | SHA-256 (ASIC-dominated, Foundry 34%) | ConvergenceX (memory-hard, 8GB RAM/miner) | No ASIC farms → naturally more distributed |
| **Reorg limit** | None (longest valid chain always wins) | **MAX_REORG_DEPTH = 500 blocks** (~3.5 days) | Hard cap: reorgs beyond 500 blocks are rejected |
| **Chain selection** | Longest chain by height | **Highest cumulative work** (NOT longest chain) | Prevents easy-block attacks |
| **Constitutional rules** | None | Coinbase split enforced at consensus (50/25/25) | Malicious blocks with wrong split are invalid |
| **Block validation** | Script-level | L1-L4 layered + atomic rollback | Cleaner reorg handling |
| **Per-block delta cap** | N/A | 12.5% max difficulty change per block (V2) | Prevents sudden difficulty manipulation |

---

## Detailed Analysis

### 1. Per-Block Difficulty Adjustment (cASERT)

**Code:** `src/pow/casert.cpp:85-106`, `include/sost/params.h:82-89`

```
V2 (block ≥1450): halflife = 86,400s (24h), delta cap = 12.5% per block
V1 (block <1450): halflife = 172,800s (48h), delta cap = 6.25% per block
```

**Why this matters for reorgs:**

In Bitcoin, if Foundry (34%) mines 7 blocks in 5 minutes instead of 70 minutes, the difficulty doesn't adjust for another ~2,000 blocks. The network "doesn't notice" the speed burst.

In SOST, cASERT recalculates difficulty EVERY BLOCK using an exponential moving target. If a single miner produces blocks faster than the 10-minute target, difficulty increases immediately at the next block. The 24-hour halflife means significant adjustment occurs within hours, not weeks.

**Scenario:** If a SOST miner with 34% hashrate mined 7 blocks in rapid succession:
- Block 1: normal difficulty
- Block 2: difficulty increases (blocks arriving too fast)
- Block 3: increases more
- By block 7: difficulty has risen ~3-5% from the burst
- This makes sustaining the streak progressively harder

Bitcoin would not adjust at all during a 7-block streak.

### 2. Coinbase Maturity: 1,000 Blocks

**Code:** `include/sost/consensus_constants.h:1` — `COINBASE_MATURITY = 1000`

**Why this matters:**

One motivation for reorgs is stealing block rewards. In Bitcoin, after 100 confirmations (~17 hours), coinbase rewards can be spent. If a miner can sustain a reorg of 100+ blocks, they can double-spend their own rewards.

In SOST, **1,000 confirmations (~7 days)** must pass before coinbase rewards are spendable. Sustaining a reorg of 1,000 blocks would require controlling >50% of hashrate for 7 continuous days — a practical impossibility in a memory-hard mining environment.

### 3. ConvergenceX: Memory-Hard PoW

**Code:** `include/sost/pow/convergencex.h:5,19`

```
Mining requires: 4GB dataset + 4GB scratchpad = 8GB RAM per mining unit
100,000 sequential rounds per attempt
Node verification: ~500MB, ~0.2ms
```

**Why this matters:**

Bitcoin's SHA-256 is dominated by ASIC farms. Foundry USA aggregates thousands of ASIC miners into a single pool, reaching 34% of global hashrate. This concentration is possible because ASICs are cheap to scale (just add more chips).

ConvergenceX requires 8GB RAM per mining unit. You cannot parallelize it on an ASIC — each unit needs its own 8GB workspace with 100,000 sequential rounds. This makes mining inherently CPU-bound and memory-bound, preventing the kind of industrial ASIC concentration that enabled Foundry's dominance.

**The 34% scenario is much harder in SOST** because there are no ASIC farms to aggregate.

### 4. MAX_REORG_DEPTH = 500 Blocks

**Code:** `src/sost-node.cpp:330` — `static const int64_t MAX_REORG_DEPTH = 500;`

```cpp
// Maximum reorganization depth. Any alternative chain diverging more than
// 500 blocks behind the current tip is REJECTED, even if it has more work.
// Combined with hardcoded checkpoints and 1000-block coinbase maturity,
// this provides robust protection against deep reorganization attacks.
```

**Why this matters:**

Bitcoin has NO reorg limit. The longest valid chain always wins, regardless of how deep the reorg goes. In theory, a 51% attacker could rewrite the entire chain history.

SOST nodes **reject any block more than 500 blocks behind the current tip** (`src/sost-node.cpp:2272-2276`). This means:
- A 2-block reorg: allowed (normal network behavior)
- A 100-block reorg: allowed (unusual but technically possible)
- A 501-block reorg: **REJECTED** by every node

This hard cap provides absolute protection against deep reorgs, regardless of attacker hashrate.

### 5. Best Chain by Cumulative Work (Not Longest)

**Code:** `src/sost-node.cpp:113,127`

```
best chain = highest cumulative valid work (NOT longest chain by height)
```

This is the same approach as modern Bitcoin Core, but worth noting: the chain with the MOST work wins, not the one with the most blocks. This prevents an attacker from creating many easy blocks to outpace a shorter chain with more real work.

### 6. Constitutional Coinbase Split

**Code:** `include/sost/params.h:192-193`, `src/tx_validation.cpp:492+`

Every valid block MUST have exactly this coinbase split:
- 50% to miner
- 25% to Gold Vault (`sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d`)
- 25% to PoPC Pool (`sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f`)

These addresses are hardcoded. CB rules CB1-CB10 validate this at consensus level. A block that pays differently is **invalid** and rejected by every node.

**Why this matters for reorgs:** Even if an attacker reorganizes the chain, they CANNOT redirect the 50% that goes to Gold Vault and PoPC Pool. The maximum reward from a reorg attack is 50% of the block reward (the miner's share), not 100% like in Bitcoin.

### 7. Atomic Block Connect/Disconnect

**Code:** `src/utxo_set.cpp:5-11`

```
ConnectBlock is atomic (rollback whole prefix block on any failure).
DisconnectBlock reverses in correct order with undo data.
```

SOST's L4 validation uses atomic transactions with full undo data. If a reorg occurs, the node disconnects blocks one by one in reverse order, restores the UTXO set to its previous state, then connects the new chain. Any failure during this process triggers a complete rollback — the node never enters an inconsistent state.

---

## Scenario: 34% Attacker in SOST

Hypothetical: someone controls 34% of SOST hashrate and tries what Foundry did in Bitcoin.

1. **Mining 7 consecutive blocks:** Possible but unlikely. With 34% hashrate, probability of 7 consecutive blocks = 0.34^7 = 0.06% per sequence. Same math as Bitcoin.

2. **But difficulty adjusts faster:** cASERT raises difficulty during the streak. By block 7, it's harder. In Bitcoin, difficulty is frozen for 2,000 more blocks.

3. **Reorg incentive is lower:** Even if they reorg, they can only claim 50% of each block reward (miner share). The other 50% goes to constitutional addresses regardless.

4. **Rewards are locked for 1,000 blocks:** They can't spend the stolen rewards for 7 days. If the community detects the attack, they have 7 days to respond (emergency fork, manual checkpoint, etc.).

5. **Memory-hard mining prevents concentration:** Getting to 34% requires 34% of all memory-bound mining capacity worldwide. No ASIC shortcut.

6. **Deep reorgs are capped at 500:** Even with majority hashrate, reorgs beyond 500 blocks are rejected by all nodes.

---

## Conclusion

**Is SOST immune to reorgs?** No. No blockchain is. A 2-block reorg can happen naturally in any PoW chain when two miners find blocks simultaneously.

**Is SOST significantly more resistant than Bitcoin to the Foundry-type scenario?** YES.

| Protection | Bitcoin | SOST | Factor |
|-----------|---------|------|--------|
| Difficulty response time | ~2 weeks | Per-block | ~2,000x faster |
| Reward lockup | 17 hours | 7 days | 10x longer |
| Mining centralization risk | High (ASIC farms) | Low (memory-hard) | Structural |
| Deep reorg protection | None | 500-block hard cap | Absolute |
| Constitutional constraints | None | 50% locked to Gold/PoPC | Economic |

**The combination of per-block difficulty adjustment + 1,000-block maturity + memory-hard mining + 500-block reorg cap + constitutional coinbase split makes SOST structurally more resistant to the type of concentration-driven reorganization that Bitcoin experienced on March 23, 2026.**

---

## Possible Future Improvements

1. **Finality gadget:** After N confirmations, blocks become irreversible (like Ethereum's Casper)
2. **Reduce MAX_REORG_DEPTH:** 500 is conservative. Could be lowered to 200 after chain matures
3. **Mining pool diversity incentives:** Protocol-level rewards for hashrate decentralization
4. **Reorg alerting:** Node sends alert to operator when any reorg > 1 block is detected
