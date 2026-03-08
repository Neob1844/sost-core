# PoPC Smart Contracts

Proof of Personal Custody (PoPC) contract implementations for Ethereum.

## Roadmap

| Phase | Timeline | Description |
|---|---|---|
| Manual verification | Now | Foundation commitments verified via `scripts/verify_popc_balance.py`. Rewards paid manually from PoPC Pool. |
| Sepolia testnet | Q2 2026 | Model A (bond + audit) and Model B (escrow timelock) deployed on Sepolia for public testing. |
| Ethereum mainnet | Q3 2026 | Production deployment. First third-party custody contracts active. |

## Contract Architecture (planned)

### Model A — Bond with Autocustody

- Participant declares ETH wallet holding XAUT/PAXG
- Locks SOST bond (12-30% of gold value)
- ConvergenceX block entropy schedules random audits
- Verification: `balanceOf(wallet) >= committed_amount`
- EOA-only (no smart contract wallets)
- Slash: 50% to PoPC Pool, 50% to Gold Vault

### Model B — Timelocked Escrow

- Immutable escrow contract (no admin, no proxy, no pause)
- Participant deposits XAUT/PAXG
- SOST reward paid immediately at deposit
- Withdraw only by original depositor after expiry
- No audits, no bond, no slash

## Fee Collection

| Model | Fee rate | Timing |
|---|---|---|
| A (bond + audit) | 5% of gross reward | At completion |
| B (timelocked escrow) | 10% of gross reward | At payout |

Fees are deducted from the gross reward — participants receive `reward × (1 - fee_rate)`.
Fee goes to the Foundation fee wallet. Both transactions sourced from the PoPC Pool.

### Phase 1 (current): Manual payout

Script: `scripts/popc_reward_payout.py`

- Generates `sost-cli send` commands (does NOT execute)
- Integer arithmetic only (stocks + basis points, no floats)
- Appends JSON log entry to `popc_payouts.json`
- Operator reviews and executes manually

### Phase 2 (planned): Automated payout daemon

Architecture for `sost-popc-daemon`:

1. **Monitor**: Watch commitment registry for expiring contracts.
2. **Verify**: At expiry, query Ethereum RPC for `balanceOf()` — pass/fail determination.
3. **Calculate**: Compute net payout and fee in integer stocks.
4. **Execute**: Submit two `sost-cli send` transactions via SOST node RPC.
5. **Attest**: Publish Capsule attestation on-chain (commitment ID, result, TX hashes).
6. **Log**: Append structured entry to payout ledger.

Operational modes:
- `--dry-run`: Generate and display commands without executing.
- `--auto`: Full automated execution (requires operator key configuration).
- `--verify-only`: Check balances without processing payouts.

The daemon will NOT handle bond slashing — slash events require separate governance review.

## Current Status

No smart contracts have been deployed yet. The `scripts/verify_popc_balance.py`
script performs manual ERC-20 balance checks against the Foundation wallet as a
proof-of-concept for the audit mechanism. Reward payouts are handled manually via
`scripts/popc_reward_payout.py`.

Contract source code will be added to this directory when development begins.
