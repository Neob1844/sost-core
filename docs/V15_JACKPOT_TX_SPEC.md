# V15 Historical DTD Jackpot — Protocol-Mandated Jackpot Tx (DESIGN, for Codex review)

**Status:** DESIGN ONLY. No consensus spend code written. Awaiting CTO/Codex approval of THIS approach
before the constitutional-spend path is implemented. Pure amount/cadence core is already implemented +
tested (23/23) — see `include/sost/jackpot.h`, `tests/test_v15_jackpot.cpp`.

**Model:** Option A — progressive constitutional **spend** (supply-neutral, no mint, no freeze).

---

## 0. The one dangerous idea, stated plainly

The reserve (Gold Vault + PoPC) coins are **real UTXOs**. NOTE (see §6): **before V15 they are NOT locked by a
consensus address rule** — only the wallet refuses to spend them (and the addresses are presumed keyless).
**From V15 this spec ADDS the consensus address-lock**, with the single exception of the exact jackpot tx.
The jackpot must move them to miners **without a signature**. We do NOT introduce a generic
"these inputs skip signature" rule (that class of change causes reserve-theft / inflation / split bugs).
Instead: the **only** tx allowed to touch reserve UTXOs is one whose **entire content is computed by
consensus itself**, and every node requires the block's jackpot tx to be **byte-for-byte identical** to
that computed tx. There is no discretion, so there is no attack surface for a malicious miner.

---

## 1. Is it a coinbase output or a normal tx? → a normal tx with constitutional inputs

For true supply-neutrality (no new emission), the jackpot must **spend** reserve UTXOs, not mint. Minting a
coinbase output would increase total-emitted. Therefore:

- The jackpot is a **dedicated protocol tx** placed at a **fixed block position `txs[1]`** (right after the
  coinbase `txs[0]`), present **only** on jackpot blocks.
- Its **inputs** are reserve UTXOs; its **outputs** are the winner payout + change back to the reserve.
- **The earlier `OUT_COINBASE_JACKPOT = 0x05` (mint) idea is DROPPED for Option A.** No new coinbase output
  type; the winner/change outputs use the normal output type. The coinbase (`txs[0]`) is UNCHANGED (miner 50% +
  the base-V15 DTD lottery output).

## 2. Cadence — a jackpot OPPORTUNITY (opportunity ≠ winner)

A **jackpot opportunity** occurs on a block iff:
- it is a base-V15 DTD **lottery block** (`height % 3 == 0`) with `height >= V15_HEIGHT`, AND
- it is the `HIST_JACKPOT_DTD_INTERVAL`-th (96th) **lottery block** since `V15_HEIGHT`
  (`is_jackpot_trigger(lottery_opportunity_index_since_v15)`).

An opportunity is **independent of whether a winner exists**, and recurs every 96 lottery blocks ≈ **~288
blocks** (**approximate** — block times vary; never "exactly 288"). On an opportunity block:

- **Winner present** (non-empty eligible set) AND `compute_jackpot().payout > 0` ⇒ the block **MUST** carry the
  protocol-mandated jackpot tx at `txs[1]`, byte-exact.
  **HARD INVARIANT — the jackpot winner IS the DTD winner of that block, nothing else.** It therefore passes
  through the **identical DTD eligibility rules** with zero new selection logic: the sliding **2016** recency
  window, the **recent-winner cooldown**, the **anti-dominance gate**, the **SbPoW activity gate**, and
  **uniform selection among eligible addresses**. There is NO separate jackpot eligibility path; if an address
  is not a valid DTD winner for that block, it cannot receive the jackpot.
- **No winner** (empty eligible set) OR reserve exhausted ⇒ **no jackpot tx may appear**; `jackpot_pending`
  grows by the base (capped at the reserve). **No coins move.**

On any **non-opportunity** block, a jackpot tx is invalid. In **mempool/relay** a jackpot tx is *always* invalid
(§8b) — it exists only as `txs[1]` inside a block.

