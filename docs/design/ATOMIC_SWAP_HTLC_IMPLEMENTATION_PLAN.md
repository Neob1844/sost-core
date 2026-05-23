# Atomic Swap HTLC — Implementation Plan (Phase 1)

**Status:** scaffolding-only. The full Phase 3 implementation has NOT
been written. This document is the design specification that a future
dedicated multi-week sprint would implement against.

**Activation gate:** `include/sost/atomic_swap.h` ::
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (OFF).

---

## 1. SOST-side HTLC LOCK transaction

A transaction that creates one `OUT_HTLC_LOCK` (proposed `0x12`) output.

**Output structure** (proposed):

```
TxOutput {
    amount        : i64        (SOST stocks)
    type          : u8         = 0x12
    pubkey_hash   : Hash160[20] = sha256(canonical_swap_state)[0..20]   // unique-by-swap address
    payload       : bytes       (80 bytes, fixed)
}

payload layout (80 bytes):
    [ 0..31]   hashlock         : sha256(preimage)
    [32..39]   refund_height    : i64 little-endian (absolute block height; refund opens here)
    [40..59]   claim_pkh        : RIPEMD160(SHA256(claim_pubkey))   (counterparty receives on reveal)
    [60..79]   refund_pkh       : RIPEMD160(SHA256(refund_pubkey))  (initiator gets refund back)
```

Total output bytes including header: amount(8) + type(1) + pkh(20) + payload_len(2) + payload(80) = 111 bytes.

The output's `pubkey_hash` is set to a hash derived from the swap state
so two different swaps cannot accidentally share the same outpoint
identity. This is **redundant** with the txid (which is unique) but
gives indexers a clean swap-id surface.

---

## 2. SOST-side HTLC CLAIM transaction

A transaction that spends an `OUT_HTLC_LOCK` UTXO via the preimage
path. Two shape options:

**Shape A: new `tx_type` byte (recommended)**

```
Transaction {
    version  : u32 = 1
    tx_type  : u8  = 0x10  (proposed TX_TYPE_HTLC_CLAIM)
    inputs   : [TxInput x 1]   // the HTLC_LOCK input
    outputs  : [TxOutput x N]   // user-controlled destination(s)
}

TxInput {
    prev_txid    : 32
    prev_index   : u32
    signature    : 64    (compact ECDSA over (txid, vin_index, preimage))
    pubkey       : 33    (claim_pubkey; sha256/ripemd160 must match payload[40..59])
}

claim-witness payload appended after the standard input fields:
    [0..31]  preimage           : 32 bytes
```

Note: the standard TxInput is 64+32+4+33 = 133 bytes. The preimage
extension forces a small serialization change for HTLC_CLAIM txs only,
gated by `tx_type == 0x10`. Pre-activation blocks never see this
tx_type so historical replay is bit-identical.

**Shape B: payload-carried preimage (rejected)**

Putting the preimage in an output `payload` is rejected because it
forces the preimage into the spend output — which means the preimage
appears in the txid hash domain and can be silently replaced by a
relay. Putting the preimage in the input witness is the standard
Bitcoin pattern and is the recommended shape.

---

## 3. SOST-side HTLC REFUND transaction

```
Transaction {
    version  : u32 = 1
    tx_type  : u8  = 0x11  (proposed TX_TYPE_HTLC_REFUND)
    inputs   : [TxInput x 1]    // the HTLC_LOCK input
    outputs  : [TxOutput x N]    // refund destination(s)
}

TxInput {
    prev_txid    : 32
    prev_index   : u32
    signature    : 64    (compact ECDSA over (txid, vin_index))
    pubkey       : 33    (refund_pubkey; sha256/ripemd160 must match payload[60..79])
}

No witness extension required (refund needs no preimage).
```

---

## 4. Required HTLC payload fields (summary)

| Field | Bytes | Purpose |
|---|---|---|
| `hashlock` | 32 | `sha256(preimage)`. Preimage size required to be exactly 32 bytes. |
| `refund_height` | 8 | absolute block height at which REFUND path opens |
| `claim_pkh` | 20 | RIPEMD160(SHA256(claim_pubkey)) |
| `refund_pkh` | 20 | RIPEMD160(SHA256(refund_pubkey)) |
| `swap_id` (derived) | n/a | = LOCK txid + LOCK vout index — implicit, not stored |
| `asset_pair` (off-chain) | n/a | tracked in OTC chat metadata, NOT in payload |
| `amount` (header) | 8 | already in TxOutput.amount |
| `claim_destination` | implicit | spend's outputs[*].pubkey_hash |
| `refund_destination` | implicit | spend's outputs[*].pubkey_hash |

