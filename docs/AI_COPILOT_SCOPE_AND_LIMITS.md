# SOST DEX — AI Copilot Scope and Limits

## What the AI CAN do

### Intent Parser (`dex-intent-parser.js`)
- Parse natural language input (English + Spanish)
- Detect action type (sell/buy full/reward, OTC, cancel)
- Extract price, expiry, amount, position ID, token
- Auto-select position when only one is active
- Produce structured intent with confidence score

### Form Assistant (`dex-ai-assistant.js`)
- Fill Trade Composer fields from parsed intent
- Build review summary ("What the assistant understood")
- Show what changes in SOST and Ethereum
- Coordinate all copilot modules into single response

### Deal Explainer (`dex-ai-explainer.js`)
- Explain full sale vs reward-only in plain language
- Show what transfers to buyer and what seller keeps
- Provide position-specific context (time to maturity, remaining rewards)

### Risk Guardian (`dex-ai-validator.js`)
- Detect suspicious prices (too low, too high)
- Check expiry reasonableness
- Verify position ownership before sell
- Check position status (active, matured, closed)
- Detect self-trading attempts
- Classify warnings: INFO / WARNING / BLOCKING

### Compare Helper (`dex-ai-compare.js`)
- Compare full sale vs reward-only sale
- Compare sell now vs hold to maturity
- Show what you give/keep/receive for each option
- Provide time-aware recommendations

### Lifecycle Guide (`dex-ai-lifecycle.js`)
- Analyze position stage (active → matured → withdrawn → closed)
- Show progress percentage and days remaining
- List available actions for current stage
- Detect split ownership (principal ≠ reward owner)
- Show reward claim progress

## What the AI CANNOT do

1. Sign any message
2. Send any message to the relay
3. Accept or cancel a deal
4. Execute settlement
5. Move funds
6. Change beneficiary
7. Unlock the wallet
8. Bypass authentication
9. Make decisions without user confirmation
10. Access private keys

## Architecture

```
User Input (natural language)
    ↓
Intent Parser → structured intent
    ↓
AI Assistant → review + form fill + explanation + risks
    ↓
User reviews "What the assistant understood"
    ↓
User clicks "Accept & Fill Form" or "Edit Manually" or "Discard"
    ↓
If accepted → form is filled, user can still edit
    ↓
User clicks "Create Signed Offer"
    ↓
Strong auth required (passkey re-authentication)
    ↓
Trade Engine signs + encrypts + sends
```

The AI is involved in steps 1-4 only. Steps 5-8 are user + crypto.

## Files

| File | Module | Lines |
|------|--------|-------|
| `dex-intent-parser.js` | Intent Parser | ~230 |
| `dex-ai-assistant.js` | Form Assistant | ~175 |
| `dex-ai-explainer.js` | Deal Explainer | ~140 |
| `dex-ai-validator.js` | Risk Guardian | ~140 |
| `dex-ai-compare.js` | Compare Helper | ~150 |
| `dex-ai-lifecycle.js` | Lifecycle Guide | ~145 |
| `auth-passkey.js` | Passkey/WebAuthn | ~200 |
