# Web wallet — Export Private Key (Advanced)

A secure, manual way to export a private key from the SOST web wallet
(`website/sost-wallet.html`), for **wallet migration** or setting up **local
sBPoW mining** with the same address. Nothing is ever exported automatically.

> ⚠️ **SECURITY:** Private-key export is dangerous and should only be used for
> migration or local mining setup. Anyone who obtains your private key can spend
> all your SOST. For normal use, prefer the encrypted seed-phrase backup.

## Where it is
**Wallet → Settings → “⚠ Export Private Key (Advanced)”** — collapsed by default,
behind a danger warning.

## What it guarantees
- Keys are decrypted **only in your browser memory** (re-entering your password
  re-runs the same AES‑256‑GCM / PBKDF2 decryption used to unlock the wallet).
- The private key is **never** sent to any server (no `fetch`/XHR/WebSocket/beacon),
  **never** written to `localStorage`/`sessionStorage`, and **never** logged.
- A reveal auto-hides after **60 seconds**; the wallet is **force-locked after any
  export**, and the plaintext field is wiped.
- Watch-only wallets have no key and are refused.

## To export you must (all three)
1. Re-enter your wallet password.
2. Type the exact phrase `EXPORT PRIVATE KEY`.
3. Tick “I understand that anyone with this key can spend my SOST.”

## Output options
- **Reveal once** — shows the key in a masked field (eye button to view, Copy button), auto-hides in 60 s.
- **Download CLI wallet JSON** *(preferred)* — a file compatible with `sost-cli` /
  `sost-miner`, named
  `sost-cli-wallet-<LABEL>-YYYYMMDD.json` (default label `SOST CEX LIQUIDITY RESERVE`).
- **Download raw key .txt** — only after an extra confirmation.

All files are generated **client-side** (Blob download); none touch a server.

## Why not an *encrypted* export?
An encrypted-at-rest export (the core's v2 scrypt+AES-GCM `wallet-export` format)
was evaluated and **rejected for the mining path**: `sost-miner` only loads the
**plaintext v1** wallet — it calls `Wallet::load()` (src/sost-miner.cpp:2377),
has no `--wallet-pass`/passphrase flag and no prompt, and `load()` parses
`"privkey"` fields that a v2 file does not contain. So an encrypted file would be
"secure but unusable for mining." The plaintext v1 JSON below is therefore the
mining format. Verified end-to-end with a throwaway dummy wallet: the miner
prints `SbPoW signing key: label='…' (loaded from …)` and derives the address.

**Handle the plaintext file safely:** keep it only inside WSL (not on the Windows
filesystem), `chmod 600` it, and delete it when done. No TOTP/2FA is added — it
cannot decrypt a client-side key and would only give false confidence; the
password that encrypts the key in the browser is the real protection.

## CLI wallet JSON schema
Matches the v1 format read by `src/wallet.cpp` / the miner:

```json
{
  "version": 1,
  "warning": "PRIVATE KEYS ARE UNENCRYPTED — KEEP THIS FILE SECURE",
  "keys": [
    { "privkey": "<64 hex>", "pubkey": "<66 hex>", "address": "sost1<40 hex>", "label": "SOST CEX LIQUIDITY RESERVE" }
  ],
  "utxos": []
}
```
(secp256k1; address = `sost1` + hex(RIPEMD160(SHA256(compressed pubkey))) — identical
derivation in the web wallet and the C++ core.)

## Mine with the exported wallet
```bash
chmod 600 sost-cli-wallet-SOST-CEX-LIQUIDITY-RESERVE-YYYYMMDD.json

./sost-miner \
  --wallet sost-cli-wallet-SOST-CEX-LIQUIDITY-RESERVE-YYYYMMDD.json \
  --mining-key-label "SOST CEX LIQUIDITY RESERVE" \
  --address sost1................................... \
  --genesis ../genesis_block.json \
  --rpc 127.0.0.1:18232 --rpc-user "$rpcuser" --rpc-pass "$rpcpassword" \
  --blocks 999999 --profile mainnet --threads 13
```
The miner looks up the key by **exact label match**, so `--mining-key-label` must
equal the `label` in the file.

## Tests
`node tests/test_wallet_export.js` — pure-logic tests (gate, schema, filename;
dummy keys only) plus static checks that the UI block is collapsed by default,
enforces the gate, and never sends/stores/logs key material. No real secret,
wallet, backup or generated export file is committed to the repo.

## Pure logic
`website/js/wallet-export.js` holds the side-effect-free helpers
(`validateExportGate`, `validateKeyMaterial`, `buildCliWalletJson`,
`exportFilename`). The UI layer in `sost-wallet.html` does the in-memory
decryption, download and locking.
