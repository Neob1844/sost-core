# V11 Phase 2 — Release Notes

## Activation
Phase 2 activates at block 7,100.
Phase 1 (cASERT cascade + state-dependent dataset) activates at
block 7,000. The 100-block deployment window between the two hard
forks (~16-17 hours at the 600-second target) gives operators time
to observe Phase 1 behaviour in production, propagate Phase 2 binaries
across the miner pool, and ANN the activation before Phase 2 fires.

## Why 7,100 and not 7,000
- Phase 1 (cASERT cascade + state-dependent dataset) activates at 7,000.
- Phase 2 also at 7,000 would mix two hard forks at the same height.
- 7,100 keeps the two forks independent and observable, with a small
  but non-trivial margin for miner updates.
- C9 Monte Carlo + accounting + reorg verification all PASS.
- cap=5 per C9 Monte Carlo (LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW).

## What changes at block 7,100
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
  blocks (7,100-12,099), then 1 of every 3 blocks permanently
  (12,100+).
- Eligibility: any address that has won >= 1 block since genesis
  AND did NOT win any of the previous 5 blocks (cooldown).

## What does NOT change
- Phase 1 rules (block 7,000) untouched.
- Total emission preserved per block (accounting invariant
  cumulatively holds: outputs_sum + ending_pending == n * subsidy).
- PoW miner always receives 50 % of (subsidy + fees).
- Full protocol-side allocation redirected on triggered blocks —
  constitutional addresses (Gold Vault, PoPC Pool) unchanged in
  rule, but receive 0 on triggered blocks at heights >= 7,100.

## Caveat
Phase 2 is NOT Sybil-proof. With sybils on the order of the
honest miner count it can be defeated. Documented honestly in
docs/V11_PHASE2_MONTE_CARLO.md. A future redesign may address this.

## Miner update path
MINERS MUST UPDATE node + miner binaries before block 7,100. Old miners
will produce invalid coinbase on triggered Phase 2 blocks
(CB11_LOTTERY_SHAPE) AND missing SbPoW signature (rejected by
ValidateSbPoW). Specifically:
- pre-Phase-2 miner produces 50 / 25 / 25 coinbase on triggered
  blocks (2 of 3 in the high-freq window) → validator rejects
  with CB11_LOTTERY_SHAPE
- pre-Phase-2 miner emits a v1 header with no miner_pubkey /
  miner_signature → ValidateSbPoW rejects with VERSION_MISMATCH
- consequence: old miners stop producing valid blocks once
  the chain reaches 7,100

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

### Activation height — FINALISED at 7,100 (C13)
C13 commits the final activation height. C10 had originally set it
to 10,000 to maximise miner update margin; C11/C12 wired the production
miner loop and the SbPoW submit transport without touching the height.
With Phase 1 (block 7,000) now visible on the live chain and the
miner update path documented + binary distribution ready, the owner
green-lit lowering `V11_PHASE2_HEIGHT` to 7,100 — 100 blocks past
`CASERT_V11_HEIGHT = 7,000`, which gives ~16-17 hours at the
600-second target between the two hard forks: enough to observe
Phase 1 behaviour, propagate binaries, and ANN.

### Pre-Phase 2 mining (legacy, address-only)
```
sost-miner --address sost1<...> --rpc 127.0.0.1:18232
```

### Post-Phase 2 mining (wallet-backed, SbPoW required)
```
sost-miner --wallet /path/to/wallet.json \
           --mining-key-label miner1 \
           --rpc 127.0.0.1:18232
```

### Update commands (unchanged)
```
git pull
cmake --build build-v11
sudo systemctl restart sost-node
sudo systemctl restart sost-miner
```

### C12 — miner SbPoW transport (RESOLVED)
C12 closes the C11 blocker. The production miner now:
- Emits `version: 2` in the submitblock JSON for every candidate
  at `height >= V11_PHASE2_HEIGHT`.
- Computes the Schnorr signature of
  `sbpow::build_sbpow_message(prev, height, commit, nonce,
   extra_nonce, miner_pubkey)` with the wallet-key privkey and
  attaches both `miner_pubkey` (66 hex / 33 bytes) and
  `miner_signature` (128 hex / 64 bytes) to the submitblock JSON.
- Aborts the candidate before mining (with the `[MINER] FATAL:
  Phase 2 active …` message) when the chain is at or past Phase 2
  and `--wallet` / `--mining-key-label` were not supplied.

The node-side parser reads `version` / `miner_pubkey` /
`miner_signature` from the submitblock JSON, validates lengths
(33 / 64 bytes) and hex-only character set, rejects malformed or
missing fields with consensus-clean error messages, and feeds the
parsed bytes into `ValidateSbPoW` (no more zero placeholders).
v2 headers contribute their `version + pubkey + signature` to the
block_id input bytes, so any tampered field changes the block_id.

### What still gates activation (post-C13)
- Live RPC sanity check at deploy time — operators with active
  miners must have wallet keys provisioned before the chain
  reaches the activation height (block 7,100).
- Operators verify both `sost-node` and `sost-miner` are rebuilt
  from the C13 head before the chain crosses 7,100. Pre-C13 miners
  produce invalid Phase 2 blocks once activation fires.

## Test posture (C13)
- ON build: 14 / 14 targeted Phase 2 tests PASS (incl. C12
  `phase2-sbpow-submit` integration test) + boundary tests
  rebuilt for V11_PHASE2_HEIGHT = 7,100.
- OFF build: 10 / 10 targeted PASS (sbpow-* not built in OFF).
- Pre-existing failures (not introduced by V11): bond-lock, popc,
  escrow, dynamic-rewards, checkpoints — see
  docs/KNOWN_TEST_FAILURES.md
