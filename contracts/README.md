# SOSTEscrow — Deployment Guide

## Prerequisites

1. Install Foundry: `curl -L https://foundry.paradigm.xyz | bash && foundryup`
2. Copy `.env.example` to `.env` and fill in your values
3. Fund your deployer wallet with ETH (Sepolia ETH for testnet)

## Quick Start (Sepolia Testnet)

### Step 1: Install dependencies
```bash
cd contracts
forge install
```

### Step 2: Run tests
```bash
forge test -vvv
```
All 14 tests must pass before proceeding.

### Step 3: Deploy to Sepolia
```bash
source .env
forge script script/DeploySepolia.s.sol --rpc-url $SEPOLIA_RPC_URL --broadcast
```
Note the deployed addresses from the output.

### Step 4: Verify on Etherscan
```bash
XAUT=<mock_xaut_address> PAXG=<mock_paxg_address> \
  bash script/VerifyEtherscan.sh sepolia <escrow_address>
```

### Step 5: Test the flow manually
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

# Check canWithdraw (should be false)
cast call <escrow> "canWithdraw(uint256)" 0 --rpc-url $SEPOLIA_RPC_URL
```

## Mainnet Deployment (when ready)

### Step 1: Double-check everything
- [ ] All Sepolia tests passed
- [ ] Manual flow tested on Sepolia
- [ ] Source verified on Sepolia Etherscan
- [ ] Security review completed
- [ ] Contract address for sostcore.com prepared

### Step 2: Deploy
```bash
source .env
forge script script/DeployMainnet.s.sol --rpc-url $MAINNET_RPC_URL --broadcast
```

### Step 3: Verify
```bash
bash script/VerifyEtherscan.sh mainnet <escrow_address>
```

### Step 4: Publish
- Add contract address to sostcore.com/sost-popc.html
- Announce in BTCTalk thread
- Update whitepaper with deployed address

## Contract Properties (immutable)
- No admin key, no upgrade proxy, no pause, no emergency withdrawal
- Only XAUT + PAXG accepted (set in constructor, immutable)
- Only original depositor can withdraw
- Only after timelock expires
- Min lock: 28 days, max lock: 366 days
