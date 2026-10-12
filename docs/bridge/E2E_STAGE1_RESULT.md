# Stage 1 local E2E — result (2026-10-12)

`python3 tests/bridge/e2e_devnet_anvil.py` — **44 / 44 PASS**. Real SOST DEVNET_FAST node, miner and CLI
(1 mining thread), real Anvil (chainId 31337), real contracts, real observers / relayer / indexer /
release processor. Disposable keys only; every process stopped by PID at the end.

## Why two phases

SOST capsules are accepted by the node and attachable by `sost-cli` only from `V12_HEIGHT = 7,350`
in **every** profile, devnet included (`capsule_activation_height` defaults to the mainnet value and
the CLI checks `V12_HEIGHT`). The devnet chain used here was at height ~140, so a REAL deposit cannot
yet carry the Ethereum recipient. Node and CLI were not modified (out of scope by rule).

- **Phase R (real devnet node + CLI):** proves the real-node adapter and the safety rules — a real
  500 SOST payment without a capsule is read exactly and is not mintable; a real vault spend without
  a release capsule turns the bridge CRITICAL and pauses new mints on the real contract.
- **Phase F (full capsule flow):** wrap 500 → mint → burn 200 → release → 300/300 BALANCED, on the real
  contract with real EIP-712 signatures, with the SOST side served in memory in the exact
  `gettransaction` shape verified against the real node in Phase R.

A fully real capsule E2E needs either a devnet chain past #7,350 (~22 h of single-thread devnet
mining) or a future dev-profile capsule height in a node/CLI release.

## Steps

```
[PASS] tool present sost-node
[PASS] tool present sost-miner
[PASS] tool present sost-cli
[PASS] tool present anvil
[PASS] devnet build (SOST_DEVNET_FORKS=ON)
[PASS] SOST node is DEV profile
[PASS] wallets: Juan, Bridge Vault (disposable devnet key), miner — vault=sost197114aa63c014a0d4a9910e7efc745377aea3311
[PASS] 1. Juan holds >= 1,000 devnet SOST — 1012.78011345
[PASS] contracts deployed on Anvil — WSOST=0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9 chainId=31337
[PASS] devnet capsule gate — devnet height 140 < 7,350: capsule deposits need the chain past V12 (node + CLI unchanged)
[PASS] R1. real node: 500 SOST to the vault WITHOUT a recipient capsule is read exactly and is NOT mintable
[PASS] R2. real node: observers produce no attestation for it
[PASS] R3. real node: reconciliation BALANCED with a manual-review warning — payment to the vault without a valid WSOST capsule: 8b68be78ae0a0afc428daedb9c247a9d0f5a1022142e6c7956f47bfea0ea0a0d:0 (500.00000000 SOST) — not mintable, manual review
[PASS] R4. real node: a vault spend without a release capsule -> CRITICAL
[PASS] R5. CRITICAL stops NEW mints on the real contract
[PASS] F1. Juan holds 1,000 SOST (in-memory SOST side)
[PASS] F2. deposit of 500 SOST with recipient capsule
[PASS] F3. before confirmations: PENDING, observers refuse
[PASS] F4. 30 confirmations reached
[PASS] F5. 2-of-3 observers attest (EIP-712, real signatures)
[PASS] relayer alone cannot mint
[PASS] relayer pre-flight: block still canonical
[PASS] F6. 500 wSOST minted on the real contract (Python signatures verified on-chain)
[PASS] F7. BALANCED
[PASS] duplicate mint reverts on-chain
[PASS] F8. Juan burns 200 wSOST -> release pending
[PASS] F9-10. release signed through the signer interface
[PASS] journal blocks a second release
[PASS] F11. 200 SOST returned (minus the fee allowance)
[PASS] F12. final: 300 wSOST, >= 300 SOST locked, BALANCED — {"A_confirmed_deposits": 50000000000, "B_pending_deposits": 0, "C_minted": 50000000000, "D_burned": 20000000000, "E_burns_awaiting_release": 0, "F_completed_releases": 19999900000, "G_vault_balance": 30000098000, "H_total_supply": 30000000000, "confirmed_backing": 30000098000, "owed": 30000000000, "surplus": 98000, "tip": 37}
[PASS] FAIL-SIM unbacked mint by 2 compromised observers -> CRITICAL
[PASS] CRITICAL pauses new mints; transfers keep working
[PASS] observers refuse new attestations while CRITICAL
[PASS] G1. mock XAUT contributed to Gold Reserve V2
[PASS] G3. arbitrary withdrawal impossible (no such function)
[PASS] G4. pause with 1 guardian fails
[PASS] G5. pause with 2-of-5 passes and moves nothing
[PASS] proposal hash identical in Python and Solidity
[PASS] G6. migration without a passing vote fails (7/12)
[PASS] G7. vote passed but timelock pending: execute fails
[PASS] G8. destination EOA fails
[PASS] G9a. rescue with 3 guardians fails
[PASS] G10. final approved successor migration passes only with all gates
[PASS] G9b. rescue with 4-of-5 moves the reserve ONLY to its quarantine
```
