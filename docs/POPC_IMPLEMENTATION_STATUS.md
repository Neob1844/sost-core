# PoPC Implementation Status

**Date:** 2026-03-29
**Author:** NeoB

## What EXISTS (ready to use)

| Component | Status | Location |
|-----------|--------|----------|
| BOND_LOCK tx type (0x10) | ACTIVE at height ≥5000 | `transaction.h:33` |
| ESCROW_LOCK tx type (0x11) | ACTIVE at height ≥5000 | `transaction.h:34` |
| Bond validation (S11) | ACTIVE | `tx_validation.cpp` |
| Lock payload parsing | ACTIVE | `transaction.h:117` |
| Wallet bond commands | ACTIVE | `sost-cli.cpp` (bond, escrow, listbonds) |
| PoPC Pool address | ACTIVE | `params.h:193` — receives 25% every block |
| PoPC Pool balance | ~3,600 SOST | Accumulating ~1.96/block |
| Etherscan checker script | READY | `scripts/popc_etherscan_checker.py` |
| PoPC registry (first entry) | READY | `data/popc_registry.json` |
| popc.h declarations | READY | `include/sost/popc.h` |
| **PoPCRegistry implementation** | **IMPLEMENTED** | `src/popc.cpp` (31 tests, all pass) |
| **Bond sizing (compute_bond_pct)** | **IMPLEMENTED** | `src/popc.cpp` — 5-tier table |
| **Reward calculation** | **IMPLEMENTED** | `src/popc.cpp` — 1/4/9/15/22% by duration |
| **Reputation system** | **IMPLEMENTED** | `src/popc.cpp` — 0/1/3/5 stars |
| **Audit entropy** | **IMPLEMENTED** | `src/popc.cpp` — ConvergenceX-derived |
| **Save/Load (JSON)** | **IMPLEMENTED** | `src/popc.cpp` |
| **TX Builders (release, reward)** | **IMPLEMENTED** | `src/popc_tx_builder.cpp` |
| **RPC: popc_register** | **IMPLEMENTED** | `src/sost-node.cpp` |
| **RPC: popc_status** | **IMPLEMENTED** | `src/sost-node.cpp` |
| **RPC: popc_check** | **IMPLEMENTED** | `src/sost-node.cpp` (manual bridge) |
| **RPC: popc_release** | **IMPLEMENTED** | `src/sost-node.cpp` |
| **RPC: popc_slash** | **IMPLEMENTED** | `src/sost-node.cpp` |
| Wallet PoPC UI | READY | `sost-wallet.html` (registration form, calculator) |

## What NEEDS to be built (next phases)

| Component | Effort | Priority | Risk |
|-----------|--------|----------|------|
| Etherscan checker daemon mode + API key | 1 day | HIGH | MEDIUM (rate limits) |
| Live reward TX broadcast (pool key management) | 1-2 days | HIGH | HIGH (moves real funds) |
| Price Bulletin system | 2-3 days | MEDIUM | LOW |
| Full Etherscan integration in C++ | 2-3 days | LOW | MEDIUM |

**Remaining estimated: ~6-9 days of focused development**

## What must NOT be rushed

1. **Reward distribution** — moves SOST from the constitutional PoPC Pool. Must be tested extensively.
2. **Slash execution** — confiscates user bonds. Must be provably correct.
3. **Consensus changes** — NONE planned. PoPC is application-layer only.

## Current activation timeline

- Height 5000 activates BOND_LOCK/ESCROW_LOCK
- Current height: ~1900
- Remaining: ~3100 blocks ≈ 21 days ≈ April 18, 2026
- PoPC registration UI ready in wallet
- Full PoPC system: target Q3-Q4 2026
