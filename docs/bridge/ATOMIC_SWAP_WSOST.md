# SOST ↔ wSOST atomic swap — compatibility audit (Stage 2B/2C)

Status: **RESEARCH / TESTNET ONLY**. Nothing is enabled publicly. Current mainnet atomic-swap claims are unchanged.

## Two different things

| | Canonical bridge | Atomic swap (this document) |
|---|---|---|
| Purpose | convert SOST ↔ wSOST 1:1 | exchange SOST that already exists for wSOST that already exists, between two users |
| Mints / burns wSOST | yes (2-of-3 observers / burn-for-release) | **never** |
| Touches the Bridge Vault | yes (lock / release) | **never** |
| Price | 1 wSOST represents 1 locked SOST | whatever the two parties agree (100 SOST ↔ 99.5 wSOST is a valid offer) |
| Works while the bridge mint is paused | no new mints | **yes** (wSOST transfers never pause) |

The atomic swap is a P2P exchange of ownership. If it fails it cannot break the bridge's backing,
and if the bridge is paused existing wSOST can still be swapped.

## Audit of the existing EVM HTLC (`contracts/atomic-swap/src/AtomicSwapHTLCv2.sol`, unchanged)

| Item | Finding |
|---|---|
| Generic ERC-20 | yes: `lockERC20(swapId, token, amount, hashlock, refundTime, claimer, refunder)` takes any token address |
| transferFrom / escrow | `_safeTransferFrom` into the contract; accepts `true` or empty return, reverts on `false`/revert |
| Hashlock | `sha256(preimage)` — the same primitive as the SOST native HTLC (`R21`), so one secret works on both chains |
| Timelock | absolute `block.number`; claim strictly before, refund at/after |
| Claim | only `claimer`, with `minReceive` slippage guard; preimage emitted in `Claimed` |
| Refund | only `refunder`, only after `refundTime` |
| Decimals | amount-only; decimals irrelevant (wSOST uses 8, like native SOST stocks) |
| Fee-on-transfer | handled: records the balance delta actually received (`lockedAmount`) — wSOST has no fee, so locked == requested (tested) |
| Rebasing | not supported by design (fixed recorded amount); wSOST does not rebase |
| Replay / domain | no signatures involved; per-contract `swapId`, state machine NONE→LOCKED→CLAIMED/REFUNDED; reuse of an id reverts `SWAP_EXISTS` |
| Allowance model | standard `approve` then `lockERC20`; no allowance → `TOKEN_CALL_FAILED` (tested) |
| Reentrancy | `nonReentrant` on every mutator; wSOST has no transfer hooks |
| Griefing | a third party could pre-create a chosen `swapId`; this only blocks that id — parties derive ids from the secret/offer |

**ATOMIC_SWAP_ERC20_COMPATIBLE: YES.**
**WSOST_ATOMIC_SWAP_SUPPORTED_WITHOUT_CORE_REDESIGN: YES** — no change to the HTLC, no change to WSOST.

## Gas

- **Canonical wrap:** the native SOST user can need no ETH; the relayer pays the mint (design).
- **wSOST atomic swap:** the Ethereum-side participant normally needs ETH for `approve`, `lockERC20`, and the
  counterparty for `claimERC20` (or `refundERC20`). A relayer could later sponsor some of this (meta-transactions);
  that is **not** a dependency of Stage 2.

## Tests

- Foundry `contracts/wsost/test/WsostAtomicSwap.t.sol` (real WSOST + real AtomicSwapHTLCv2 + Gold Reserve):
  claim path, refund path, negotiated ratio, wrong secret / wrong caller / double claim / refund-after-claim /
  id reuse, allowance edge cases, bridge paused but swap settles, canonical unwrap after a swap, fuzz (512 runs)
  and 3 invariants (4,096 calls each): bridge numbers never move, the HTLC holds exactly the LOCKED sum, supply conserved.
- Local cross-chain E2E `tests/bridge/e2e_swap_sost_wsost.py`: REAL SOST devnet native HTLC (unchanged
  `sost-cli createhtlclock/claimhtlc/refundhtlc`, signed by the lab tool `tests/bridge/lab/sost_lab_sign.cpp`)
  + Anvil wSOST/HTLCv2. **27/27 PASS**: lock both sides with one hashlock, Alice claims wSOST (secret revealed),
  Bob claims SOST with it; node rejects wrong preimage (R21), wrong key (S2), replay, early refund (R24);
  refund path on both chains; Bridge Vault, wSOST supply/minted/burned, burn nonce and mint pause unchanged after every phase.

## Remaining before any public pair

1. Sepolia run of the same E2E (blocked only on funding the disposable deployer, see STAGE2_TESTNET.md).
2. A wallet-level signer for HTLC transactions: today `createhtlclock/claimhtlc/refundhtlc` print unsigned hex
   and no shipped tool signs them (the lab signer is test-only). Same family as the capsule gap in CLI_CAPSULE_OFFLINE_DESIGN.md.
3. External review. The pair stays disabled publicly.