## 3. FIFO selection (deterministic, bit-identical on every node)

- The reserve pool = all UTXOs at `ADDR_GOLD_VAULT` and `ADDR_POPC_POOL` in the UTXO set at the parent tip.
- Ordering key (total order, stable across x86/ARM): **(creation_height ASC, txid ASC (lex on 32 bytes),
  vout ASC)**. Gold and PoPC are one combined pool under this key — the oldest coins drain first regardless of
  which compartment they came from.
- Select oldest-first, accumulating value, until `sum(selected) >= payout`. The selected set (in FIFO order)
  are the tx inputs.
- `reserve_remaining` = live `sum(all reserve UTXOs)` (no separate counter → no double-count possible; the
  UTXO set is the ledger).

## 4. The exact tx (fully determined)

```
inputs  = FIFO-selected reserve UTXOs, in FIFO order
out[0]  = { pkh = DTD_winner_pkh, amount = payout }            // payout from compute_jackpot()
out[1]  = { pkh = ADDR_GOLD_VAULT_pkh, amount = sum(inputs) - payout }   // change → reserve
          (omitted iff sum(inputs) == payout exactly)

**CANONICAL CHANGE ADDRESS:** *All* jackpot change returns to **`ADDR_GOLD_VAULT`** as the single canonical
reserve-change address — even when some/all spent inputs came from `ADDR_POPC_POOL`. Both compartments are one
FIFO pool draining oldest-first; the remaining reserve consolidates into Gold Vault over time. This is simpler
and safer (one change sink), MUST be tested, and the explorer must show it so PoPC winding down toward the Gold
Vault address does not look anomalous.
no signatures; version/locktime fixed to constants
```
`payout` and the new `jackpot_pending` come from the already-tested pure `compute_jackpot(pending_before,
reserve_remaining, has_winner)` (base 100, cap 500, rollover, ≤ reserve). Value conservation:
`sum(inputs) == out[0] + out[1]` (no mint, no burn) ⇒ **no inflation, by construction**.

## 5. Byte-exact validation (the safety core)

On connect, every validator **independently recomputes** the expected jackpot tx from its own chain state
(FIFO selection + winner + `compute_jackpot`) and requires:
```
serialize(block.txs[1]) == serialize(expected_jackpot_tx)     // byte-for-byte
```
Any deviation (different inputs, order, amounts, winner, change, extra/missing tx) ⇒ **REJECT block**. The
miner has zero freedom; the tx is dictated, not proposed.

## 6. Reserve lock — TODAY it is only wallet-side; V15 ADDS a real consensus lock

