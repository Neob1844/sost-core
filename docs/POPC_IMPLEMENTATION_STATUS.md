# PoPC Implementation Status

**Date:** 2026-03-28
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
| popc.h skeleton | READY | `include/sost/popc.h` |
| Wallet PoPC UI | READY | `sost-wallet.html` (registration form, calculator) |

## What NEEDS to be built (Phase 34+)

| Component | Effort | Priority | Risk |
|-----------|--------|----------|------|
| src/popc.cpp — PoPCRegistry full implementation | 3-5 days | HIGH | LOW (application layer, not consensus) |
| RPC: popc_register, popc_status, popc_list | 2-3 days | HIGH | LOW |
| Etherscan checker daemon mode + API key | 1 day | HIGH | MEDIUM (rate limits) |
| Reward distribution (manual or semi-auto) | 2-3 days | HIGH | HIGH (moves real funds) |
| Slash execution script | 1-2 days | MEDIUM | HIGH (moves real funds) |
| Audit entropy from ConvergenceX blocks | 2-3 days | MEDIUM | LOW |
| Reputation system (stars 0→1→3→5) | 1 day | LOW | LOW |
| Price Bulletin system | 2-3 days | MEDIUM | LOW |

**Total estimated: ~15-20 days of focused development**

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
