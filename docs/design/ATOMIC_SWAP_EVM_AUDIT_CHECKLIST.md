# Atomic Swap — EVM HTLC contract audit checklist (Phase D)

Status: tests written + green locally; external audit STILL REQUIRED before
the SOST-side gate `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` flips from
`INT64_MAX` to `V14_HEIGHT`. This document is the operator-facing map of
"what we tested" and "what we deliberately did not test" so a reviewer
can pick up the contract and reach the same conclusions.

## Scope of this contract

`contracts/atomic-swap/src/AtomicSwapHTLC.sol` — non-custodial Hashed
Time-Locked Contract for the EVM side of SOST ↔ EVM atomic swaps:
- native chain currency (ETH, BNB) via `lockNative`
- ERC-20 tokens (USDT, USDC, PAXG, XAUT, others) via `lockERC20`
- claim by preimage before timeout (`claim`)
- refund after timeout (`refund`)
- no owner, no admin, no pause, no upgrade path, no emergency drain

The contract is one source file, one external dep (a minimal `IERC20`
interface), no inheritance, no proxies. Audit surface is intentionally
tiny.

## Threat model

The contract is exposed to:
1. Anyone calling `lock*` with any parameters (no permissioning).
2. Any ERC-20 token, including malicious or non-compliant ones.
3. Reentrant callbacks on native transfer (claim/refund) and on ERC-20
   `transferFrom` (lock).
4. Direct ETH transfer (`receive()` / `fallback()`).
5. Forced ETH via EIP-6780 selfdestruct.
6. Front-running of `claim` (anyone who sees the preimage can submit it).

The contract is NOT exposed to:
- Cross-chain timeout coordination — that's the wallet's job. The
  contract only enforces "this chain's refundTime".
- Issuer freezes on USDT/USDC/PAXG/XAUT — out of contract scope; the
  UI surfaces this as ISSUER-RISK labelling.
- Replay across chains — `swapId` is caller-supplied; the wallet must
  derive it deterministically and verify uniqueness.

## Checklist coverage (item → test name)

Each line is one operator-facing requirement → the Foundry test that
proves it. All tests live in
`contracts/atomic-swap/test/AtomicSwapHTLC.t.sol`.

### A. Exact balance conservation

| Requirement | Test |
|---|---|
| Native: claim drains contract to zero | `test_balance_nativeClaim_drainsContractToZero` |
| Native: refund drains contract to zero | `test_balance_nativeRefund_drainsContractToZero` |
| ERC-20: claim drains contract to zero | `test_balance_erc20Claim_drainsContractToZero` |
| ERC-20: refund drains contract to zero | `test_balance_erc20Refund_drainsContractToZero` |

These tests assert `address(htlc).balance == 0` (or `token.balanceOf(htlc)
== 0`) AND recipient delta equals the recorded amount, on the same tx.

### B. Negative paths (parameter validation, state-machine, ordering)

#### B.1 lock parameter validation

| Requirement | Native | ERC-20 |
|---|---|---|
| Zero amount rejected | `test_lockNative_rejectsZeroAmount` | `test_lockERC20_rejectsZeroAmount` |
| Zero claimer rejected | `test_lockNative_rejectsZeroClaimer` | `test_lockERC20_rejectsZeroClaimer` |
| Zero refunder rejected | `test_lockNative_rejectsZeroRefunder` | `test_lockERC20_rejectsZeroRefunder` |
| refundTime ≤ block.number rejected | `test_lockNative_rejectsRefundInPast` | `test_lockERC20_rejectsRefundInPast` |
| Duplicate swapId rejected | `test_lockNative_rejectsDuplicateSwapId` | `test_lockERC20_rejectsDuplicateSwapId` |
| Zero token address rejected (ERC-20 only) | — | `test_lockERC20_rejectsZeroToken` |

#### B.2 state-machine and ordering

| Requirement | Native | ERC-20 |
|---|---|---|
| Wrong preimage rejected | `test_claimNative_rejectsWrongPreimage` | `test_claimERC20_rejectsWrongPreimage` |
| Claim after timeout rejected | `test_claimNative_rejectsAfterTimeout` | `test_claimERC20_rejectsAfterTimeout` |
| Refund before timeout rejected | `test_refundNative_rejectsBeforeTimeout` | `test_refundERC20_rejectsBeforeTimeout` |
| Cannot claim twice | `test_claimNative_cannotClaimTwice` | `test_claimERC20_cannotClaimTwice` |
| Cannot refund twice | `test_refundNative_cannotRefundTwice` | `test_refundERC20_cannotRefundTwice` |
| Refund after claim rejected | `test_refundAfterClaim_rejected` | `test_refundERC20_afterClaim_rejected` |
| Claim after refund rejected | `test_claimAfterRefund_rejected` | `test_claimERC20_afterRefund_rejected` |
| Unknown swapId rejected | `test_claimNative_cannotClaimUnknownSwap` | (covered by the same `NOT_LOCKED` revert) |

