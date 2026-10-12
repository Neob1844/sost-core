# Operations — Stage 1 (local / devnet only)

Everything in this file runs on a developer machine against a SOST DEVNET_FAST node and a local
Anvil. **No mainnet, no testnet, no real XAUT, no production keys.** Testnet (Sepolia + SOST
testnet) is a later stage and needs explicit authorisation.

## Build and test

```bash
# contracts
cd contracts/wsost && ~/.foundry/bin/forge test --offline

# python
python3 -m pytest -q tests/bridge

# full local E2E (real SOST devnet node + miner + CLI, real Anvil, real contracts)
#   needs build-devnet (cmake -DSOST_DEVNET_FORKS=ON) and ~/.foundry/bin/anvil
python3 tests/bridge/e2e_devnet_anvil.py --work /tmp/sost-stage1
```

The E2E uses ports 18655 / 19655 (SOST devnet) and 8546 (Anvil), starts its own processes and stops
them by PID when it ends. It mines with ONE thread so it does not starve a mainnet miner running on
the same machine. It funds Juan (~130 devnet blocks), so it takes tens of minutes.

## Roles (devnet)

| Role | Holds | Can | Cannot |
|---|---|---|---|
| Observer (×3) | disposable EIP-712 key, own SOST RPC view | attest deposits, pause new mints | mint alone, release SOST |
| Relayer | an Ethereum account with gas | submit ≥2 attestations | mint without them |
| Release signer | the Bridge Vault wallet file (disposable devnet key) | sign + submit releases for burns | release without a burn (journal + indexer) |
| Indexer | read-only RPC access to both chains | reconcile, report, trigger the mint pause | move anything |
| Admin (WSOST config) | an Ethereum account (future: guardian multisig) | propose / apply config after 2 days, unpause | mint, confiscate |
| Guardians (×5, Gold Reserve) | Ethereum accounts | pause 2/5, rescue 4/5, register successor 4/5, queue migration 4/5 | withdraw anywhere |

## Commands

```bash
# indexer: exit code 0 BALANCED, 1 PENDING, 2 CRITICAL; --pause-from stops new mints on CRITICAL
ops/bridge-indexer.py --sost-rpc http://127.0.0.1:18655/ --vault sost1… --start <h> \
   --eth-rpc http://127.0.0.1:8546 --wsost 0x… --abi-dir contracts/wsost/out --out bridge_status.json

# observer: prints attestations as JSON lines
ops/bridge-observer.py --name obs1 --key-file obs1.key --sost-rpc http://127.0.0.1:18655/ --vault sost1… \
   --start <h> --eth-rpc http://127.0.0.1:8546 --wsost 0x… --abi-dir contracts/wsost/out

# governance recount
ops/governance-indexer.py --sost-rpc http://127.0.0.1:18655/ --proposal proposal.json --census census.json
```

## Wrap / unwrap (devnet)

```bash
sost-cli --wallet juan.json --node 127.0.0.1:18655 --yes send <VAULT> 500 \
   --capsule-mode open-note --capsule-text "WSOST:0x<recipient>"
# … 30 confirmations, observers attest, relayer mints …
# unwrap: WSOST.burn(200e8, "sost1<juan>") on Anvil; the ReleaseProcessor sends 200 − 0.001 SOST
#   with capsule WSOST-RELEASE:0x<burnId> from the vault wallet.
```

## Incident handling

- **CRITICAL** — new mints stop (any observer may call `pauseMint`). Transfers and burns continue.
  Read the exact `reasons` in the indexer output; never edit accounting by hand. Unpausing is an
  admin decision after the cause is understood.
- **Burn not released** — check the release journal (`PENDING` entries mean signing started and
  did not finish): verify on chain before doing anything; never sign the same burn twice.
- **Reorg** — attestations are only valid for the canonical block; observers re-attest after the
  deposit is buried again. A deep reorg after a mint is CRITICAL by design.
- **Gold token risk** — pause (2/5) buys time and moves nothing; rescue (4/5 + delay) can only go to
  the fixed Quarantine Vault; leaving quarantine needs the full governed migration.

## Parameters (provisional, configurable)

| Parameter | Stage 1 value | Where |
|---|---|---|
| min confirmations | 30 | WSOST config (timelocked) + observer config |
| release fee allowance | 0.001 SOST | indexer / release processor |
| exposure cap, daily cap | test values | WSOST config (timelocked) |
| admin delay | 2 days | WSOST constant |
| migration timelock (minimum) | 7 days in tests | GoldReserveVault constructor |
| rescue delay | 6 hours in tests | GoldReserveVault constructor |
| governance finality depth | 30 (configurable) | governance indexer |
| min binding age | 576 blocks (research) | `EligibilityRules` |

No pilot value is approved by this document; any mainnet pilot cap is a separate decision.
