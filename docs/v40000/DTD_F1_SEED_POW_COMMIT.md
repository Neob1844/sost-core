# DTD-F1: DTD and Jackpot seeds from the PoW commit (V17, block #40,000)

Status: **consensus rule of the V17 package, activates at `V17_HEIGHT`** (mainnet 40,000, devnet 60,
testnet unscheduled). No new activation height. Below `V17_HEIGHT` every draw is computed exactly
as before.

## 1. Rule

For a draw at height `h`, let `W(h)` be the blocks `h-16 … h-1` of the active chain, in ascending
height order.

| Draw | `h < V17_HEIGHT` (unchanged) | `h >= V17_HEIGHT` (DTD-F1) |
|---|---|---|
| Normal DTD | `sha256("SOST_LOTTERY_V11" ‖ block_id[W] ‖ u64le(h))` | `sha256("SOST_DTD_V17" ‖ commit[W] ‖ u64le(h))` |
| Jackpot V2 | `sha256("SOST_HIST_JACKPOT" ‖ block_id[W] ‖ u64le(h))` | `sha256("SOST_HIST_JACKPOT_V17" ‖ commit[W] ‖ u64le(h))` |

`commit` is the ConvergenceX PoW commit of the block: the 32-byte value on which the PoW target
inequality is checked (`StoredBlock::commit`, field `commit` of the block JSON and of `getblock`).

Everything else is unchanged: the eligibility sets, cooldown and its V16 retry, anti-dominance,
recency, SbPoW gate, the Jackpot V2 candidate rules and linear weight, the canonical raw-pkh order,
the reductions `u64le(seed[0..8]) % E` (DTD) and `% total_weight` with the cumulative walk
(Jackpot), amounts, cadence, base, cap and rollover.

The rule is selected by the height of the draw only. In a reorg every block is validated with the
rule of its own height.

## 2. Why

`block_id = sha256(full_header ‖ "ID" ‖ commit)` and the full v2 header contains the 64-byte
BIP-340 `miner_signature`, which the PoW does not cover. Any BIP-340 signer can produce unlimited
valid signatures over the same message (`aux_rand`), so the miner of `h-1` could re-sign one PoW
solution without limit and publish the variant whose `block_id` made its own address win at `h`
(DTD) or at a jackpot height (Jackpot V2). See `DTD_SECURITY_AUDIT.md` §3 A1 (CRITICAL).

## 3. Preimages (code references)

At `fix/v17-final-findings` 1ca77eb1 (before this change):

* **CURRENT_DTD_SEED_INPUT**: `src/lottery.cpp:323-360` `select_lottery_winner_index_from_history`:
  `LOTTERY_RNG_DOMAIN` (`include/sost/lottery.h:93`, `"SOST_LOTTERY_V11"`) ‖ `b.block_hash` for
  every block in `[h-16, h-1]` ascending (`lottery.cpp:352`) ‖ `u64le(h)` (`:354`). The node fills
  `block_hash = b.block_id` in every history builder (`src/sost-node.cpp:1978, 2217, 2418, 2451,
  2524, 6238, 6300, 6355, 8055`).
* **CURRENT_JACKPOT_SEED_INPUT**: `src/jackpot_v2.cpp:111-121` `jv2_seed`:
  `"SOST_HIST_JACKPOT"` (`include/sost/jackpot_v2.h:50`) ‖ entropy ‖ `u64le(h)`, with entropy =
  `v.block_hash` of `[h-16, h-1]` (`src/sost-node.cpp:6156-6160`, `compute_v2_jackpot_winner`).
* **BLOCK_ID_PREIMAGE**: `src/pow/convergencex.cpp:268-272` `compute_block_id` =
  `sha256(full_header ‖ "ID" ‖ commit)`; `full_header` = magic ‖ `"HDR2"` ‖ hc72(prev, merkle,
  timestamp, bits_q) ‖ checkpoints_root ‖ nonce ‖ extra_nonce ‖ version ‖ miner_pubkey ‖
  **miner_signature** (`src/sost-node.cpp:1479-1486` `build_hc72`, `:1492-1523`
  `build_full_header_bytes`); recomputed and compared at connect time (`:8315`).
