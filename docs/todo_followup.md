# Follow-up TODOs

Items spotted during a session but intentionally **not fixed in that
session** so as to keep scope tight. Each entry should record what
the issue is, where it lives, and any context the next session needs
to fix it safely.

---

## Wallet — Capsule sighash inconsistency (1 byte vs 2 bytes)

**Discovered:** 2026-04-30 (during Cancel/RBF wallet work).
**Where:** `website/sost-wallet.html`.

The `hashOutputs` computation in `buildAndSignTx` (around line 1789)
hashes one byte for `payload_len`:

```js
hoParts.push(new Uint8Array([0x00]));        // payload_len byte (0)
```

…but the actual TX serialization (around line 1839) writes two bytes:

```js
parts.push(new Uint8Array([0x00, 0x00]));    // payload_len (2 bytes u16 LE = 0)
```

This is fine **today** because all current wallet TXs ship with
`payload_len == 0` so both encodings hash the same data — but the
moment the wallet starts attaching a Capsule (M-Capsule wiring), the
sighash and the on-wire bytes will diverge and every Capsule TX will
fail signature verification on the node.

`buildAndSignCancellationTx` (added 2026-04-30) inherits the same
1-byte form for `hashOutputs` to stay byte-identical with the current
node behaviour. Fix both functions in the same change when wiring the
Capsule encoder so the node accepts payload-bearing wallet TXs.

**Fix sketch:** in both `hashOutputs` blocks, replace the single zero
byte with the actual two-byte little-endian `payload_len` (and append
the payload itself when non-empty), matching the on-wire format
exactly. Cross-check against `src/tx_validation.cpp` /
`include/sost/capsule.h` so the node and wallet agree on byte-for-byte
hashing.
