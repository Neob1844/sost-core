# V15 consensus security audit (P7)

Adversarial review of the V15 hard-fork consensus diff (`git diff main...HEAD`) over the consensus
files: `jackpot.h`, `jackpot_block.h`, `jackpot_reserve.h`, `params.h`, `lottery.h`,
`transaction.h`, `consensus_constants.h`, `sost-node.cpp`, `sost-miner.cpp`, `tx_validation.cpp`,
`utxo_set.cpp`. Atomic-swap files were out of scope (decoupled from V15 consensus). The reviewer
traced every `ConnectBlock` caller, value-conservation enforcement, DEV gating, overflow bounds,
determinism, and reorg rollback.

## Result
**0 critical/exploitable (A) findings. 2 defense-in-depth (B) findings**, both verified NOT
reachable in the current tree. 12 defect classes checked and found clean.

## Findings and resolution

### B-1 — jackpot value-conservation had no independent backstop  → FIXED
`src/sost-node.cpp` (jackpot exemption at the per-tx ConnectBlock loop) + `src/utxo_set.cpp`.
The canonical `TX_TYPE_JACKPOT` is (correctly) exempted from `ValidateTransactionConsensus`, whose
S7 rule is the only place that enforces `sum(inputs) >= sum(outputs)`. `ConnectTransaction` checks
input existence + no-double-spend but NOT amounts. So value-conservation for the keyless reserve
spend rested solely on `validate_live_jackpot`'s byte-exact canonical reconstruction. The reviewer
**verified this is safe as wired** (all four `ConnectBlock` callers — main path, reorg restore,
reorg connect via `process_block(reorg_connect=true)`, and `load_chain` — run `validate_live_jackpot`
first). The risk was a single-gate design with misleading comments claiming the amount safety came
from `ConnectTransaction`, which could mislead a future maintainer into adding an ungated caller.

**Fix (this branch):**
- Added an INDEPENDENT value-conservation backstop for `TX_TYPE_JACKPOT` in the ConnectBlock per-tx
  loop: it looks up each input's amount in the scratch UTXO view and rejects the block if
  `sum(outputs) > sum(inputs)` (or any input is missing). The canonical jackpot redistributes the
  reserve, so `sum(in) == sum(out)` by construction — the guard is belt-and-suspenders that makes it
  impossible for ANY path (present or future) to let a jackpot MINT value.
- Corrected the two misleading comments to state accurately that jackpot value-conservation comes
  from `validate_live_jackpot` + this explicit backstop, NOT from `ConnectTransaction`.
- Re-validation (consensus change → re-run the jackpot gates): the backstop is exercised by every
  block carrying a canonical jackpot. **Definitive evidence — the payout harness PASSED** on the
  rebuilt node: block 24 carries the canonical jackpot (tx_count=2), it spends ALL 26 reserve UTXOs,
  and `EXACT accounting: reserve_before == payout + change; mint=burn=fee=0` — i.e. the canonical
  jackpot (which conserves value by construction) is ACCEPTED through the backstopped ConnectBlock,
  not false-rejected (`revb1-payout.log`). The attack harness also confirmed `honest block 24
  accepted with canonical jackpot` plus 18 mutation rejections. Architecturally the backstop sits
  BEHIND `validate_live_jackpot`, so it cannot change attack-rejection behaviour — only the
  canonical-accept path, which payout proves intact. (One attack-matrix re-run and M02 hit a machine
  RESOURCE limit, not a consensus failure — see the operational note below; the 17-case matrix was
  already 20/0 earlier this session on the same rejection path, which B-1 does not touch.)

### B-2 — failed-reorg restore `break`s mid-loop on an impossible error  → HARDENING BACKLOG
`src/sost-node.cpp` (original-chain restore loop). If restoring a previously-valid block fails
(`validate_live_jackpot` mismatch or `ConnectBlock` failure — "should never happen"), the loop
`break`s, potentially leaving the in-memory chain truncated rather than fully restored. This is a
**pre-existing pattern** (the `ConnectBlock` break predates V15; V15 added the jackpot-mismatch
break above it) and is never hit in the 49/49 failed-reorg atomicity harness.

