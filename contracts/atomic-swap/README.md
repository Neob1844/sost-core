# SOST Atomic Swap — EVM Counterparty HTLC

Self-contained Foundry sub-project implementing the EVM side of the
SOST OTC / P2P atomic-swap flow. **NOT DEPLOYED. NOT AUDITED. NOT
ACTIVE.** The SOST-side activation gate (`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`
in `include/sost/atomic_swap.h`) stays at `INT64_MAX` (sentinel OFF)
until the full Phase 4 stack (BTC signing + this contract + coordinator
+ external review) is complete.

## Scope

- **In scope:** lock / claim / refund HTLC for native ETH/BNB and any
  compliant ERC-20 (USDT, USDC, PAXG, XAUT, ...).
- **Out of scope:** PoPC DEX, `SOSTEscrow.sol`, position market, PoPC
  contracts, reward-right trades, Gold Vault governance, PoPC settlement
  logic. None of those files are touched.

## Hard properties

- **No owner.** **No admin.** **No pause.** **No upgrade.** **No
  emergency drain.** The contract holds no privileged role. Verified
  by `test_noOwnerFunctionsExist_runtime`.
- **No `selfdestruct`.**
- **Checks-effects-interactions** pattern throughout. Reentrancy guard
  + state-machine guard both block re-entry; verified by
  `test_reentrancy_blockedByGuardAndStateMachine`.
- **No mainnet RPC URLs.** `foundry.toml` deliberately declares no RPC
  endpoints. Deployment is an explicit operator-side step.
- **No private keys.** No deploy scripts.
- **Direct ETH transfers rejected.** Sending ETH to the contract
  address without calling `lockNative` reverts with
  `DIRECT_TRANSFER_REJECTED`. Prevents accidental fund loss.

## Hashlock compatibility

`sha256(preimage)` matches:
- SOST consensus (`src/tx_validation.cpp` rule R21).
- BTC redeem script (`include/sost/atomic_swap_btc.h` `OP_SHA256`).

A preimage that satisfies the SOST CLAIM also satisfies this EVM CLAIM
and vice versa. Cross-chain atomicity at the cryptographic level.

## Timeout

Absolute `block.number`. The wallet MUST select cross-chain timeouts
such that `T1_sost > T2_evm + safety_margin` so the responder cannot
claim the SOST side after refunding here.

## ISSUER-RISK WARNING

ERC-20 tokens USDT (Tether), USDC (Circle), PAXG (Paxos), XAUT (TG
Commodities) can be frozen by their issuers at any time. If a freeze
happens mid-swap the SOST side still refunds correctly but the EVM
side becomes uncollectible until the issuer unfreezes. UI MUST surface
this risk to users.

The contract is asset-agnostic — it does not differentiate Category A
(trust-minimized: ETH, BNB) from Category B (issuer-risk: USDT, USDC,
PAXG, XAUT). The differentiation is a UI-level concern documented in
`docs/design/ATOMIC_SWAP_ASSETS_BTC_ETH_USDT_USDC_BNB_PAXG_XAUT.md`.

## Files

```
contracts/atomic-swap/
├── foundry.toml                     # local-only Foundry config (no RPC)
├── README.md                        # this file
├── src/
│   └── AtomicSwapHTLC.sol           # the contract (no deps beyond IERC20)
└── test/
    ├── AtomicSwapHTLC.t.sol         # 28+ assertions + 1 fuzz test
    └── mocks/
        └── MockERC20.sol            # MockERC20 + MockFailERC20 + MaliciousClaimReceiver
```

## Running tests

```bash
cd contracts/atomic-swap
forge build
forge test -vvv
```

All tests must pass. Tests are pure unit tests with no network
dependency.

## What is NOT in this commit

- Deployment scripts.
- Mainnet / testnet addresses.
- Wallet integration.
- Coordinator state machine.
- BTC signing path (see `include/sost/atomic_swap_btc.h` for the
  redeem-script-only Phase 4A-0 scope).
- External security audit.
- Activation flip of the SOST gate.

See `docs/reviews/ATOMIC_SWAP_PRE_ACTIVATION_REVIEW.md` for the full
re-flip checklist.
