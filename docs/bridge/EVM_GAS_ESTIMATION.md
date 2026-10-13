# EVM gas estimation: why forge under-estimated Sepolia deployments

Status: **EXPLAINED**. Every Stage 2 Sepolia deployment is reproduced exactly from a measured cost model (residual under 0.03 %).
Measured 2026-10-13 with read-only RPC calls only. Nothing was signed or sent.

## Summary

- Glamsterdam activated on Sepolia on **2026-10-06 13:53:36 UTC**.
  - Proof: `eth_config` reports `activationTime` 1791294816. Block headers carry `blockAccessListHash` (EIP-7928) and `slotNumber`. The builder-deposit system contract (EIP-7732) is present.
  - Glamsterdam includes **EIP-8037**, which prices state creation per byte with `CPSB = 1530` gas/byte.
- Under EIP-8037:
  - code deposit costs **1,530 gas/byte** (was 200);
  - a new account costs **120 × 1530 = 183,600**;
  - a new storage slot costs **64 × 1530 = 97,920** of state gas (was 20,000).
- forge 1.5.1 simulates with the pre-Glamsterdam schedule.
  - `evm_version = cancun`. Prague and Osaka give identical figures here.
  - forge 1.5.1 does not implement Amsterdam: `anvil --hardfork amsterdam` panics with `unimplemented Amsterdam`.
  - It multiplies its local result by 130 %.
- For WSOST that gave 2,239,725 × 1.3 = **2,911,642**, which is exactly the limit of the first failed tx. The real cost is **15,095,931**: 6.74× the local figure, or 5.2× forge's padded limit.
- **Code deposit dominates.** WSOST's 8,821 runtime bytes cost 13.50 M gas, 89 % of the deployment.

## Failed transactions (on-chain facts)

| Tx | Limit | Result | Explanation |
|---|---|---|---|
| `0x9b1b300e06ed89208e56ad594995cacc1d349e5632b66df5b29654a6098a61e9` (nonce 0, block 11904085) | 2,911,642 | out of gas (status 0, all gas used) | WSOST initcode, byte-identical to the later successful deploy. Limit = local 2,239,725 × 1.30 (forge default `-g 130`). |
| `0x6485843dc435bc1a32f51a968cf2cc984afa01fb4017e9fa2f2f85cdcdd9aaeb` (nonce 1, block 11904093) | 5,599,312 | out of gas | Same initcode. Limit = 2,239,725 × 2.50 (`-g 250`). |
| `0x6a082175f7494ff613db0c1728d52f4a3e7508681410f9d7d715b2876563afcb` (nonce 8, block 11904221) | 21,000 | status 0, gasUsed 21,000 | 0.0005 ETH to a new account. Under EIP-8037 a value transfer that creates an account costs 204,600 (measured). The 183,600 new-account state charge does not fit in 21,000. |

## Method

- All Sepolia figures come from `eth_simulateV1`. It returns the exact `gasUsed` per call against the latest state, with no key and no transaction.
  - Replaying the four Stage 2 deployment inputs gives **exactly** the on-chain `gasUsed`.
  - `eth_estimateGas` on reth overshoots by about 0.8–1.5 % because of its binary-search tolerance, so it was not used for fitting.
- The pre-Glamsterdam baseline is the same calls on a local anvil (forge 1.5.1, Prague). That is the EVM forge simulates.
- Reproduce with `tests/bridge/lab/evm_gas_probe.py`.
- Raw results:
  - `docs/bridge/sepolia/gas-model-sepolia.json`
  - `docs/bridge/sepolia/gas-model-classic-anvil.json`

## Synthetic measurements

| Case | Sepolia (Glamsterdam) | Local forge/anvil | Δ |
|---|---:|---:|---:|
| ETH transfer to self (existing account) | 12,000 | 21,000 | −9,000 (lower intrinsic cost) |
| 1 wei to a **new** account | **204,600** | 21,000 | +183,600 = 120 × 1530 |
| 0 wei to a new account (no account created) | 15,000 | 21,000 | −6,000 |
| CREATE, empty runtime | 207,668 | 53,068 | **+154,600** |
| CREATE, runtime 1,000 B | 1,737,982 | 253,190 | |
| CREATE, runtime 2,000 B | 3,268,266 | 453,288 | |
| CREATE, runtime 4,000 B | 6,328,847 | 853,497 | |
| CREATE, runtime 8,000 B | 12,450,064 | 1,653,964 | |
| → slope per runtime byte | **1,530.3** | 200.0 | **+1,330** |
| CREATE + 1 new storage slot | 317,716 | 75,196 | |
| CREATE + 10 new slots | 1,308,708 | 274,908 | |
| CREATE + 50 new slots | 5,713,124 | 1,162,524 | |
| → slope per new non-zero slot | **110,110** | 22,190 | **+87,920** |

