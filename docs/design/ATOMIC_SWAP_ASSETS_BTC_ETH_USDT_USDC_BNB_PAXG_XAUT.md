# Atomic Swap — Asset-Specific Design (Phase 2)

**Status:** design only. No code exists yet for any of these counterparty
legs. The SOST side is gated by
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (OFF).

This document defines the per-asset integration plan, including the
**trust profile** for each asset. Different assets give different
levels of atomicity: BTC is the cleanest trust-minimized path; the
ERC-20 stablecoins (USDT, USDC) and the gold tokens (PAXG, XAUT) carry
issuer-freeze risk that means the swap is "atomic only as long as the
issuer does not intervene".

The OTC user-experience surface must distinguish these two categories
visibly so users understand the actual trust profile of each path.

---

## Asset overview

| Asset | Settlement chain | Mechanism | Trust-minimized? | Issuer-freeze risk? |
|---|---|---|---|---|
| BTC   | Bitcoin                 | Bitcoin Script HTLC (P2WSH / P2TR) | YES | no |
| ETH   | Ethereum                | Solidity HTLC contract             | YES | no |
| BNB   | BNB Chain (EVM)         | Solidity HTLC contract             | YES | no (chain-level; BNB itself is not frozen by issuer) |
| USDT  | Ethereum / Tron         | Solidity HTLC contract             | partial | **YES** (Tether can freeze) |
| USDC  | Ethereum                | Solidity HTLC contract             | partial | **YES** (Circle can freeze) |
| PAXG  | Ethereum (ERC-20)       | Solidity HTLC contract             | partial | **YES** (Paxos can freeze) |
| XAUT  | Ethereum (ERC-20)       | Solidity HTLC contract             | partial | **YES** (Tether Gold issuer can freeze) |

The UI must label the "partial" assets explicitly. See Section 8.

---

## 1. BTC — Bitcoin script HTLC

**Pattern.** Standard hashed-time-locked contract using
`OP_IF / OP_HASH256 / OP_EQUALVERIFY / OP_CHECKSIG / OP_ELSE / OP_CSV /
OP_CHECKSIG / OP_ENDIF`. Deployed via P2WSH (segwit v0) or via a tap
leaf (segwit v1 / Taproot) for slightly lower fees.

**Hash.** SHA-256 of the preimage. Bitcoin's `OP_HASH256` is actually
double-SHA-256, so the wallet uses `OP_SHA256` to match SOST exactly.

**Timeout.** Bitcoin enforces timeouts via `OP_CSV` (relative
sequence) or `OP_CLTV` (absolute height). For atomic-swap the absolute
height form (`OP_CLTV`) is preferred because it matches the SOST
absolute-height `refund_height` design.

**Confirmation safety.** Bitcoin re-orgs of depth >= 6 are statistically
extremely rare; safety margin on `T1 > T2` should account for 6 blocks
on Bitcoin (~60 min) plus 6 blocks on SOST (~60 min at 10-min target),
i.e. `T1 - T2 >= ~12 blocks`. Wallet enforces.

**Trust profile.** No issuer. As trust-minimized as cryptography allows.

---

## 2. ETH — Ethereum HTLC smart contract

**Pattern.** A minimal Solidity contract with three public functions:

```
function lock(bytes32 hashlock, uint256 refundHeight, address claim, address refund) external payable;
function claim(uint256 lockId, bytes32 preimage) external;
function refund(uint256 lockId) external;
```

The contract holds the locked ETH in escrow. `claim()` checks
`sha256(preimage) == hashlock` and `block.number < refundHeight`,
then sends ETH to `claim`. `refund()` checks `block.number >=
refundHeight`, sends to `refund`.

**Hash.** SHA-256 (precompile at address 0x02), matching SOST.

**Timeout.** Solidity reads `block.number`. Same absolute-height
discipline as SOST.

**Confirmation safety.** Post-merge Ethereum re-org probability is
near-zero past 32-slot finality (~6 min). Suggested margin: at least 2
epochs (~12 min) past `T2` for `T1`.

**Reference.** SOST already maintains `SOSTEscrow.sol` (Model B). The
HTLC contract is a SISTER deployment, not a modification of
SOSTEscrow.sol. The two contracts coexist; SOSTEscrow.sol stays the
PoPC custody-evidence contract; the new HTLC contract is exclusively
for atomic swaps.

**Trust profile.** No issuer. Trust-minimized.

---

## 3. BNB — BNB Chain (EVM-compatible)

**Pattern.** Identical to the ETH HTLC contract (BNB Chain is
EVM-compatible). The contract is redeployed on BNB Chain at a
canonical address documented per release.

**Hash.** SHA-256 (precompile available on BNB Chain).

**Timeout.** `block.number` on BNB Chain. BNB Chain blocks are ~3
seconds, so `T2 - T1` arithmetic must use BNB-Chain block heights for
the BNB leg, NOT seconds. The wallet performs the unit conversion.

