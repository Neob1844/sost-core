# Browser Crypto Feasibility — SOST DEX Private Web App

## Verdict: BROWSER-PARTIAL → CONNECTED

The crypto motor exists in `sost-comms-private` (31 files, 3,376 lines, 231 tests).
It is Node.js-only. The browser adaptation uses `libsodium-wrappers` to provide
identical crypto primitives with full envelope compatibility.

## Stack Decision

| Primitive | Node.js (existing) | Browser (new) |
|-----------|-------------------|---------------|
| ED25519 | `crypto.sign/verify` | `libsodium crypto_sign_*` |
| X25519 | `crypto.diffieHellman` | `libsodium crypto_scalarmult` |
| HKDF-SHA256 | `crypto.hkdfSync` | Manual HMAC-SHA256 via libsodium |
| ChaCha20-Poly1305 | `crypto.createCipheriv` | `libsodium crypto_aead_chacha20poly1305_ietf_*` |
| SHA-256 | `crypto.createHash` | Web Crypto `subtle.digest` + libsodium fallback |
| Random | `crypto.randomBytes` | `crypto.getRandomValues` (native) |
| Key storage | `fs` (JSON files) | IndexedDB + Argon2id encryption |

## Files Created (Phase A)

| File | Purpose | Lines |
|------|---------|-------|
| `website/js/browser-crypto.js` | ED25519, X25519, HKDF, AEAD, key bundles | ~350 |
| `website/js/keystore.js` | IndexedDB identity store with Argon2id passphrase encryption | ~250 |
| `website/js/relay-client.js` | HTTP client for blind relay API | ~180 |
| `website/js/prekey-store-browser.js` | IndexedDB prekey bundle management | ~130 |
| `website/dex-crypto-test.html` | Browser test suite (60+ tests) | ~350 |

## Envelope Compatibility

Browser-generated envelopes are byte-compatible with Node.js envelopes:
- Same ChaCha20-Poly1305 IETF (12-byte nonce, 16-byte tag)
- Same canonical header format for signing
- Same HKDF labels (sost-deal-key-a, sost-deal-key-b)
- Same session ID derivation (SHA-256(shared || dealId)[0:16])

A message encrypted in the browser can be decrypted by the Node.js relay/client
and vice versa.

## What's Next

### Phase B — Private DEX Flow
- Connect Trade Composer to real sign/encrypt
- Private inbox with local decryption
- Deal channel with real encrypted messages
- OTC with signed requests

### Phase C — Passkeys + AI
- WebAuthn registration/login
- Reauth for sensitive actions
- AI form assistant (intent parser)
- Risk guardian