The slot slope breaks down as follows:
- Of the +87,920, 77,920 is the state-gas change (97,920 − 20,000).
- The other 10,000 is execution-side SSTORE repricing (EIP-8038 constants). It is measured, not split further.

## Cost model and fit to the real deployments

The Sepolia (Glamsterdam) cost of a deployment is:

```
local_classic + 154,600 + 1,330 × runtime_bytes + 87,920 × new_nonzero_slots
```

- `local_classic` is the forge/anvil gasUsed.
- New slots were counted with an anvil `prestateTracer` diff. WSOST has 11, both vaults have 12 and the HTLC has none.

| Contract | Local gas | Runtime B | New slots | Model | Sepolia gasUsed | Residual | Sepolia / local | Code-deposit share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WSOST | 2,239,725 | 8,821 | 11 | 15,093,375 | **15,095,931** | +2,556 (0.017 %) | 6.74× | 89.4 % |
| QuarantineVault | 1,494,309 | 5,304 | 12 | 9,758,269 | **9,760,465** | +2,196 (0.022 %) | 6.53× | 83.1 % |
| GoldReserveVault | 2,072,738 | 7,987 | 12 | 13,905,088 | **13,907,788** | +2,700 (0.019 %) | 6.71× | 87.9 % |
| AtomicSwapHTLCv2 | 1,386,123 | 6,166 | 0 | 9,741,503 | **9,742,661** | +1,158 (0.012 %) | 7.03× | 96.8 % |
| **Total** | 7,192,895 | | | | **48,506,845** | | 6.74× | |

- The residual of 1–3 k gas comes from other small execution-gas repricings: cold access, calldata and the like.
- Optimizer settings and initcode size do not explain the gap:
  - Both sides execute the same bytes.
  - The EIP-3860 initcode word cost and calldata are within the residual.
- The **"~5×"** figure is the real cost divided by forge's padded limit. For WSOST that is 15.10 M / 2.91 M = 5.2×. Over the four contracts it is 5.0–5.4×.

### EIP-8037 reservoir and the EIP-7825 cap

On Sepolia now, the EIP-7825 cap (16,777,216) applies to **execution** gas only. The rest of the gas limit goes into a state-gas reservoir, and unused reservoir gas is returned.

- Measured: a contract with 24,576 B of runtime costs 37,817,024 gas. It succeeds when the transaction gas limit is above 16.7 M and fails at 16,777,216.
- A 24,577 B runtime also deployed, so EIP-170's 24,576 limit is no longer enforced as before. The public RPC's 50 M call cap prevented testing higher.
- Consequence for tooling: clamping the limit to 16,777,216 is safe only when the node estimate fits under the cap.
  - WSOST's estimate is 15,216,907, just under the cap.
  - A contract of about 10.8 KB or more of runtime **cannot** be deployed with a cap-clamped limit on Sepolia.

## What forge does (verified locally with a recording RPC proxy)

- `forge script --broadcast` without `--skip-simulation`:
  - gas limit = forge's **local** EVM gasUsed × `--gas-estimate-multiplier` (130).
  - The node's `eth_estimateGas` is never called.
  - **Unsafe** on Sepolia, and on any chain whose gas schedule forge does not implement.
- `forge script --broadcast --skip-simulation`:
  - gas limit = node `eth_estimateGas` × 1.3.
  - Safe with respect to pricing. On WSOST it would give 19.8 M, which is valid only because Sepolia has the reservoir.
- `forge create`:
  - gas limit = node `eth_estimateGas` with **no margin**.
- No `--evm-version` / `--hardfork` value in forge/anvil 1.5.1 reproduces Sepolia: `amsterdam` is unimplemented.
- When Foundry is upgraded, re-check against `tests/bridge/lab/evm_gas_probe.py`. Even then, the node estimate stays the source of truth.

## Tooling changes

