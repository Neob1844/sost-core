# SOSTEscrow — Internal Hardening Review

## Changes Made

1. **Explicit unlockTime validation.** Added `UnlockTimeNotInFuture` error
   and a check (`unlockTime <= block.timestamp`) that reverts BEFORE the
   subtraction `unlockTime - block.timestamp`. Previously, if unlockTime
   was at or before the current timestamp, the subtraction would underflow
   (caught by Solidity 0.8 overflow checks, but with an opaque panic
   rather than a descriptive error).

2. **O(1) totalLocked tracking.** Added `totalLockedByToken` mapping that
   is incremented on deposit and decremented on withdraw. The `totalLocked()`
   view function now returns this value directly instead of looping over
   all deposits. This eliminates the O(n) gas cost that would eventually
   hit gas limits as deposit count grows.

3. **Checks-effects-interactions pattern documented.** Both `deposit()` and
   `withdraw()` now have explicit `CHECKS / EFFECTS / INTERACTIONS` section
   comments. In `deposit()`, state changes (recording the deposit, updating
   totalLockedByToken) now happen before the `transferFrom` call.

4. **Unit comments corrected.** Removed confusing "1 mg of gold" phrasing.
   Minimum amounts are now documented in terms of token units with clear
   decimal/oz conversion math.

5. **Deploy script chain-ID guards.** `DeployMainnet.s.sol` requires
   `block.chainid == 1` and `DeploySepolia.s.sol` requires
   `block.chainid == 11155111`. Prevents accidental deployment to the
   wrong network.

6. **Expanded test suite.** Added 14+ new test cases covering boundary
   conditions (exact min/max durations, exact min amounts, off-by-one),
   the new `UnlockTimeNotInFuture` revert, withdrawal at exact unlock
   time, totalLocked decrement after withdrawal, and a `MockFailERC20`
   that returns false on transfer to exercise the `TransferFailed` path.

## Risks Mitigated

- **Opaque revert on past unlockTime.** Now gives a clear custom error.
- **O(n) gas bomb in totalLocked.** Now O(1).
- **CEI ordering in deposit().** State changes now happen before the
  external transferFrom call (was previously: external call, then state).
- **Wrong-chain deployment.** Chain ID checks prevent accidents.
- **Insufficient edge-case test coverage.** Boundary conditions now tested.

## Risks Still Open

- **Issuer freeze risk.** XAUT/PAXG issuers can freeze the contract.
  Not mitigable at the contract level.
- **Off-chain watcher dependency.** SOST rewards depend on the watcher.
  If it goes down, rewards stop (but gold is still safe).
- **No external audit.** This is internal hardening only.
- **Unrecoverable direct transfers.** Tokens sent to the contract outside
  of `deposit()` are permanently locked. This is by design but could
  result in user error losses.
- **No upgradeability.** By design, but means bugs found post-deploy
  require a new contract deployment and user migration.

## Testnet Readiness Assessment

The contract is ready for Sepolia testnet deployment:
- All known edge cases are tested.
- Deploy script has chain-ID guard.
- Mock tokens are provided for testnet use.
- No external dependencies to configure.

## What Would Still Be Needed Before Mainnet With Serious Funds

1. **Independent security review or audit** by a qualified third party.
2. **Testnet soak period** — run on Sepolia for at least 2-4 weeks with
   realistic deposit/withdraw flows to catch any integration issues.
3. **Watcher integration testing** — confirm the off-chain watcher
   correctly reads events from the deployed testnet contract.
4. **Small mainnet pilot** — deploy to mainnet with a small amount
   (e.g., 0.01 oz) and complete a full deposit-lock-withdraw cycle
   before advertising the contract for larger deposits.
5. **Formal verification** (optional but recommended for high-value
   contracts) of the core invariant: sum of non-withdrawn deposits
   equals totalLockedByToken.
6. **Etherscan source verification** with constructor args confirmed.
7. **Monitoring and alerting** on the watcher to detect if it falls behind
   on event processing.
