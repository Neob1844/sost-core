# OTC-3b — EVM leg on testnet (AtomicSwapHTLC.sol)

**Status:** review/testnet only. **NOT deployed, NOT audited, NOT active.** This
guide covers the EVM counterparty contract for SOST↔EVM atomic swaps
(`contracts/atomic-swap/src/AtomicSwapHTLC.sol`) and how to exercise it on a
local Anvil chain or a public testnet (Sepolia / BNB testnet).

> **Safety invariants (unchanged by anything here):**
> - The SOST-side gate `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` stays `INT64_MAX`
>   (OFF). Nothing in OTC-3b touches it.
> - The contract has **no owner, no admin, no upgrade path, no pause, no
>   emergency drain, no privileged role**. The contract *is* the escrow; there
>   is no operator. Funds move **only** via `claim` (preimage) or `refund`
>   (after timeout).
> - **Testnet only.** Do not deploy to mainnet. `foundry.toml` declares no RPC
>   endpoints on purpose — deployment is an explicit operator step with
>   credentials that are NOT in this repo.

---

## 1. Contract summary

`AtomicSwapHTLC` is a minimal, dependency-free Hashed Time-Locked Contract:

| Function | Who | Effect |
|---|---|---|
| `lockNative(swapId, hashlock, refundTime, claimer, refunder)` payable | locker | escrows `msg.value` (ETH/BNB; `token = address(0)`) |
| `lockERC20(swapId, token, amount, hashlock, refundTime, claimer, refunder)` | locker | pulls `amount` via `transferFrom` (USDT/USDC/PAXG/XAUT/any ERC-20) |
| `claim(swapId, preimage)` | anyone | if `sha256(preimage)==hashlock` and `block.number < refundTime`: pays `claimer`, reveals preimage in the `Claimed` event |
| `refund(swapId)` | anyone | if `block.number >= refundTime`: pays `refunder` |

- **Hashlock** = `sha256(preimage)` — identical to the SOST consensus validator
  (R21) and the BTC redeem script, so one preimage unlocks all legs.
- **Timeout** = absolute `block.number` (`refundTime` = T2). The SOST
  `refund_height` (T1) MUST exceed T2 by the wallet's safety margin (the
  contract does NOT enforce cross-chain ordering — that's the wallet's job,
  the OTC-2 orderboard `ValidateOffer`).
- State machine `NONE → LOCKED → {CLAIMED | REFUNDED}`; each terminal once.
- `nonReentrant` + checks-effects-interactions; `receive()`/`fallback()` revert
  to reject accidental plain transfers.

---

## 2. Build & test

forge-std (test framework) is not committed — install it once:

```bash
cd contracts/atomic-swap
forge install foundry-rs/forge-std --no-commit   # or: git clone --depth 1 https://github.com/foundry-rs/forge-std lib/forge-std
forge build
forge test -vv
```

Expected: **52 passed, 0 failed**. The suite covers native + ERC-20 happy
paths, wrong preimage, refund-too-early, claim-after-refund, refund-after-claim,
double-claim/refund, reentrancy (malicious receiver + malicious token), weird
ERC-20s (no-return legacy-USDT shape rejected at lock; fee-on-transfer
documented unsupported), forced-ETH via `selfdestruct` (EIP-6780, state not
corrupted), a runtime no-owner/admin/drain selector probe, balance-conservation
(contract drains to exactly 0), and fuzz over the preimage and the `refundTime`
boundary.

---

## 3. Deploy — local (Anvil)

```bash
anvil &                                   # local chain at 127.0.0.1:8545
cd contracts/atomic-swap
export PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80  # anvil acct 0
forge create src/AtomicSwapHTLC.sol:AtomicSwapHTLC \
  --rpc-url http://127.0.0.1:8545 --private-key $PK --broadcast
# -> Deployed to: 0x...   (record the address as $HTLC)
```

## 4. Deploy — public testnet (Sepolia / BNB testnet)

Use a funded testnet key and the network RPC (NOT stored in the repo):

```bash
# Sepolia
forge create src/AtomicSwapHTLC.sol:AtomicSwapHTLC \
  --rpc-url "$SEPOLIA_RPC_URL" --private-key "$TESTNET_PK" --broadcast --verify
# BNB testnet
forge create src/AtomicSwapHTLC.sol:AtomicSwapHTLC \
  --rpc-url "https://data-seed-prebsc-1-s1.binance.org:8545" --private-key "$TESTNET_PK" --broadcast
```

The same bytecode works on any EVM chain (Ethereum, BNB Chain, and their
testnets). Get testnet ETH/BNB from a faucet first.

---

## 5. Run a swap (cast)

Assume `$HTLC` is the deployed address, the maker knows `secret`, and
`hashlock = sha256(secret)`.

```bash
SECRET=0x00000000000000000000000000000000000000000000000000000000000c0ffee
HASHLOCK=$(cast keccak-256 ...)   # NOTE: hashlock is sha256(secret), compute off-chain to match SOST/BTC
SWAPID=$(cast keccak "swap-1")
RT=$(( $(cast block-number --rpc-url $RPC) + 200 ))   # refundTime = now + 200 blocks (T2)
```

**Lock (native):**
```bash
cast send $HTLC "lockNative(bytes32,bytes32,uint256,address,address)" \
  $SWAPID $HASHLOCK $RT $CLAIMER $REFUNDER --value 0.01ether \
  --rpc-url $RPC --private-key $LOCKER_PK
```

