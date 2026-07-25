# V15 — Historical DTD Jackpot + Gold Vault/PoPC Emission Transition — Canonical Consensus Spec

Status: **DRAFT for implementation** · Author: CTO/consensus · Date: 2026-07-25
Scope: the consensus rules that MUST exist before V15 (mainnet block **25000**,
testnet block 300) can honestly activate. This document is the single source of
truth; the website/explorer copy is marketing and MUST be reconciled to match it
(see §11). Nothing here is implemented yet except the parameters in `params.h`
(`HIST_JACKPOT_*`) and the moved `V15_HEIGHT` — the payout/transition logic is
NOT in the validator as of this draft.

Two DISTINCT mechanisms are bundled under "V15 Core / jackpot". Keep them separate:

- **(T) Emission Transition** — at V15, stop feeding the Gold Vault (25%/block) and
  PoPC Pool (25%/block); redirect that flow to the DTD lottery. Small, surgical
  change to the coinbase split. Deterministic, low-risk.
- **(J) Historical Jackpot** — drain the reserve ALREADY accumulated in the Gold
  Vault + PoPC addresses at V15 (~52k SOST) back to DTD winners over ~3 years, on a
  288-block cadence, base 100 / cap 500 SOST, supply-neutral. This is the novel,
  higher-risk mechanism (it spends constitutional-address coins).

---

## 0. Non-negotiable invariants

1. **PRE-V15 behaviour is byte-for-byte unchanged.** Every rule here is gated at
   `height >= V15_HEIGHT` (T) or `height >= HIST_JACKPOT_FIRST_HEIGHT` (J). Historical
   replay of blocks `< V15_HEIGHT` MUST validate identically to today.
2. **No oracle, no external API, no floating point, no wallet-dependent decision,
   no centralized signer, no admin override** in any consensus path.
3. **Supply-neutral.** The jackpot moves coins that already exist; it MUST NOT change
   the total emitted supply curve. Verified by an accounting identity (§7).
4. **All arithmetic overflow-safe** (int64 stocks, checked adds as in
   `apply_lottery_block`).
5. **Deterministic across all nodes** from chain data alone.

---

## 1. Activation, first height, cadence  (params: `include/sost/params.h`)

| Item | Value | Notes |
|---|---|---|
| `V15_HEIGHT` (mainnet) | **25000** | moved from 20000 (2026-07-25; insufficient runway) |
| `V15_HEIGHT` (testnet) | 300 | see §10 open item |
| `HIST_JACKPOT_ACTIVATION_HEIGHT` | `= V15_HEIGHT` | transition + jackpot arm here |
| `HIST_JACKPOT_CADENCE_BLOCKS` | 288 | ~48h; `= 96` DTD draws (288/3) |
| `HIST_JACKPOT_FIRST_HEIGHT` (mainnet) | **25290** | `25000 + 290`; `% 3 == 0` → a DTD draw block; `>= 12100` → permanent 1-of-3 regime. Both `static_assert`ed. |
| `HIST_JACKPOT_BASE_STOCKS` | 100 SOST | base per jackpot |
| `HIST_JACKPOT_CAP_STOCKS` | 500 SOST | hard cap incl. rollover |

**Cadence rule (`is_hist_jackpot_height`, already in params):** a height `h` is a
jackpot height iff `h >= HIST_JACKPOT_FIRST_HEIGHT` and
`(h - HIST_JACKPOT_FIRST_HEIGHT) % 288 == 0`. Because 288 is a multiple of 3 and the
first height is draw-aligned (`% 3 == 0`), **every** jackpot height is a DTD draw block
in the permanent 1-of-3 regime. This is the load-bearing property that lets the
jackpot reuse the DTD winner instead of running a second selection.

---

## 2. (T) Gold Vault / PoPC emission transition

**Today** (`src/sost-node.cpp` coinbase shape decision, ~line 1429):
- IDLE block (`!is_lottery_block`): `50 / 25 / 25` → miner / `ADDR_GOLD_VAULT` / `ADDR_POPC_POOL`.
- DTD draw block: `50 miner / 50 lottery` (vault/popc outputs = 0).

**Post-V15** (`height >= V15_HEIGHT`): the two 25% slices are redirected to the DTD
lottery pending instead of to the vault/popc addresses.
- IDLE block: `50 miner / 50 → lottery pending`. `gold_vault_reward = popc_pool_reward = 0`.
  The redirected `subsidy - miner_share` accumulates into `pending_lottery_amount`
  exactly like the existing UPDATE branch does for an empty eligibility set — reuse
  that machinery; do not add a parallel accumulator.
- DTD draw block: unchanged (`50 miner / 50 lottery`), which now also flushes the
  faster-growing pending.

Result matches the published pie: **miner 50% / DTD 50% / vault·popc 0%.**

