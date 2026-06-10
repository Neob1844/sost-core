# OTC-4 — End-to-end SOST↔{BTC,EVM} atomic swap (coordinator)

**Status:** review/testnet only. The OTC-4 **session coordinator** ties the
three already-built legs into one orchestrated, **non-custodial** flow:

1. **SOST HTLC** — OTC-1 consensus + OTC-2 builders + OTC-2.5 `gethtlcstatus`/`listhtlclocks`.
2. **BTC HTLC** — OTC-3a libwally signing (regtest).
3. **EVM HTLC** — OTC-3b `AtomicSwapHTLC.sol` (Anvil / Sepolia / BNB testnet).

> **Hard invariants (unchanged):** the session NEVER signs, broadcasts, holds a
> key, opens a socket, or acts as a custodian; it is a pure decision +
> persistence layer. No central order book is required. The SOST gate
> `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` stays `INT64_MAX` and
> `SOST_BTC_HTLC_SIGNING` stays OFF — the coordinator runs as a dry-run/testnet
> walk-through with no mainnet involvement. Atomicity is **never** promised for
> issuer tokens (USDT/USDC/PAXG/XAUT) — they always carry an issuer-freeze
> warning.

The operator (your wallet) builds and submits each tx with the per-leg
builders; the coordinator only tells you **the next safe action** and remembers
where the swap is across restarts.

---

## 1. Phase machine

```
Created → Offered → Accepted → SostLocked → CounterpartyLocked → ClaimSeen → Claimed → Completed
                       │            │                │
                       │ timeout    │ timeout        │ timeout (pre-claim)
                       ▼            ▼                ▼
                    Expired     RefundReady ───────────────→ Refunded
   any non-terminal ── Failure ──▶ Failed        Corruption ──▶ RecoveryNeeded
```

- **Created→Offered→Accepted** — off-chain offer/accept (validated:
  timeout ordering T2 < T1 with margin ≥ 6, structural sanity, issuer-freeze).
- **Accepted→SostLocked→CounterpartyLocked** — initiator locks SOST first;
  responder locks the counterparty leg second (T2 opens *before* T1).
- **CounterpartyLocked→ClaimSeen** — the initiator claims the counterparty leg
  with the secret, **revealing the preimage on-chain**.
- **ClaimSeen→Claimed→Completed** — each side claims its receiving leg;
  `Completed` once both legs are claimed.
- **RefundReady→Refunded** — if a leg isn't completed before its timeout.
- **RecoveryNeeded** — observed facts don't match the modelled order; stop and
  inspect both legs before acting.

