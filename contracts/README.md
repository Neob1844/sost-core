# SOSTEscrow

## What the contract does

SOSTEscrow is a timelocked gold token escrow on Ethereum for SOST PoPC Model B.
Users deposit XAUT (Tether Gold) or PAXG (Paxos Gold) for a fixed duration
(28-366 days). After the lock expires, only the original depositor can withdraw
their tokens. The contract has no admin, no upgrade mechanism, no pause, and no
emergency withdrawal. Once deployed, its behavior is immutable.

## What it does NOT do

- It does NOT custody physical gold. It locks ERC-20 gold tokens.
- It does NOT mint, distribute, or control SOST tokens.
- It does NOT know about SOST chain addresses (Gold Vault, Miner, PoPC Pool).
- It does NOT have any admin, owner, or governance functions.
- It does NOT support partial withdrawals, deposit extensions, or modifications.
- It does NOT charge fees.

## Trust model

- **The contract itself is trustless.** No one can move locked tokens before
  expiry. No one can prevent withdrawal after expiry. The code is the only
  authority.
- **SOST reward payout is trust-dependent.** An off-chain watcher reads
  `GoldDeposited` events and triggers SOST mining rewards on the SOST chain.
  If the watcher fails, users still get their gold back at expiry -- they just
  don't receive SOST rewards until the watcher is restored.
- **Token issuer risk exists.** XAUT and PAXG issuers can freeze addresses.
  This is a property of the underlying tokens, not the escrow contract.

## Escrow contract (Ethereum) vs. payout logic (SOST chain)

| Concern | Where it lives |
|---|---|
| Gold token locking/unlocking | This contract (Ethereum) |
| Deposit event emission | This contract (Ethereum) |
| SOST reward calculation | Off-chain watcher + SOST chain consensus |
| SOST token minting | SOST chain (not Ethereum) |
| Gold Vault / Miner / PoPC Pool | SOST chain addresses (not known to this contract) |

The escrow contract is deliberately minimal. It does one thing -- lock and
release gold tokens -- and emits events that the rest of the system reads.

## Contract Properties (immutable)

- No admin key, no upgrade proxy, no pause, no emergency withdrawal
- Only XAUT + PAXG accepted (set in constructor, immutable)
- Only original depositor can withdraw, only after timelock expires
- Min lock: 28 days, max lock: 366 days

---

## Deployment Guide

### Prerequisites

1. Install Foundry: `curl -L https://foundry.paradigm.xyz | bash && foundryup`
2. Copy `.env.example` to `.env` and fill in your values
3. Fund your deployer wallet with ETH (Sepolia ETH for testnet)

### Quick Start (Sepolia Testnet)

#### Step 1: Run tests
```bash
cd contracts
forge test -vvv
```

#### Step 2: Deploy to Sepolia
```bash
source .env
forge script script/DeploySepolia.s.sol --rpc-url $SEPOLIA_RPC_URL --broadcast
```

#### Step 3: Verify on Etherscan
```bash
XAUT=<mock_xaut_address> PAXG=<mock_paxg_address> \
  bash script/VerifyEtherscan.sh sepolia <escrow_address>
```

#### Step 4: Test the flow manually
```bash
# Mint test XAUT to your address
cast send <mock_xaut> "mint(address,uint256)" $YOUR_ADDR 1000000 \
  --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $SEPOLIA_RPC_URL

# Approve escrow
cast send <mock_xaut> "approve(address,uint256)" <escrow> 1000000 \
  --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $SEPOLIA_RPC_URL

# Deposit (unlock in 30 days)
UNLOCK=$(date -d "+30 days" +%s)
cast send <escrow> "deposit(address,uint256,uint256)" <mock_xaut> 1000000 $UNLOCK \
  --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $SEPOLIA_RPC_URL

# Check deposit
cast call <escrow> "getDeposit(uint256)" 0 --rpc-url $SEPOLIA_RPC_URL
```

### Mainnet Deployment

```bash
source .env
forge script script/DeployMainnet.s.sol --rpc-url $MAINNET_RPC_URL --broadcast
```

Both deploy scripts include chain-ID guards to prevent accidental misdeployment.
