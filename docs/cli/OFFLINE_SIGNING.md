# Offline transaction signing — `buildtx` / `signtx`

Wallet/CLI feature only. **No consensus change**: the transactions are ordinary SOST transfers
(optionally carrying an existing capsule mode) signed with the same sighash the wallet always used.

## Workflow

```
ONLINE  (watch-only, no private key)
  sost-cli --node 127.0.0.1:18232 --from-address sost1<vault> \
           [--capsule-mode open-note --capsule-text "WSOST:0x…"] \
           buildtx sost1<destination> 100 --out tx.json [--network mainnet]

OFFLINE (no network)
  sost-cli --wallet cold.v2.json signtx tx.json --out signed.hex \
           [--passphrase-file ~/.sost/cold.pass]      # or --passphrase-fd n, or typed at the prompt

ONLINE
  sost-cli --node 127.0.0.1:18232 sendrawtransaction $(cat signed.hex)
```

`buildtx` queries the node for the UTXOs of `--from-address` and the tip height, runs the same coin
selection and fee convergence as `send`, and writes `tx.json` (`format: sost-unsigned-tx-v1`) with the
network, genesis, every input `{txid, vout, amount, output_type, address}`, the fee, the capsule and the
unsigned transaction bytes. It never overwrites an existing file.

`signtx` reads only the file and the wallet. Before signing it checks: known format, network and genesis
match the signer, the bytes decode, the input list matches the bytes exactly, no duplicate input, nothing
already signed, only standard transfers, declared fee == inputs − outputs, and that the wallet holds a
key for every input. It then prints every input, every output (change marked), the fee, and the capsule
(size, type, SHA-256 and printable text), asks for `yes` (or `--yes`), signs, and **verifies each
signature** before writing `signed.hex`. Plain v1 and encrypted v2 wallets are both accepted.

## Why a tampered file cannot steal funds

The sighash commits to every input's amount and output type, to all outputs (amounts, destinations,
capsule payloads) and to the genesis hash. Changing any of them after signing — or lying about an input
amount in `tx.json` — produces a signature the node rejects (`E6`). What the offline signer displays is
exactly what it signs.

## Limits

- `--network` is a tooling guard. Mainnet, testnet and devnet share the same genesis hash, so a signature
  is not cryptographically bound to one network; keep devnet keys separate from mainnet keys.
- `signtx` signs standard transfers (spending transfer / coinbase outputs). HTLC claim/refund and other
  special spends are not covered yet.

## Tests

- `tests/test_offline_build.cpp` (ctest `offline-build`): unsigned build + external signing is byte-identical
  to the wallet-signed transaction, with and without a capsule; watch-only build needs `--from-address`;
  the default signed path still requires the key.
- `tests/cli/test_offline_signing.py`: real devnet node — build, sign (v1 and encrypted v2), broadcast, confirm;
  replay, wrong network, wrong wallet, wrong passphrase, fee mismatch, truncated tx, mismatched/duplicate
  inputs, refusal without `yes`, and node rejection of a destination/amount/input-amount/capsule changed after
  signing. `--capsule` adds the capsule cases (devnet height ≥ 7,350).
