# SOST — Biometric / Passkey Authentication Flow

## How It Works

SOST uses **WebAuthn / Passkeys** for modern device authentication.
The protocol does NOT read your fingerprint. It asks your device's
secure authentication system to verify you are you.

```
User opens DEX/Talk
    ↓
Browser checks: WebAuthn available?
    ↓ YES                          ↓ NO
Show "Login with Passkey"       Show "Unlock with Passphrase"
    ↓                              ↓
Device prompts:                 User types passphrase
  - Fingerprint                     ↓
  - Face ID                    Keystore unlocked
  - Secure PIN                      ↓
    ↓                          Session active
Passkey verified
    ↓
Session active
```

## When Biometrics Are Used

### Login (Level 1)
- Open DEX in private mode
- Open SOST Talk for posting
- Resume after session timeout

### Re-authentication (Level 2) — Sensitive Actions
- Sign a trade offer
- Accept a deal
- Send an OTC request
- Export identity backup
- Any action that transfers rights (ownership, reward, beneficiary)

### Not Required
- Reading public market data
- Browsing explorer
- Reading SOST Talk messages
- Viewing documentation

## Supported Devices

| Platform | Authenticator | Status |
|----------|--------------|--------|
| Android Chrome | Fingerprint / PIN | Supported via WebAuthn |
| iPhone Safari | Face ID / Touch ID | Supported via WebAuthn |
| Desktop Chrome | Windows Hello / Touch ID | Supported via WebAuthn |
| Desktop Edge | Windows Hello | Supported via WebAuthn |
| Older browsers | N/A | Fallback to passphrase |

## Fallbacks

1. **WebAuthn not available** → passphrase-only mode
2. **Passkey not registered** → prompt to register, continue with passphrase
3. **User cancels biometric prompt** → retry or use passphrase
4. **Session expired** → re-authenticate (biometric or passphrase)
5. **Different device** → import identity backup + register new passkey

## Security Model

- Your fingerprint/face is NEVER sent to any server
- Your device handles all biometric verification locally
- The passkey is a cryptographic credential stored in your device's secure enclave
- The SOST DEX only receives a yes/no from the device
- Private keys remain in the browser keystore (IndexedDB + Argon2id)
- The passkey gates access; the keystore holds the actual crypto keys

## Files

| File | Purpose |
|------|---------|
| `js/auth-passkey.js` | WebAuthn register/login/reauth/strong-auth gates |
| `js/dex-session.js` | Session lifecycle with auto-lock |
| `js/dex-onboarding.js` | UI integration (wallet panel, passkey button) |
| `js/keystore.js` | Encrypted key storage (Argon2id) |
