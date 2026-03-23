# SOST Wallet Safe Usage Guide

## Wallet Encryption

SOST wallet uses AES-256-GCM with scrypt key derivation.

### Creating an Encrypted Wallet
```bash
sost-cli newwallet
# Enter a strong passphrase when prompted
# The wallet file is encrypted at rest
```

### Best Practices for Passphrase
- Use 20+ characters
- Mix uppercase, lowercase, numbers, symbols
- Do NOT reuse from other services
- Store passphrase backup in a separate physical location from wallet file

## Sending Funds Safely

### Before Every Send

1. **Verify the destination address character by character**
   - Clipboard hijacking malware can swap addresses
   - Compare at least first 8 and last 8 characters
   - If possible, verify on a separate device

2. **Check the amount**
   - SOST uses 8 decimal places (1 SOST = 100,000,000 stocks)
   - A misplaced decimal can send 100x more than intended

3. **Check the fee**
   - Default: 1 stock/byte (~1000 stocks minimum)
   - Use `--fee-rate` to override if needed
   - Abnormally high fees may indicate a bug or attack

### Send Command
```bash
sost-cli send <destination_address> <amount_in_sost>
# Always verify the output summary before confirming
```

## Key Management

### Generating New Addresses
```bash
sost-cli getnewaddress
# Each call creates a new key pair
# IMPORTANT: Back up your wallet after generating new keys
```

### Backup
```bash
# Copy the wallet file to a secure location
cp ~/.sost/wallet.dat /path/to/secure/backup/
# Encrypt the backup independently if storing remotely
```

### Private Key Export (DANGEROUS)
```bash
sost-cli dumpprivkey <address>
# WARNING: This exposes the raw private key
# Anyone with this key can spend your funds
# Only use for migration or emergency recovery
# Never share, email, or paste into websites
```

## Address Safety

### SOST Address Format
```
sost1 + 40 hex characters = 45 characters total
Example: sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33
```

### Known Risks
- **No checksum**: A typo in the address will send to the wrong destination
- **Irreversible**: There is no undo for sent transactions
- **Verify carefully**: Always double-check addresses before sending

## Node Security

### RPC Access
- Default: localhost only (127.0.0.1:18232)
- NEVER expose RPC to the internet without a firewall
- Use strong RPC credentials (not default/empty)

### Firewall
- Allow P2P port 19333 from anywhere
- Block RPC port 18232 from external access

## What SOST Does NOT Have (Yet)

| Feature | Status | Impact |
|---------|--------|--------|
| HD wallet / seed phrase | Not implemented | Must back up entire wallet file |
| Multisig | Not implemented | Single key controls funds |
| Hardware wallet support | Not implemented | Keys stored on computer |
| Watch-only addresses | Not implemented | Need private key to see balance |
| Address checksum | Not in format | Typos not detected |
| Auto-lock timer | Not implemented | Manually lock wallet |
| Transaction labels | Not implemented | No local notes on txs |

## Emergency Procedures

### If You Suspect Key Compromise
1. Transfer all funds to a new address immediately
2. Generate new wallet on a clean machine
3. Send from compromised wallet to new wallet
4. Destroy old wallet file securely

### If You Lose Your Wallet File
- If no backup exists: **funds are permanently lost**
- There is no recovery mechanism without the private keys
- This is why regular backups are critical
