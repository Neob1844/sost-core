# SOST Transaction Fee/Size Metric — Reconciliation

**Status:** investigative diagnosis + invariant pinning. No consensus
rule changed. No node, wallet or signer changed.

## Symptom that prompted this audit

The first Trinity Useful Compute on-chain payment was mined in
block 8512 of mainnet on 2026-05-13:

| Field | Value |
| --- | --- |
| txid | `787cda89dec3d31f40b6281e10ba1b711685e4a713d4117a4e44dccd616f2d82` |
| inputs | 1 (a 100 000-stock UTXO) |
| outputs | 2 (31 500 stocks payout + 68 298 stocks change) |
| fee | 202 stocks |
| explorer-reported size | ≈ 226 bytes |
| ratio (fee / explorer size) | 0.894 stocks / byte |
| consensus rule S8 (per `sost-cli --help`) | `fee >= tx_size × 1 stock/byte` |

A naïve reading is "the tx was accepted at 0.894 stocks/byte, which
is below the S8 floor of 1.0 stocks/byte." That would imply a
consensus bug. **It is not.**

## The three metrics

There are three independent points in the codebase that need a
notion of "tx size":

### 1. `createtx` (wallet side)

`src/sost-cli.cpp:1049`:

```cpp
static int64_t calculate_fee(int64_t tx_size_bytes) {
    int64_t fee = tx_size_bytes * g_fee_rate;
    if (fee < MIN_FEE_STOCKS) fee = MIN_FEE_STOCKS;
    return fee;
}
```

`tx_size_bytes` is the result of `tx.Serialize(raw)` where `raw` is
`std::vector<sost::Byte>`. The serializer (`src/transaction.cpp:213`
and `:240`) lays each input as 32 + 4 + 64 + 33 = **133 bytes** and
each output as 8 + 1 + 20 + 2 + payload_len = **31 + payload** bytes.

A two- to three-pass fee adjustment in `createtx` re-serialises
after the fee changes so the final raw vector is what the wallet
actually broadcasts.

### 2. Consensus rule S8 (node side)

`src/tx_validation.cpp:380`:

```cpp
int64_t fee = input_sum - output_sum;
size_t tx_size = EstimateTxSerializedSize(tx);
int64_t min_fee = (int64_t)tx_size * 1;
if (fee < min_fee) {
    return TxValidationResult::Fail(TxValCode::S8_FEE_TOO_LOW, ...);
}
```

`EstimateTxSerializedSize` (`src/tx_validation.cpp:68`) computes the
size with the same formula the serializer uses:

```cpp
size += 4;                          // version
size += 1;                          // tx_type
size += CompactSizeLen(inputs.size());
size += inputs.size() * 133;        // fixed per input
size += CompactSizeLen(outputs.size());
for (output : outputs) {
    size += 8 + 1 + 20 + 2;         // amount + type + pkh + payload_len
    size += output.payload.size();
}
```

The estimator and the serializer are pinned to the same wire format
by construction.

### 3. Block-explorer reported size

The on-chain RPC (`src/sost-node.cpp:1767`) reports `raw.size()`
from the same `tx.Serialize()` call — so the JSON RPC field
`size` agrees with createtx and S8.

A block explorer's UI may compute its own length over the hex
string, including JSON framing or a different rounding rule. The
explorer's number is **display only** and does not feed back into
consensus. The 226-vs-202 delta seen for txid `787cda89…` is in
that display layer.

## Reconciliation for txid 787cda89…

The tx has 1 input and 2 outputs with no payload, so:

```
size = 4 + 1 + 1 + 1×133 + 1 + 2×31
     = 4 + 1 + 1 + 133 + 1 + 62
     = 202 bytes
```

`fee = 202 stocks`. `min_fee = 202 × 1 = 202 stocks`. `fee >= min_fee`
holds exactly at the floor. **The tx is consensus-valid.** The
explorer's 226 is +24 bytes of display overhead, unrelated to S8.

## Invariant pinned by this commit

`tests/test_tx_validation.cpp` gains a `T_FEE_SIZE_*` suite that
locks the contract between the two metrics that DO matter:

| Test | Verifies |
| --- | --- |
| `T_FEE_SIZE_estimate_matches_serialize_1in_1out` | 1-in 1-out, no payload: `Serialize().size() == EstimateTxSerializedSize() == 171` |
| `T_FEE_SIZE_estimate_matches_serialize_1in_2out` | Reproduces the 787cda89… shape: 202 bytes both ways, fee 202 == floor, S8 accepts |
| `T_FEE_SIZE_estimate_matches_serialize_2in_3out` | 2-in 3-out: 366 bytes both ways, S8 accepts |
| `T_FEE_SIZE_S8_at_exact_floor_accepts` | `fee == size` exactly: accepted |
| `T_FEE_SIZE_S8_one_below_floor_rejects` | `fee == size − 1`: rejected as `S8_FEE_TOO_LOW` |

If anyone ever changes `EstimateTxSerializedSize` or
`Transaction::Serialize` without keeping the other in sync, these
tests fail and the change cannot land.

## What was NOT changed

- No consensus rule modified.
- No wire format modified.
- No wallet builder modified.
- No node RPC behaviour modified.
- The block explorer's display calculation is **not** in the scope
  of this branch (it lives under `website/`); a separate docs PR
  will note the display caveat for operators.

## Operational guidance

When auditing whether a future tx would have been consensus-valid,
use the on-chain RPC `getrawtransaction <txid>` and read the `size`
field; that number is what S8 measured. If the difference between
explorer and RPC ever grows beyond ~30 bytes, audit
`EstimateTxSerializedSize` and `Transaction::Serialize` and confirm
the suite above still passes.
