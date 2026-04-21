# SOSTEscrow — Security Analysis

## Contract Summary

SOSTEscrow is a timelocked gold token escrow for SOST PoPC Model B.
It accepts XAUT and PAXG deposits, locks them for a user-specified
duration, and returns them to the original depositor after expiry.

**Status: Internally hardened and reviewed. Not externally audited.**

## Immutability Properties

| Property | Enforced by |
|---|---|
| No admin key | No `owner`, no `admin`, no `Ownable` |
| No upgrade proxy | No `delegatecall`, no proxy pattern |
| No pause function | No `paused` state, no `whenNotPaused` modifier |
| No emergency withdrawal | No function bypasses the timelock |
| No extension/modification | No `extend()`, `modify()`, `renew()` |
| Deposit locked until unlock | `withdraw()` reverts if `block.timestamp < unlockTime` |
| Only depositor withdraws | `withdraw()` reverts if `msg.sender != depositor` |
| Token allowlist immutable | `XAUT` and `PAXG` are `immutable` (set in constructor) |

## Attack Surface Analysis

### 1. Reentrancy
**Mitigated.** Both `deposit()` and `withdraw()` use the `nonReentrant`
modifier. Both functions follow the checks-effects-interactions pattern
explicitly: all state changes occur before any external ERC-20 call.
`withdraw()` sets `withdrawn = true` and decrements `totalLockedByToken`
BEFORE calling `transfer()`.

### 2. ERC-20 transfer failures
**Mitigated.** Both `transferFrom()` (deposit) and `transfer()` (withdraw)
check the return value. If either returns `false`, the transaction reverts
with `TransferFailed()`. Note: XAUT and PAXG both return `bool` on
transfer (they are standard ERC-20 compliant). Non-standard tokens that
don't return bool (e.g., USDT) are NOT supported — but XAUT and PAXG are
the only accepted tokens.

### 3. Integer overflow / underflow
**Not applicable.** Solidity 0.8+ has built-in overflow checking.
All arithmetic reverts on overflow/underflow by default. The
`unlockTime - block.timestamp` subtraction is additionally guarded
by an explicit `unlockTime > block.timestamp` check that reverts with
a clear `UnlockTimeNotInFuture` error before the subtraction.

### 4. Timestamp manipulation
**Acceptable risk.** Miners can manipulate `block.timestamp` by a few
seconds (typically <15s on Ethereum mainnet). The minimum lock duration
is 28 days (~2.4M seconds), so a 15-second manipulation is negligible
(0.0006%). The unlock check uses `>=` not `==`, so minor timestamp
drift is harmless.

### 5. Front-running
**No obvious value-extracting front-running vector identified.**
Deposits and withdrawals are user-specific (keyed by depositor address).
There is no price-sensitive swap or auction that an attacker could
sandwich. Front-running a deposit or withdrawal would require the
attacker to BE the depositor (have their private key).

### 6. Denial of service via gas
**Mitigated.** `deposit()`, `withdraw()`, and `totalLocked()` are all
O(1). The `totalLocked()` function reads from a pre-computed running
total rather than looping over all deposits.

### 7. Token approval race condition
**No obvious exploitable vector.** The user must `approve()` the contract
before calling `deposit()`. The classic approve race (front-running an
`approve()` change) exists at the ERC-20 level but is not meaningfully
exploitable here: the user typically approves the exact deposit amount
in a single flow, and the contract does not hold or spend approvals
across transactions.

### 8. Contract receiving ERC-20 without deposit() call
**No risk.** If someone sends XAUT/PAXG directly to the contract
address (not via `deposit()`), those tokens are NOT tracked by the
contract and are effectively burned. This is standard ERC-20 behavior
and not a vulnerability — the contract only returns tokens it tracks.

### 9. Deposit ID prediction
**Not exploitable.** Deposit IDs are sequential (auto-incrementing).
An attacker can predict the next ID, but this doesn't help: only the
depositor can withdraw, and the depositor is `msg.sender` at deposit
time — not a parameter the attacker controls.

### 10. XAUT/PAXG issuer risk
**External risk, not mitigable by the contract.** If Tether (XAUT) or
Paxos (PAXG) freeze the contract address, all locked tokens become
unrecoverable. This is disclosed in the whitepaper as "issuer risk"
and is the reason Phase III plans migration to physical gold custody.

## Known Limitations

1. **Issuer freeze risk.** XAUT and PAXG issuers (Tether, Paxos) can
   freeze any Ethereum address. If the escrow contract address is frozen,
   locked tokens become unrecoverable. This is an inherent property of
   custodial gold tokens and cannot be mitigated at the smart contract level.

2. **Dependence on off-chain watcher for SOST reward payout.** The escrow
   contract only locks and releases gold tokens. The actual SOST mining
   reward is computed and distributed by an off-chain watcher that reads
   `GoldDeposited` events. If the watcher fails, users still recover their
   gold at expiry but do not receive SOST rewards until the watcher is fixed.

3. **No partial withdrawals.** A deposit is all-or-nothing. The user
   cannot withdraw a portion of a locked deposit early. This is by design
   (simplicity, immutability) but means users who need partial liquidity
   must plan deposit sizes accordingly.

4. **Only two allowlisted tokens.** The contract only accepts XAUT and
   PAXG. Adding new tokens would require deploying a new contract. This
   is intentional: immutability over flexibility.

5. **totalLocked tracking is approximate if tokens charge transfer fees.**
   XAUT and PAXG do not currently charge transfer fees, so
   `totalLockedByToken` is exact. If either issuer introduced a fee-on-transfer
   mechanism in the future, the tracked total could drift from the actual
   contract balance. This is noted for completeness; it is not a current risk.

6. **This contract does NOT know or control SOST chain addresses (Gold Vault,
   Miner, PoPC Pool). Those are SOST-side consensus logic.** The escrow
   contract lives on Ethereum and has no awareness of the SOST chain. The
   bridge between the two is the off-chain watcher reading Ethereum events.

## Gas Estimates

| Operation | Estimated gas | ETH cost (~10 gwei) |
|---|---|---|
| `deposit()` | ~80,000 | ~$0.30 |
| `withdraw()` | ~50,000 | ~$0.20 |
| `totalLocked()` | ~2,600 | free (view) |
| `getDeposit()` | ~5,000 | free (view) |
| `canWithdraw()` | ~5,000 | free (view) |

## Deployment Checklist (pre-mainnet)

- [ ] Verify XAUT mainnet address: `0x68749665FF8D2d112Fa859AA293F07A622782F38`
- [ ] Verify PAXG mainnet address: `0x45804880De22913dAFE09f4980848ECE6EcbAf78`
- [ ] Deploy with verified source on Etherscan
- [ ] Verify constructor args match on Etherscan
- [ ] Test deposit/withdraw on Sepolia with mock tokens
- [ ] Test with real XAUT/PAXG on mainnet (small amount, 1 month lock)
- [ ] Confirm no proxy, no admin, no selfdestruct in bytecode
- [ ] Independent audit (if budget permits)
- [ ] Publish contract address on sostcore.com before accepting deposits
