# Offline capsule transactions — minimal wallet/CLI design (DESIGN ONLY, not implemented)

## Gap

- `sost-cli send` attaches capsules (`--capsule-mode/--capsule-text`) but builds, signs **and broadcasts** in one step on an online machine.
- `sost-cli createtx` builds + signs without broadcasting, but ignores the capsule flags and still syncs UTXOs from a node.
- `createhtlclock / claimhtlc / refundhtlc` print **unsigned** hex and nothing shipped signs it.

The bridge release signer (Stage 1 `ColdSingleSigner`) and any air-gapped vault therefore cannot sign a
capsule-bearing release offline. No consensus change is needed: capsules and HTLC spends are already valid
transactions; this is wallet tooling only.

## Proposal (smallest first)

**Step 1 — `createtx` honours the capsule flags (tiny).** Reuse `build_capsule_for_mode()` exactly as `send`
does, then print the signed hex instead of broadcasting. Same signing code, same fee logic. Still needs a node
for UTXOs, so it is "sign without broadcast", not air-gapped.

**Step 2 — explicit offline triple.**
1. `sost-cli buildtx --from <addr> <to> <amt> [--capsule-*] --out tx.json` (online, watch-only): writes
   `{unsigned_hex, inputs:[{txid,vout,amount,type,address}], outputs, fee, capsule_decoded}`.
2. `sost-cli signtx tx.json --wallet <cold.json> --out signed.hex` (air-gapped, no network): decodes and
   **shows every output and the capsule text** for confirmation, recomputes the fee from the declared input
   amounts, refuses unknown output types, signs each input with `SignTransactionInput` using the declared
   `{amount,type}` (the same values consensus uses in the sighash, so a lying `tx.json` only produces an invalid signature).
3. `sost-cli sendrawtransaction signed.hex` (online, exists today).

`signtx` would also sign HTLC CLAIM/REFUND inputs (spent type `0x12`), closing the HTLC signing gap.

## Security notes

- The sighash already commits to every input amount and type and to all outputs (including capsule payloads),
  so the cold signer cannot be tricked into signing different outputs than it displays.
- `signtx` must never contact the network and must refuse a wallet that is not encrypted unless `--allow-plaintext` (lab).
- Tests: byte-identical signatures vs `send` for the same inputs; capsule round-trip; HTLC claim/refund accepted by a devnet node; tampered `tx.json` → node rejects.

## Status

Design only. Not implemented; needs explicit authorization. The lab tool `tests/bridge/lab/sost_lab_sign.cpp`
shows the signing path works but is test-only and is not part of sost-cli.
