# SOSTEscrow — Security Analysis

## Contract Summary

SOSTEscrow is a timelocked gold token escrow for SOST PoPC Model B.
It accepts XAUT and PAXG deposits, locks them for a user-specified
duration, and returns them to the original depositor after expiry.

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
modifier. `withdraw()` follows checks-effects-interactions: it sets
`withdrawn = true` BEFORE calling `transfer()`.

### 2. ERC-20 transfer failures
**Mitigated.** Both `transferFrom()` (deposit) and `transfer()` (withdraw)
check the return value. If either returns `false`, the transaction reverts.
Note: XAUT and PAXG both return `bool` on transfer (they are standard
ERC-20 compliant). Non-standard tokens that don't return bool (e.g.,
USDT) are NOT supported — but XAUT and PAXG are the only accepted tokens.

### 3. Integer overflow
**Not applicable.** Solidity 0.8+ has built-in overflow checking.
All arithmetic reverts on overflow/underflow by default.

### 4. Timestamp manipulation
**Acceptable risk.** Miners can manipulate `block.timestamp` by a few
seconds (typically <15s on Ethereum mainnet). The minimum lock duration
is 28 days (~2.4M seconds), so a 15-second manipulation is negligible
(0.0006%). The unlock check uses `>=` not `==`, so minor timestamp
drift is harmless.

### 5. Front-running
**Not applicable.** There is no price-sensitive operation. Deposits
and withdrawals are user-specific (keyed by depositor address).
Front-running a deposit or withdrawal would require the attacker to
BE the depositor (have their private key), which is already game over.

### 6. Denial of service via gas
**Mitigated for core operations.** `deposit()` and `withdraw()` are O(1).
`totalLocked()` is O(n) and should NOT be used in transactions — it is
a view function for off-chain reads only. If depositCount grows very
large (>10K), `totalLocked()` may exceed gas limits for `eth_call` —
acceptable since it's view-only and can be replaced with a subgraph.

### 7. Token approval race condition
**Standard ERC-20 risk.** The user must `approve()` the contract before
calling `deposit()`. The classic approve race (front-running an
`approve()` change) exists but is irrelevant here: the user only
approves the exact amount they're depositing in a single transaction.

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

## Gas Estimates

| Operation | Estimated gas | ETH cost (~10 gwei) |
|---|---|---|
| `deposit()` | ~80,000 | ~$0.30 |
| `withdraw()` | ~50,000 | ~$0.20 |
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
