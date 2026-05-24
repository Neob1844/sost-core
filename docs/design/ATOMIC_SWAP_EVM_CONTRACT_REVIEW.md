# AtomicSwapHTLC.sol — Internal Review (Phase 4B-1)

**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Path:** `contracts/atomic-swap/`
**Status:** internally-tested but **NOT deployed**, **NOT audited** by an
independent third party, and **NOT active** in the SOST protocol flow.
The SOST-side activation gate (`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`)
stays at `INT64_MAX` (sentinel OFF) until external review signs off.

This document records the internal review checks performed on the
contract before commit. It is NOT a substitute for an external audit.

---

## 1. Scope guarantees

  - `SOSTEscrow.sol` — bit-identical, not touched.
  - PoPC DEX surface — not touched.
  - Existing `contracts/test/`, `contracts/script/`, `contracts/popc/`,
    `contracts/security/`, `contracts/interfaces/` — bit-identical.
  - New artifacts live exclusively under `contracts/atomic-swap/`.
  - SOST consensus rules (R17-R24) — bit-identical.
  - SOST gate (`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`) — bit-identical
    (still `INT64_MAX`).

## 2. Functional surface

The contract exposes 4 external functions + 1 view:

| Function | Effect |
|---|---|
| `lockNative(swapId, hashlock, refundTime, claimer, refunder)` payable | Escrows `msg.value` ETH/BNB under hashlock + refundTime |
| `lockERC20(swapId, token, amount, hashlock, refundTime, claimer, refunder)` | Escrows ERC-20 via `transferFrom` |
| `claim(swapId, preimage)` | Releases to `claimer` iff `sha256(preimage) == hashlock` AND `block.number < refundTime` |
| `refund(swapId)` | Releases to `refunder` iff `block.number >= refundTime` |
| `getSwap(swapId) view returns (Swap)` | Read-only swap state |

## 3. State machine

```
NONE ── lockNative / lockERC20 ──▶ LOCKED ── claim ──▶ CLAIMED
                                       │
                                       └─ refund ─▶ REFUNDED
```

State transitions are strictly one-way. Once a swap leaves `LOCKED` it
cannot re-enter; double-claim, refund-after-claim, and claim-after-refund
all revert at `NOT_LOCKED`. Tests verify each case.

## 4. Hard properties (verified by tests)

| Property | Test |
|---|---|
| no owner / admin / pause / upgrade / emergencyWithdraw | `test_noOwnerFunctionsExist_runtime` |
| no `selfdestruct` | grep audit (0 hits in src/) |
| no `delegatecall` | grep audit (0 hits in src/) |
| no `tx.origin` | grep audit (0 hits in src/) |
| no mainnet RPC URL hardcoded | `foundry.toml` declares no `[rpc_endpoints]` |
| no private keys / deploy scripts | grep audit (0 hits) |
| direct ETH transfers rejected | `test_rejectsPlainEthTransfer` |
| reentrancy guard + state-machine guard | `test_reentrancy_blockedByGuardAndStateMachine` |
| failing ERC-20 (returns false on transferFrom) rejected | `test_lockERC20_rejectsFailingToken` |
| zero amount / zero claimer / zero refunder rejected | `test_lockNative_rejectsZero{Amount,Claimer,Refunder}` |
| refund time in past rejected | `test_lockNative_rejectsRefundInPast` |
| duplicate swapId rejected | `test_lockNative_rejectsDuplicateSwapId` |
| wrong preimage rejected | `test_claimNative_rejectsWrongPreimage` |
| claim after timeout rejected | `test_claimNative_rejectsAfterTimeout` |
| refund before timeout rejected | `test_refundNative_rejectsBeforeTimeout` |
| double claim rejected | `test_claimNative_cannotClaimTwice` |
| double refund rejected | `test_refundNative_cannotRefundTwice` |
| refund after claim rejected | `test_refundAfterClaim_rejected` |
| claim after refund rejected | `test_claimAfterRefund_rejected` |
| event emission correctness | `test_event_{LockCreated,Claimed,Refunded}_native` |

Fuzz: `testFuzz_claim_onlyAcceptsExactPreimage` runs 256 random preimages
and confirms each one (other than the canonical) reverts with
`WRONG_PREIMAGE`.

## 5. Test results

