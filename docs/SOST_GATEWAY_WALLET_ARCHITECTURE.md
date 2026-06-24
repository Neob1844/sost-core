# SOST Payment Gateway — Wallet Architecture (design, OFF by default)

> Status: **DESIGN ONLY.** Nothing in this document is activated. Every surface ships behind
> a feature flag defaulting to `false`. No consensus change is introduced by HOLD/PAY/ESCROW.
> Author: NeoB. License: MIT.

## 0. One sentence

A single **SOST Gateway** panel inside the wallet that turns SOST into three things —
a **key** (HOLD), a **means of payment** (PAY) and a **guarantee** (ESCROW) — plus an
advanced **SWAP** on/off-ramp that uses Atomic Swap as a liquidity bridge, not as the
checkout.

---

## 1. The core insight: four buttons, two engines

SOST is a Bitcoin-derived UTXO chain (vendored libwally-core, `src/script.cpp` script engine,
`sost1` P2PKH / `sost3` P2SH addresses). Because of that, the four user-facing modules collapse
onto **two** underlying engines:

| Engine | What it does | Powers | Moves funds? |
|---|---|---|---|
| **E1 — Sign + balance read** | Wallet signs a challenge; API reads on-chain balance | **HOLD** | No |
| **E2 — Script-lock (P2SH: hashlock + timelock + multisig)** | Lock UTXOs to a redeem script; spend by release / refund / hashlock | **ESCROW**, SOST-leg of **SWAP**, PoPC Model-A bond | Yes |

`PAY` is the **degenerate case of E2** — a plain P2PKH send with no script. So:

> **ESCROW and SWAP are the same machine with a different lock script.**
> - SWAP = HTLC whose unlock is a **hashlock** shared cross-chain (atomic with the ETH/BNB leg).
> - ESCROW = the same P2SH, unlock = **beneficiary-sig (release) OR timelock (refund) OR arbiter (dispute)**, no cross-chain hashlock.

Consequence: we do **not** build escrow as a new subsystem. We build **one** "SOST script-lock
builder" (redeem-script + claim/refund/dispute spend paths) and expose the four modules as presets.

---

## 2. What the codebase already gives us (V14)

| Capability | Status | Where |
|---|---|---|
| HD wallet, `sost1` derivation, build/sign/broadcast tx, UTXO select, change | EXISTS | `website/sost-wallet.html`, `src/hd_wallet.cpp`, `src/tx_signer.cpp` |
| Multisig P2SH (`sost3`, 2-of-3), PSBT offline signing | EXISTS | `website/sost-wallet.html`, `src/psbt.cpp`, `src/script.cpp` |
| Script opcodes for HTLC: `OP_SHA256`, `OP_HASH160`, `OP_CHECKMULTISIG`, P2SH eval, CLTV via nSequence | EXISTS (consensus-valid) | `src/script.cpp`, `src/atomic_swap_btc.cpp` (BIP-199 redeem builder) |
| Sign-message for HOLD | EXISTS but **DISABLED** | `website/sost-wallet.html:6425` (`GEA_SIGN_ENABLED=false`) |
| Access API (HOLD/PAY backend, flags OFF) | DEPLOYED OFF | `apps/access-api` (GeaSpirit infra), console panel on VPS `/opt/ree-locator` |
| EVM Atomic Swap HTLC (ETH/BNB/USDT/USDC/PAXG/XAUT) | LIVE V14 | `contracts/atomic-swap/src/AtomicSwapHTLC.sol` |
| **SOST-native swap leg (BTC-style HTLC signing)** | **STUB — gated to V15** | `src/atomic_swap_btc_signing.cpp` |
| PoPC bond (`BOND_LOCK` UTXO, dynamic sizing 12–25%) | EXISTS (app-layer, non-consensus) | `src/popc.cpp` |
| PoPC Model-B Gold Vault (XAUT/PAXG, no admin key) | EXISTS | `contracts/SOSTEscrow.sol` |
| RPC: `listunspent`, `sendrawtransaction` (via proxy), `gettxout`, `validateaddress`, `estimatefee` | EXISTS | `src/sost-rpc.cpp`, `ops/sost-rpc-proxy.py` |

**Bottom line:** HOLD, PAY and SOST-native ESCROW are buildable **on V14 today** (script is already
consensus-valid). SWAP's SOST leg and BTC are **V15**.

---

## 3. Feature flags (all default `false`)

Wallet (client) and API read the same names:

