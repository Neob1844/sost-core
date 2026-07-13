# V15 — Final Decentralization Fork (SPEC, for review)

**Status:** DRAFT — awaiting founder approval before any consensus code is written.
**Activation height:** `V15_HEIGHT = 20000` (repurposed from the deprecated PoPC-V15 activation).
**Build flags (mandatory):** `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`
**One-line intent:** At block 20000 SOST becomes a fully autonomous PoW coin — the Gold-Vault and PoPC emission shares are redirected to the DTD distribution, and no protocol feature requires a founder, custodian, treasury or operator ever again.

This is the **final** consensus change to SOST's emission model.

---

## 0. What does NOT change

- Subsidy schedule (`R0_STOCKS`, epoch geometric decay) — untouched.
- **Miner reward stays 50%** of every block (subsidy + fees). Miner economics are identical before and after V15.
- Difficulty (cASERT V6/V7) — untouched.
- Atomic Swap (V14.5 / V14.7, heights 16000 / 17000) — untouched; remains founder-testing / ON HOLD, not part of this fork.
- DTD lottery **cadence** (1-of-3 blocks), RNG/winner-selection, cooldown, and the V13 dominance gate — all kept.
- All coinbase outputs, UTXOs and locked balances created **before** block 20000 — untouched. The gold already accumulated in the Gold Vault address stays locked exactly as it is today (it was never spendable). Only **future** emission is redirected.

---

## 1. Emission split — the "50% → DTD" change

### Current model (height < 20000)
| Block type | Coinbase outputs |
|---|---|
| Non-lottery (`height % 3 != 0`) | miner 50% · **gold_vault 25%** · **popc_pool 25%** (3 outputs) |
| Lottery, eligible non-empty (`height % 3 == 0`) | miner 50% · `OUT_COINBASE_LOTTERY` = 50% + pending. gold/popc OMITTED |
| Lottery, eligible empty | miner 50% only. `pending += 50%`. gold/popc OMITTED |

### New model (height ≥ 20000)
**Gold Vault and PoPC pool outputs are eliminated on ALL blocks.** Every block is **50% miner / 50% DTD**. The DTD half is routed through the existing `pending_lottery_amount` accumulator:

| Block type | Coinbase outputs | State |
|---|---|---|
| **Non-payout** (`height % 3 != 0`) | miner = `total − total/2` (1 output) | `pending += total/2` |
| **Payout, eligible non-empty** (`height % 3 == 0`) | miner = `total − total/2` · `OUT_COINBASE_LOTTERY` = `total/2 + pending` (2 outputs) | `pending = 0` |
| **Payout, eligible empty** | miner only (1 output) | `pending += total/2` |

