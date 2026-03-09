# Foundation PoPC Commitments

This document records all Foundation Proof of Personal Custody commitments.
The Foundation participates under the same rules as any third-party participant,
including the standard 5% protocol fee. No exceptions.

## Progressive Decentralization

The Foundation commits to progressive decentralization and full automation of all operational
processes as soon as technically viable. Manual operations in Phase 1 — including PoPC
verification, reward payouts, and vault conversions — are transitional by design, not permanent.
Every manual process has a planned automation path documented in the protocol roadmap. This is a
constitutional commitment, not a discretionary goal.

## Active Commitments

### FOUND-001 — XAUT (Model A)

| Field | Value |
|---|---|
| Model | A (bond + autocustody audit) |
| Asset | XAUT (Tether Gold) |
| Amount | 0.4 oz |
| Duration | 3 months |
| Start date | 2026-03-28 |
| Expiry date | 2026-06-28 |
| Protocol fee | 5% (standard) |
| Status | PENDING |
| XAUT contract | `0x68749665FF8D2d112Fa859AA293F07A622782F38` |

### FOUND-002 — PAXG (Model A)

| Field | Value |
|---|---|
| Model | A (bond + autocustody audit) |
| Asset | PAXG (Paxos Gold) |
| Amount | 0.4 oz |
| Duration | 3 months |
| Start date | 2026-03-28 |
| Expiry date | 2026-06-28 |
| Protocol fee | 5% (standard) |
| Status | PENDING |
| PAXG contract | `0x45804880De22913dAFE09f4980848ECE6EcbAf78` |

## Foundation Ethereum Wallet

- **Address:** `0xd38955822b88867CD010946F0Ba25680B9DfC7a6`
- **Etherscan:** https://etherscan.io/address/0xd38955822b88867CD010946F0Ba25680B9DfC7a6
- **Verification:** Anyone can check XAUT and PAXG balances at any time via Etherscan or direct RPC query.

## Verification Process

During the commitment period, the Foundation wallet balance is checked against committed amounts:

```
XAUT: balanceOf(0xd389...C7a6) >= 0.4 * 10^18  (0.4 oz)
PAXG: balanceOf(0xd389...C7a6) >= 0.4 * 10^18  (0.4 oz)
```

Verification runs are logged with: Ethereum block number, timestamp, balance values, pass/fail.
Results are published on the explorer (sost-foundation.html).

Until PoPC smart contracts are deployed, verification is manual and the script at
`scripts/verify_popc_balance.py` can be run by anyone with an Ethereum RPC endpoint.

## Renewal Policy

- Foundation commitments may be renewed for additional terms.
- Renewal must be announced at least 15 days before the current term expires.
- If not renewed, the commitment expires normally — no penalty, no slash.
- New commitments are documented here with a new FOUND-XXX identifier.

## Fee Structure

PoPC protocol fees fund the SOST ecosystem. Fees are deducted from the gross reward — participants never pay extra.

| Parameter | Model A | Model B |
|---|---|---|
| Fee rate | 5% of gross reward | 10% of gross reward |
| Fee timing | Calculated at creation, disbursed at completion | Calculated at creation, disbursed at completion |

### How fees are collected (Phase 1 — Manual)

Fees are **calculated at commitment creation** and **disbursed at commitment completion**. This is a two-step process:

**Step 1 — At commitment creation** (`--action create`):
1. Operator runs `scripts/popc_reward_payout.py --action create` with commitment details.
2. Script calculates fee from gross reward (integer stocks, no floats).
3. Fee amount is recorded but **not collected yet** — no transaction occurs at creation.
4. Operator records calculated fee in `popc_payouts.json`.

**Step 2 — At commitment completion** (`--action complete`):
1. Operator runs `scripts/popc_reward_payout.py --action complete` with commitment details.
2. Script generates two `sost-cli send` commands (does NOT execute):
   - **TX 1**: PoPC Pool → Foundation fee wallet (5% or 10% fee)
   - **TX 2**: PoPC Pool → Participant (net reward = gross minus fee)
3. Operator reviews, executes manually, records TX hashes in `popc_payouts.json`.

The Foundation pays the same 5% fee as any participant — no exceptions.

### Fee math (integer only)

All calculations use stocks (1 SOST = 100,000,000 stocks) and basis points:

```
fee_rate_bps = int(fee_rate × 10000)    # 500 for 5%
fee_stocks   = (gross_stocks × fee_rate_bps) // 10000
payout_stocks = gross_stocks - fee_stocks
```

No floating-point arithmetic is used in monetary calculations.

### Fee recipient

- **Address:** `sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429` (Foundation fee wallet)
- **Source:** `sost144cc82d3c711b5a9322640c66b94a520497ac40d` (PoPC Pool)

## Reward Process

Until PoPC smart contracts automate reward distribution:

1. At contract creation, the exact SOST reward amount and fee are calculated and published here.
2. At successful completion, both fee and net reward are disbursed from the PoPC Pool:
   - **TX 1**: PoPC Pool → Foundation fee wallet (5% or 10% of gross reward).
   - **TX 2**: PoPC Pool → Participant (gross reward minus fee).
3. All transaction IDs are recorded here and are verifiable on-chain.
4. Payout log is maintained at `popc_payouts.json` with full audit trail.

## Disclaimer

PoPC commitments demonstrate protocol mechanics. They are not a guarantee of gold backing.
SOST is not pegged to gold. There is no redemption right. The reserve ratio is an observable
market metric. Participation in PoPC is voluntary and carries risk (Model A: bond slash risk).
