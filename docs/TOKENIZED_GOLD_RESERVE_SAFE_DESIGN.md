# Tokenized Gold Reserve — Ethereum Safe Multisig Design (NOT CREATED)

**Status: NOT CREATED.** This is a technical design document only. No Safe exists,
no keys have been generated, no funds are held, and nothing here is deployed. It
specifies *how* the tokenized-gold custody vault would be built so that, once the
preconditions are met (§11), the reserve is credibly **multi-authorised,
time-delayed, and destination-constrained** — not merely "a multisig".

Related: [`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md),
[`GOLD_ACCUMULATION_AUCTION_PROGRAM.md`](GOLD_ACCUMULATION_AUCTION_PROGRAM.md).

---

## 1. Purpose

The **Tokenized Gold Reserve** is the Ethereum-mainnet vault that receives and holds
the tokenized gold (PAXG / XAUT) obtained when the protocol converts a small,
governed amount of Gold Vault SOST (see the Auction Program). It is the *destination*
of the conversion rails — **never an AMM, never a bridge, never wrapped SOST**.

Design goals, in priority order:
1. **No single point of failure** — no one key can move assets.
2. **Immobility by default** — the reserve sits sealed; moving anything is slow,
   constrained, and public.
3. **Transparency** — address, balances, modules and every operation are public.
4. **Recoverability** — key loss/compromise is survivable without losing the reserve.

---

## 2. Why a multisig is not enough (the three immobility layers)

A bare m-of-n multisig makes funds *multi-authorised*, not *immobile*. This design
stacks three independent layers so that even a colluding quorum is constrained:

| Layer | Component | What it guarantees |
|---|---|---|
| **Authorisation** | Safe **3-of-5** | ≥3 independent keys needed for any action |
| **Time** | Zodiac **Delay Modifier** (timelock) | Every outflow is queued and can only execute after a mandatory cooldown |
| **Scope** | Zodiac **Roles Modifier** + **Safe Guard** | Outflows are only possible to a pre-committed allowlist of destinations/functions; everything else reverts |

Inbound deposits need none of this — anyone can *send* gold to the vault. The layers
only ever gate **outflows**.

---

## 3. Architecture

- **Base wallet:** [Safe{Wallet}](https://safe.global/) (formerly Gnosis Safe) on
  **Ethereum mainnet**. Audited, the most battle-tested treasury contract.
- **Threshold:** **3 of 5** owners.
- **Modules (Zodiac):**
  - **Delay Modifier** — a timelock cooldown (proposed: **72 h**, tunable) on any
    transaction routed to spend assets. During the cooldown any owner can cancel.
  - **Roles Modifier** — scopes the Safe so the only permitted outflow calls are
    `transfer(PAXG|XAUT, → allowlisted destination)`. Calls outside the policy revert.
  - **Safe Guard (Scope Guard)** — a transaction guard as a belt-and-braces check
    that blocks any tx not matching the destination/asset allowlist.
- **No cross-chain bridge, no wrapped SOST, no custom minting.** The Safe only ever
  *holds* standard ERC-20 gold tokens.

```
             deposit (no signatures)                 governed outflow (rare)
OTC / Atomic ───────────────────────►  SAFE 3/5  ──► Roles allowlist? ─► Delay 72h ─► execute
Swap settlement (PAXG / XAUT)          (sealed)      (else revert)       (cancellable)
                                          │
                                          └────────► Protocol Registry (public record)
```

---

## 4. Signers (owners) and key management

Five owners, threshold three, chosen so **no single person or location holds a quorum**:

| # | Holder (role) | Key type | Location |
|---|---|---|---|
| 1 | Founder — primary | Hardware wallet (Ledger/Trezor) | Location A |
| 2 | Founder — secondary | Hardware wallet | Location B (separate) |
| 3 | Independent trustee | Hardware wallet | Independent party |
| 4 | Independent trustee / advisor | Hardware wallet | Independent party |
| 5 | Cold backup | Hardware wallet, air-gapped | Sealed off-site |

Rules:
- **Every owner key is a hardware wallet.** No hot/browser keys as owners.
- **No entity controls ≥3 keys.** The founder holds at most 2 → cannot move funds
  alone, by construction.
- **Seed backups** stored separately from the devices, in distinct secure locations.
- **Key rotation** (add/remove owner, change threshold) is itself a Safe transaction
  and therefore also passes the Delay timelock — an attacker cannot silently swap
  owners.

---

## 5. Assets held

| Token | Issuer | Mainnet contract (verify at setup) | Role |
|---|---|---|---|
| **PAXG** | Paxos (Pax Gold) | `0x45804880De22913dAFE09f4980848ECE6EcbAf78` | **Primary** |
| **XAUt** | Tether (Tether Gold) | `0x68749665Ff8D2d112Fa859AA293F07A622782F38` | Secondary / optional |

> ⚠️ These addresses are the current Etherscan-verified mainnet contracts, but they
> **MUST be independently re-verified** against the official issuer at setup time and
> pinned into the Roles allowlist. A wrong token address is catastrophic. Sources:
> [PAXG on Etherscan](https://etherscan.io/token/0x45804880de22913dafe09f4980848ece6ecbaf78),
> [XAUt on Etherscan](https://etherscan.io/token/0x68749665ff8d2d112fa859aa293f07a622782f38).

PAXG is primary because it is NY-DFS-regulated, redeemable, and carries monthly
attestations — the best fit for an auditable reserve. Both are ERC-20s native to
Ethereum mainnet with redemption and deepest liquidity there — the reason the vault
lives on mainnet despite gas: it is meant to sit sealed and rarely move.

---

## 6. Operations

**Inbound (the normal path).** Anyone — the OTC/atomic-swap counterparty — sends
PAXG/XAUT to the Safe address. No signatures, no modules involved. The Auction
Program requires the gold to land here *before* any SOST is released.

**Outbound (rare, heavily gated).** Requires ALL of:
1. **3-of-5** owner signatures.
2. Destination on the **Roles allowlist** (e.g. a redemption address / a successor
   custody address) — otherwise the call reverts.
3. **Delay timelock** elapsed (72 h), during which any owner can **cancel**.
4. Passes the **Safe Guard** policy check.

Legitimate outbound use cases: redemption of tokenized gold to physical, a governed
reserve rebalance, or migration to a successor vault. **Not** routine spending.

**Emergency handling.** There is no "instant drain" to stop, because the Delay
timelock means every outflow is visible and cancellable for 72 h. A compromised
key short of quorum can do nothing. A compromised quorum still faces the timelock +
public visibility, giving honest owners time to cancel and rotate keys.

---

## 7. Transparency

- The **Safe address** and all **module addresses** are published on the public
  Gold & Metals Reserve page.
- **Balances** are readable on-chain by anyone (Etherscan / a live dashboard).
- **Every** inbound and outbound operation is recorded in the **Protocol Registry**
  (SOST txid · EVM txid · token · amount · price/ref · vault address · new balance).
- Optional: periodic attestation reconciling the on-chain balance with the Registry.

---

## 8. Security considerations

- **No bridge, no wrapped SOST** — eliminates the single largest class of crypto
  losses. SOST↔gold conversion uses the existing SOST-native ↔ EVM atomic-swap HTLC.
- **Blind-signing** is the main residual risk: owners MUST verify calldata on the
  hardware device and **simulate every transaction** (e.g. Tenderly / Safe's
  simulation) before signing. The Roles/Guard allowlist is the backstop if a signer
  is tricked.
- **Phishing / fake Safe UI** — owners bookmark the official Safe app and verify the
  chain ID, Safe address, and module addresses out-of-band.
- **Module risk** — Zodiac modules are audited; their configuration (allowlist,
  delay) is itself only changeable through a timelocked Safe tx.
- **Redundancy** — 3-of-5 tolerates the loss of up to 2 keys without losing access
  and the compromise of up to 2 keys without loss of funds.

---

## 9. Costs

- One-time: gas to deploy the Safe + Zodiac modules and configure the allowlist.
- Ongoing: **no custody fee** (Paxos charges none; the reserve simply holds the
  token). On-chain PAXG transfers carry Paxos's small on-chain fee; XAUt has none.
  Because the vault rarely moves, mainnet gas is not a material cost.

---

## 10. Setup runbook (FUTURE — not executed here)

1. **Sepolia dry-run first.** Deploy the Safe (3/5) + Delay + Roles + Guard on
   testnet. Configure the destination/asset allowlist with test tokens.
2. **Adversarial test.** Confirm: a disallowed destination **reverts**; an allowed
   outflow is **timelocked and cancellable**; owner rotation is **timelocked**;
   sub-quorum signing **cannot** move funds.
3. **Mainnet deploy.** Recreate the exact config; independently verify PAXG/XAUT
   addresses; verify every module address.
4. **Symbolic funding.** Send a tiny PAXG amount, record it in the Protocol Registry,
   confirm the dashboard reflects it.
5. **Publish.** Safe address, module addresses, threshold, allowlist, and policy on
   the public page.

---

## 11. Preconditions before creating the Safe

```
Status: NOT CREATED
Requires:
- signer set agreed + hardware wallets provisioned (5 owners, 3 threshold)
- destination allowlist decided (redemption / successor addresses)
- Delay + Roles + Guard configuration finalised
- Sepolia dry-run passed (adversarial tests green)
- legal / compliance review (custody + MiCA context)
- Protocol Registry live for reserve operations
```

---

## 12. What this design deliberately does NOT do

- No public AMM, no CEX dependency, no bridge, no wrapped SOST.
- No single-key control; the founder alone cannot move the reserve.
- No instant/undelayed outflow; no unconstrained destinations.
- No claim of gold ownership by SOST holders; the reserve belongs to the protocol.
- Nothing here is deployed — it is a design to be dry-run on Sepolia first.