### C. Exact event fields

| Event | Native | ERC-20 |
|---|---|---|
| `LockCreated(swapId, locker, token, amount, hashlock, refundTime, claimer, refunder)` | `test_event_LockCreated_native` | `test_event_LockCreated_ERC20` |
| `Claimed(swapId, preimage, claimer)` | `test_event_Claimed_native` | `test_event_Claimed_ERC20` |
| `Refunded(swapId, refunder)` | `test_event_Refunded_native` | `test_event_Refunded_ERC20` |

Each test pins the EXACT field tuple (not just the topic) via
`vm.expectEmit(true, true, false, true, address(htlc))`.

### D. Weird ERC-20 behaviour

| Class | Behaviour | Test |
|---|---|---|
| false-return on transferFrom | Lock rejected with `TRANSFER_FAILED` | `test_lockERC20_rejectsFailingToken` |
| No return value (legacy USDT shape) | Lock reverts at decode | `test_lockERC20_rejectsNoReturnERC20` |
| Fee-on-transfer | Lock succeeds; claim fails (asymmetric balance) → UNSUPPORTED; wallet must blacklist | `test_lockERC20_feeOnTransferTokenIsUnsupported_lockSucceedsClaimFails` |
| Malicious reentrant on transferFrom | Re-entry blocked by `nonReentrant`; outer call reverts; no state change | `test_lockERC20_blocksMaliciousTokenReentrancy` |
| Malicious reentrant on native transfer | Same guard blocks the receiver callback | `test_reentrancy_blockedByGuardAndStateMachine` |

### E. Forced ETH pathways

| Vector | Outcome | Test |
|---|---|---|
| Plain `address(htlc).call{value:…}("")` | Rejected at `receive()` | `test_rejectsPlainEthTransfer` |
| Plain call with non-matching selector | Rejected at `fallback()` | (compile-time: `fallback()` reverts; subsumed by direct-transfer test) |
| Forced ETH via EIP-6780 selfdestruct | Increases balance, does NOT affect any swap state, legitimate flows still work, orphaned ETH is permanently stuck (no admin path, by design) | `test_forcedEthViaSelfdestruct_doesNotCorruptState` |

### F. No-admin invariants

| Invariant | Test |
|---|---|
| No `owner()`, `admin()`, `pause()`, `unpause()`, `withdraw()`, `emergencyWithdraw()`, `upgradeTo(address)` selectors at runtime | `test_noOwnerFunctionsExist_runtime` |

Compile-time review: `git grep -nE "owner|onlyOwner|upgrade|proxy|pause|emergency|drain|selfdestruct|delegatecall" contracts/atomic-swap/src` returns zero hits in the contract source. The contract has NO inheritance, NO modifiers other than `nonReentrant`, NO library deps.

### G. Fuzz tests

| Property | Test | Runs |
|---|---|---|
| Any preimage that hashes to the same hashlock claims; any other reverts | `testFuzz_claim_onlyAcceptsExactPreimage(bytes32)` | 256 |
| Boundary at `refundTime` is sharp: claim works at `rt-1`, refund works at `rt`, swap is exclusive | `testFuzz_refundTime_boundaryIsSharpAtRefundTime(uint16)` | 256 |

## What we deliberately did NOT test

These are out of scope for this contract's audit; they are addressed
elsewhere in the stack and noted here so a reviewer does not waste time
hunting for the test:

- **Cross-chain timeout safety** (T1 > T2 margin). The wallet computes
  the SOST-side `refund_height` and the EVM-side `refundTime` such that
  the SOST refund cannot fire before the EVM refund. Verified in
  `tests/test_atomic_swap_coordinator.cpp` (39 tests) and
  `tests/test_atomic_swap_e2e_sim.cpp` (10 scenarios, 43 assertions),
  not here.
- **Issuer freezes on USDT/USDC/PAXG/XAUT.** Off-chain risk; the
  wallet surfaces it as an ISSUER-RISK label. The contract is
  asset-agnostic and cannot detect or prevent a freeze.
- **MEV / preimage front-running.** Once the claim is broadcast, the
  preimage is public; anyone could resubmit. Funds still go to the
  recorded claimer (not the submitter), so a front-runner cannot
  redirect funds, only pay the gas to deliver a claim that was
  already economically inevitable. This is a known property of
  hashlocked atomic swaps, not a vulnerability in this contract.
- **Gas griefing via large `claimer`/`refunder` contract callbacks.**
  Both transfer paths use `.call{value:…}("")` which forwards all
  gas. A claimer/refunder contract that consumes excessive gas in
  receive() can grief the submitter (pay more gas, fail the tx) but
  cannot steal funds. The wallet should warn users when the
  claimer/refunder is a contract address.
