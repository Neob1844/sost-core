# DEX asset compatibility audit (P3) — against AtomicSwapHTLC.sol

**Verified in the contract:** `AtomicSwapHTLC.sol` uses a strict minimal IERC20 whose `transfer`/
`transferFrom` are declared `returns (bool)`, and checks them as
`bool ok = IERC20(token).transferFrom(...); require(ok, "TRANSFER_FAILED")` (lines 194, 229, 256).
It does **NOT** use SafeERC20. This is the deciding factor for each asset below.

| Asset | Chain | Decimals | Verdict | Reason |
|---|---|---|---|---|
| **BTC** | Bitcoin | 8 | **SAFE** | Not EVM — handled by the P2WSH BTC HTLC engine, not this contract. |
| **ETH** | EVM native | 18 | **SAFE** | Uses `.call{value:...}` with `require(ok)`; native transfer, no ERC-20 return-value issue. |
| **USDC** | EVM | 6 | **ENABLE + CAVEAT** | Standard ERC-20, `transfer`/`transferFrom` return `bool` → compatible with `require(ok)`. BUT Circle can **blacklist/pause**: a swap can be frozen mid-flight if the escrow or a party is blacklisted. Surface the risk. |
| **USDT** | EVM | 6 | **DISABLED** | Mainnet USDT `transfer`/`transferFrom` **return NO value** (non-standard). Decoding a `bool` from a no-return call under the strict `returns (bool)` interface **reverts** on lock/claim → the swap cannot complete. Needs SafeERC20 (low-level call, tolerate empty return) before USDT can be enabled. |
| **PAXG** | EVM | 18 | **DISABLED** | **Fee-on-transfer**: the escrow receives `amount − fee`, but claim tries to send the full `amount` → reverts / accounting mismatch with fixed-amount escrow. Needs balance-delta accounting (measure received) before enabling. |
| **XAUT** | EVM | 6 | **DISABLED pending live test** | Returns `bool` and has no on-chain transfer fee (likely compatible), but 6-decimals + real behaviour must be validated against the contract on a fork/testnet before enabling. Not proven → stays off. |

## Actions taken
- The DEX marks **USDT, PAXG, XAUT as `disabled`** and **USDC as `caveat`** in `sost-dex.html`
  (`ASSET_STATUS`). Selecting a disabled asset shows the reason and keeps the swap CTA blocked; it
  never implies the asset is tradeable. ETH/BTC/SOST/USDC remain selectable (USDC with its caveat).
- To ENABLE USDT/PAXG the contract needs a **SafeERC20-style** path (low-level call tolerating an
  empty return; balance-delta accounting for fee-on-transfer). That is a contract change — devnet
  only, audited — not done here.

## Not done / honest scope
Live per-token behaviour (approve/allowance/transferFrom, return-value quirks, fee-on-transfer,
pause/blacklist paths) was NOT exercised against forked-mainnet tokens in this environment — the
verdicts are from the contract's transfer pattern + well-documented token behaviours. A forked-
mainnet integration test per token is the follow-up (BLOCKED-ENVIRONMENT here).
