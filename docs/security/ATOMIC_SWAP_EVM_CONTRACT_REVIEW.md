# Atomic Swap EVM Contract — Security Review (SafeERC20 + CEI hardening)

Status: **QUARANTINED — NOT merged into the V15 integration branch, NOT deployed.**
Branch: `feat/atomic-swap-evm-safeerc20`. Custody-critical: this contract holds
user funds in escrow. 60/60 Foundry tests pass, but that is necessary, NOT
sufficient — this change must pass a dedicated external security review before it
may graduate to the V15 branch or any deployment.

## Scope of the change (`contracts/atomic-swap/src/AtomicSwapHTLC.sol`)
1. **`computeSwapId(...)` (new pure view):** collision-resistant swapId derivation
   via sha256 over (locker, claimer, refunder, token, amount, hashlock,
   refundTime, chainId, nonce). Byte-identical to the C++ `DeriveSwapId`
   (parity-tested). Anti-squatting relies on callers using it with a secret
   random nonce; the contract still *accepts* arbitrary caller-supplied ids
   (full on-chain enforcement would be a breaking `lock*` signature change).
2. **SafeERC20 helpers (`_callOptionalReturn` / `_safeTransfer` /
   `_safeTransferFrom`):** tolerate no-bool-return tokens (real mainnet USDT),
   reject an explicit `false`, and bubble inner revert reasons.
3. **`lockERC20` rewritten to balance-delta accounting:** records the ACTUAL
   received amount (`balanceOf(this)` after − before) so fee-on-transfer /
   rebasing tokens escrow their true delivered value; `claim`/`refund` ERC20
   legs use `_safeTransfer`. Native ETH/BNB paths unchanged.

## The item an auditor MUST scrutinize
`lockERC20` now writes swap state **after** the guarded external `transferFrom`
(it must, to learn the received amount). This deviates from strict
checks-effects-interactions.
- **Claimed mitigations:** the global `nonReentrant` mutex; the pre-transfer
  `DUPLICATE_SWAP_ID` guard; verified by the malicious-reentrant-token test.
- **Unresolved:** independent confirmation that no reentrancy or cross-swap
  state-corruption path exists given the post-interaction write, across all
  weird-ERC20 behaviours (reentrant, false-return, no-return, fee-on-transfer,
  balance-changing, hooks/ERC-777-style).

## Trust / custody assumptions
- The HTLC is the escrow; no owner/admin/pause/upgrade/drain (unchanged).
- Token issuers (USDT/USDC/PAXG/XAUT) can freeze the contract balance mid-swap;
  the SOST leg still refunds, the EVM leg becomes uncollectible until unfrozen.
- Fee-on-transfer tokens (e.g. PAXG) deliver the escrowed delta, which is
  **less than nominal** — the UI must disclose this; do not present as 1:1.

## Per-token behaviour (post-change)
| Token | Behaviour | Product status |
|---|---|---|
| ETH / BNB (native) | unchanged | TESTING (unaudited/undeployed) |
| USDC (bool ERC20) | standard via SafeERC20 | TESTING; issuer-freeze risk |
| USDT (no-bool) | now handled by no-bool path | TESTING (was DISABLED) |
| XAUT (bool ERC20) | standard | TESTING; issuer-freeze risk |
| PAXG (fee-on-transfer) | balance-delta safe, delivers < nominal | TESTING + caveat |

No pair is AVAILABLE. Nothing here changes the deployed capability matrix.

## Tests run
- Foundry: 60/60 (positive USDT-shape lock/claim/refund; fee-on-transfer records
  actual received + claim succeeds; computeSwapId determinism/binding; derived-id
  lock+claim). Reentrant/false-return/no-return token cases covered.

## Graduation gate (all required before merge/deploy)
- [ ] External security review of the CEI-ordering change + SafeERC20 paths.
- [ ] Foundry fuzzing + invariant tests (weird-token adversarial matrix).
- [ ] On-chain E2E on a testnet (claim + timeout refund + issuer-freeze).
- [ ] Decision on on-chain swapId enforcement (breaking change) vs wallet-derived.
- [ ] Deployment plan (Sepolia/BNB-testnet → mainnet); console refuses unset addr.

Until every box is checked, this branch stays out of V15 and undeployed.