```
SOST_GATEWAY_ENABLED            = false   # master; hides the whole panel
SOST_GATEWAY_HOLD_ENABLED       = false
SOST_GATEWAY_PAY_ENABLED        = false
SOST_GATEWAY_ESCROW_ENABLED     = false
SOST_GATEWAY_ATOMIC_SWAP_ENABLED= false
```

Backend (GeaSpirit access-api, already present, OFF): `GEA_ACCESS_API_ENABLED`,
`GEA_HOLDING_UNLOCK_ENABLED`, `GEA_PAY_WITH_SOST_ENABLED`. Rollback = set any flag to `0`.

---

## 4. Module specs

### 4.1 HOLD — prove you hold SOST (Engine 1, no funds move)

Flow:
1. API issues a `nonce` bound to the address (already in `access-api/auth.py`).
2. Wallet shows a **human-readable** challenge message; user signs (enable `GEA_SIGN_ENABLED`).
3. Wallet exports a proof JSON: `address, pubkey, signature_der, message, message_sha256, timestamp`.
4. API verifies signature (real secp256k1) + reads balance (`getaddressbalance`) → grants a
   short-lived entitlement token (HMAC, masked to last 6).

Rules: never ask for seed/private key; never store the signature in `localStorage`; the token
**expires** (re-validate every N hours) so moving funds after unlock can't keep access open.

Tiers (example): 100 SOST → light downloads · 1 000 → advanced reports · 10 000 → limited API / early access.

### 4.2 PAY — buy access with SOST (Engine 2, degenerate: plain send)

Flow:
1. GeaSpirit/API creates a **payment intent**: `merchant, concept, amount_sost, destination,
   memo/reference, expires_at, required_confirmations`.
2. Wallet renders a strong confirmation screen → builds, signs, broadcasts a normal tx.
3. Wallet shows `txid` + an exportable **receipt JSON** (no secrets) + a "Verify payment status" button.
4. API verifies the tx pays `destination` ≥ `amount_sost` with ≥ `required_confirmations` and the
   `txid` is unused → grants access. (`payments.evaluate_payment` already models
   paid/underpaid/wrong_destination/insufficient_confirmations/reused_tx/expired.)

Tiers (example): 25 SOST → mine report · 100 → country/mineral ranking · 500 → temporary premium dataset.

**Verification dependency (flag in roadmap):** today the public RPC exposes `getrawtransaction`
for the **mempool only** and `gettxout` for the UTXO set; there is no chain-history
`gettransaction`. PAY verification must therefore either (a) watch the destination via
`gettxout`/balance-delta + confirmations, or (b) add a `txindex`-backed
`getrawtransaction <txid>` from chain. **Decide before PAY goes live.**

### 4.3 ESCROW — lock SOST as a guarantee (Engine 2, native P2SH)

Native SOST escrow as a P2SH redeem script. **No new consensus** — reuses `OP_CHECKMULTISIG` /
hashlock / CLTV already valid in `src/script.cpp`. Two canonical templates:

- **2-of-3 with arbiter** (marketplace / data-room / B2B): `2 of {payer, beneficiary, arbiter}`,
  plus a CLTV refund-to-payer branch after `expiry`. Release = payer+beneficiary (happy path) or
  arbiter+one party (dispute). This is the **wallet's existing sost3 multisig + a timelock branch**.
- **Hashlock + timelock HTLC** (when tied to an event/preimage, incl. the SWAP leg): beneficiary
  spends with preimage before `expiry`; payer refunds after.

Spec object (design, not consensus):
```
escrow_id, payer, beneficiary, amount_sost, purpose,
expiry_height, release_condition, refund_condition, optional arbiter,
status ∈ {draft, locked, released, refunded, expired, disputed}
```
Wallet UX: **Lock**, **Release**, **Refund**, **Dispute** — built on PSBT so the parties co-sign
offline. Claiming the hashlock branch is the one genuinely new wallet spend-path (the multisig
release path already works).

Uses: marketplace of mines, opportunity reservation, data-room guarantee, B2B
delivery-or-refund, **PoPC operator bond**.

### 4.4 SWAP — get/sell SOST with ETH/BNB/PAXG/XAUT (Atomic Swap engine)

Atomic Swap is the **liquidity bridge**, surfaced contextually ("Need SOST? Swap"), not the
checkout. Pairs: SOST↔ETH, SOST↔BNB, then audited ERC-20 (USDC first; PAXG/XAUT last). BTC = V15.

