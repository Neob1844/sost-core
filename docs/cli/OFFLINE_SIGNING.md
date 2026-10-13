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

## Pending transactions: mempool spends and local reservations

`getaddressutxos` lists *confirmed* outputs only. An output spent by a tx that is still in the mempool
is listed as unspent, and an unsigned build that has not been broadcast yet is invisible to the node.
`buildtx` therefore excludes two kinds of taken inputs before coin selection:

1. **Spent by a pending mempool tx.** Read with the node RPC `getmempoolspends <address>`
   (read-only, same auth as `getaddressutxos`): `{address, mempool_size, spent:[{txid, vout,
   amount_stocks, spent_by}]}` — the confirmed outputs of the address that a mempool tx spends.
   Against an older node without it, `buildtx` uses `getmempoolinfo` + `getrawmempool` +
   `getrawtransaction <txid> true`; because `getrawmempool` is capped at one block template, the
   build **fails closed** if it lists fewer txs than the mempool holds. Any failure to read the
   mempool refuses the build. `--skip-mempool-check` overrides that (warning printed); the node would
   then reject a conflicting build — never a double spend.
2. **Reserved by an earlier unsigned build.** Each successful `buildtx` appends its inputs to a local
   ledger, `sost-buildtx-reservations.json` in the directory of `--out` (or `--reservations PATH`;
   builds that must see each other share the directory or the path). Mode 0600, atomic replace, and a
   `flock` serialises concurrent builds. If the reservation cannot be written, the unsigned file is
   removed. A reservation is released when
   - it expires (`--reservation-ttl SECONDS`, default 86400, range 60..2592000),
   - none of its inputs is an unspent output any more (the tx, or a conflicting one, confirmed), or
   - explicitly: `buildtx --clear-reservations --from-address A [--reservations PATH | --out dir/x]`.

   `buildtx --list-reservations [--reservations PATH | --out dir/x]` prints them. A damaged ledger is
   never discarded silently: the build is refused until the file is inspected or moved.
   `--ignore-reservations` builds as if nothing were reserved (warning printed) — broadcast only one of
   the conflicting transactions.

When the inputs that are left cannot pay amount + fee, `buildtx` fails without writing anything:

```
Error: insufficient available funds: 12.00000000 SOST available for sost1… (2 output(s) / 100.00000000 SOST
spent by pending mempool txs, 1 output(s) / 50.00000000 SOST reserved by local unsigned builds)
```

Change outputs of a pending tx are not spendable by `buildtx` until it confirms (`getaddressutxos`
lists confirmed outputs only). A tx broadcast to a *different* node that has not reached this node's
mempool yet cannot be seen; the node then rejects the conflicting build as before.

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
  Pending-transaction section: tx A signed and left in the mempool, then B built immediately uses
  disjoint inputs and is accepted; an unbroadcast build C reserves its inputs and D avoids them;
  `--list-reservations`, `--clear-reservations`, `--ignore-reservations` (still skips mempool inputs);
  "insufficient available funds" with nothing written; the fallback path against a node without
  `getmempoolspends` (a local proxy hides the method). Pass `--mine-cmd "<miner … --blocks 1>"` so
  blocks are mined only while waiting for a confirmation and pending txs stay pending deterministically.
- `tests/test_buildtx_reservations.cpp` (ctest `buildtx-reservations`): ledger round trip, mode 0600,
  damaged ledgers refused, expiry, release on confirmation, per-address clear, and the exclusion rule
  (a second build never reuses the first build's inputs; with every coin taken it fails as insufficient).
