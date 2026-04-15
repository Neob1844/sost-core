# PoPC Deployment Guide

**Date:** 2026-03-29
**Status:** Phase 3 Complete — Registry + RPC + TX Builders + Auto-Distribution

## Architecture

PoPC is an **application-layer** system built on top of the existing consensus-level `BOND_LOCK (0x10)` mechanism. No consensus rules were changed.

| Layer | Component | Status |
|-------|-----------|--------|
| Consensus | BOND_LOCK output type (0x10) | ACTIVE at height >= 5000 |
| Consensus | ESCROW_LOCK output type (0x11) | ACTIVE at height >= 5000 |
| Consensus | S11 time-lock enforcement | ACTIVE |
| Application | PoPCRegistry (register, complete, slash) | IMPLEMENTED |
| Application | Bond sizing (compute_bond_pct) | IMPLEMENTED |
| Application | Reward calculation (compute_reward_pct) | IMPLEMENTED |
| Application | Reputation system (0/1/3/5 stars) | IMPLEMENTED |
| Application | Audit entropy (ConvergenceX-derived) | IMPLEMENTED |
| Application | Save/Load (JSON persistence) | IMPLEMENTED |
| Application | TX Builders (release, reward, slash) | IMPLEMENTED |
| Application | RPC: popc_register | IMPLEMENTED |
| Application | RPC: popc_status | IMPLEMENTED |
| Application | RPC: popc_check | IMPLEMENTED (manual bridge) |
| Application | RPC: popc_release | IMPLEMENTED |
| Application | RPC: popc_slash | IMPLEMENTED |
| Application | Etherscan checker script | READY (scripts/popc_etherscan_checker.py) |
| Application | Auto-distribution (Option B) | READY (scripts/popc_auto_distribute.sh) |
| Application | Cron installer | READY (scripts/install_popc_cron.sh) |
| Application | RPC commands | NEXT PHASE |
| Application | Etherscan checker daemon | READY (scripts/popc_etherscan_checker.py) |

## How to Build

```bash
cd ~/SOST/sostcore/sost-core
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

## How to Test

```bash
cd build
ctest --output-on-failure    # All 24 suites (22 existing + 2 PoPC)
./test-popc                  # 31 individual PoPC registry tests
./test-popc-tx               # 12 individual PoPC TX builder tests
```

## RPC Commands

### popc_register — Register a PoPC commitment
```bash
curl -s -u user:pass -X POST http://127.0.0.1:18232 -d '{
  "method": "popc_register",
  "params": ["sost1...", "0xETH...", "XAUT", "31103", "6"],
  "id": 1
}'
# Returns: commitment_id, required_bond, expected_reward
```

### popc_status — View all commitments and pool balance
```bash
curl -s -X POST http://127.0.0.1:18232 -d '{"method":"popc_status","id":1}'
# Returns: active_count, total_bonded, pool_balance, commitments list
```

### popc_check — Verify gold custody (manual bridge to Python checker)
```bash
curl -s -u user:pass -X POST http://127.0.0.1:18232 -d '{
  "method": "popc_check",
  "params": ["0xETH..."],
  "id": 1
}'
# Returns: instructions to run scripts/popc_etherscan_checker.py
```

### popc_release — Complete commitment and release bond + reward
```bash
curl -s -u user:pass -X POST http://127.0.0.1:18232 -d '{
  "method": "popc_release",
  "params": ["COMMITMENT_ID_HEX"],
  "id": 1
}'
# Returns: reward amount, completion confirmation
```

### popc_slash — Slash a commitment for custody failure
```bash
curl -s -u user:pass -X POST http://127.0.0.1:18232 -d '{
  "method": "popc_slash",
  "params": ["COMMITMENT_ID_HEX", "XAUT balance dropped to 0"],
  "id": 1
}'
# Returns: slash confirmation, amount confiscated
```

## How to Deploy to VPS

1. **Stop the node safely:**
   ```bash
   ssh vps
   systemctl stop sost-node
   ```

2. **Back up current binary:**
   ```bash
   cp /opt/sost/bin/sost-node /opt/sost/bin/sost-node.bak
   ```

3. **Build on VPS (or copy binary):**
   ```bash
   cd /opt/sost/sost-core
   git pull origin main
   mkdir -p build && cd build
   cmake .. -DCMAKE_BUILD_TYPE=Release
   make -j$(nproc)
   ```

4. **Copy binary:**
   ```bash
   cp build/sost-node /opt/sost/bin/sost-node
   ```

5. **Restart and verify:**
   ```bash
   systemctl start sost-node
   systemctl status sost-node
   # Verify chain is syncing:
   curl -s -X POST http://127.0.0.1:18232 -d '{"method":"getblockcount","id":1}'
   ```

## PoPC Lifecycle (Future RPC Phase)

```
1. User creates BOND_LOCK TX (existing CLI: sost-cli create-bond <amount> <blocks>)
2. User registers PoPC metadata via RPC: popc_register
3. System tracks commitment in PoPCRegistry
4. Etherscan checker verifies gold custody periodically
5. After commitment period: popc_release (bond returned + reward from PoPC Pool)
6. If custody fails: popc_slash (bond confiscated to PoPC Pool + Gold Vault)
```

## Files Modified/Created

| File | Action | Description |
|------|--------|-------------|
| src/popc.cpp | CREATED | Full PoPCRegistry implementation |
| tests/test_popc.cpp | CREATED | 31 tests covering all PoPC functions |
| CMakeLists.txt | MODIFIED | Added popc.cpp to library, test-popc target |
| include/sost/popc.h | UNCHANGED | Skeleton already existed |

## Test Results

- **23/23 CTest suites pass** (22 existing + 1 new)
- **31/31 individual PoPC tests pass**
- **Zero regressions** in existing test suites

## Constants (from popc.h)

| Constant | Value | Description |
|----------|-------|-------------|
| Bond rates | 10-25% | Based on SOST/gold price ratio |
| Reward 1mo | 1% | Of bond (Tier 1 base max) |
| Reward 3mo | 4% | |
| Reward 6mo | 9% | |
| Reward 9mo | 15% | |
| Reward 12mo | 22% | |
| Tier system | 6 tiers | 100%/75%/50%/30%/15%/8% by active contracts |
| Hard cap | 1,000 SOST | Max reward per contract |
| Max contracts | 1,000 | Active simultaneously |
| Protocol fee | 3% (A) / 8% (B) | Differentiated: risk-taker discount vs zero-risk premium |
| Slash split | 50/50 | PoPC Pool / Gold Vault |
| Audit grace | 288 blocks | ~48 hours |

## What Must NOT Be Rushed (Next Phases)

1. **RPC commands** — Need careful auth integration
2. **Reward distribution** — Moves real SOST from PoPC Pool. Must be tested extensively.
3. **Slash execution** — Confiscates user bonds. Must be provably correct.
4. **Etherscan daemon** — Rate limits, API key management
