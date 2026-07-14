# V15 — Historical DTD Jackpot (wind-down of Gold Vault + PoPC) — SPEC (DRAFT, for review)

**Status:** DRAFT — awaiting founder + Codex approval on the **supply model** (§2) BEFORE any consensus code is written.
**Part of:** the V15 Final Decentralization Fork (`V15_HEIGHT = 20000`). This is the LAST fork.
**Depends on:** the base V15 emission redirect (already implemented + tested).

## 0. Goal

From block 20,000 the Gold Vault and PoPC Pool stop receiving new emission (already done). This spec adds:
the **existing** Gold Vault + PoPC balances are progressively returned to active miners as a special
**Historical DTD Jackpot** — no founder control, no listing wallet, no manual distribution.

Requested parameters:
- Jackpot base: **100 SOST** per interval.
- Interval: **every 96 DTD lottery opportunities (~288 blocks, approximate)** from block 20,000.
- Only **DTD-eligible** addresses (window 2016, cooldown, anti-dominance gate, SbPoW gate, uniform selection).
- **Rollover** if no valid winner (jackpot stays pending, retried next interval).
- **Cap** per payout: **500 SOST** (excess stays pending).
- **No new emission** beyond the historical balance — jackpots must be funded by the reserve, and can
  never pay out more than the historical balance that existed at block 20,000.
- Runs until the historical balance is exhausted (~3 years at current balances).

---

## 1. The core technical problem (read first)

The ~48k–58k SOST in Gold Vault + PoPC are **real UTXOs** in the consensus UTXO set (≈26,000 outputs at
two fixed reserve addresses — wallet-locked today, consensus address-locked from V15; see TX_SPEC §6).
"Returning the reserve **without new emission**" means those
coins must actually leave the reserve. There is no way around this: to hand a winner 100 real SOST from the
reserve, 100 SOST must be removed from the reserve side of the ledger. **This is the crux — and it forces a
supply-model decision.**

---

## 2. Supply model — Option A (progressive constitutional spend). FINAL, single design.

No private keys are ever used. The reserve moves ONLY by consensus rule, never by signature — no human,
founder included, can touch it outside the protocol. Public addresses (`ADDR_GOLD_VAULT`, `ADDR_POPC_POOL`)
are already in params.h.

**Chosen and ONLY model:** the jackpot **spends** the real Gold/PoPC UTXOs via a **protocol-mandated
transaction at `txs[1]`** (full mechanics in `docs/V15_JACKPOT_TX_SPEC.md`) — FIFO oldest-first, paying the DTD
winner and returning change to the reserve. Coins move reserve → winner:
- **Total-ever-emitted is UNCHANGED — no new emission, no mint, no freeze-and-reissue.**
- The "remaining reserve" is the **live sum of the Gold/PoPC UTXOs in the set** — the UTXO set IS the ledger, so
  double-counting is structurally impossible. There is **NO authoritative `reserve_remaining` chain-state
  counter**; an explorer may derive/display one, but it is informational only.
- The **only** new persisted chain state is **`jackpot_pending`** (the rollover accumulator).

*(REJECTED, not to be reintroduced without a new decision: the freeze-and-reissue / mint variant with
`OUT_COINBASE_JACKPOT` — it raises total-emitted and needs a public "reissue" disclaimer.)*

Supply reconciliation invariant (asserted by a test):
```
circulating + reserve_UTXO_sum == total_emitted     (unchanged; jackpot payouts already counted in circulating)
Σ(all jackpot payouts over time) == R (reserve total at V15), after which the jackpot is permanently disabled
```

---

## 3. Cadence — a jackpot OPPORTUNITY every 96 DTD lottery blocks (≈288 blocks, NOT exactly)

Anchored to the DTD lottery, NOT a `height % 288` timer:
- A **jackpot opportunity** occurs on the **96th DTD lottery block since `V15_HEIGHT`**
  (`is_jackpot_trigger(lottery_opportunity_index_since_v15)`), i.e. every 96 lottery blocks ≈ **~288 blocks**
  (≈48 h) at the permanent 1-of-3 cadence — **approximate**, because block times vary. Never call it "exactly 288".
- An opportunity is **independent of whether a winner exists** (§4). The winner, when present, is the DTD winner
  already selected for that block (reuses eligibility 2016 / cooldown / anti-dominance / SbPoW / uniform
  selection — no new selection logic).

---

## 4. Payout rule (deterministic) — OPPORTUNITY vs WINNER

Only new chain state: **`jackpot_pending`** (int64 stocks) in `StoredBlock`, persisted + reorg-undone exactly
like `pending_lottery_after`. `reserve_remaining` is the live reserve-UTXO sum (NOT stored).

On a **jackpot-opportunity** block (§3):
```
reserve_remaining = sum(reserve UTXOs at parent tip)
result = compute_jackpot(jackpot_pending_before, reserve_remaining, has_eligible_winner)   // pure, already tested

if has_eligible_winner AND result.payout > 0:
    the block MUST contain the protocol-mandated jackpot tx at txs[1], byte-exact (V15_JACKPOT_TX_SPEC.md)
    jackpot_pending = result.pending_after
else:                       # opportunity but NO eligible winner (empty set), OR reserve exhausted
    NO jackpot tx may appear
    jackpot_pending = result.pending_after     # += base, capped at reserve (no coins move)
```
On any **non-opportunity** block: no jackpot tx is valid; `jackpot_pending` carries forward unchanged.
Below `V15_HEIGHT`: no jackpot state, no jackpot tx (byte-identical to today).

