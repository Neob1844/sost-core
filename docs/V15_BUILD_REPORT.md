# V15 Final Decentralization Fork — Implementation & Build Report

**Status:** Implemented on the working tree. **NOT deployed. NOT committed.** For review before any flag-day.
**Spec:** `docs/V15_FINAL_DECENTRALIZATION_SPEC.md`
**Build flags:** `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release` (mandatory set).
**Live tip at implementation:** block 17168 → fork target 20000 is ~2832 blocks (~2–3 weeks) away.

---

## 1. What was implemented

From `V15_HEIGHT = 20000` (mainnet), every block routes through the DTD accumulate/payout
machinery: **50% miner / 50% DTD**, the Gold-Vault and PoPC coinbase outputs are gone, and
DTD eligibility additionally requires mining ≥1 block in a **sliding 2016-block window**.
Miner economics (50%) are unchanged.

Design choice that kept the surface small: the coinbase **validator was already correct** for
the PAYOUT (2-output) / UPDATE (1-output, accumulate) shapes — it obeys the caller-supplied
`Phase2CoinbaseContext`. So the change lives in **who builds the context/coinbase**, not in the
validator. Both the block-template (miner-facing) and the submitblock validator go through one
shared helper, `dtd_block_triggered`, so they can never disagree. The **miner binary needs no
change** — it follows the node's `coinbase_shape` (`NORMAL` / `UPDATE_EMPTY` / `PAYOUT`), and V15
non-lottery blocks simply emit the existing `UPDATE_EMPTY` (accumulate) shape. Reorg/undo is
**implicit**: `pending_lottery_after` is stored per block, so disconnect restores it automatically.

### Files changed (`git diff --stat`)
```
 CMakeLists.txt                     |  9 +   (register the V15 test)
 include/sost/lottery.h             | 28 +   (dtd_block_triggered helper; eligibility window param)
 include/sost/params.h              | 25 +   (DTD_RECENT_MINER_WINDOW, v15_dtd_fork_active; retire gates)
 include/sost/popc_v15.h            |  4 +   (POPC_V15_ACTIVATION_HEIGHT -> INT64_MAX on mainnet)
 src/lottery.cpp                    | 14 +   (sliding recency-window filter)
 src/sost-node.cpp                  | 69 +   (block-template + validation ctx + audit + supply, all V15-aware)
 tests/test_lottery_eligibility.cpp | 15 +   (premise updated: gate retired)
 tests/test_v14_fork_gates.cpp      | 18 +   (static_asserts made profile-aware)
 + docs/V15_FINAL_DECENTRALIZATION_SPEC.md   (spec)
 + tests/test_v15_decentralization.cpp       (new consensus tests, 37 checks)
```

### Consensus edits (the 3 coordinated sites, all via one helper)
- `handle_getlotterystate` (block template the miner follows): non-lottery V15 blocks → `UPDATE_EMPTY`
  (accumulate the redirected 50%); eligibility scan only on payout-cadence blocks; sliding window passed.
- Submitblock validation context builder: `triggered = dtd_block_triggered(...)`; non-lottery V15
  blocks accumulate; eligibility uses the sliding window.
- `handle_getlotteryaudit` (winner replay): sliding window passed so the audit reproduces the
  consensus winner past V15 (no false "manipulation" alarm).
- `supply_dtd_lottery_distributed` (analytics): counts the full 50% redirected from V15.

### Deprecated automation RETIRED on mainnet (never auto-activates at 20000/25000)
`POPC_V15_ACTIVATION_HEIGHT`, `POPC_SINGLE_MODEL_HEIGHT`, `DTD_POPC_ELIGIBILITY_HEIGHT` → `INT64_MAX`;
`DTD_POPC_GATE_CONSENSUS_ACTIVE` → `false`. The **testnet** profile keeps the old values so the PoPC
subsystem can still be soaked there. Gold-Vault G4/G5/slice-1/gold-boost stay `INT64_MAX` (unchanged).
No PoPC/Gold-Vault code was deleted — it remains as historical design.

---

## 2. Build result

`cmake --build` with the mandatory flags: **SUCCESS.** Binaries produced:
- `sost-node` (23.9 MB), `sost-miner` (7.8 MB), `sost-cli` (7.7 MB) — all compile clean.

---

## 3. Test result

### Consensus core — ALL GREEN (exit 0)
| Test | Result |
|---|---|
| `test-v15-decentralization` (new) | **37 / 37 passed** |
| `test-coinbase-phase2` | 50 / 50 passed |
| `test-lottery-eligibility` | 77 / 77 passed |
| `test-lottery-rollover` | 53 / 53 passed |
| `test-lottery-frequency` | 71 / 71 passed |
| `test-v14-fork-gates` | passed |

The new V15 suite proves: `dtd_block_triggered` (every block routed through DTD from 20000, only
lottery-cadence blocks pay out), the sliding-2016 window (dormant addresses dropped; the
`[h-2016, h-1]` edge is exact — a miner whose last block was at `h-2016` is IN, at `h-2017` is OUT),
the 50/50 split (odd stock to miner), the activation boundary (19999 off / 20000 on), and that the
PoPC/Gold-Vault gates are retired.

### PoPC subsystem tests — now PROFILE-AWARE and GREEN
The `test-popc-v15*` / `test-popc-single-model` suites previously asserted mainnet PoPC activation
(`popc_v15_active_at(20000) == true`), which the fork makes false. They are now **profile-aware**:
on the **testnet** profile they exercise the live PoPC subsystem as before; on the **mainnet**
profile they verify the **retirement invariant** (`popc_v15_active_at` / `popc_single_model_active`
== false at every height) and exit green. No verbal exceptions — the mainnet suite is 100% green.

| PoPC test (mainnet) | Result |
|---|---|
| test-popc, test-popc-tx, test-popc-v15-authz, test-popc-v15-set, test-popc-v15-eligibility | pass (unaffected) |
| test-popc-v15, test-popc-v15-carrier, test-popc-v15-lifecycle, test-popc-single-model, test-popc-v15-soak, test-popc-v15-carrier-e2e | **pass (profile-aware: assert retirement on mainnet)** |

**Full relevant suite: 17 / 17 green (0 red) on the mainnet profile.** No PoPC/Gold-Vault code was
deleted — it remains as historical design and is still fully exercised on the testnet profile.

---

## 4. Not done (by instruction) / open items

- **Not deployed, not committed.** Awaiting your diff review.
- **Flag-day coordination** with the ~90% dominant miner before block 20000 (same process as V14.7).
- **Website / comms** stay frozen until the binary is approved and the flag-day is dated.
- Files changed by the PoPC-test profile-aware pass (all green): `tests/test_popc_v15.cpp`,
  `test_popc_v15_carrier.cpp`, `test_popc_v15_lifecycle.cpp`, `test_popc_single_model.cpp`,
  `test_popc_v15_soak.cpp`, `test_popc_v15_carrier_e2e.cpp`, `test_lottery_eligibility.cpp`,
  `test_v14_fork_gates.cpp`.

---

## 5. One-command reproduction
```
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli test-v15-decentralization \
      test-coinbase-phase2 test-lottery-eligibility test-lottery-rollover \
      test-lottery-frequency test-v14-fork-gates -j$(nproc)
./build/test-v15-decentralization   # 37/37
```