**Miner reward after V15 (explicit — common question):** the miner's DIRECT share stays
**50% of subsidy on every block, unchanged**. Only the *other* 50% changes destination:
pre-V15 it went 25/25 to Vault/PoPC on non-draw blocks (and to DTD on draw blocks);
post-V15 it goes to the DTD lottery on ALL blocks. The **Historical Jackpot (J) is NOT
part of this split** — it is a separate, additional spend of the OLD reserve paid on top
of the normal DTD payout to the same winner. So on a jackpot block the DTD winner
receives: normal DTD payout (from the 50% subsidy pending) **plus** 100–500 SOST from the
historical reserve; the block producer still gets their 50%. Net effect: 100% of new
emission flows to active miners (50% direct + 50% via DTD), and the old reserves drip to
miners via (J) until drained.

**Coinbase validation:** the validator's expected-split computation
(`src/sost-node.cpp` around the `cbr` coinbase check) must branch on `height >=
V15_HEIGHT` and reject any block that still pays `ADDR_GOLD_VAULT` / `ADDR_POPC_POOL`
after V15. New reject code (e.g. `CB_V15_VAULT_OUTPUT_FORBIDDEN`).

**Test boundary:** `V15_HEIGHT-1` (old 50/25/25), `V15_HEIGHT` (new split),
`V15_HEIGHT+1`, and several subsequent draws.

---

## 3. (J) Reserve accounting — **DECISION: MODEL A — LOCKED 2026-07-25 (founder sign-off)**

Founder approved Model A with 6 mandatory constraints, all binding on the implementation:
1. **Deterministic reserve-UTXO selection**, consensus-defined, NEVER wallet-dependent:
   oldest eligible reserve UTXO first, tie-break `(block_height, txid, vout)` ascending.
   All validating nodes derive the identical set from chain state.
2. **Change → canonical reserve destination only** (`ADDR_GOLD_VAULT` as the single change
   sink). Never to the block producer, the constructing wallet, or any other address.
3. **Supply-neutral**: a spend of existing SOST, never a mint/subsidy/synthetic credit.
   Test must prove total supply does not increase.
4. **Cap real**: max 500 SOST per event even if the reserve is far larger. Base 100,
   cap 500, cadence 288, rollover per §4.
5. **Reserve membership explicit** (see §5b below, now closed) — no vague "vault-like address".
6. **Reorg-reversible via normal UTXO connect/disconnect** — no auxiliary manual rollback;
   round-trip must leave reserve state identical (§6).

The reserve is not a counter today; it is **real UTXOs** at `ADDR_GOLD_VAULT` and
`ADDR_POPC_POOL` (balances computed by summing those UTXOs; explorer reads them the
same way). To pay the jackpot supply-neutrally we must move those exact coins. Two
models:

### Model A — spend the constitutional UTXOs (RECOMMENDED)
On a jackpot payout block, consensus authorizes the coinbase (or a protocol tx) to
spend up to `payout` worth of reserve UTXOs — **no signature**; the block's validity
is the authorization. Deterministic selection: **oldest-first** by
`(block_height, txid, vout)` ascending, across the union of both reserve addresses.
Pay `payout` to the winner; return the remainder as **change** to a single canonical
reserve address (pick `ADDR_GOLD_VAULT` as the change sink for determinism). Supply
is exactly conserved (inputs = outputs). This is the honest "real protocol spend of
those coins" the marketing already claims.
- Cost: a new constitutional-spend authorization rule + deterministic UTXO selection
  + coinbase tx structure change + reorg-safe UTXO restore.

### Model B — reserve counter + burn-and-mint
Snapshot `hist_jackpot_reserve` at V15, burn the reserve UTXOs, and mint each payout
from the counter. Simpler selection, but "burn then mint" is easy to get wrong on
supply-neutrality and reorg, and it destroys the clean UTXO audit trail.

**Recommendation: Model A.** It is the only model that is *natively* supply-neutral
and matches the published semantics. **This choice gates the payout code and needs
founder sign-off before implementation** (it is the one genuinely ambiguous economic
rule; per the brief, it is documented here rather than silently inferred).

`HIST_JACKPOT_RESERVE_AT_V15` is therefore NOT a hard-coded number — it is whatever
the vault+popc UTXO sum is at `V15_HEIGHT`, read from the UTXO set. Runway (~525 draws
at base 100) is a consequence, not an input.

---

## 4. (J) Payout amount, rollover, cap

Per jackpot block, define `avail = min(remaining_reserve, ...)`:

```
prize_target = HIST_JACKPOT_BASE_STOCKS + jackpot_rollover      // 100 SOST + carried
prize        = min(prize_target, HIST_JACKPOT_CAP_STOCKS)        // hard cap 500 SOST
payout       = min(prize, remaining_reserve)                     // never overspend reserve
```

