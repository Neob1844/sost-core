# SOST DEX — Private Deal Flow Architecture

## Overview

The SOST DEX private flow connects browser crypto (Phase A) to real trading operations.

## Flow

```
1. User unlocks keystore (passphrase)
2. Session activates → inbox polling starts
3. User composes offer in Trade Composer
4. Trade Engine builds structured offer
5. Offer is signed with ED25519
6. Recipient key resolved via directory/relay
7. Channel keys derived (X25519 DH + HKDF)
8. Payload encrypted (ChaCha20-Poly1305 IETF)
9. Envelope submitted to blind relay
10. Recipient fetches pending messages
11. Decrypts locally with channel keys
12. Can accept/cancel from browser
13. Deal channel tracks full lifecycle
```

## Files

| File | Purpose |
|------|---------|
| `js/dex-session.js` | Session lifecycle (unlock/lock/timeout) |
| `js/dex-trade-engine.js` | Build/sign/encrypt/send offers |
| `js/private-inbox.js` | Fetch/decrypt/display pending messages |
| `js/recipient-directory.js` | Counterpart discovery + prekey lookup |

## Security

- Private keys never leave the browser
- Relay cannot read encrypted content
- Channel keys are per-deal directional
- Session auto-locks after 5 min inactivity
- All sensitive actions require unlocked wallet

## What remains operator-assisted

- Settlement execution (SOST + ETH chain writes)
- Beneficiary sync (Ethereum tx)
- Escrow operations (SOSTEscrow contract calls)
- Refund processing