Consensus invariants (from `compute_jackpot`, already tested): payout ≤ cap, payout ≤ reserve_remaining,
payout + pending_after ≤ reserve_remaining; when reserve_remaining == 0 the jackpot is disabled forever.

Constants (params.h, implemented): `HIST_JACKPOT_BASE_STOCKS = 100e8`, `HIST_JACKPOT_CAP_STOCKS = 500e8`,
`HIST_JACKPOT_DTD_INTERVAL = 96`.

---

## 5. Block shape — the jackpot is a TX, not a coinbase output

The coinbase (`txs[0]`) is **UNCHANGED** (base-V15: miner 50% + DTD lottery/accumulate). The jackpot is a
**separate protocol-mandated transaction at `txs[1]`** that SPENDS reserve UTXOs (see V15_JACKPOT_TX_SPEC.md).
There is **NO `OUT_COINBASE_JACKPOT` output type and no mint**. `txs[1]` exists only on jackpot-opportunity
blocks that have a winner; a jackpot tx anywhere else (any other block, or in mempool) ⇒ invalid.

---

## 6. Reorg / undo

`jackpot_pending` is stored per block in `StoredBlock` and read from the tip (like `pending_lottery_after`) →
disconnect restores it automatically. The reserve needs no separate storage: the jackpot tx's spent inputs +
change output are restored by the existing `DisconnectTransaction` UTXO-undo, so `reserve_remaining` (the live
UTXO sum) is restored for free.

---

## 7. Tests — 25 MANDATORY before merge

1. No jackpot before block 20,000.
2. Reserve is measured from the LIVE Gold/PoPC UTXO set (no counter seed, no snapshot, no mint,
   no freeze-reissue). The reserve at any height is simply `sum(UTXOs at ADDR_GOLD_VAULT + ADDR_POPC_POOL)`.
3. Gold/PoPC receive 0 new emission from >=20,000.
4. Future redirected 50% goes to normal DTD.
5. Historical jackpot does not interfere with normal DTD.
6. Jackpot opportunity every 96 DTD lottery blocks (~288 blocks, approximate). Exact first opportunity:
   with V15=20,000, first lottery block = 20,001, so opportunity #96 = height 20,286 (off-by-one pinned by test).
7. Jackpot base = 100 SOST.
8. No eligible winner → pending rolls forward.
9. Pending > cap → payout = 500, remainder stays pending.
10. Winner must be DTD-eligible via the 2016 rolling window.
11. Cooldown applies.
12. Anti-dominance applies.
13. SbPoW activity gate applies.
14. Uniform address selection applies.
15. Jackpot never pays more than reserve_remaining.
16. Final partial payout works if reserve_remaining < 100 SOST.
17. Jackpot disables permanently when reserve_remaining == 0.
18. Reorg/undo before 20,000.
19. Reorg/undo at 20,000.
20. Reorg/undo after jackpot payout.
21. Reorg/undo after no-winner rollover.
22. Supply reconciliation: circulating + locked + jackpot_paid + reserve_remaining must reconcile (see §2).
23. Old Gold/PoPC UTXOs cannot be spent normally (constitutional lock intact).
24. No duplicate payout in the same jackpot-opportunity window (96 DTD lottery blocks, ~288).
25. Explorer/RPC reports reserve_remaining, jackpot_pending, last_jackpot_height, next_jackpot_height, total_paid, liquidation_percent.

---

## 8. Explorer + cards (must be updated)

1. **Gold Vault card** → label "Historical Gold Reserve"; status **RETIRED / WINDING DOWN**; show historical
   balance / remaining / paid-via-jackpot.
2. **PoPC Pool card** → label "Historical PoPC Pool"; status **RETIRED / WINDING DOWN**.
3. **New card — V15 Historical DTD Jackpot**: remaining reserve · pending jackpot · next jackpot block · last
   payout · total paid · estimated duration · rules (100 SOST / every 96 DTD lottery opportunities ~288 blocks / cap 500 / DTD-eligible only).
4. **DTD card** → show normal DTD and the historical jackpot **separately**; never mix normal-DTD-distributed
   with jackpot-paid unless clearly labeled.
5. **Warning line**: "Historical jackpot redistributes retired Gold/PoPC balances. It is not new emission."
6. New RPC `gethistoricaljackpot` (reserve_remaining, jackpot_pending, last_jackpot_height, next_jackpot_height,
   total_paid, liquidation_percent) · version bump + auto-reload.

---

## 9. Decisions — CLOSED

- **Supply model: FINAL = Option A, progressive constitutional spend** (real UTXO spend, supply-neutral).
  **No mint. No freeze-and-reissue. No `OUT_COINBASE_JACKPOT`. No Option B without a NEW explicit decision.**
- Cap = **500 SOST** — confirmed.
- Cadence = hung off the DTD lottery: **every 96 DTD lottery opportunities (~288 blocks, approximate)** —
  confirmed. NOT a `height % 288` timer.
- Public-notice framing (settled): *"The historical Gold Vault and PoPC balances are not kept as a treasury.
  They are progressively redistributed to active miners through a protocol-level Historical DTD Jackpot. This
  is not new emission."*