---

## 5. Validation rules (consensus-enforced when activated)

**Gate every rule below with `atomic_swap_htlc_active_at(block_height)`.**
If the helper returns false, the validator rejects any HTLC tx_type or
output type as "unknown type" exactly as it does today.

**R-HTLC-1. HTLC_LOCK output structural validity.**
- `type == 0x12`
- `payload.size() == 80`
- `amount >= DUST_THRESHOLD`
- `refund_height > current_block_height` at acceptance time

**R-HTLC-2. HTLC_CLAIM spend rules.**
- spends exactly one HTLC_LOCK output (no mixed inputs)
- `tx.tx_type == TX_TYPE_HTLC_CLAIM (0x10)`
- preimage extension present in input; `sha256(preimage) == hashlock`
- `current_block_height < refund_height` (strictly before refund opens)
- input signature valid against `claim_pubkey` whose RIPEMD160(SHA256)
  equals `claim_pkh` in the LOCK payload
- output amounts sum to LOCK amount minus declared fee
- preimage length exactly 32 bytes

**R-HTLC-3. HTLC_REFUND spend rules.**
- spends exactly one HTLC_LOCK output (no mixed inputs)
- `tx.tx_type == TX_TYPE_HTLC_REFUND (0x11)`
- `current_block_height >= refund_height` (timeout passed)
- input signature valid against `refund_pubkey` whose RIPEMD160(SHA256)
  equals `refund_pkh` in the LOCK payload
- output amounts sum to LOCK amount minus declared fee

**R-HTLC-4. Double-spend impossibility.**
- the UTXO set's removal-on-spend already enforces single-spend, so a
  LOCK output cannot be both CLAIMED and REFUNDED. No additional rule
  needed beyond standard UTXO consumption.

**R-HTLC-5. Cross-chain replay impossibility.**
- `hashlock` is opaque to SOST consensus — no off-chain state is read.
  Replay protection on the counterparty chain is the wallet's
  responsibility (timeouts T1 > T2 + safety margin).

---

## 6. Serialization rules

- `OUT_HTLC_LOCK` reuses the existing `TxOutput.SerializeTo` path. The
  80-byte payload is serialized exactly as the existing `BOND_LOCK` (8
  bytes) and `ESCROW_LOCK` (28 bytes) payloads — length-prefixed via
  the existing `payload_len: u16 LE` field.
- New `tx_type` values 0x10 and 0x11 are serialized as the existing
  single-byte tx_type field — no shape change.
- The preimage extension on HTLC_CLAIM inputs is appended after the
  standard 133-byte TxInput, conditional on `tx.tx_type == 0x10`. The
  serializer reads/writes it only when that branch is taken.

Backwards compatibility: all pre-activation blocks contain only
`tx_type in {0x00, 0x01}` (standard, coinbase) and `out.type in {0x00,
0x01, 0x02, 0x03, 0x04, 0x10, 0x11}` (transfer + coinbase variants +
reserved bond/escrow). The HTLC additions never appear in pre-
activation blocks because the validator rejects them. Historical
replay is bit-identical.

---

## 7. Mempool rules

- HTLC_LOCK accepted if R-HTLC-1 passes + standard mempool fee rules.
- HTLC_CLAIM accepted if R-HTLC-2 passes + LOCK utxo is unspent +
  fee >= MIN_RELAY_FEE_PER_BYTE * tx_bytes.
- HTLC_REFUND accepted if R-HTLC-3 passes + LOCK utxo is unspent +
  current chain tip >= refund_height.
- If two competing spends of the same LOCK utxo arrive (CLAIM + REFUND
  near the timeout boundary), standard first-seen mempool policy
  applies; the block validator enforces the timeout rule definitively.

---

## 8. Block validation rules

- L3 `ValidateBlockTransactionsConsensus` calls
  `ValidateTransactionConsensus` per tx, which now dispatches into the
  HTLC rules via `atomic_swap_htlc_active_at(block.height)`.
- HTLC outputs participate in the standard UTXO set add/remove flow.
- Coinbase maturity (`COINBASE_MATURITY = 1000`) does NOT apply to
  HTLC outputs (they originate from a standard SOST input, not from
  coinbase).

---

## 9. Replay protection

- Each LOCK is uniquely identified by `(LOCK_txid, vout_index)`. A new
  swap with the same `hashlock` and `refund_height` but different
  funding tx is a different swap because its LOCK has a different
  txid.
- The preimage reveal is one-shot per LOCK: after CLAIM removes the
  LOCK UTXO, no further spend of that outpoint is possible.

---

## 10. Fee handling

- Fee is the standard `sum(inputs) - sum(outputs)` formula, same as
  every other SOST transaction.
