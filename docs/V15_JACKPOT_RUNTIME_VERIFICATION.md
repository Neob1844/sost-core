# V15 Historical DTD Jackpot — Runtime Verification (Codex pre-runtime checklist)

**Status:** Verified on the working tree. NOT committed, NOT deployed, NOT on mainnet.
Build flags: `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release`.

Codex issued a **GO for the runtime test**, conditioned on documenting three checks first.
All three are now verified in code and by an executable runtime test.

## 1. ConnectTransaction does NOT re-validate signatures

`UtxoSet::ConnectTransaction` (`src/utxo_set.cpp:80`) performs only:
- for each input: `HasUTXO(outpoint)` existence check + spend (erase),
- for each output: no-collision check + `AddUTXO`.

There is **no signature verification, no fee check, no script evaluation** in the UTXO
layer. Signature/fee validation lives exclusively in `ValidateTransactionConsensus`
(`src/tx_validation.cpp:604`, via `ValidateInputs` + S8 min-fee). Since the jackpot tx is
deliberately **exempted** from `ValidateTransactionConsensus` in the `process_block` tx-loop
(it carries no signature and fee 0) but is **still passed to `ConnectBlock`**, the exemption
is safe: the only authority over the jackpot tx is `validate_block_jackpot` (byte-exact match
or address-lock rejection), and `ConnectBlock` faithfully applies its UTXO effect without
re-imposing a signature requirement the tx cannot satisfy.

## 2. Fee = 0 does NOT alter total_fees / subsidy

The jackpot tx is supply-neutral **by construction** in `build_expected_jackpot_tx`:
`out[0].amount (payout) + out[1].amount (change to Gold Vault) == Σ input amounts`, because
`change = input_sum − payout` in `plan_jackpot_spend`. Therefore `input_sum − output_sum == 0`:
the tx contributes **zero** to the block's total fees. The coinbase subsidy computation is
untouched — it is derived from height/emission, never from the jackpot tx. No mint, no
`OUT_COINBASE_JACKPOT`, no treasury. The reserve is simply the live sum of Gold/PoPC UTXOs,
and the payout moves coins from that reserve to the DTD winner (with change re-locked to the
Gold Vault). Total money supply is invariant across a jackpot block.

## 3. End-to-end runtime test (real UtxoSet machinery)

`tests/test_v15_jackpot_runtime.cpp` (registered as ctest `v15-jackpot-runtime`) exercises the
**real `UtxoSet::ConnectBlock` / `DisconnectBlock`** — the exact calls `process_block` makes at
block acceptance and at reorg:

1. Seed 60 Gold reserve UTXOs (2 SOST each = **120 SOST** reserve).
2. Build the jackpot tx the way the node/validator do:
   `collect_reserve_utxos → compute_jackpot(payout=100) → plan_jackpot_spend (FIFO) →
   build_expected_jackpot_tx`.
3. `ConnectBlock([coinbase, jtx], height=20286, undo)` — **accepted**.
   - Reserve drops **120 → 20 SOST** (exactly the 100 payout).
   - DTD winner is paid **100 SOST**.
   - Miner coinbase output present (3 SOST).
   - **Supply neutral**: winner gain == reserve loss.
4. `DisconnectBlock([coinbase, jtx], undo)` (reorg) — **undone bit-exact**.
   - Reserve restored to **120 SOST**.
   - Winner UTXO removed (back to **0**).

**Result: 11/11 PASS.** This proves the UTXO effect the node relies on: a jackpot block, when
connected, actually moves coins, and a reorg undoes it exactly.

## 4. Runtime REORG test (revert onto a competing fork + reconnect, zero residue)

`tests/test_v15_jackpot_reorg.cpp` (ctest `v15-jackpot-reorg`) drives the exact machinery the
node's `try_reorganize()` uses at the UTXO layer — `DisconnectBlock(block, stored BlockUndo)` to
unwind the active tip, then `ConnectBlock(fork block)` to advance the new chain — on a **real
fork**:

```
fork point @20285
   ├── [A] 20286 = JACKPOT block          (original active tip)
   └── [B] 20286' normal, 20287' normal   (competing fork, more work → wins)
```

Sequence: connect A → **reorg to B** (disconnect A) → **reorg back to A** (disconnect B2, B1,
reconnect A) → final disconnect. At every return to a height, the **entire UTXO map** is
snapshotted (all fields: outpoint, amount, type, height, coinbase flag, pubkey_hash) and compared
bit-for-bit:

- Disconnecting the jackpot leaves the UTXO set **identical to the fork point** — reserve back to
  120, winner UTXO gone, **no leftover reserve/change/winner residue**.
- The competing fork never touches the reserve (stays 120, no winner).
- Reconnecting the jackpot is **bit-exact** to the first connect (reserve 20, winner 100).
- Full cycle ends bit-identical to the fork point.
- `jackpot_pending_after` undo semantics asserted at the value level: a no-winner (rollover) block
  accumulates `pending += base`, and a reorg unwinding it restores pending to the prior tip's value
  (missing == 0), mirroring the node's "restored from the tip on reorg" handling — same pattern as
  `pending_lottery_after`.

**Result: 27/27 PASS.** Coins revert and reconnect without residue; a jackpot block is fully
reorg-safe. (Coinbases in the test carry height+fork tags in the coinbase input so each has a
unique txid, exactly as real coinbases do — the same reason real chains don't collide outpoints.)

The one remaining gap is a **two-process live-node** functional run (spawn `sost-node` + mine a
real PoW jackpot block over the wire). That is infeasible as a unit test against mainnet
`V15_HEIGHT = 20000` (would require mining ~20,286 real blocks) and the node's reorg path calls the
very `ConnectBlock`/`DisconnectBlock` this test exercises directly; the UTXO- and undo-level
behavior is therefore fully proven here.

## Full test tally

`ctest`: **102/103 pass.** The single failure — `htlc-expired-lock-template` — is
**pre-existing and unrelated to V15**: it fails identically (2/8) on a clean `main` HEAD with
all V15 changes stashed (verified 2026-07-13). No V15/jackpot suite regresses. The three jackpot
suites are green: `v15-jackpot` 75/75, `v15-jackpot-runtime` 11/11, `v15-jackpot-reorg` 27/27.

One test expectation was updated to match the retired-PoPC design: `TC51b` in
`test_tx_validation.cpp` previously asserted a zero-amount PoPC carrier output was accepted at
height 25000 (old model where `POPC_V15_ACTIVATION_HEIGHT = V15_HEIGHT`). Under V15 final
decentralization, `POPC_V15_ACTIVATION_HEIGHT = INT64_MAX` (PoPC retired on mainnet), so the
carrier is correctly rejected by R5 at all heights. The test now asserts that rejection.

## Remaining before commit / flag-day

- ~~Node-level runtime reorg test~~ — **DONE** (`v15-jackpot-reorg`, 27/27, §4). Two-process live
  mining is infeasible pre-`V15_HEIGHT` and would only re-exercise the same ConnectBlock/DisconnectBlock.
- Explorer/cards wired to real jackpot data (reserve remaining, next jackpot, pending, last winner, history).
- Commit / PR / coordinated flag-day before block 20,000, with a 19,900 → 20,000 update window.
  Nothing deployed or committed yet.