`total = subsidy + fees`. `total/2` is floor; the odd stock goes to the miner (same rounding direction as today's `phase2_coinbase_split`).

### Net effect over any 3-block window
- Miner: 50% of all 3 blocks (each miner keeps their own block's 50%).
- DTD winner (paid on the payout block): the accumulated 50% of all 3 blocks.
- **Result: 50% of all emission → miners, 50% → DTD winners. 0% → Gold Vault, 0% → PoPC.**

### ⚠️ Important framing note (lumping)
The economics are exactly "2 SOST miner / 2 SOST DTD per 4-SOST block" **on average**, but the DTD half is **not streamed** — it accumulates for 2 blocks and is paid as **one lump every 3rd block** (~3× a per-block half ≈ 1.5× a full block reward per payout). This is deliberate: it reuses the existing lottery machinery untouched and keeps DTD a real lottery (lumpy jackpots). Paying every block instead would change the cadence/RNG and enlarge the consensus surface — **not** recommended.

---

## 2. DTD eligibility — new "recent active miner" rule

### Current rule (`compute_lottery_eligibility_set`, C7.1)
1. Address won ≥1 block **ever** (`[0, h-1]`).
2. Address did **not** win a block in `[h − exclusion_window, h−1]` (cooldown; `exclusion_window = 6` post-V13).
3. (at caller) V13 dominance gate applied.
4. Winner chosen **uniform per address** (not weighted by hashrate).

### New rule (height ≥ 20000)
- **Rule 1 REPLACED** — sliding recency window:
  > An address is a candidate **iff it won ≥1 block in `[h − DTD_RECENT_MINER_WINDOW, h−1]`**.
  - `DTD_RECENT_MINER_WINDOW = 2016` blocks (~14 days at 10-min target).
  - This is a **sliding** window recomputed at every height — NOT fixed segments (fixed segments would empty the eligible set at each boundary; the sliding window has no sawtooth).
  - **Kills dormant addresses:** an address that mined once long ago is no longer eligible; only recently-active miners participate.
- **Rule 2 KEPT** unchanged — recent-winner cooldown (`exclusion_window = 6`).
- **Rule 3 KEPT** unchanged — V13 dominance gate.
- **Rule 4 KEPT** unchanged — uniform per address. *(This is the real equalizer: a 90% miner and a 0.1% miner, if both eligible, each get one vote.)*

### Activation-boundary behaviour (no cliff)
At `h = 20000`, the window is `[17984, 19999]` — it reaches **below** the fork height and counts pre-fork blocks. So any miner active in the ~14 days before the fork is eligible **immediately** at 20000. There is no empty-eligibility cliff at activation.

### Known residual weakness (honest)
Uniform-per-address is sybil-able: a large miner could split mining across many addresses to hold many votes. Mitigations retained: the **dominance gate** + the **2016-block recency requirement** (each sybil address must keep mining to stay eligible, costing block slots). This is inherent to any fair-distribution PoW lottery and is **not made worse** by this fork; the recency rule marginally raises the sybil cost.

---

## 3. Features turned OFF permanently (from the consensus audit)

To guarantee the deprecated automation never auto-activates, set the following to the "never" sentinel and ship them in the V15 binary:

| Constant | File | Current | Set to |
|---|---|---|---|
| `POPC_V15_ACTIVATION_HEIGHT` | `include/sost/popc_v15.h` | `V15_HEIGHT` (20000) | `INT64_MAX` |
| `POPC_SINGLE_MODEL_HEIGHT` | `include/sost/params.h` | `V15_HEIGHT` (20000) | `INT64_MAX` |
| `DTD_POPC_GATE_CONSENSUS_ACTIVE` | `include/sost/params.h` | `true` | `false` |
| `DTD_POPC_ELIGIBILITY_HEIGHT` | `include/sost/params.h` | 25000 | `INT64_MAX` |
| `POPC_GOLD_BOOST_HEIGHT` | `include/sost/params.h` | `INT64_MAX` | (leave) |
| `GV_G4/G5/SLICE1_ACTIVATION_HEIGHT` | `gv_g4.h/gv_g5.h/gold_vault_slice1.h` | `INT64_MAX` | (leave) |

`V15_HEIGHT` stays `20000` but its **meaning** changes: from "activate PoPC" to "activate this final-decentralization fork".

The Gold-Vault and PoPC-pool **addresses** stay defined (for historical UTXO validity of pre-20000 coinbases); they simply receive **no new emission** from 20000 onward.

---

## 4. Reorg / undo (the one real state-care point)

`pending_lottery_amount` already has undo machinery. The **new** path — accumulating `total/2` on *non-payout* blocks ≥20000 — must write undo data (`pending_before`) on connect and restore it on disconnect, exactly like the existing UPDATE/PAYOUT paths. Disconnecting across the 20000 boundary must restore pre-fork behaviour with no off-by-one.

---

## 5. Consensus validation (CB rules) to add for height ≥ 20000

The block validator must, for `height ≥ 20000`:
1. **Reject** any coinbase containing a `OUT_COINBASE_GOLD` or `OUT_COINBASE_POPC` output.
2. **Non-payout block** (`height%3 != 0`): require exactly **1** output (`OUT_COINBASE_MINER = total − total/2`); require `pending_after = pending_before + total/2`.
3. **Payout block, non-empty eligibility**: require **2** outputs (miner + `OUT_COINBASE_LOTTERY = total/2 + pending_before`); require `pending_after = 0`; winner index = `select_lottery_winner_index(...)` over the new eligibility set.
4. **Payout block, empty eligibility**: require **1** output (miner); `pending_after = pending_before + total/2`.
5. Eligibility set computed with the **sliding 2016 window** (Rule 1 new), cooldown (Rule 2), dominance gate (Rule 3), uniform selection (Rule 4).

Both miner and validator MUST go through the single shared helpers (as today). Below 20000, all current V14.x rules apply unchanged.

---

## 6. Test surface (must pass before flag-day)

- Coinbase shape ≥20000: reject gold/popc outputs; 1-output non-payout; 2-output payout; miner amount exact.
- Accumulation: `pending` grows by `total/2` on every non-payout block; on empty-eligibility payout too.
- Payout: winner receives `total/2 + pending`; `pending` resets to 0.
- Eligibility: sliding-2016 includes a miner active at `h−2016`, excludes one whose last block was at `h−2017`; dormant address excluded; cooldown + dominance gate still bite.
- Activation boundary: 19999 old rules, 20000 new rules, window counts pre-fork blocks (no cliff), no off-by-one.
- Reorg: disconnect/reconnect payout and non-payout blocks across 20000; `pending` restored bit-exact.
- PoPC/GV: confirm `popc_v15_active_at()` and `popc_eligibility_enforced()` are false for all heights after the sentinel flips.

---

## 7. Rollout — coordinated flag-day (same playbook as V14.7)

1. Founder approves this spec (gate — nothing is coded before this).
2. Implement + full test pass (§6), built with the mandatory flags.
3. Publish the release + the two community notices (BBCode / Telegram), with the concrete height (20000) and the binary.
4. **Coordinate the dominant miner** (~90% hashrate) to run the V15 binary **before block 20000**. As a hard fork at 20000, non-upgraded nodes diverge at that height — identical process to V14.5 / V14.7.
5. At 20000 the fork activates; DTD begins receiving the full 50%.

**Timeline:** tip is **17168**; **2832 blocks (~2–3 weeks)** to 20000. The Atomic-Swap founder self-swap test fits inside the 17000–20000 window and is independent of this fork.

---

## 8. Out of scope (kept as-is / historical)

- **Gold Vault & PoPC** remain in the code and public history as SOST's *initial design idea* — **not deleted**, just no longer receiving emission or activating.
- **Atomic Swap** — separate technical layer, founder-testing / ON HOLD, not marketed as a public DEX.
- **GeaSpirit** — external ecosystem initiative; SOST consensus does not depend on it.
- **Governance / voting** — deferred; a fully autonomous protocol needs no on-chain treasury governance.
