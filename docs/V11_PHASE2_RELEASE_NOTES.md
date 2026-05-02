# V11 Phase 2 — Release Notes

## Activation
Phase 2 activates at block 10,000.
At ~10 min target / block, that's ~3 weeks from current chain tip
(~6931 as of this commit).

## Why 10,000 and not 7,000
- Phase 1 (cASERT cascade + state-dependent dataset) activates at 7,000.
- Phase 2 also at 7,000 would mix two hard forks at the same height.
- 10,000 gives ~3,000 blocks of margin for miners to update.
- C9 Monte Carlo + accounting + reorg verification all PASS.

## What changes at block 10,000
- SbPoW (signature-bound proof-of-work) becomes mandatory:
  the block header must include miner_pubkey + miner_signature
  (BIP-340 Schnorr) over the PoW commitment + height. Miners now
  need a wallet-backed mining identity, not just a payout address.
- Lottery becomes active. Triggered blocks redirect the entire
  protocol-side allocation (Gold 25 % + PoPC 25 %, together 50 %
  of the block reward) to one eligible miner. The PoW miner's
  50 % share is never touched.
- Coinbase shape changes on triggered blocks (variable output
  count: 3 / 1 / 2 outputs for non-triggered / UPDATE / PAYOUT).
- Lottery frequency: 2 of every 3 blocks for the first 5,000
  blocks (10,000-14,999), then 1 of every 3 blocks permanently
  (15,000+).
- Eligibility: any address that has won >= 1 block since genesis
  AND did NOT win any of the previous 5 blocks (cooldown).

## What does NOT change
- Phase 1 rules (block 7,000) untouched.
- Total emission preserved per block (accounting invariant
  cumulatively holds: outputs_sum + ending_pending == n * subsidy).
- PoW miner always receives 50 % of (subsidy + fees).
- Constitutional addresses (Gold Vault, PoPC Pool) unchanged —
  they just receive 0 on triggered blocks at heights >= 10,000.

## Caveat
The lottery is NOT Sybil-proof. With sybils on the order of the
honest miner count it can be defeated. Documented honestly in
docs/V11_PHASE2_MONTE_CARLO.md. A future redesign may address this.

## Miner update path
Production miners MUST update before block 10,000. Old binaries:
- pre-Phase-2 miner produces 50 / 25 / 25 coinbase on triggered
  blocks (2 of 3 in the high-freq window) → validator rejects
  with CB11_LOTTERY_SHAPE
- consequence: old miners stop producing valid blocks once
  the chain reaches 10,000

Update commands:
```
git pull origin v11-phase2
cd build-v11 && cmake --build . --target sost-node sost-miner
sudo systemctl restart sost-node
sudo systemctl restart sost-miner
```
(Adjust paths to match the local deployment.)

## Operational notes for the miner production loop

### C11 — production miner wiring (DONE, activation height unchanged)
C11 wires the miner production loop to the new node RPC
`getlotterystate`. The mining loop now dispatches between three
coinbase builders based on the RPC's `coinbase_shape` field:

| coinbase_shape | builder                              | output count |
|----------------|--------------------------------------|--------------|
| `NORMAL`       | `build_coinbase_tx` (50/25/25)       | 3 (MINER+GOLD+POPC) |
| `UPDATE_EMPTY` | `build_phase2_update_coinbase_tx`    | 1 (MINER only) |
| `PAYOUT`       | `build_phase2_payout_coinbase_tx`    | 2 (MINER + LOTTERY) |

If the RPC fetch fails (timeout, connection refused, missing field),
the miner aborts the block candidate and waits for the next loop
tick. This prevents an unmodified miner from emitting an invalid
coinbase due to a transient node outage.

Miner invocation:
- Pre-Phase 2 (legacy address-only):
  ```
  sost-miner --address sost1<your40hex> --rpc 127.0.0.1:18232
  ```
- Post-Phase 2 (wallet-backed SbPoW signing key required):
  ```
  sost-miner --wallet wallet.json --mining-key-label miner1 \
             --rpc 127.0.0.1:18232
  ```
- The miner refuses to start if the chain is at or past
  `V11_PHASE2_HEIGHT` and the user did NOT supply
  `--wallet` + `--mining-key-label`.

### Activation height — UNCHANGED at 10,000
C11 was scoped to ALSO consider lowering `V11_PHASE2_HEIGHT` from
10,000 to 7,050 (50 blocks past the Phase 1 cASERT V11 fork at
7,000). That change is NOT in this commit. C3 wired the wallet-key
flags and the validator-side SbPoW gate, but the miner-side does
not yet emit a v2 BlockHeader (the fields `version`, miner pubkey
and miner signature are not plumbed through to `submitblock`).
Activating Phase 2 today would force every block submission to be
rejected by the validator's SbPoW gate. The activation height stays
at 10,000 until the v2-header miner emission lands.

### What unblocks moving activation to 7,050 (or any height)
- Miner emits `version: 2` in the submitblock JSON.
- Miner attaches the Schnorr signature of
  `build_sbpow_message(prev, height, commit, nonce, extra_nonce, pkh)`
  signed with the wallet key.
- Node parses `pubkey` / `signature` fields from `submitblock` and
  passes them to `ValidateSbPoW` (currently passes zero bytes).
- After those land: re-run TAREA 8 verification matrix. If green,
  drop activation to a height with >= 200 blocks of margin from the
  current live tip and >= 50 blocks past `CASERT_V11_HEIGHT`.

## Test posture
- ON build: 12 / 12 targeted Phase 2 tests PASS + 38 / 42 full ctest
- OFF build: 9 / 9 targeted PASS + 34 / 39 full ctest
- Pre-existing failures (not introduced by V11): bond-lock, popc,
  escrow, dynamic-rewards, checkpoints — see
  docs/KNOWN_TEST_FAILURES.md
