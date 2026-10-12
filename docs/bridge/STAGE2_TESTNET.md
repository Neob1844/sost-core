# Stage 2 — wSOST / Gold Reserve V2 testnet + SOST↔wSOST atomic swap (status 2026-10-12)

Branch `feat/wsost-stage2-testnet` (from Stage 1 `796bef1f`, not merged). No consensus, node, miner or sost-cli change.
No Ethereum mainnet, no real XAUT, no real SOST, no production keys.

## Architecture preserved

Canonical conversion stays: native SOST → Bridge Vault → wSOST, and wSOST burn → verification → native release.
The atomic swap (ATOMIC_SWAP_WSOST.md) never mints, burns, unlocks the vault or touches the Gold Reserve.

## Sepolia

- Existing contracts are the superseded PoPC experiment and are **not** reused as architecture:
  SOSTEscrow `0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113`.
- Existing test tokens verified read-only and usable as **TEST TOKENS**: "Mock XAUT" `0x38Ca34c6B7b3772B44212d6c2597Fd91a6f944D0`
  (6 decimals, public `mint`, no owner/pause/blacklist — worthless by construction), "Mock PAXG" `0x754A7D020D559EDD60848450c563303262cAdec7` (PAXG path stays gated).
- New deployment script `contracts/wsost/script/DeployStage2.s.sol` (refuses chainId 1): WSOST, QuarantineVault,
  GoldReserveVault (XAUT enabled, PAXG gated), a fresh AtomicSwapHTLCv2. Dry-run on Anvil: OK.
- Disposable deployer generated (key in `~/sost-keys/`, mode 600, never committed): `0xB6C433C46B4F7Cd95A524B1a4c8A19fa9b51835D`.
  **Balance 0 Sepolia ETH → Sepolia deployment BLOCKED until funded from a faucet (~0.05 ETH).**

## Real capsule E2E

Capsules are valid only from V12_HEIGHT 7,350 in every profile. The devnet is being mined toward 7,350 with
4 threads at nice 19 (≈0.45 blocks/s, ≈4 h), only after checking that the mainnet miner had its cores and RAM.
Status: **IN PROGRESS** (not yet reached).

## Results so far

| Item | Result |
|---|---|
| Solidity (WSOST, Gold Reserve, swap, fuzz, invariants) | 63/63 |
| Existing HTLC suite (unchanged) | 71/71 |
| Python bridge + governance (incl. malicious / conflicting / stale observers) | 36/36 |
| SOST↔wSOST swap E2E, real SOST devnet HTLC + Anvil | 27/27 |
| Slither wsost (15 findings) | triaged: no exploitable issue (CEI respected; strict-equality / timestamp / assembly / naming are informational) |
| Slither HTLCv2 (4 findings) | reentrancy-benign under `nonReentrant`; low-level calls intended |
| Bridge reorg tests (1, 2–5, after threshold, deep after mint) | pass (Stage 1 suite) |

## Open

1. Fund the Sepolia deployer → deploy → Sepolia wrap / unwrap / swap E2E.
2. Devnet past 7,350 → 100 % real capsule wrap/unwrap E2E.
3. Wallet signer for capsule and HTLC transactions (design: CLI_CAPSULE_OFFLINE_DESIGN.md; needs authorization).
4. External review before any mainnet recommendation.

MAINNET_RECOMMENDATION: **DO NOT DEPLOY**.