**Trust profile.** BNB itself is not subject to issuer freeze at the
asset level. The BNB Chain is operated by Binance, which is a more
centralized governance model than Bitcoin or Ethereum, but the BNB
token itself is not freezable in the way USDT/USDC are.

---

## 4. USDT — Tether (ERC-20)

**Pattern.** Solidity HTLC contract holding the USDT token approval +
`transferFrom`. The `lock()` step requires the user to first `approve`
the HTLC contract to spend USDT, then `lock()` calls
`transferFrom(user, htlc, amount)`.

**Hash + timeout:** same SHA-256 + absolute-height pattern as the ETH
HTLC.

**ISSUER FREEZE RISK.** **Tether Limited can freeze any USDT address.**
If Tether freezes the address holding the locked USDT mid-swap:
- the responder cannot `claim()` the USDT.
- the initiator's SOST is still locked under the SOST hashlock.
- the initiator can `refund()` on the SOST side after `T1` (the
  cryptographic atomicity holds for the SOST leg).
- the USDT side is uncollectible by either party until Tether
  manually unfreezes (which may never happen).

**Wallet UI MUST surface this risk explicitly** before any user signs
a USDT atomic-swap LOCK. The "atomic" label must carry an asterisk
referencing this section.

**Mitigation in design.** Limit USDT atomic-swap amounts to amounts
the user is willing to lose if Tether freezes mid-swap; prefer ETH or
BTC for larger amounts. The SOST DEX UI must show "USDT — partial
atomicity, issuer-freeze risk" on any USDT swap path.

---

## 5. USDC — Circle (ERC-20)

**Pattern.** Same as USDT (Solidity HTLC + `transferFrom`).

**Hash + timeout:** same SHA-256 + absolute-height pattern.

**ISSUER FREEZE RISK.** **Circle can freeze any USDC address.** Circle
operates an active blacklist (`isBlacklisted`) and has frozen funds
in the past in response to sanctions and court orders. The risk
analysis is identical to USDT.

**Wallet UI MUST surface this risk explicitly.**

---

## 6. PAXG — Paxos Gold (ERC-20)

**Pattern.** Same as USDT/USDC. PAXG is an ERC-20 token from Paxos,
backed 1:1 by physical gold.

**ISSUER FREEZE RISK.** **Paxos can freeze any PAXG address.** In
addition, the underlying physical gold is custodied by Paxos and is
subject to the legal jurisdiction of Paxos's custody location.

**Wallet UI MUST surface this risk explicitly.**

---

## 7. XAUT — Tether Gold (ERC-20)

**Pattern.** Same as USDT/USDC/PAXG.

**ISSUER FREEZE RISK.** **TG Commodities Limited (the XAUT issuer)
can freeze any XAUT address.** Similar custody risk to PAXG.

**Wallet UI MUST surface this risk explicitly.**

---

## 8. UI distinction — load-bearing

The SOST DEX / OTC UI must split atomic-swap paths into two categories:

**Category A — TRUST-MINIMIZED**
- SOST ↔ BTC
- SOST ↔ ETH
- SOST ↔ BNB (chain-governance caveat noted, but no asset-level freeze)

**Category B — ISSUER-RISK**
- SOST ↔ USDT  (Tether can freeze)
- SOST ↔ USDC  (Circle can freeze)
- SOST ↔ PAXG  (Paxos can freeze; physical-gold custody risk)
- SOST ↔ XAUT  (TG Commodities can freeze; physical-gold custody risk)

The UI MUST NOT claim "perfect atomicity" for Category B. Suggested
label:

> Atomic swap with issuer-freeze risk. The cryptographic mechanism is
> the same as the trust-minimized swaps, but the underlying token can
> be frozen by its issuer at any time, which can break the atomic
> property mid-swap on the counterparty leg. Use small amounts; for
> larger amounts prefer SOST ↔ BTC or SOST ↔ ETH.

---

## 9. Implementation order

When Phase 3 lands (V14 or later), the asset legs should be enabled in
this order:

1. **BTC** — cleanest, oldest pattern, most external review available.
2. **ETH** — second-cleanest, reuses SOSTEscrow.sol experience.
3. **BNB** — straightforward EVM redeploy after ETH leg.
4. **USDT** + **USDC** — add the freeze-risk warning UI first; never
   ship these without the warning.
5. **PAXG** + **XAUT** — add separately; the physical-gold custody
   risk warrants its own explicit warning beyond the generic
   freeze-risk warning.

---

## 10. Out of scope for V13

All of this. V13 ships only the activation constant (INT64_MAX), the
helper function (never called), and these design docs. No counterparty
contracts are deployed, no wallet integration exists, no UI is wired
to live swap execution. The OTC page surface lives in the previously
committed feat/otc-atomic-swap-v13-design-preview branch and is also
strictly preview-only.