**Lock (ERC-20)** — approve first, then lock:
```bash
cast send $TOKEN "approve(address,uint256)" $HTLC $AMOUNT --rpc-url $RPC --private-key $LOCKER_PK
cast send $HTLC "lockERC20(bytes32,address,uint256,bytes32,uint256,address,address)" \
  $SWAPID $TOKEN $AMOUNT $HASHLOCK $RT $CLAIMER $REFUNDER --rpc-url $RPC --private-key $LOCKER_PK
```

**Claim (reveals the preimage on-chain):**
```bash
cast send $HTLC "claim(bytes32,bytes32)" $SWAPID $SECRET --rpc-url $RPC --private-key $ANY_PK
```

**Refund (after `refundTime`):**
```bash
cast send $HTLC "refund(bytes32)" $SWAPID --rpc-url $RPC --private-key $ANY_PK
```

**Read swap state:**
```bash
cast call $HTLC "getSwap(bytes32)((uint8,address,uint256,bytes32,uint256,address,address))" $SWAPID --rpc-url $RPC
```

---

## 6. Extract the revealed preimage (cross-chain link)

When `claim` confirms, the preimage is in the `Claimed(swapId, preimage, claimer)`
event:

```bash
cast logs --rpc-url $RPC --address $HTLC \
  "Claimed(bytes32,bytes32,address)" --from-block <lockBlock> | cat
# the second (non-indexed) data word is the 32-byte preimage
```

That preimage is the secret the counterparty needs to unlock the **SOST** leg.
Feed it to the OTC-2 watcher, which verifies `sha256(preimage) == hashlock`
(`IngestRevealedPreimage`) and auto-claims the SOST `OUT_HTLC_LOCK` via the
OTC-1 builders. On the SOST side, the OTC-2.5 `gethtlcstatus` RPC then reports
`status: claimed` and echoes the same `revealed_preimage` — symmetric to the
BTC leg (see `V15_OTC_BTC_REGTEST_GUIDE.md`).

Full SOST↔EVM testnet cycle:

```
maker locks EVM (lockNative/lockERC20) ── taker claims EVM with secret ── preimage in Claimed event
        │                                                                        │
        └── maker also locks SOST (OUT_HTLC_LOCK) ◄── watcher reads preimage ────┘
                         │
                         └── watcher claims SOST leg (OTC-1 CLAIM) → gethtlcstatus: claimed
```

The timeout discipline (responder/T2 opens first on the EVM side, initiator/T1
last on SOST, margin ≥ 6) is enforced off-chain by the OTC-2 orderboard before
either leg is locked.

---

## 7. Issuer-freeze warning — USDT / USDC / PAXG / XAUT

These are **centrally-issued tokens**: the issuer (Tether / Circle / Paxos / TG
Commodities) can **freeze/blacklist any address**, including this contract's
balance. If a freeze lands mid-swap:

- The **SOST side still settles correctly** — cryptographic atomicity holds on
  the SOST chain (claim with preimage, or refund after timeout).
- The **EVM side can become uncollectible** until the issuer unfreezes — neither
  `claim` nor `refund` can move frozen tokens (the ERC-20 `transfer` reverts).

This breaks perfect atomicity **at the asset level**, not at the contract level.
The contract is asset-agnostic and correct; the risk is intrinsic to the token.

- **Freezable:** USDT, USDC, PAXG, XAUT → the OTC-2 orderboard
  (`AssetHasIssuerFreeze`) flags every such offer with an `ISSUER_FREEZE_RISK`
  warning (`IssuerFreezeWarning`), and any swap UI MUST surface it before lock.
- **Not freezable (asset-level):** BTC, ETH, BNB, SOST — no issuer can freeze
  the asset itself.

Recommendation surfaced to users: prefer native ETH/BNB or smaller test amounts
for issuer-token legs, and never lock the EVM side first for a freezable token.

---

## 8. Confirmed safety properties

Verified by source review + the runtime test `test_noOwnerFunctionsExist_runtime`:

- **No owner / admin** — no privileged role; `owner()/admin()/pause()/withdraw()/emergencyWithdraw()/upgradeTo()` selectors do not exist.
- **No upgrade** — no proxy, no `delegatecall`, immutable bytecode.
- **No pause** — no circuit breaker.
- **No emergency drain** — no path moves funds except `claim`/`refund` to the recorded `claimer`/`refunder`.
- **Funds move only by claim/refund** — `lock*` is the only inflow; forced ETH (selfdestruct) is orphaned and un-withdrawable by design, never affecting accounted swaps.

---

## 9. What is still NOT done (deferred past OTC-3b)

- Deployment to any public network (testnet deploy is an operator step; mainnet is out of scope entirely).
- **External smart-contract audit** — required before any mainnet consideration.
- SafeERC20 wrapping for no-return / fee-on-transfer tokens (intentionally out of scope for this minimal HTLC; those tokens are rejected/blacklisted at the wallet layer).
- An end-to-end automated SOST↔EVM swap harness (the watcher integration is conceptual here; wiring a live EVM watcher is a later step).
- Flipping `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` — only after the full Phase-4 stack (BTC + EVM + coordinator) plus external cryptographic/economic review.
