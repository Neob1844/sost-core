# Native SOST multisig — future consensus feature (DESIGN ONLY)

Status: **not implemented, not scheduled.** This document lists what a real native multisig would
require so that the bridge can later replace `ColdSingleSigner` with `NativeMultisigSigner`.
Activating it is a separate, explicit future decision with its own release, tests, audit and notice.

## Why the existing library code cannot simply be switched on

`include/sost/script.h` / `src/script.cpp` (OP_CHECKMULTISIG, P2SH, `sost3`) and `include/sost/psbt.h`
are library code with unit tests only:

- `OUT_SCRIPT_HASH = 0x30` collides with V16 `OUT_NODE_PROTOCOL = 0x30` (NODE_BIND / heartbeats).
- `TxInput` carries exactly one 64-byte signature and one 33-byte public key; there is no scriptSig.
- `address_valid` accepts only `sost1`; every RPC rejects `sost3`.
- `IsActiveOutputType` / rule R11 reject the script-hash output type.
- PSBT multisig finalisation is a stub; no CLI or RPC uses PSBT.
- `MULTISIG_ACTIVATION_HEIGHT = 2000` is a dead constant with no consensus effect.

## Requirements for a future fork

1. **New, unused output type code** — never 0x30. Registry check against every V16 type.
2. **Transaction serialization**: a versioned input format able to carry M signatures (or a
   witness-like section), with a height-gated activation so historical replay stays byte-identical.
3. **Validation**: M-of-N verification (low-s, ordered keys, no duplicate keys, N ≤ 15), sighash
   that commits to every input amount and the redeem data, fee and size limits.
4. **Address encoding**: a `sost3`-style script-hash address with checksum; `address_valid` and every
   RPC updated; wallets must refuse to send to it before activation.
5. **Wallet**: create, import, watch; coin selection over multisig UTXOs.
6. **PSBT**: create / sign / combine / finalize for multisig, in the CLI and RPC.
7. **Mempool / relay policy**: standardness rules, size limits, fee estimation.
8. **Reorg safety** and **historical replay** tests across the activation boundary.
9. **Activation boundary**: explicit height, ordering invariants with existing forks, static asserts.
10. **Adversarial tests**: wrong M, duplicate signatures, key-order games, malleability, replay
    across inputs, mixed single-key + multisig transactions, deep reorg around activation.
11. **Explorer / indexer support** to show multisig vaults transparently.

## Bridge migration path once active

1. Create a new M-of-N Bridge Vault (independent signers, not one operator's machines).
2. Freeze minting; let the indexer show BALANCED.
3. Move the vault balance with a single, published release-to-new-vault transaction (or let the
   old vault drain through normal releases) — documented and reconciled.
4. Point WSOST's `bridgeVault` at the new vault via a new deployment or an explicit, timelocked,
   audited migration (Stage 1 WSOST fixes `bridgeVault` at deployment by design).
5. Swap `ColdSingleSigner` for `NativeMultisigSigner`; nothing else in the accounting changes.