* **POW_COMMIT_PREIMAGE**: `src/pow/convergencex.cpp:615-636` (verify_cx_proof phases 4-5):
  `seed = sha256(magic ‖ "SEED" ‖ hc72 ‖ block_key(prev) ‖ u32le(nonce) ‖ u32le(extra_nonce))`;
  `commit = sha256(magic ‖ "COMMIT" ‖ hc72 ‖ seed ‖ final_state ‖ x_bytes ‖ checkpoints_root ‖
  segments_root ‖ u64le(stability_metric) ‖ i8(profile_index))`. The PoW check is
  `pow_meets_target(commit, bits_q)` (`src/sost-node.cpp:8367`, always, including fast-sync),
  followed by `verify_cx_proof` (challenges derived from `commit`) outside the fast-sync trust.

After this change: `lottery_seed_input_from_history` (`src/lottery.cpp:323-359`, the one preimage
builder for the consensus path, the template, the RPCs and the tools), `lottery_seed_from_history`
(`:361-366`), `jv2_seed_v17` (`src/jackpot_v2.cpp:123-133`), `jv2_seed_at`
(`include/sost/jackpot_v2.h:218-222`), node entropy (`src/sost-node.cpp:6156-6165`), and
`LotteryMinedBlockView::pow_commit` (`include/sost/lottery.h:205`) filled from `StoredBlock::commit`
by all nine history builders.

## 4. Security properties of the new input

The V17 seeds are a function of `(h, commit[h-16], …, commit[h-1])` only. Anything that is not in a
window commit cannot reach them.

1. **Committed before the PoW is satisfied.** The commit *is* the PoW output: the miner computes the
   ConvergenceX transcript over (hc72, nonce, extra, profile) and the commit before it knows whether
   `commit <= target`. The draw at `h` is fixed the moment a valid commit for `h-1` exists.
2. **Unchanged when the miner signature changes.** `miner_signature` is not in the commit preimage;
   the SbPoW message signs the commit (`include/sost/sbpow.h:65-128`), not the reverse. Re-signing
   changes `block_id` only. Re-signing an earlier block `h-k` changes `block_id(h-k)` and therefore
   the `prev` inside `commit(h-k+1)`, which is then a new PoW for `h-k+1`; `commit(h-k)` itself and
   every already-mined later commit are untouched.
3. **Miner identity only through a new PoW.** The pubkey is not in the commit, but
   `ValidateSbPoW` forces `HASH160(miner_pubkey) == coinbase output[0] pkh`
   (`src/sbpow.cpp:516-517`); the coinbase is in the merkle root, the merkle root in hc72, hc72 in
   the commit. A different payout identity is a different commit = a new PoW. A different pubkey
   with the same pkh would need a HASH160 second preimage, and would still not change the seed
   (the pubkey is not a seed input).
4. **Nonce**: in the CX seed (`u32le(nonce)`), hence in the transcript and the commit → new PoW.
5. **Timestamp**: in hc72 → new PoW.
6. **Transactions / order / merkle**: the merkle root binds every txid and their order; in hc72 →
   new PoW. This covers NODE_BIND and HEARTBEAT inclusion.
7. **Every other field that could alter a draw**: `extra_nonce` (CX seed), `bits_q` (hc72),
   `prev` (hc72 and `block_key`), `checkpoints_root`, `segments_root`, `final_state`, `x_bytes`,
   `stability_metric`, `profile_index` (commit preimage). Header `version` is not committed but is
   forced to 2 from 7,100 and is not a seed input. The eligibility sets depend only on coinbase pkhs
   and, for the jackpot, on NODE_BIND/HEARTBEAT transactions, all inside committed merkle roots.

**Uniqueness per PoW solution.** For given (hc72, nonce, extra, profile) the transcript is
deterministic, so there is one commit per solution. A different commit for the same header fields
would have to satisfy `commit <= target` *and* the `verify_cx_proof` challenges derived from itself:
producing one is producing a PoW solution, so the number of usable commits grows only with PoW
work. A cheap way to mint target-meeting commits would be a PoW break independent of the DTD.

**Encoding malleability.** The seed hashes the 32 raw commit bytes, not text. The JSON hex is
decoded once; upper/lower-case hex gives the same bytes and the same `block_id` check. The declared
`profile_index` is range-checked and committed as one byte; `extra_nonce` is in the CX seed. None
can vary without changing the commit.

