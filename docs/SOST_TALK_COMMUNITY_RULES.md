# SOST Talk — Community Rules

## What is SOST Talk

A moderated community space for SOST miners, traders, developers and participants.
Five rooms: General, Miners, DEX/PoPC, OTC / P2P Board, Bugs/Feedback.

## Moderated by SOST Sentinel

The bot moderates spam, scams and abuse — **not criticism**.

## Allowed

- Criticism (including harsh criticism)
- Bug reports (including repeated ones)
- Questions (including basic ones)
- Skepticism and debate
- Technical discussion
- Negative feedback
- Feature requests

## Not Allowed

- Spam and flooding (rate limit: 5s between messages, max 5/min)
- Scam solicitations ("send me coins", "guaranteed returns")
- Phishing links
- Impersonation of admins, founder, or officials
- Malicious links or malware
- Repeated copy-paste spam
- Abusive flooding

## Important

- Admins will NEVER ask you to send funds
- Only trust sostcore.com and sostprotocol.com
- Report suspicious behavior via the report button
- Identity required to post (prevents anonymous spam)

## Auto-responses

SOST Sentinel provides helpful auto-responses for common issues:
- Sync problems → bootstrap/rebuild instructions
- Wallet issues → wallet generation guide
- DEX issues → DEX unlock steps
- Memory errors → swap file instructions

## OTC / P2P Board Rules

The OTC / P2P Board is a **community discussion room** where users may
post buy/sell offers between each other. It is **not** an exchange,
**not** an escrow service, **not** a trading desk, and **not** a
liquidity guarantee.

### Hard invariants

- **SOST Protocol does not intermediate trades.** Every post on the
  board is between users, at the users' own risk.
- **SOST Protocol does not custody funds.** No SOST address holds
  buyer or seller balances on behalf of a counterparty.
- **SOST Protocol does not provide escrow.** Anyone claiming to be
  "official escrow", "admin escrow", or "SOST escrow" is a scammer.
- **Admins never DM first.** Real moderators never initiate private
  messages asking for funds, wallet credentials, or test transfers.
- **Use small test transactions first.** Especially when trading with
  a counterparty for the first time.
- **Report suspicious behaviour** via the report button; SOST Sentinel
  flags obvious scam vocabulary automatically.

### What is allowed on the board

- Neutral offers in plain wording, e.g. "WTB 100 SOST at 0.0001 BTC each",
  "WTS 50 SOST, accept BTC or USDT, escrow via mutually-agreed third party".
- Community discussion of price, liquidity, available counterparties.
- Reviews and reputation discussion of past traders (without doxxing).
- Coordination of in-person or off-platform settlement.

### What is NOT allowed

- Claims of "official" buyer, seller, escrow, liquidity, or trading desk.
- Asking another user to send funds first without a mutually-agreed
  third-party escrow.
- "Guaranteed return / risk-free profit / double your SOST" patterns
  (these are scams by construction).
- Phishing links disguised as wallet verification, airdrop claim, or
  trade confirmation.
- Impersonation of NeoB, SOST admins, or any SOST team member.
- Spam and flooding (same rate-limits as other rooms apply: 5 s between
  messages, max 5 per minute).

### Liability

Posts on this board are user content. SOST Protocol, its contributors,
and the moderation bot are **not** parties to any trade arranged here
and are **not** liable for losses arising from such trades. Trade at
your own risk and use independent escrow when the counterparty is
unknown to you.

## OTC / P2P Tactical Safety Rules

The three NOT invariants (non-custodial, no escrow, no intermediation)
are necessary but not sufficient. The board hosts the conversation;
the user runs the trade. Most OTC scams collapse if the user follows
the rules below.

### Three rules that stop most scams

1. **Screenshots are NOT proof of payment.** A screenshot the
   counterparty sends you can be edited, faked, or come from a
   different account. Until the money is in your bank or wallet,
   you have not been paid.
2. **Verify funds DIRECTLY in your bank or wallet** — log in and
   check the balance/transaction yourself. Do NOT trust SMS
   notifications, email alerts, or push notifications alone (they
   can be spoofed and they lag the actual settlement).
3. **Beware payment methods with chargeback risk.** Wait the FULL
   clearing window before releasing SOST:
   - PayPal Friends & Family — reversible up to 180 days.
   - SEPA / instant bank transfer — reversible up to 8 weeks.
   - Wise / Revolut instant — reversible on fraud claim.
   - Cash in person — irreversible. Safest fiat method.
   - USDC / USDT settled on-chain — irreversible after confirmations.
     Safest crypto-vs-crypto method.

### Scammer vs honest counterparty

| Scammer | Honest counterparty |
|---|---|
| Sends a screenshot and pressures you to release fast. | Tells you they paid; lets you verify at your pace. |
| Wants to move chat to Telegram / Signal / WhatsApp / DM. | Continues on the public OTC / P2P Board chat. |
| Claims "I'm verified", "I'm an admin", "I work with SOST". | Makes no special claims. |
| Asks YOU to send SOST first ("I'll send mine after"). | Agrees to a small test tx OR mutually-trusted 3rd-party escrow. |
| Urgency: "release fast", "order expiring", "hurry up". | Respects your verification timeline. |
| Price MUCH better than market. | Price close to market. |
| Pays via reversible methods + "you can release now". | Uses irreversible settlement (cash in person, on-chain stablecoin). |
| Claims an "official SOST escrow" exists. | Knows SOST does not provide escrow. |