**Finding (must be stated):** the reserve is **NOT** consensus-locked today. `wallet.cpp:367` ("Never spend
constitutional UTXOs") is only a wallet coin-selection rule, and `IsSpendableOutputType` treats the coinbase
GOLD/POPC output types as spendable. The reserve is safe today only because no key is used — not because
consensus forbids spending it.

**The V15 jackpot fork adds a NEW, ADDRESS-based consensus rule** (from `V15_HEIGHT`):

> Any tx input that spends a UTXO whose pubkey-hash is `ADDR_GOLD_VAULT` or `ADDR_POPC_POOL` is **INVALID**,
> **EXCEPT** when it is an input of the protocol-mandated jackpot tx at `txs[1]` on a valid jackpot-opportunity
> block, and that tx equals the computed tx byte-for-byte.

- **Address-based, not output-type-based** — so it covers BOTH the original GOLD/POPC UTXOs **and the change
  UTXO** (§4, paid back to `ADDR_GOLD_VAULT`, therefore locked by the same rule). This resolves the "change must
  stay constitutionally locked" concern.
- Bonus: this **hardens a latent hole** — the reserve was consensus-spendable if ever keyed; after V15 it is
  spendable only by the one protocol tx.
- **Test (correction 4):** a normal signed tx spending any reserve-address UTXO — including a jackpot change
  UTXO — is REJECTED at consensus. (Criteria 3 & 8.)

## 7. Undo / reorg (reuses existing machinery)

- The jackpot tx is an ordinary tx to the UTXO layer: `ConnectTransaction` spends the reserve inputs and adds
  the winner+change outputs, appending spent UTXOs to `BlockUndo`; `DisconnectTransaction` restores them.
  This is **existing, tested infrastructure** (utxo_set.h) — no new UTXO-undo code.
- New per-block state `jackpot_pending` is stored in `StoredBlock` and read from the tip (identical pattern to
  `pending_lottery_after`) → disconnect restores it automatically. `reserve_remaining` needs no storage (it is
  the live reserve UTXO sum, restored for free when the UTXOs are restored).
- Reorg across `V15_HEIGHT`, across a jackpot block, and across a no-winner rollover all restore bit-exact.

## 8. No double-pay

- One jackpot tx per jackpot block, none elsewhere (§2, §5).
- Cadence is deterministic (`is_jackpot_trigger`); `jackpot_pending` tracks rollover; a replayed/duplicated
  jackpot tx fails the byte-exact check.

## 8b. Mempool / relay — the jackpot tx is NEVER valid outside a block (correction 5)

The jackpot tx is a **block-only, position-fixed (`txs[1]`), byte-exact** object. It is therefore **rejected by
mempool/relay unconditionally**: it references reserve UTXOs (forbidden to normal txs by §6), it carries no
signature, and its validity depends on block context (opportunity height, the block's DTD winner). Nodes MUST
NOT accept, store, or relay a jackpot tx as a standalone/mempool transaction; it is validated only during block
connection. (This prevents any attempt to smuggle a reserve-spending tx through the mempool.)

## 9. Interaction with the normal coinbase & normal DTD

- `txs[0]` coinbase: **unchanged** (miner 50% + DTD lottery/accumulate exactly as base V15).
- `txs[1]` jackpot: separate, additive, only on jackpot blocks; funded from the reserve, never from subsidy.
- The regular DTD distribution and the historical jackpot are **never mixed** — different sources
  (subsidy-redirect vs reserve UTXOs), reported separately in the explorer.

## 10. Supply reconciliation (Option A)

```
total_emitted            = unchanged (jackpot is a spend, not a mint)
circulating              += payout each jackpot
reserve_remaining(UTXOs) -= payout each jackpot
Σ(all jackpot payouts over time) == R (the reserve total at V15), then jackpot disables forever
```

---

## 11. Meets the 8 approval criteria

| # | Criterion | How |
|---|---|---|
| 1 | Deterministic | tx fully computed from chain state (§3–§4) |
| 2 | Reconstructible by any node | independent recompute + byte-exact match (§5) |
| 3 | Spends only Gold/PoPC UTXOs | FIFO over reserve addresses only (§3) |
| 4 | Pays only DTD-eligible winner | reuses the DTD winner (§2) |
| 5 | Change only to reserve | out[1] → ADDR_GOLD_VAULT (§4) |
| 6 | Full undo | existing tx undo + `jackpot_pending` from tip (§7) |
| 7 | Fails if any byte differs | byte-exact serialize compare (§5) |
| 8 | No normal-tx path to spend reserve | constitutional lock kept + single-tx exception (§6) |

## 12. What is NOT yet written (needs approval before coding)

- FIFO selection over the UTXO set + the deterministic ordering key.
- The `expected_jackpot_tx` builder (shared by miner + validator).
- The block-validation hook (position `txs[1]`, presence rule, byte-exact compare, reserve-input guard).
- Miner construction of `txs[1]`.
- `jackpot_pending` in `StoredBlock` + serialization + undo.
- The remaining ~13 integration/UTXO/reorg tests (spec §7 of the parent doc).

**Nothing above is implemented.** Only the pure `compute_jackpot` / `is_jackpot_trigger` core exists.
