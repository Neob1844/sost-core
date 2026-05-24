# Atomic Swap — EVM Counterparty Implementation Decision (Phase 4B-0)

**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Status:** **STOP CONDITION TRIGGERED — design + install plan only.**
**Gate:** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (sentinel OFF).

---

## STOP CONDITION TRIGGERED

The user brief for Phase 4B-0 says:

> "If test infra cannot be installed/run without network or unsafe
> dependency changes, stop and report."

**This stop condition is triggered on this VPS.** The EVM toolchain
required to author and test a Solidity `AtomicSwapHTLC.sol` is **not
installed**:

| Tool | Status |
|---|---|
| `solc` (Solidity compiler) | MISSING |
| `forge` (Foundry build/test) | MISSING |
| `anvil` (Foundry local node) | MISSING |
| `hardhat` (alternative test framework) | MISSING |
| `node` (Node.js runtime) | MISSING |
| `npm` / `npx` / `yarn` (Node package managers) | MISSING |

The existing `contracts/foundry.toml` + `contracts/SOSTEscrow.sol` +
`contracts/test/SOSTEscrow.t.sol` + `contracts/test/MockERC20.sol`
indicate Foundry was used previously on a different machine (likely
operator-side). On the VPS the contracts can be read but cannot be
compiled or tested.

Installing the Foundry toolchain requires:

```
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

That requires:
  - outbound HTTPS to `foundry.paradigm.xyz`
  - subsequent downloads from GitHub releases
  - installing the `forge`, `cast`, `anvil`, `chisel` binaries (~300 MB)
  - shell PATH modification

Per the user's brief that combination is "network or unsafe dependency
changes" and triggers the stop condition. **This commit does NOT install
Foundry, does NOT add `AtomicSwapHTLC.sol`, and does NOT modify any
existing contract.**

---

## What ships in this commit

  - **This document** — the EVM implementation decision and the explicit
    install plan for the next sprint.
  - **Nothing in `contracts/`** is modified. `SOSTEscrow.sol` and its
    tests remain bit-identical.

## Next-sprint installation plan (operator-side, not VPS)

To unblock Phase 4B-1 (writing and testing `AtomicSwapHTLC.sol`), the
operator should set up Foundry on a development machine (NOT the VPS;
the VPS hosts the SOST node + miner and should not gain a JS / Solidity
build toolchain unnecessarily). The exact steps:

```
# On a dev machine (Linux / macOS):
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc   # or ~/.zshrc
foundryup

# Clone or pull this branch:
git clone https://github.com/Neob1844/sost-core.git
cd sost-core/contracts
git checkout feat/atomic-swap-htlc-v13-candidate

# Verify existing setup still builds:
forge build
forge test
```

Once `forge test` is green on the existing `SOSTEscrow.t.sol`, the
operator (or a follow-up sprint) can author `AtomicSwapHTLC.sol` next
to it.

## Proposed `AtomicSwapHTLC.sol` design (specification only — NOT code)

When Phase 4B-1 lands, the contract should follow this surface:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract AtomicSwapHTLC {
    enum State { NONE, LOCKED, CLAIMED, REFUNDED }

    struct Swap {
        State    state;
        bytes32  hashlock;       // sha256(preimage); must match SOST side
        uint256  refundHeight;   // absolute Ethereum block height
        address  claimer;
        address  refunder;
        uint256  amount;         // native units (ETH/BNB) OR ERC-20 amount
        address  token;          // address(0) for native; otherwise ERC-20
    }

    mapping(bytes32 => Swap) public swaps;   // keyed by swapId

    event LockCreated(bytes32 indexed swapId, address indexed locker,
                      bytes32 hashlock, uint256 refundHeight,
                      address claimer, address refunder,
                      uint256 amount, address token);
    event Claimed(bytes32 indexed swapId, bytes32 preimage);
    event Refunded(bytes32 indexed swapId);

    // Native lock — msg.value is the amount.
    function lockNative(bytes32 swapId, bytes32 hashlock,
                        uint256 refundHeight,
                        address claimer, address refunder) external payable;

    // ERC-20 lock — caller must have approved this contract.
    function lockToken(bytes32 swapId, bytes32 hashlock,
                       uint256 refundHeight,
                       address claimer, address refunder,
                       address token, uint256 amount) external;

    // Claim path — anyone who knows the preimage can trigger; funds go
    // to swap.claimer regardless of msg.sender.
    function claim(bytes32 swapId, bytes32 preimage) external;

    // Refund path — only available after refundHeight; anyone can trigger;
    // funds go to swap.refunder.
    function refund(bytes32 swapId) external;
}
```

