# SOST Sentinel — Moderation Rules and Limits

## Lema
"Protects the channel from spam, scams and noise — not from criticism."

## Rate Limits
- Minimum 5 seconds between messages per user
- Maximum 5 messages per minute per user
- Exceeding: auto-mute for 60 seconds

## Message Limits
- Minimum: 2 characters
- Maximum: 1,000 characters
- Duplicate detection: 60-second window

## Scam Detection Patterns
Blocks messages matching:
- "send me your SOST/BTC/ETH/coins"
- "free airdrop/giveaway"
- "double your investment"
- "guaranteed return/profit/yield"
- "invest now" + percentage
- "admin DM" / "DM admin" / "support DM"
- "verify your wallet"
- "connect your wallet to"
- "claim your reward/airdrop/bonus"
- Telegram/WhatsApp links

## Impersonation Detection
Blocks usernames matching:
- NeoB, Neo B
- SOST Admin, SOST Support, SOST Team, SOST Official
- Moderator, Mod

## Link Policy
- Official domains (whitelisted): sostcore.com, sostprotocol.com, github.com/neob1844
- External links: flagged as INFO (not blocked, but marked)
- Suspicious domains: collapsed pending review

## Auto-Responses (11 patterns)
Triggered by common questions/issues:
1. Sync problems → rebuild + bootstrap instructions
2. Wallet issues → wallet.json backup + generation guide
3. DEX issues → unlock steps + browser console check
4. Memory/bad_alloc → swap file instructions
5. Explorer issues → hard refresh + cache clear
6. How to mine → quickstart link
7. What is SOST → overview + links
8. PoPC questions → Model A/B explanation + timeline
9. Passkey/biometric → WebAuthn explanation + DEX link
10. Contact/report → contact page + BitcoinTalk link
11. General help → relevant documentation links

## What Sentinel Does NOT Block
- Negative opinions about the protocol
- Harsh criticism
- Skeptical questions
- Repeated reasonable questions
- Bug reports (even angry ones)
- Price discussion
- Technical debate