Reality check: the **EVM** HTLC is live (`AtomicSwapHTLC.sol`); the **SOST-native** HTLC leg is a
**V15 stub** (`atomic_swap_btc_signing.cpp`). Therefore in V14, SWAP either (a) waits for V15
native HTLC, or (b) runs **assisted-OTC**: EVM side trustless via the contract, SOST side
coordinated/manual. Recommended: ship SWAP as a **link/embed to the atomic-swap console** first,
then in-wallet once V15 lands. PAXG/XAUT only after SafeERC20 + balance-delta + token-specific tests.

The two payment routes the user sees:
- **Has SOST →** PAY directly (fast, cheap, single-chain).
- **No SOST, has ETH/BNB/PAXG →** SWAP into SOST, then PAY. (We never "pay GeaSpirit in ETH" at
  launch — splits accounting, weakens SOST utility, and report-unlock is off-chain anyway.)

---

## 5. Wallet UX (single panel)

```
SOST Gateway
 ├─ Hold Access      Prove you hold SOST. No payment.
 ├─ Pay with SOST    Buy access, reports or credits with SOST.
 ├─ Need SOST? Swap  Swap ETH/BNB/PAXG/XAUT → SOST (Atomic Swap).
 └─ Escrow / Guarantee  Lock SOST for marketplace, PoPC bonds, B2B.
```
The user never sees "HTLC / hashlock / claim / refund" — only: *I have SOST → pay; I don't → swap;
I want a guarantee → escrow.*

---

## 6. PoPC mapping

- **Model A = native SOST bond** via `BOND_LOCK` UTXO (already in `src/popc.cpp`, sizing 12–25%).
  It is a timelocked self-escrow with slashing → **reuses the ESCROW module (Engine 2)**.
- **Model B = Gold Vault** (`contracts/SOSTEscrow.sol`, XAUT/PAXG, no admin key) — already exists.
- **Recommendation:** start PoPC **Model B / no-slashing for normal users**; require **Model A bond
  (native escrow) only for operators/validators** once slashing exists. Don't put any bond into the
  first PAY. PoPC auto-slash/settle is already **V15-gated** (`DTD_POPC_ELIGIBILITY_HEIGHT`).

---

## 7. Security rules (non-negotiable)

- Never request the seed phrase; never transmit a private key; signing stays in-browser.
- No private key / full signature logged or persisted unless strictly needed.
- Strong explicit confirmation before any **sign / pay / lock**.
- Receipts and proofs are exportable **without secrets**; tokens masked to last 6.
- Everything OFF by default; instant rollback by flag.
- ESCROW redeem scripts must always have a **refund branch** (no funds can be permanently stuck).

---

## 8. What needs consensus / V15 vs buildable now

| Item | V14 (now) | V15 / later |
|---|---|---|
| HOLD (sign + balance) | ✅ | — |
| PAY (plain send + verify) | ✅ (needs PAY-verification decision §4.2) | — |
| ESCROW native P2SH (multisig + CLTV refund) | ✅ (script already consensus-valid) | hashlock claim spend-path = new **wallet** code (not consensus) |
| SWAP EVM leg (ETH/BNB/ERC-20) | ✅ contract live | — |
| SWAP SOST-native HTLC leg | ❌ stub | ✅ V15 |
| SWAP BTC | ❌ | ✅ V15 |
| PoPC auto-slash / Gold Vault gates | tracking only | ✅ V15 (`DTD_POPC_*`) |

---

## 9. Phased roadmap

1. **Phase 1 — HOLD.** Flip `GEA_SIGN_ENABLED` in a flagged build; wire the existing access-api;
   ship the proof-export. Lowest risk, no funds move.
2. **Phase 2 — PAY.** Payment-intent UX over existing build/sign/broadcast; decide PAY-verification
   path (§4.2); dummy intents first.
3. **Phase 3 — ESCROW (native).** Script-lock builder + Lock/Release/Refund/Dispute over PSBT;
   2-of-3+CLTV template first, hashlock template second.
4. **Phase 4 — SWAP.** Link/embed atomic-swap console (EVM trustless); move in-wallet at V15.
5. **Phase 5 — PoPC bond.** Operator bond as an ESCROW preset, when slashing lands (V15).

---

## 10. Deliverables of this design pass

- This document.
- Recommended next concrete step: a **flag-gated, hidden wallet skeleton** (`SOST Gateway` panel,
  `SOST_GATEWAY_ENABLED=false`) with the four sub-tabs as inert placeholders + flag/validation unit
  tests — no signing, no network, nothing visible in production.
- Open decisions to confirm before building: (a) PAY verification path (watch-address vs txindex);
  (b) SWAP at launch = embed vs wait-for-V15; (c) PoPC = Model B-first (recommended) vs Model A bond now.
