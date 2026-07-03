# Gold & Metals Reserve — Governance Policy

**Status:** read-only policy document. This document describes what the Gold &
Metals Reserve **is today** and how governed spending is **designed to work in the
future**. It activates nothing, moves no funds, and changes no consensus rule.

**One-line summary:** The Gold Vault accumulates SOST today. Governed spending is
not active. No SOST from the vault is currently being sold or moved, and no
tokenized-gold reserve has been created yet.

---

## 1. Current state (what is and is not active)

| Component | State | Enforced by |
|---|---|---|
| **SOST Gold Vault — accumulation** | **ACTIVE** since genesis | Consensus (coinbase rules CB5/CB6) |
| **Governed spending from the vault** | **NOT ACTIVE** | Deferred — activation height `INT64_MAX` on mainnet |
| **Tokenized Gold Reserve (Ethereum Safe)** | **NOT CREATED** | Off-chain; no contract exists yet |
| **PAXG / XAUT held in reserve** | **0 / pending** | — |
| **Governance gates G1–G5** | **DEFERRED** | Sentinel-disabled; planned for V15 (block 20,000) |
| **Public Protocol Registry of operations** | **PREPARED (empty)** | No operations executed yet |

- The Gold Vault address is fixed at consensus level:
  `sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d`.
- Every valid block pays exactly 25% of the block subsidy (`q = reward // 4`) into
  that vault. A block that does not is rejected. This is the **only** part of the
  reserve system that is live.
- The **spend** side is scaffolding + audit only. The classifier and Slice-1
  validator helpers exist and are unit-tested, but on mainnet they are wired behind
  `GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX`, so consensus behaviour is identical to
  having no spend rule at all. Nothing can be spent from the vault today.

---

## 2. The governance gates, explained simply (G1–G5)

These are the consensus-level checks a future Gold Vault spend must pass. Today
they are all deferred (disabled) on mainnet.

- **G1 — Purpose whitelist.** A spend may only go to a pre-committed reserve
  destination (e.g. an OTC/conversion address). Anything else is rejected.
- **G2 — Dual whitelist cross-check.** The destination list is committed in **two**
  independent places that must agree byte-for-byte; any mismatch fails closed.
- **G3a — Per-spend cap.** No single spend may exceed a fixed fraction of the vault
  balance.
- **G3b — Accumulated cap / rate-limit.** A minimum number of blocks must pass
  between spends, so the vault cannot be drained in a burst. **This is the current
  technical blocker** (see §3).
- **G4 — Miner signaling.** A non-trivial spend must be approved by miner block
  signaling over a fixed window (BIP9-style, Sybil-resistant via PoW cost).
- **G5 — Transitional Guardian veto.** A strictly temporary, signed veto that can
  only **block** a spend, never force one. Silence = accept. It auto-disconnects
  forever at a hardcoded height and can never be re-enabled.

## 3. G3b is the blocker before any activation

The per-spend cap (G3a) is wired; the **rate-limit (G3b) is not**. The validator
needs to know how many blocks have passed since the last vault spend, which
requires a new `gold_vault_last_spend_height` field on the stored block — a schema
change that lands in a separate, tested commit. Until G3b is wired and cross-
validated, **no responsible activation of governed spending is possible**. The
helper is unit-tested for correctness; it is simply not called by consensus yet.

---

## 4. How a future sale would work (design, not active)

When (and only when) governance, caps, legal/compliance and a runbook are all in
place, a single reserve operation would flow like this:

1. **Proposal.** "Sell X SOST from the Gold Vault to acquire Y PAXG/XAUT."
2. **Timelock.** A mandatory delay before the operation can execute.
3. **Caps.** G3a per-spend cap + G3b accumulated rate-limit must pass.
4. **Miner signaling (G4).** The network approves the spend by block signaling.
5. **Guardian veto window (G5).** A temporary guardian may veto; silence = accept.
6. **Execution — OTC / Atomic Swap.** Founder-controlled, small size, agreed
   reference price. **No public AMM.** SOST is not wrapped: the existing SOST-native
   ↔ EVM Atomic Swap (HTLC) is the rail, so there is no bridge risk.
7. **Custody.** The received PAXG/XAUT lands in the Ethereum Safe multisig and is
   sealed.
8. **Public registry.** Every field is published (see §6).

---

## 5. Two vaults, two responsibilities

- **SOST Gold Vault** — lives on the SOST chain, receives the 25% emission, can only
  ever move SOST through Gold Vault Governance.
- **Tokenized Gold Reserve** — will live on **Ethereum mainnet** as a **Safe
  multisig (3/5)** with a **timelock**, a **whitelist of destinations**, and a
  **public dashboard**. No single key should be able to move reserve assets. The
  goal is a reserve that is multi-authorised **and** time-delayed **and**
  destination-constrained — not merely multisig.

**Asset policy:** **PAXG primary** (Paxos; NY-regulated, redeemable, monthly
attestations — best fit for an auditable reserve), **XAUT secondary/optional** (for
liquidity diversification). No more than these two initially.

**Why Ethereum mainnet initially?** PAXG and XAUT are ERC-20 tokens native to
Ethereum mainnet, their redemption and deepest liquidity are on mainnet, and Safe
plus the surrounding custody/audit tooling is the most battle-tested there. Because
the reserve is meant to sit sealed and rarely move, mainnet gas is not a meaningful
cost. References: Paxos PAXG (paxos.com/pax-gold), Safe (safe.global).

**Why not a direct SOST/PAXG or SOST/XAUT AMM pair?** SOST is its own L1, not an
ERC-20. A native AMM pair would require wrapping SOST via a bridge, and bridges are
the single largest source of losses in crypto. So SOST/PAXG and SOST/XAUT are
**conversion rails (OTC / Atomic Swap)**, not a vault and not a live AMM.

---

## 6. Public Protocol Registry (prepared, empty)

Every future reserve operation will be published with:

- SOST txid
- EVM (Ethereum) txid
- token received (PAXG / XAUT)
- amount
- price / reference used
- vault address (Ethereum Safe)
- resulting balance
- notes / status

**No tokenized-gold reserve operations have been executed yet.**

---

## 7. What will not happen before activation

No SOST will be sold or moved from the Gold Vault until **all** of the following
are true: governance gates active (incl. G3b), per-spend + accumulated caps set, a
destination whitelist committed, a timelock in place, miner signaling wired, the
Ethereum Safe created, legal/compliance cleared, and an operational runbook
published. Until then: accumulation only.
