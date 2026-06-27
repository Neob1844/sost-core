# V15 PoPC — Mainnet Activation Notice

> **Status:** activation commit (this PR). **Mainnet consensus fork.**
> Reviewed-not-merged until the coordinated release. Date prepared: 2026-06-27.

## 🚨 MINER / NODE UPGRADE — MANDATORY BEFORE BLOCK 20,000

The **V15 PoPC** consensus rules activate at **block 20,000** on mainnet. This is a
**mandatory binary upgrade**: every node and miner must run a binary built from the
commit containing this change **before block 20,000**, or it will diverge from the
network once the chain crosses the fork height.

```bash
cd sost-core
git checkout main && git pull origin main
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-cli sost-miner -j$(nproc)
# restart node + miner with the new binaries
```

## What activates, and when

| Height | What goes live |
|---|---|
| **20,000** (`POPC_V15_ACTIVATION_HEIGHT = V15_HEIGHT`) | PoPC V15 **on-chain carrier subsystem** (Register/Activate/Renew/Suspend carriers, deterministic active-set recompute, auto-slash / auto-settle) + the single-model PoPC settle path. PoPC carrier transactions (0-value marker output) become **valid** (the PR #24 tx-validation exemption fires from here). |
| **25,000** (`DTD_POPC_ELIGIBILITY_HEIGHT = V15_HEIGHT + 5,000 grace`) | The **DTD lottery now REQUIRES an OPEN PoPC contract** to be eligible (in addition to the existing V13 anti-dominance + SbPoW-activity gates). `DTD_POPC_GATE_CONSENSUS_ACTIVE = true`. |

### ⚠️ "Create AND maintain" — read this
Holding a PoPC is **not a one-time action**. A PoPC commitment **auto-slashes** if it
does not answer its audit challenge every `POPC_V15_AUDIT_INTERVAL_BLOCKS` (1,440)
+ a 288-block grace (~1,728 blocks). A miner who creates a PoPC at block 20,000 and
then does nothing will be auto-slashed (~block 21,728) **before** eligibility even
bites at 25,000. To stay eligible from 25,000 you must **create and keep your PoPC in
good standing** (respond to audits). The ~5,000-block grace (20,000→25,000) is the
window to get set up — it is not a free park.

How to put a PoPC on chain (until the wallet flow automates it):
```bash
sost-cli popc carrier-hex --type register --sost-address <you> --commitment-id <cid> --end-height <h>
sost-cli send --to <you> --amount 1 --popc-carrier <hex>
# then the Activate (attestation) carrier, and re-attest each audit interval
```

## Explicitly NOT activated by this fork
- **Gold Boost** — `POPC_GOLD_BOOST_HEIGHT` stays `INT64_MAX` (deferred; needs the continuous gold-verification pipeline). Boost = 0.
- **Gold Vault Governance** — `GV_G4/G5/SLICE1` stay `INT64_MAX` (deferred; future founder-only-capped pilot).
- **Emission** — unchanged.
- **PoPC DEX** — remains gated off (`POPC_DEX_ENABLED=false`).

## Exact changes in this PR
- `include/sost/popc_v15.h`: `POPC_V15_ACTIVATION_HEIGHT` mainnet `INT64_MAX → V15_HEIGHT` (20,000).
- `include/sost/params.h`: `DTD_POPC_GATE_CONSENSUS_ACTIVE` mainnet `false → true`.
- Test guards/assertions updated from the deferred state to the activated state
  (`test_v14_fork_gates`, `test_lottery_eligibility`, `test_popc_v15`,
  `test_popc_v15_carrier`, `test_popc_v15_lifecycle`, `test_popc_v15_soak`,
  `test_tx_validation`).

## Verification
- Mainnet build (`-DSOST_TESTNET_FORKS=OFF`): **full suite 95/95 pass**.
- Testnet build: PoPC/DTD/carrier suites pass (1 pre-existing, unrelated
  `atomic-swap-htlc-lock` testnet-build failure exists on `main` independent of this PR).
- Prior validation: testnet **live soak PASS** (carrier on-chain, `active_count` 0→1,
  PoPC owner eligible / non-PoPC excluded) + carrier tx-validation fix PR #24 (merged).

## Rollback
Before block 20,000: revert the two constants (`POPC_V15_ACTIVATION_HEIGHT → INT64_MAX`,
`DTD_POPC_GATE_CONSENSUS_ACTIVE → false`) and recompile/redeploy. After the chain
crosses 20,000 a rollback is itself a coordinated fork — avoid.