- `ops/sostbridge/evm_gas.py`: a reusable module plus a dry-run CLI. It never signs or sends.
  - **Refuses chainId 1** unless `--i-understand-mainnet` is given. That flag is not to be used without a separate decision.
  - Can also pin `--expect-chain-id`.
  - Gas limits come only from the **target node's** `eth_estimateGas`, plus a margin (default 1.15).
    - The limit is clamped to the EIP-7825 cap when the estimate fits under it.
    - An estimate above the cap needs `--allow-above-7825-cap` (EIP-8037 chains only).
  - The dry run prints each transaction's estimate and limit and the total ETH, at the node's gas price or `--gas-price-gwei`. It also reports whether the chain has Glamsterdam-era headers.
  - Plan file format:

    ```
    python3 ops/sostbridge/evm_gas.py --rpc "$RPC" --from 0xDEPLOYER --plan plan.json --gas-price-gwei 1
    # plan.json: [{"name": "WSOST", "data_file": "init_WSOST.hex"}, {"name": "fund", "to": "0x..", "value": 1}]
    ```
- `tests/bridge/sepolia_stage2_deploy.py`:
  - now uses the module for the chain guard (Sepolia only) and gas limits;
  - gains `--dry-run --from 0x..`, which needs no key file.
  - Live dry-run on 2026-10-13: WSOST 15,216,907 / QuarantineVault 9,839,096 / GoldReserveVault 14,019,105 / AtomicSwapHTLCv2 9,821,151. Total 48.9 M gas, 0.0489 ETH at 1 gwei.
- `tests/bridge/test_evm_gas.py`: 19 unit tests against a mocked RPC, no network. They cover:
  - the mainnet refusal, which happens before any estimate;
  - the expected-chain check;
  - the margin, cap and above-cap flag;
  - totals and costs;
  - the CLI;
  - that the module has no send or sign path.
- `tests/bridge/lab/evm_gas_probe.py`: the read-only measurement probe used for this document.
- Guards were added to:
  - `contracts/wsost/script/DeployStage2.s.sol`
  - `contracts/atomic-swap/script/DeployHTLCv2.s.sol`
  - `contracts/atomic-swap/deploy/DEPLOY_HTLCV2.md`
  - `contracts/README.md`
  - `docs/V15_OTC_EVM_TESTNET_GUIDE.md`

  The rule they state: never `forge script --broadcast` without `--skip-simulation`, and run the dry-run plan first.

## Implications for an eventual Ethereum Mainnet deployment

These checks used **read-only** calls only (no transaction):
- `eth_config`
- `eth_getBlockByNumber`
- `eth_estimateGas` from the deployer address with the same initcode

Results on 2026-10-13:
- Mainnet runs the BPO2 configuration, active since 2026-01-07.
- It has a 60 M block gas limit.
- Its headers have **no** `blockAccessListHash`, and **no next fork is scheduled** in `eth_config`.
- Mainnet still uses the classic schedule. Node estimates today:

  | Contract | Mainnet estimate |
  |---|---:|
  | WSOST | 2,258,668 |
  | QuarantineVault | 1,507,336 |
  | GoldReserveVault | 2,090,356 |
  | AtomicSwapHTLCv2 | 1,398,291 |
  | **Total** | about **7.25 M** gas |

  These are within about 1 % of the local figures.

| Scenario | Total gas (4 contracts) | @ 0.3 gwei | @ 1 gwei | @ 5 gwei | @ 20 gwei |
|---|---:|---:|---:|---:|---:|
| Mainnet today (classic) | ~7.25 M | 0.0022 ETH | 0.0073 ETH | 0.036 ETH | 0.145 ETH |
| Mainnet if Glamsterdam ships with EIP-8037 as on Sepolia | ~48.5 M | 0.0146 ETH | 0.0485 ETH | 0.243 ETH | 0.970 ETH |

Do not assume either row. Before any mainnet decision, re-measure on mainnet:
1. Check which fork is active at the planned time (`eth_config`, header fields).
2. Get node `eth_estimateGas` for the exact final initcode, using `evm_gas.py`'s dry run. The mainnet flag is needed for that, and it is not authorised here.
3. Check whether EIP-8037's parameters on mainnet still match. EIP-8037 is in Last Call until 2026-11-01, so CPSB and the per-item byte counts may change.
4. Check whether the cap or reservoir rules allow a limit above 16.7 M.
5. Use the gas price at that moment.

The higher costs also apply to ordinary operations: every new account and every new non-zero storage slot costs about 88 k more. That covers the first mint to a holder, a new HTLC lock and similar. Sepolia operation costs in `STAGE2_SEPOLIA_RESULT.md` already reflect this: mint 609 k, lockERC20 928 k.

## Sources

- EIP-8037, State Creation Gas Cost Increase: https://eips.ethereum.org/EIPS/eip-8037. It gives CPSB 1530, 120 / 64 / 23 state bytes and the reservoir model.
- The Glamsterdam Sepolia activation, 2026-10-06 13:53:36 UTC, is confirmed by the node's `eth_config` `activationTime` and by public announcements.