**Availability in chain state.** `commit` is a required 64-hex field of every block
(`process_block` rejects a block without it), it is bound to `block_id` by the recomputation at
connect time on every path, including fast-sync/assumevalid (only the CX transcript is skipped
there; the `block_id` recomputation and `pow_meets_target(commit)` always run), and it is stored in
`StoredBlock::commit` (`sost-node.cpp:8941`) and persisted in `chain.json` (raw block JSON).
On restart it is read back from `chain.json`. New: for blocks at heights
`>= V17_HEIGHT - 16` (the only ones a V17 draw reads), `load_chain` recomputes `block_id` from the
stored header fields and commit and fails closed (`chain_load_fail`, re-download from peers) if the
stored commit does not reproduce it (`stored_commit_binds_block_id`, `sost-node.cpp:10952`). A reorg
truncates `g_blocks` and reconnects through `process_block`, so the window is rebuilt from the new
chain. The fast-sync trust ends far below 40,000 and does not change what is stored.

**Domain separation.** Four distinct tags; with a full window the four preimages have pairwise
distinct lengths (536, 532, 537, 541 bytes), so no preimage of one rule is a preimage of another.
`"SOST_HIST_JACKPOT"` being a prefix of `"SOST_HIST_JACKPOT_V17"` is harmless for that reason, and
the two jackpot rules never apply at the same height. The DTD and Jackpot draws at a V17 jackpot
height read the same commits under different tags and are computationally independent.

## 5. Consumers

| Consumer | Change |
|---|---|
| Block validation (normal DTD winner, `process_block`) | history builder fills `pow_commit`; selection via the library (height dispatch) |
| Template / coinbase construction (`getlotterystate`, `getblocktemplate` jackpot plan, `build_live_jackpot_tx`, `validate_live_jackpot`) | same builders + `compute_v2_jackpot_winner` uses `jv2_seed_at` |
| Chain load / reindex (`validate_live_jackpot` on load) | same; plus the load-time commit binding check |
| `getlotterystate` | new field `seed_rule` (`V11_BLOCK_ID` / `V17_POW_COMMIT`) |
| `getlotteryaudit` | `seed_input_hex`/`seed_hex` from `lottery_seed_input_from_history`; new `seed_rule`, `seed_domain`, and `commit` per window block |
| `getjackpotv2audit`, `checkhistoricaljackpoteligibility`, `getjackpotstate`, `gethistoricaljackpotstatus` | winners via the shared functions; `getjackpotv2audit` adds `seed_rule`, `seed_domain` |
| `sost-miner` | computes nothing: it uses the node's `getlotterystate` / template values |
| `sost-cli` | forwards node RPCs only |
| Explorer (`website/sost-explorer.html`) | displays the node's values; explanatory text updated for the V17 rule |

## 6. Vectors and tests

* `tests/test_dtd_f1_seed.cpp` (ctest `dtd-f1-seed`): domains, preimage layout, height dispatch at
  `V17_HEIGHT-1` / `V17_HEIGHT`, pre-V17 byte identity (garbage commits leave pre-V17 seeds
  unchanged), N re-signatures of one PoW solution through `validate_sbpow_for_block`
  (`--resign 100000`), frozen mainnet vectors.
* `tests/vectors/dtd_f1_v17.json`: draw at 40,266 (a V17 jackpot height): 16 input commitments,
  candidate identities, DTD eligible set, DTD seed and winner, Jackpot weighted set, seed and winner,
  three re-signatures of block 40,265 with distinct `block_id`s and identical results, and a pre-V17
  control seed. `tests/vectors/verify_dtd_f1_vectors.py` re-derives every value independently.
* `tests/dtd_f1/history_replay.cpp`: every historical DTD draw and jackpot against the on-chain
  payouts, built against the production library and this one; outputs must be byte-identical.
* `tests/dtd_f1/field_matrix_v17.cpp`: per-field grinding matrix from real block #30,428, old rule
  vs new rule.
* `tests/dtd_f1/withholding_v17.py`: residual withholding economics after the fix.
* `tests/run_v17_dtd_f1_devnet.sh`: real devnet node + miner across activation at 60, re-signed
  blocks submitted to a real node before and after activation, reorg across 60, restarts.

## 7. Residual risk (not addressed here)

* **Withholding / PoW re-grinding.** After F1 each alternative `h-1` is a full PoW block. For the V17
  normal DTD, discarding a valid block is irrational for every hashrate share below 0.9 (break-even
  ticket share `q* = (1-α)·R_m/DTD`, `R_m/DTD = 5.33`). At jackpot heights it remains rational for a
  miner above roughly 1-6 % hashrate (prize 100-500 SOST against one forfeited block reward). Open,
  separate finding (audit F4).
* **Rotating identities / Sybil tickets and the anti-dominance gate**: unchanged by design here; see
  `docs/design/DTD_ROTATING_IDENTITIES.md`.
