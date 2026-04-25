# Where Biometrics / Passkeys Belong in SOST

## WHERE THEY BELONG (user ↔ browser)

### SOST DEX
- Unlock wallet / identity
- Sign offers
- Accept deals
- Export backup
- Re-authenticate after timeout

### SOST Talk
- Login with passkey (verified badge)
- Prevent impersonation

### Browser Wallet / Security
- Create / import / export identity
- Passphrase unlock
- Passkey registration
- Device authentication explanation

## WHERE THEY DO NOT BELONG (node ↔ node)

### E2E P2P Protocol
- X25519 key exchange between nodes
- ChaCha20-Poly1305 AEAD between nodes
- Block sync, tx relay, keepalive
- This is machine-to-machine, NOT user-facing

### ConvergenceX PoW
- Mining proof system
- No user authentication involved

### cASERT Difficulty
- Consensus algorithm
- No user interaction

### Explorer (data layer)
- Read-only data display
- No authentication needed for viewing

## Summary

| Layer | Authentication | Biometrics? |
|-------|---------------|-------------|
| Browser wallet / DEX | User ↔ Browser | YES |
| SOST Talk | User ↔ Browser | YES |
| P2P Transport | Node ↔ Node | NO |
| ConvergenceX | Miner ↔ Chain | NO |
| Explorer | Read-only | NO |