```
$ cd contracts/atomic-swap
$ forge build           # compiles clean under solc 0.8.24
$ forge test
[PASS] testFuzz_claim_onlyAcceptsExactPreimage(bytes32) (runs: 256)
[PASS] test_claimAfterRefund_rejected
[PASS] test_claimERC20_happyPath
[PASS] test_claimERC20_rejectsWrongPreimage
[PASS] test_claimNative_cannotClaimTwice
[PASS] test_claimNative_cannotClaimUnknownSwap
[PASS] test_claimNative_happyPath
[PASS] test_claimNative_rejectsAfterTimeout
[PASS] test_claimNative_rejectsWrongPreimage
[PASS] test_event_Claimed_native
[PASS] test_event_LockCreated_native
[PASS] test_event_Refunded_native
[PASS] test_lockERC20_happyPath
[PASS] test_lockERC20_rejectsFailingToken
[PASS] test_lockERC20_rejectsZeroToken
[PASS] test_lockNative_happyPath
[PASS] test_lockNative_rejectsDuplicateSwapId
[PASS] test_lockNative_rejectsRefundInPast
[PASS] test_lockNative_rejectsZeroAmount
[PASS] test_lockNative_rejectsZeroClaimer
[PASS] test_lockNative_rejectsZeroRefunder
[PASS] test_noOwnerFunctionsExist_runtime
[PASS] test_reentrancy_blockedByGuardAndStateMachine
[PASS] test_refundAfterClaim_rejected
[PASS] test_refundERC20_happyPath
[PASS] test_refundNative_cannotRefundTwice
[PASS] test_refundNative_happyPath
[PASS] test_refundNative_rejectsBeforeTimeout
[PASS] test_rejectsPlainEthTransfer

29 tests passed, 0 failed, 0 skipped.
```

## 6. Hashlock cross-chain compatibility

The contract uses `sha256(abi.encodePacked(preimage))` where `preimage`
is a `bytes32`. `abi.encodePacked(bytes32)` emits exactly 32 raw bytes,
so the Solidity SHA-256 precompile call equals:

  - SOST consensus: `sost::sha256(preimage.data(), 32)` from
    `src/tx_validation.cpp` rule R21.
  - BTC redeem script: `OP_SHA256 <hashlock_32B> OP_EQUALVERIFY` from
    `include/sost/atomic_swap_btc.h`.

A preimage that satisfies any one of the three sides satisfies all
three. This is the load-bearing cryptographic property of the
cross-chain atomic swap.

## 7. Timeout coordination (wallet responsibility)

The contract enforces only `block.number >= refundTime` (refund) and
`block.number < refundTime` (claim) on the EVM side. Cross-chain
timeout coordination (`T1_sost > T2_evm + safety_margin`) is enforced
by the wallet, not the contract. A wallet that signs a LOCK with
`T2_evm >= T1_sost` exposes the user to the responder-claims-after-
refund attack and the responsibility for that ordering belongs in the
wallet UI layer (Phase 4C-1 coordinator state machine).

## 8. ISSUER-RISK assets

The contract is asset-agnostic. The four ISSUER-RISK assets
(USDT, USDC, PAXG, XAUT) work mechanically the same as the
trust-minimized assets (ETH, BNB) at the contract level. The
issuer-freeze risk is documented at the UI level
(`docs/design/ATOMIC_SWAP_ASSETS_BTC_ETH_USDT_USDC_BNB_PAXG_XAUT.md`,
`website/sost-otc.html` Phase 4D section, whitepaper section
`#sec-trading`).

## 9. Known limitations

  - **No batch lock.** Each swap is one call.
  - **No fee-on-transfer ERC-20 support.** If a token deducts a fee on
    transfer, the locked balance will be less than the recorded amount,
    and claim/refund attempts will revert with `TRANSFER_FAILED` when
    the contract tries to send out the full recorded amount. Users
    must not lock fee-on-transfer tokens through this contract. The
    UI should refuse known fee-on-transfer tokens at the form layer.
  - **No EIP-2612 permit.** ERC-20 callers must `approve` separately
    before `lockERC20`. Future ergonomics improvement.
  - **No timeout in seconds.** Only `block.number`. Cross-chain
    coordination is cleaner with block heights but requires the
    wallet to compute target heights from wall-clock times.

## 10. What is NOT in this commit

  - Deployment scripts.
  - Mainnet / testnet addresses.
  - Wallet integration.
  - The cross-chain coordinator state machine (Phase 4C-1).
  - External cryptographic / economic audit.

## 11. Activation requirement

This contract being internally-tested is not sufficient to flip the
SOST gate. The gate flip
(`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` = `V14_HEIGHT`) requires ALL of:

  1. BTC signing path (Phase 4A-1).
  2. THIS contract — done.
  3. Cross-chain coordinator (Phase 4C-1).
  4. End-to-end testnet swaps (Phase 4D-end-to-end).
  5. External cryptographic + economic review.

See `docs/reviews/ATOMIC_SWAP_PRE_ACTIVATION_REVIEW.md`.