Hard rules for the implementation:

  - `swapId` is supplied by the caller (typically derived from
    `keccak256(hashlock || refundHeight || claimer || refunder || nonce)`),
    so a single contract can host many concurrent swaps without storage
    collision.
  - `claim` MUST validate `sha256(preimage) == hashlock` AND `block.number
    < refundHeight` AND `state == LOCKED`.
  - `refund` MUST validate `block.number >= refundHeight` AND `state ==
    LOCKED`.
  - Native lock uses `payable` + `msg.value`; the contract holds the ETH.
  - Token lock uses `IERC20.transferFrom(msg.sender, address(this), amount)`;
    the contract holds the tokens.
  - State transitions are one-way: `NONE -> LOCKED -> CLAIMED` OR
    `NONE -> LOCKED -> REFUNDED`. Double-claim and refund-after-claim are
    impossible by state-machine.
  - **NO owner.** **NO pausable.** **NO upgradeable proxy.** **NO admin
    drain.** The contract holds no privileged role.
  - **NO `selfdestruct`.** A `selfdestruct` would let an attacker who
    compromises any caller drain via forced ETH receive.
  - Reentrancy: `state = CLAIMED` (or `REFUNDED`) is set BEFORE the
    external `transfer` / `call`. The standard checks-effects-interactions
    pattern.
  - ERC-20 transfer return value is checked (some tokens like USDT do not
    revert on failure but return false); use a `SafeERC20` wrapper.

## Hard rules for the Solidity tests (`AtomicSwapHTLC.t.sol`)

The tests must include (matching the user brief):

  1. native lock
  2. native claim with correct preimage
  3. native refund after timeout
  4. claim with wrong preimage reverts
  5. claim after timeout reverts
  6. refund before timeout reverts
  7. ERC-20 lock + claim + refund using `MockERC20`
  8. attempt at owner-drain reverts (proves no owner exists)
  9. reentrancy attack via malicious receiver reverts
  10. double-claim reverts
  11. claim-after-refund reverts
  12. refund-after-claim reverts
  13. `MockFailERC20` (already in `contracts/test/`) makes lock revert when
      `transferFrom` returns false
  14. event emission correctness (`LockCreated`, `Claimed`, `Refunded`)

Use Foundry fuzz tests for preimage / hashlock / amount randomness:

  ```
  function testFuzz_ClaimRequiresExactPreimage(bytes32 preimage) public { ... }
  ```

## Issuer-risk documentation (required UI surface)

The four issuer-risk tokens must be labelled in the SOST DEX OTC UI:

| Token | Issuer | Freeze capability |
|---|---|---|
| USDT | Tether Limited | Can freeze any USDT balance |
| USDC | Circle | Operates an active blacklist |
| PAXG | Paxos | Can freeze; physical gold custody risk |
| XAUT | TG Commodities | Can freeze; physical gold custody risk |

If an issuer freezes the counterparty side mid-swap, the SOST side still
refunds correctly (cryptographic atomicity holds on the SOST chain) but
the counterparty side becomes uncollectible by the SOST holder. This is
documented in `website/sost-otc.html` (Phase 4D commit c1ba5f68) and
mirrored in the whitepaper (same commit).

## Activation gating

Even when `AtomicSwapHTLC.sol` ships and is deployed on Sepolia / mainnet
(post Phase 4B-1), the SOST side stays gated. Setting
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` to a finite value requires ALL of:

  - SOST-side validation (DONE on this branch)
  - SOST-side wallet/RPC/CLI (DONE on this branch)
  - BTC redeem-script builder (DONE on this branch, Phase 4A-0)
  - BTC signing path (PENDING, Phase 4A-1)
  - EVM contract deployed + tested (PENDING, Phase 4B-1 to 4B-3)
  - End-to-end testnet swaps (PENDING)
  - External cryptographic + economic review (PENDING)

See `docs/reviews/ATOMIC_SWAP_PRE_ACTIVATION_REVIEW.md` for the full
re-flip checklist.