- HTLC has no protocol-level fee differentiation: a HTLC_LOCK,
  HTLC_CLAIM, and HTLC_REFUND each pay normal SOST network fees,
  measured in stocks/byte against `MIN_RELAY_FEE_PER_BYTE`.

---

## 11. Dust / minimum amount

- HTLC_LOCK output `amount` must satisfy `amount >= DUST_THRESHOLD`
  (currently 10000 stocks = 0.0001 SOST). Below dust, the output is
  rejected at validation.
- Smaller HTLCs are not useful in practice because the network fees
  for LOCK + CLAIM + (optional) REFUND would exceed the value.

---

## 12. Timeout safety rules

- The HTLC primitive itself accepts any `refund_height >
  current_block_height` at LOCK time. There is no consensus rule on
  how far ahead the refund must be.
- The wallet (off-chain) must choose:
  - `T1 = refund_height on SOST side` (the initiator's refund window)
  - `T2 = refund_height on counterparty chain` (the responder's
    refund window)
  - `T1 > T2 + safety_margin`
  where `safety_margin` is large enough to cover the worst-case
  re-org depth on both chains plus the worst-case block propagation
  latency. Suggested defaults in the Asset Design doc.

---

## 13. Why T1 > T2 with margin (load-bearing)

If `T1 <= T2`, a responder can wait until `T1` to refund the
counterparty side, then claim the SOST side immediately. The
initiator gets nothing on the counterparty side and has lost the
chance to refund the SOST side. **The atomic property is broken
the moment `T1 <= T2`.** The wallet MUST refuse to sign any HTLC
where `T1 <= T2 + safety_margin`. The consensus layer does not
enforce this (it has no view into the counterparty chain) — the
wallet is the only line of defence.

---

## 14. Failure cases

See `docs/design/ATOMIC_SWAP_V13_DESIGN_PREVIEW.md` Section 8 for the
table. Replicating here so this doc stands alone:

| Failure | Outcome | Mitigation |
|---|---|---|
| Responder never locks counterparty leg | Initiator refunds at T1 | wait + auto-refund |
| Responder locks then disappears before claiming | Both refund at their T | auto-refund both sides |
| Initiator never reveals preimage | Both refund at their T | auto-refund both sides |
| Network re-org on faster chain after responder claims | Responder must re-broadcast | watchtower + RBF |
| Operator forgets to refund (wallet offline at T) | Funds locked indefinitely until operator returns and refunds | clear UI warnings, automated refund flow |
| Wrong timeout configured (T1 <= T2) | Responder can claim, initiator cannot | wallet must reject; consensus does NOT |
| Hash collision / weak hash | Theoretical | SHA-256, audited primitive |
| Fake "swap admin" / "I can unlock both sides" scammer | User sends funds to a non-existent role | Sentinel patterns 16-19; OTC page warning |
| Stablecoin issuer freezes counterparty tokens | Counterparty side becomes uncollectible mid-swap | Asset Design doc; OTC UI must mark USDT/USDC/PAXG/XAUT as "issuer-risk" |

---

## 15. What is V13-safe and what must fallback to V14

**V13-safe (this commit):**
- Activation constant `INT64_MAX` in a new header.
- Helper function (never called).
- Three design docs.
- Web cache-buster bump.

**V13 candidate but unlikely (would need a dedicated multi-week sprint
before V13 freeze):**
- Adding `OUT_HTLC_LOCK / TX_TYPE_HTLC_CLAIM / TX_TYPE_HTLC_REFUND`
  enum constants to `include/sost/transaction.h`.
- Adding payload reader helpers to `include/sost/transaction.h`.
- Adding validation rules to `src/tx_validation.cpp` gated by
  `atomic_swap_htlc_active_at(height)`.
- Adding mempool acceptance branches.
- Adding wallet builders + RPC endpoints.
- Adding 20+ adversarial tests.
- External cryptographic / economic review.

**V14 candidate (realistic landing):**
- Everything in the V13-candidate list above.
- Wallet integration on the BTC side (Bitcoin-Script HTLC).
- Wallet integration on the EVM side (Solidity HTLC contract; reuse
  pattern from `SOSTEscrow.sol`).
- Asset-specific docs for BTC / ETH / USDT / USDC / BNB / PAXG / XAUT.
- Activation commit setting `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT =
  V14_HEIGHT` (or chosen height).

**STOP CONDITION (triggered):** Phase 3 cannot be completed cleanly in
the V13 cycle window. Therefore this commit ships only scaffolding +
docs; `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` remains INT64_MAX. The
codebase is now ready for a future Phase 3 sprint without any rebase
churn.