- **Eligible winner exists** → pay `payout` to the DTD winner; `jackpot_rollover = prize_target - prize` (the portion above the cap carries; the capped-off excess is retained, never lost); if `payout < prize` because the reserve ran dry, the reserve is now 0 and the jackpot is retired.
- **No eligible winner** (empty DTD eligibility set on that block) → **nothing is paid**; `jackpot_rollover += HIST_JACKPOT_BASE_STOCKS` (still clamped so the next `prize_target` cannot exceed the cap accounting). The reserve is untouched.
- **Reserve exhausted** (`remaining_reserve == 0`) → jackpot permanently retired; jackpot blocks become ordinary DTD draws. One-way latch.

`jackpot_rollover` is new chain state (see §6), analogous to `pending_lottery_amount`.

---

## 5. (J) Winner eligibility — reuse DTD verbatim

The jackpot winner **is** the DTD lottery winner of that block. The eligibility set is
the IDENTICAL 6-filter set already computed for DTD (`select_lottery_winner_index` +
the eligibility builder in `lottery.cpp`): ① block producer, ② 2016-recency,
③ recent-winner cooldown, ④ anti-dominance (≥10% of last 288 excluded), ⑤ SbPoW
gate, ⑥ uniform per-address. **No new selection engine. No `$10`/fiat/purchase rule
(explicitly forbidden). No PoPC requirement** (retired in V15). If DTD pays no one
this block (empty set), the jackpot pays no one either (§4).

---

## 5b. (J) Reserve membership — closed definition (consensus, not marketing)

The Historical Jackpot reserve is the set of UTXOs, in the live UTXO set, that are:
- locked to **`ADDR_GOLD_VAULT`** via output type `OUT_COINBASE_GOLD`, OR
- locked to **`ADDR_POPC_POOL`** via output type `OUT_COINBASE_POPC`, OR
- the **change output of a prior jackpot spend** (locked to the canonical change sink
  `ADDR_GOLD_VAULT`; it re-enters the reserve set as an ordinary reserve UTXO).

Rules:
- **One combined pool.** Gold Vault and PoPC UTXOs are pooled into a single reserve for
  selection; ordering is global oldest-first `(block_height, txid, vout)` across both.
- **Height range.** All such UTXOs created at any height `< V15_HEIGHT` (the pre-V15
  25/25 emission) plus any jackpot-change UTXOs created at/after `HIST_JACKPOT_FIRST_HEIGHT`.
  No Vault/PoPC UTXOs are created at/after `V15_HEIGHT` (emission stopped by §2), so the
  reserve is a closed, monotonically-draining set apart from its own change outputs.
- **Enters the set** when such an output is added to the UTXO set (block connect).
- **Leaves the set** when spent by a jackpot payout (its change, if any, re-enters).
- Membership is a pure predicate over `(address, output_type)` — no address heuristics,
  no "vault-like" matching. `ADDR_GOLD_VAULT` / `ADDR_POPC_POOL` are the existing
  constitutional constants; the reserve is exactly what those two addresses hold.

## 5c. (J) Payout transaction structure — A1 DECISION (LOCKED 2026-07-25)

The reserve is real UTXOs, but the **coinbase cannot spend them**: coinbase is a
single null-input transaction (`TX_TYPE_COINBASE`). Forcing reserve inputs into
the coinbase would corrupt that structure. The tx model already supports
consensus-authorized typed transactions with custom (signature-free) spend rules
— the HTLC types (`TX_TYPE_HTLC_CLAIM/REFUND`) are the precedent (authorized by a
preimage, not an ECDSA signature). The Gold Vault governance spend (G1–G5) is the
wrong precedent — it is operator-initiated and authorized by an approval marker
(G4)/veto (G5); the jackpot is automatic, keyless and protocol-mandated.

**Decision:** the jackpot payout is a dedicated protocol transaction
**`TX_TYPE_JACKPOT`** (new tx type), included at a fixed position (**index 1**, immediately
after the coinbase) in — and only in — a jackpot block that has an eligible DTD
winner and a non-empty reserve.
- **Inputs:** EXACTLY the deterministic oldest-first reserve-UTXO selection
  (§5b/§3.1) covering the payout. No signatures; the block being a valid jackpot
  block IS the authorization (validators re-derive the identical selection).
- **Outputs:** `[0] = winner (payout, to the DTD winner pkh)`, and if the selected
  inputs exceed the payout, `[1] = change (remainder, to ADDR_GOLD_VAULT — the
  canonical reserve sink)`. No other outputs. No miner/wallet/other destination.
- **Supply-neutral:** `Σ inputs == Σ outputs` (payout + change). No mint, no fee,
  no burn. Change re-enters the reserve set (§5b).
