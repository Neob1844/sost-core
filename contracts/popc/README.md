# PoPC Smart Contracts

Proof of Personal Custody (PoPC) contract implementations for Ethereum.

## Roadmap

| Phase | Timeline | Description |
|---|---|---|
| Manual verification | Now | Foundation commitments verified via `scripts/verify_popc_balance.py`. Rewards paid manually from PoPC Pool. Transitional by design — automation is a constitutional commitment, not a discretionary goal. |
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
| A (bond + audit) | 5% of gross reward | At commitment creation (upfront) |
| B (timelocked escrow) | 10% of gross reward | At commitment creation (upfront) |

Fees are collected **upfront at commitment creation** — deducted from the gross reward before any payout.
Participants receive `reward × (1 - fee_rate)` at completion. Fee goes to the Foundation fee wallet.
Both transactions sourced from the PoPC Pool.

### Phase 1 (current): Manual two-step process

Script: `scripts/popc_reward_payout.py`

**Step 1 — At creation** (`--action create`): Collects protocol fee upfront.
**Step 2 — At completion** (`--action complete`): Pays net reward to participant.

- Generates `sost-cli send` commands (does NOT execute)
- Integer arithmetic only (stocks + basis points, no floats)
- Appends JSON log entry to `popc_payouts.json`
- Operator reviews and executes manually

### Phase 1.5 (current): PoPC Daemon

Script: `scripts/popc_daemon.py` — lifecycle manager for PoPC commitments.

**Contract Registry**: `scripts/popc_contracts.json` — pre-populated with FOUND-001 (XAUT) and FOUND-002 (PAXG).

**Actions:**

```bash
# Activate a commitment — collect upfront fee, status → FEE_PENDING
python3 scripts/popc_daemon.py --action activate --contract-id FOUND-001

# Check all active commitments — verify Ethereum balances
python3 scripts/popc_daemon.py --action check-all --eth-rpc https://eth-mainnet.g.alchemy.com/v2/KEY

# Complete a commitment — generate net reward payout command
python3 scripts/popc_daemon.py --action complete --contract-id FOUND-001

# Show status of all contracts
python3 scripts/popc_daemon.py --action status

# Dry run — preview without state changes
python3 scripts/popc_daemon.py --action check-all --dry-run
```

**Lifecycle:**
1. `PENDING` → activate → `FEE_PENDING` (operator executes fee TX) → manual update to `ACTIVE`
2. `ACTIVE` → check-all verifies Ethereum balances periodically
3. `ACTIVE`/`EXPIRED` → complete → `PAYOUT_PENDING` (operator executes reward TX) → manual update to `COMPLETED`

**Balance verification**: Queries ERC-20 `balanceOf()` via Ethereum JSON-RPC. Pass = balance >= committed amount.

The daemon does NOT execute transactions — generates `sost-cli send` commands for operator review. All state changes are logged to `popc_payouts.json`.

### Phase 2 (planned): Full automation

Architecture for future `sost-popc-daemon` auto mode:

1. **Monitor**: Watch commitment registry for expiring contracts.
2. **Verify**: At expiry, query Ethereum RPC for `balanceOf()` — pass/fail determination.
3. **Calculate**: Compute net payout and fee in integer stocks.
4. **Execute**: Submit `sost-cli send` transactions via SOST node RPC.
5. **Attest**: Publish Capsule attestation on-chain (commitment ID, result, TX hashes).
6. **Log**: Append structured entry to payout ledger.

The daemon will NOT handle bond slashing — slash events require separate governance review.

## Current Status

No smart contracts have been deployed yet. The `scripts/verify_popc_balance.py`
script performs manual ERC-20 balance checks against the Foundation wallet as a
proof-of-concept for the audit mechanism. Reward payouts are handled manually via
`scripts/popc_reward_payout.py`.

Contract source code will be added to this directory when development begins.