Roles: **Initiator** = maker (holds the secret, gives SOST in the canonical
example, receives the counterparty asset). **Responder** = taker (learns the
secret only when it's revealed on-chain).

---

## 2. The operator tool

`otc-coordinator` (built from `tools/otc_swap_coordinator.cpp`) persists a swap
to a local file and prints the next action. It maps to the conceptual `otc`
commands:

| Conceptual command | Tool invocation |
|---|---|
| `otc offer create` | `otc-coordinator create <file> --role ... --hashlock ... --secret ... --t1 ... --t2 ...` |
| `otc offer inspect` / `otc resume` | `otc-coordinator inspect <file>` (parses the saved file; redacts the secret) |
| `otc accept` | `otc-coordinator observe <file> --event offer-accepted` |
| `otc watch` | `otc-coordinator next <file> --height <H>` |
| `otc claim` | `otc-coordinator observe <file> --event {cp-claim,sost-claim}` (after you submit the claim tx) |
| `otc refund` | `otc-coordinator observe <file> --event {sost-refund,cp-refund}` |
| (preimage seen) | `otc-coordinator observe <file> --event preimage --preimage <hex>` |

Events you feed after verifying them on-chain: `offer-published offer-accepted
sost-locked cp-locked preimage sost-claim cp-claim sost-refund cp-refund
timeout failure corruption`.

The session file stores the secret in **cleartext** (the initiator needs it
across restarts); the file is flagged with a `# WARNING:` header. Keep it local
and protected; `inspect` output is redacted (`secret=REDACTED`) and safe to
share.

---

## 3. Exact flows

The cross-chain glue is one shared `hashlock = sha256(secret)` and the timeout
discipline T2 (counterparty refund) < T1 (SOST refund) − margin. Compute
`hashlock` off-chain and use it identically on every leg.

### 3.1 SOST ↔ BTC (regtest)

1. **Offer/lock setup** — maker picks `secret`, `hashlock`, T1 (SOST
   `refund_height`), T2 (BTC `refundTime`, opens first). `otc-coordinator create`.
2. **SOST lock** — maker builds the SOST `OUT_HTLC_LOCK` with the OTC-2 CLI
   (`sost-cli createhtlclock ...`), submits it; on confirmation
   `observe --event sost-locked`. Watch state with OTC-2.5 `gethtlcstatus`.
3. **BTC lock** — responder funds the P2WSH from `V15_OTC_BTC_REGTEST_GUIDE.md`;
   `observe --event cp-locked`.
4. **Claim BTC** — maker `SignBtcHtlcClaim` (OTC-3a), broadcasts; the preimage
   is now in the BTC witness. `observe --event cp-claim`.
5. **Reveal → SOST claim** — responder reads the preimage from the BTC witness,
   `observe --event preimage --preimage <hex>`, then claims SOST
   (`sost-cli claimhtlc ...`); `observe --event sost-claim` → `Completed`.

### 3.2 SOST ↔ ETH (Anvil)

Same shape; the counterparty leg is `AtomicSwapHTLC.sol` on a local Anvil chain
(see `V15_OTC_EVM_TESTNET_GUIDE.md`): `lockNative` (cp-locked), `claim` reveals
the preimage in the `Claimed` event (cp-claim), responder ingests it and claims
SOST.

### 3.3 SOST ↔ ERC-20 (mock)

Identical, with `lockERC20` (approve + lock) on the EVM side. The contract is
asset-agnostic; the swap logic is unchanged.

---

## 4. GO / NO-GO checklist (before locking ANY funds)

- [ ] **Timeout ordering** — T2 < T1 with margin ≥ 6 (the coordinator refuses
      to create the session otherwise: `TIMEOUT_ORDER_INVALID`).
- [ ] **Hashlock matches** — the same `sha256(secret)` on all legs; initiator's
      secret verified against the offer hashlock at `create`.
- [ ] **Roles correct** — initiator locks SOST first; responder locks second.
- [ ] **Issuer-freeze** — if the counterparty asset is USDT/USDC/PAXG/XAUT, the
      session flags `ISSUER_FREEZE_RISK`; acknowledge it (see §6).
- [ ] **Testnet only** — SOST gate OFF, BTC on regtest, EVM on Anvil/testnet;
      no mainnet RPC.
- [ ] **Margin still valid at lock time** — the responder must NOT lock once T2
      is reached (the coordinator's `next` says so).

NO-GO if any box is unchecked. The coordinator's `next` action surfaces the
relevant one at each step.

---

## 5. What is automated vs what needs you

**Automated (coordinator):** state tracking, next-action decision, timeout
ordering / margin checks, preimage verification (`sha256`), issuer-freeze flags,
persistence + resume, recovery flagging.

**Manual (you / your wallet):** building and signing each tx (OTC-1/3a/3b
builders), broadcasting it, observing confirmations and reading the revealed
preimage off-chain, then feeding the verified observation back with `observe`.
The coordinator never broadcasts and never holds a key — by design.

A future step (not OTC-4) can wire a live watcher loop that polls
`gethtlcstatus`/`listhtlclocks` and the EVM/BTC RPCs and feeds `observe`
automatically; OTC-4 keeps the human in the loop.

---

## 6. Issuer-freeze (USDT / USDC / PAXG / XAUT)

These tokens can be **frozen by their issuer** (Tether / Circle / Paxos / TG
Commodities), including the HTLC's balance. If a freeze lands mid-swap, the SOST
leg still settles cryptographically but the EVM leg can become uncollectible
until unfrozen — atomicity breaks **at the asset level**. The session sets
`issuer_freeze_risk` and emits `ISSUER_FREEZE_RISK`; BTC/ETH/BNB/SOST have no
asset-level freeze. Never lock the freezable EVM leg first, and prefer small
test amounts. The coordinator will not suppress this warning.

---

## 7. Status / what remains

- OTC-1…OTC-3b ✅ (SOST + BTC + EVM legs); OTC-4 ✅ (this coordinator).
- Still gated/OFF, no mainnet, no production deploy.
- Remaining before any real use: a live auto-watcher loop, end-to-end testnet
  rehearsals on real BTC-regtest + EVM-Anvil, and an **external cryptographic /
  economic audit** — all well before any discussion of flipping
  `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`.