- **Token approval race.** The user calls `approve(htlc, amount)`
  before `lockERC20`. Standard ERC-20 approval race applies but is
  inert here because the contract only ever pulls exactly the
  approved amount in a single `transferFrom`.

## Activation conditions (DO NOT FLIP YET)

The SOST-side gate at `include/sost/atomic_swap.h`:
```cpp
inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX;
```
stays at `INT64_MAX` until ALL of the following are GREEN:

1. ✅ Phase D — EVM hardening (this document; tests in
   `contracts/atomic-swap/test/AtomicSwapHTLC.t.sol`).
2. ⏳ Phase C — BTC signing via `libwally-core`. Currently
   `src/atomic_swap_btc_signing.cpp` is a disabled stub. The CMake
   option `SOST_BTC_HTLC_SIGNING` stays `OFF` until libwally is
   integrated and the test vectors in
   `tests/test_atomic_swap_btc_test_vectors.cpp` run against real
   signing (not the stub).
3. ⏳ Testnet harnesses — SOST↔BTC regtest, SOST↔ETH Sepolia,
   SOST↔ERC-20 (testnet token), each covering happy path + timeout
   + refund. Not yet built.
4. ⏳ External cryptographic audit — BTC signing usage, Solidity
   contract, timeouts/economy, UX recovery. Not yet engaged.

Only after 1, 2, 3 AND 4 turn green do we:
- flip `SOST_BTC_HTLC_SIGNING` from OFF to ON in the mainnet build,
- flip `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` from `INT64_MAX` to
  `V14_HEIGHT` (`15000`),
- ship a V14 hard fork with operator + miner + wallet recompiles.

## Local reproduction

```bash
cd contracts/atomic-swap
forge test -vv
# expected: 52 tests passed, 0 failed, 0 skipped
```

Foundry version pinned at `1.5.1-stable` (commit `b0a9dd9` as of
this commit). Solc `0.8.24`. Optimizer ON, runs 200.

## Known compiler warnings (intentional)

- `Warning (5159) — selfdestruct deprecated`. Used in
  `SelfdestructForcer` to exercise the EIP-6780 forced-ETH path.
  This is a test-only mock; the HTLC contract itself contains no
  `selfdestruct`.
- `Warning (2018) — Function state mutability can be restricted to view`
  on `test_noOwnerFunctionsExist_runtime`. The function performs a
  series of `staticcall`s which are read-only at runtime but the
  Solidity compiler does not detect this through the loop. Marking
  it `view` would still let the call go through; leaving it `public`
  matches the rest of the test conventions in this file.

## V14 founder web console — verification & UI hardening (2026-06-21)

The EVM side is now driven by the founder console (`website/atomic-swap-console.html` +
`website/js/atomic-swap-evm.js`, a dependency-free ABI codec). This round's double-verification:

- **End-to-end on local `anvil`:** deployed the real contract and ran `lockNative` → `getSwap` →
  `claim` using the **exact calldata the console codec produces** → LOCKED→CLAIMED, funds delivered,
  wrong-preimage claim reverts. Codec selectors are byte-identical to `cast` (selectors:
  lockNative 0xbef939c1, lockERC20 0x9cbaca50, claim 0x84cc9dfb, refund 0x7249fbb6, getSwap
  0x3da0e66e). `forge test` 57/57; codec unit tests 15/15.

- **UI policy now enforces the "weird-ERC20 is the UI's job" decision:**
  - `ERC20_ENABLED = false` → **native ETH/BNB only** until SafeERC20 + balance-delta land.
  - `FEE_ON_TRANSFER = ['PAXG']` → PAXG hard-blocked (would get stuck per
    `test_lockERC20_feeOnTransferTokenIsUnsupported_...`); USDT/USDC/PAXG/XAUT carry freeze warnings.
  - Real mainnet **LOCK gated** on SOST height ≥ 15,010 + full readiness checklist; Sepolia /
    BNB-testnet allowed as a free rehearsal.
  - **Local `sha256(secret) == on-chain hashlock`** pre-check before CLAIM (+ state/timeout check).
  - **Bytecode verification**: `eth_getCode` vs the vendored repo runtime
    (`website/js/atomic-swap-htlc-runtime.js`, kept in sync with `out/.../AtomicSwapHTLC.json`).
  - Pre-sign banner shows network + chainId + contract + from + calldata + value.

- **Contract header updated** to current reality (gate = V14_HEIGHT, founder-only, EVM-only, NOT
  audited, BTC→V15). Logic unchanged; 57/57 tests still green.

Still REQUIRED before any non-founder use: external audit; live cross-chain e2e with reorg
handling; SafeERC20 + balance-delta before re-enabling ERC-20; documented confirmation/reorg-depth
policy in the console.