- **Presence rule:** a jackpot block with a winner + non-empty reserve MUST contain
  exactly one `TX_TYPE_JACKPOT` at index 1; any other block MUST contain none.
  Missing/extra/misplaced/duplicate jackpot txs are rejected. If the block has no
  eligible winner (or the reserve is empty) there is NO jackpot tx — the rollover/
  retire accounting (§4) still applies via chain state.

This keeps the coinbase structure untouched, reuses the existing typed-tx
validation dispatch, and makes the jackpot spend fully auditable on-chain.

## 6. (J) Chain state, connect, disconnect/reorg

New per-block chain state (persist in `StoredBlock`, mirror the existing
`pending_lottery_after` pattern):
- `jackpot_reserve_after` — reserve remaining after this block.
- `jackpot_rollover_after` — carried prize after this block.

**Connect block** at jackpot height `h`:
1. Compute DTD result as today.
2. Read `reserve_before`, `rollover_before` from tip.
3. Apply §4 to get `payout`, `reserve_after`, `rollover_after`.
4. If Model A: validate the coinbase spent exactly the deterministic oldest-first
   reserve UTXOs totalling `payout (+ change back)`.
5. Store `jackpot_reserve_after`, `jackpot_rollover_after`.

**Non-jackpot block:** carry both values forward unchanged.

**Disconnect/reorg:** symmetric inverse (restore prior reserve/rollover from the block
being disconnected; Model A restores the spent reserve UTXOs). MUST be exact — add a
reorg-across-jackpot-boundary and reorg-across-V15-boundary test (§9). The DTD schedule
is height-anchored (`height % 3`) so a reorg cannot shift which blocks are draws/jackpots.

---

## 7. Supply-neutrality identity (test-enforced)

For any window `[a,b]`:
`Σ emitted_subsidy(h)` (unchanged curve) `==` `Σ miner_out + Σ lottery_out + Σ vault_out + Σ popc_out`
and additionally, across V15: `reserve_at_V15 == Σ jackpot_payout + remaining_reserve`.
No mint ever occurs on a jackpot block (Model A). A golden test asserts total supply is
identical with and without the jackpot spends.

---

## 8. Determinism checklist
- [ ] No `double`/`float` anywhere in the path.
- [ ] UTXO selection ordered by a total, stable key `(height, txid, vout)`.
- [ ] Winner selection uses existing `select_lottery_winner_index` (already golden-tested).
- [ ] All amounts int64 stocks, checked adds.
- [ ] Cadence/first-height `static_assert`ed (done).

---

## 9. Consensus test matrix (must all pass before mainnet arm)
pre-V15 coinbase · exact V15 block · post-V15 coinbase (T) · first jackpot (J) ·
subsequent jackpot · rollover (no-winner then winner) · 500 cap hit · reserve draining
to exactly 0 · reserve-dry retirement latch · empty eligibility · anti-dominance ·
cooldown · SbPoW gate · connect · disconnect · reorg across jackpot boundary · reorg
across V15 boundary · deterministic winner golden vector · reserve overflow/underflow
resistance · supply-neutrality identity (§7).

---

## 10. Open items — RESOLVED
1. **§3 reserve model** — ✅ **Model A, LOCKED** (founder sign-off 2026-07-25) with the 6
   constraints in §3.
2. **Testnet schedule** — ✅ resolved: adopt option (a) — a testnet-only low
   `V11_PHASE2_HEIGHT` (and window) so DTD draws exist well before testnet `V15_HEIGHT`,
   letting the full fork (V15 activation → DTD → jackpot → rollover → reorg) be exercised
   at low height. MUST NOT alter mainnet DTD historical rules. Implementation detail of
   task #6/#10; the testnet `HIST_JACKPOT_FIRST_OFFSET` is finalized there.
3. **Change-sink** — ✅ `ADDR_GOLD_VAULT` is the single canonical change sink (§5b).

## 12. BTC scope (updated 2026-07-25)
BTC atomic swap is **NOT a blocker for V15**. V15 ships with SOST↔EVM active and SOST↔BTC
labelled **TESTING / COMING SOON** until its full regtest lifecycle (CREATE→FUND→CONFIRM→
REDEEM and CREATE→FUND→TIMEOUT→REFUND) passes automated CI. Do not enable BTC merely
because V15 exists.

---

## 11. Marketing/explorer reconciliation (§17 of the brief)
The website/explorer currently say "block 20,000" and "first jackpot #20,286". After the
height move these are wrong. Update to **V15 #25,000 / first jackpot #25,290** across:
`website/*.html` (explorer card, sost-dex, homepage V15 panel), any `website/api/*.json`,
and docs. Until the payout logic ships, the explorer jackpot card MUST stay labelled
**PLANNED** and MUST NOT render fabricated payouts.