### Pre-trade checklist (the modal in SOST Talk shows this)

Before posting or replying in the OTC / P2P Board, confirm:

1. SOST Protocol does NOT intermediate, custody, or escrow my trade.
2. I will verify any payment DIRECTLY in my bank/wallet.
3. I know payment methods with chargeback risk and will wait their
   clearing window.
4. I will not move chat to private DMs with someone I do not already
   trust.
5. I will use small test transactions for any new counterparty.
6. Admins NEVER DM first. Claims of "official escrow" / "verified
   buyer" / "guaranteed liquidity" are scams.

The checklist appears once per browser (localStorage) the first
time the user opens the OTC room. Clearing localStorage re-shows it.

### What SOST Sentinel auto-flags

In addition to the existing scam patterns (`guaranteed return`,
`official escrow`, `send funds first`, etc.), Sentinel also flags
the common OTC pressure patterns:

- "release first / send first / I'll send after" patterns.
- "order is about to expire / hurry up / release fast".
- "let's move to telegram / DM me on signal" patterns.
- "I sent the screenshot, look at the screenshot" patterns.
- "trust me / I'm verified / I'm an admin / I work with SOST".

Sentinel cannot stop all scams. The first line of defence is the
user reading and following the rules above.


## OTC Reputation Room Rules (community-curated, unverified)

The `otc-rep` room is an opt-in space where users may share their
experiences with past OTC / P2P counterparties.

### Hard invariants

- **SOST Protocol does NOT verify, attest, or endorse any reputation
  claim posted in this room.** A positive review is not a SOST
  guarantee. A negative review is not a SOST accusation.
- **Reputation in a non-custodial board is community-curated, not
  platform-attested.** SOST has no identity system to anchor these
  claims against.
- **Fake reputation is itself a scam pattern.** Scammers can create
  multiple identities and post fake positive reviews about themselves
  (Sybil attack). Cross-check before trusting any single thread.
- **No doxxing.** Do not post the counterparty's real name, address,
  phone, ID, employer, or any other personal data. Counterparty
  handles only.
- The OTC / P2P Tactical Safety Rules apply identically here.

### Suggested posting format (voluntary)

A useful reputation post is one another user can cross-check:

```
[REP+] or [REP-] — counterparty handle: @handle
Trade size: X SOST  /  Y fiat
Payment method: <method>
Date: YYYY-MM-DD
Outcome: delivered / partial / undelivered / scam
Evidence (if available): txid, block explorer link, screenshot of
  on-chain payment (NOT a private chat screenshot)
Lesson: (one sentence)
```

The more verifiable detail, the more useful. Vague "this user is a
scammer" with no evidence carries little weight and may itself be a
smear-campaign tactic.

### Sentinel applies

Sentinel's scam-pattern flags apply in this room too. A post that
itself uses scam vocabulary ("release first", "guaranteed buyer",
"DM me on Telegram") will be flagged regardless of whether it
claims to be a "reputation" post.

### What this room is NOT

- Not a SOST-curated trader directory.
- Not a SOST-issued reputation score.
- Not a SOST-arbitrated dispute log.
- Not enforceable evidence against anyone.

It is a community noticeboard. Read it. Cross-check it. Decide for
yourself.


---

## Atomic Swap V14 — Supported Asset Categories

When atomic swap HTLC activation lands (target: V14 / block 15,000), the
supported asset pairs split into two trust categories. **This split is
load-bearing**: the cryptographic mechanism is identical, but the
operational risk differs.

**Category A &mdash; trust-minimized** (no token-issuer freeze risk):

- `SOST` &harr; `BTC`  (Bitcoin Script HTLC: P2WSH or Taproot, SHA-256 + CLTV)
- `SOST` &harr; `ETH`  (EVM HTLC contract on Ethereum mainnet)
- `SOST` &harr; `BNB`  (same EVM contract redeployed on BNB Chain)

**Category B &mdash; issuer-risk** (the underlying token can be frozen by its
issuer at any time; cryptographic atomicity holds on the SOST side but
the counterparty side may become uncollectible mid-swap):

- `SOST` &harr; `USDT`  (Tether Limited can freeze any USDT address)
- `SOST` &harr; `USDC`  (Circle operates an active blacklist)
- `SOST` &harr; `PAXG`  (Paxos can freeze; physical-gold custody risk)
- `SOST` &harr; `XAUT`  (TG Commodities can freeze; physical-gold custody risk)

**Operational rule:** for Category B, use small amounts (amounts you are
willing to lose entirely if the issuer freezes mid-swap). For larger
amounts, prefer Category A.

**Activation status:** NOT LIVE. The activation gate
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` is currently `INT64_MAX` (sentinel
OFF). It will be flipped to `V14_HEIGHT` (15,000) only after:

1. Phase 4A &mdash; BTC HTLC builder
2. Phase 4B &mdash; Solidity HTLC contract
3. Phase 4C &mdash; cross-chain coordinator
4. Phase 4D &mdash; OTC UI integration (this doc + asset list)
5. End-to-end testnet validation
6. External cryptographic + economic review

are all GREEN. See `docs/reviews/ATOMIC_SWAP_PRE_ACTIVATION_REVIEW.md`.