**Decision:** NOT patched on this pre-fork branch. Changing the mainnet reorg failure mode (silent
truncation → fatal abort) 28 days before the fork trades one bad state for an availability risk on
a never-hit path; it belongs in a TESTED, height-gated post-fork hardening release (consistent with
the project's existing consensus-hardening-backlog policy). Tracked there with the suggested fix
(treat restore failure as fatal/abort-before-persist, not a silent break).

## Checked clean (verified NOT violated)
1. **Accidental pre-fork consensus change** — clean. Every V15 rule is gated on `height >= V15_HEIGHT`
   or `is_hist_jackpot_height()`. Mainnet consensus constants are byte-identical; only `V15_HEIGHT`
   (a future, not-yet-reached fork height) changed. DEV overrides isolated in `#if SOST_DEVNET_FORKS`.
2. **Ungated/wrong hardcoded heights** — clean. Jackpot heights derive from `V15_HEIGHT + offset`;
   `static_assert`s prove draw-alignment and placement. (Corroborated by the P9 boundary test.)
3. **DEV code reachable in production** — clean. `--attack-jackpot`, `--dump-block`, `--inject-tx-at1`,
   the reorg failpoint, and RPCs `devsetreorgfailpoint`/`devchainstate`/`devjackpotstate` are all
   inside `#ifdef SOST_DEVNET_FORKS` (definition AND handler registration); the RPCs additionally
   hard-fail unless `ACTIVE_PROFILE==DEV`. Confirmed `count=0` in mainnet/testnet binaries.
4. **Asserts/aborts on remote input** — clean. No assert/abort/throw in the jackpot path; validators return false.
5. **Integer overflow/underflow** — clean. BASE 1e10, CAP 5e10, rollover clamped ≤ 4e10, reserve
   supply-bounded (~4.67e14) — all far below INT64_MAX (9.2e18). Add/sub with min/clamp; negative-state guarded.
6. **Consensus non-determinism** — clean. Reserve discovery iterates the ordered `std::map` then
   `std::sort`s canonically; history from the ordered block vector; height-seeded winner selection.
   No `unordered_*`, `rand()`, or wall-clock feeding a hash/selection.
7. **Reorg/ConnectBlock state revert** — clean (except B-2's should-never-happen path). Reserve &
   rollover are DERIVED from the UTXO set + block history (no persisted counter), so UTXO rollback
   reverts them automatically.
8. **Jackpot authorization too broad** — clean in effect (now backstopped by B-1's fix). Byte-exact
   canonical reconstruction before every ConnectBlock caller; exactly one jackpot at index 1; winner
   coupled to the real coinbase; current miner excluded (no self-payout).
9. **Mempool accepting a jackpot tx** — clean. `handle_sendrawtransaction` rejects `TX_TYPE_JACKPOT` up-front (-26).
10. **Wrong emission / reserve spendable by non-canonical path** — clean. Supply-neutral reserve
    redistribution; reserve outputs locked to keyless constitutional addresses; the (T) redirect
    withholds the former Gold/PoPC half to lottery pending (not newly minted).
11. **Secrets / local paths / PII** — clean (none in the audited files).
12. **TODO/FIXME/HACK** — clean (none in the new headers or diff).

## Operational note — DEV harness re-runs must move to a second machine
While re-validating on THIS box (which runs the 13-thread mainnet miner), the kernel OOM-killer
killed several DEV SbPoW harness miners (`sost-miner`, ~4.2 GB RSS each — DEVNET SbPoW allocates
~4 GB/block). The mainnet miner survived, but it carries the same `oom_score_adj:0` and is at risk:
running DEV SbPoW harnesses concurrently with the mainnet miner can exhaust the 23 GiB RAM. This is
exactly the "do not interfere with the miner" boundary. **Policy for the remainder of validation on
this box: no concurrent DEV SbPoW harnesses.** The payout re-validation above completed BEFORE the
pressure peaked and is conclusive for B-1; any further DEV harness re-runs (full attack matrix, M02,
soak) and the long testnet SbPoW run belong on the second (non-miner) machine — see REMAINING_GATES.md.

## Net
The V15 consensus surface is sound: no exploitable finding, the one money-minting gate is now
double-guarded, and the emission/jackpot rules are strictly height-gated at 25000. The single
remaining item (B-2) is a pre-existing, never-hit robustness nit deferred to a tested post-fork
hardening release.
