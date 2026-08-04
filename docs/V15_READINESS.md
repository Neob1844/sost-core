# V15 Readiness

Living status doc. Updated 2026-07-25. Branch `feat/v15-jackpot-explorer-card`
(pushed; NOT on main, NOT deployed). Evidence-based — a feature is only "READY"
when its release gate (below) is green, not when it compiles.

## Canonical activation values
| Value | Height | Notes |
|---|---|---|
| V15 mainnet activation | **25,000** | moved from 20,000 (2026-07-25) for implementation + soak runway |
| First Historical DTD Jackpot | **25,290** | draw-aligned (`%3==0`), static_asserted |
| DTD-PoPC eligibility | **30,000** | derived = V15_HEIGHT + 5,000 grace (cascaded automatically) |
| Current mainnet height | ~19,022 | deployed binary has V15 gates DEFERRED → nothing activates at 20,000 |
| Forge program | independent / **unchanged** | its 20,000/25,000 are its own phases, not V15 |

## Component status
| Component | Implemented | Tested | Mainnet ready | Blockers |
|---|---|---|---|---|
| Gold Vault/PoPC transition (T) | ✅ | ✅ 289 asserts | ❌ | live regtest soak; testnet DTD schedule |
| Historical Jackpot (J) — pure core | ✅ | ✅ 62 asserts | ❌ | — |
| Historical Jackpot (J) — A1 tx (canonical+exact-match) | ✅ | ✅ (in 62) | ❌ | — |
| Historical Jackpot (J) — live wiring: process_block canonical gate + keyless auth + mempool isolation + min-validation exception | ✅ CODE (commits 9834c889/cf6c1afa/864ea3c2) | ✅ unit (jackpot 108 + block-rule); ❌ live integration | ❌ | regtest harness (needs accelerated testnet schedule: testnet V15=300 sits BELOW DTD activation 7100 — incoherent), miner/template jackpot construction, live Connect/Disconnect/reorg/restart/reindex tests, testnet, soak |
| Explorer V15 (25,000/25,290/30,000) | ✅ | ✅ 24 (gateway) | ❌ (not deployed) | coordinate deploy with node rollout |
| Consumer swap dashboard | ✅ | parse-validated | ❌ (founder-testing) | real quotes need counterparty; not deployed |
| Atomic Swap — policy layer (timeout/swapId/preimage/RPC) | ✅ | ✅ 49 | n/a (off-chain) | route coordinator/orderbook through it |
| Atomic Swap EVM — contract (SafeERC20 + balance-delta) | ⏸ held | ✅ 60 Foundry | ❌ | **fund-custody change — needs external audit before landing/deploy** |
| Atomic Swap BTC — HTLC signing lifecycle | ✅ (gated OFF) | ✅ 121 ON / 50 OFF | ❌ | live bitcoind regtest (no infra), external crypto review; gate stays OFF |

## Release gates
**V15 CONSENSUS:** T ✅ · T tests ✅ · J core ✅ · J process_block gate ✅ · **keyless auth bound to exact canonical tx on EVERY ConnectBlock caller (process_block + reorg + load_chain/reindex) ✅** · adversarial module tests ✅ (test_jackpot 108: wrong winner/amount/input/order/position/extra/missing/duplicate/non-event-height/empty-reserve/signature-set all rejected) · mempool isolation ✅ · min-validation exception ✅ · activation-boundary (T) ✅ · miner/template ❌ · live node accept/Disconnect ❌ · reorg ❌ · restart/reindex ❌ · regtest harness ❌ · testnet ❌ · soak ❌ → **NOT MET** (2026-08-04: security-audit §2 CLOSED, commit d15be583; ctest 101/101; remaining = network-param refactor → harness → runtime integration → testnet/soak)
**EVM SWAP:** create/fund/detect/redeem/refund logic present · timeout policy ✅ · persistence partial · E2E ❌ · contract audit ❌ → **NOT MET**
**BTC SWAP:** script ✅ · funding ✅ · sign ✅ · redeem/refund ✅ · preimage ✅ · regtest ❌ · review ❌ → **NOT MET** (gate stays OFF)
**DASHBOARD:** UI ✅ · backend hooks partial · history ✅ · unsupported pairs disabled ✅ · deployed ❌ → **NOT MET**

## Overall verdict
**V15 READY FOR TESTNET/REGTEST ONLY (partial).** Real blockers to reach Release Candidate:
1. **J live wiring CODE is done** (2026-08-04): process_block calls the canonical
   `validate_block_jackpot` gate BEFORE `ConnectBlock` (the SOLE keyless authorization =
   byte-exact match to the reconstruction from pre-block reserve + this block's DTD winner +
   history-derived rollover), the block loop grants the narrowest exemption (skip R2/signature
   + G1 governance only for the canonical jackpot at a jackpot height), and the mempool
   rejects `TX_TYPE_JACKPOT` explicitly. ctest 101/101. **Remaining:** the regtest **harness**
   (real node+miner) to PROVE end-to-end acceptance/disconnect/reorg/restart/reindex, the
   **miner/block-template** jackpot construction, and testnet + soak. The harness is blocked
   on the incoherent testnet schedule (V15=300 < DTD=7100) which must be lowered coherently.
2. **Regtest/testnet infra**: lower testnet DTD schedule so V15+DTD+J are exercisable; a live fork+jackpot+reorg soak (needs bitcoind for the BTC leg).
3. **EVM contract audit** decision before any SafeERC20 landing/deploy.
4. **Node-upgrade rollout plan** before the public Explorer banner is deployed.

## Network-schedule refactor — resolved design (2026-08-04, the harness unblocker)
The harness is blocked on getting a build where V15/DTD/jackpot activate at reachable
heights. An investigation this session **proved why the naive fix is wrong** and picked the
safe approach:

**The trap (proven, do NOT repeat):** lowering testnet `V15` to a small height (e.g. 300)
is incoherent. The V15 every-block DTD draw depends on machinery that activates *above* it:
- `DTD_DOMINANCE_GATE_HEIGHT = 12100` (DTD anti-dominance / SbPoW-activity gate — `lottery.cpp:140,191`)
- `V13_HEIGHT = 12000` (DTD flip, lottery window 6, drift 30s)
- `V11_PHASE2_HEIGHT = 7100` (SBPoW active — required for DTD)
- the cASERT difficulty ladder (`CASERT_V2..V6/CEILING/STAGED/GRANULAR`, heights 1450→7350).

Dragging `V13`/`Phase2` down to be `< V15` forces the **entire ancient fork ladder** down
with them — dozens of consensus-sensitive difficulty constants and ~20 cASERT/DTD test files
(`test_casert_*`, `test_sbpow_*`, `test_v13_helpers`, `test_coinbase_phase2`, …). That is a
large, consensus-divergence-risky cascade and must NOT be bulldozed. (Two prior attempts to
lower `V13`/`Phase2`/`HIGH_FREQ` on testnet broke `test_v13_helpers`; both correctly reverted.)

**Chosen approach — testnet/regtest V15 ABOVE the ancient ladder (zero ancient-ladder risk):**
- Set testnet `V15_HEIGHT` to a value `> DTD_DOMINANCE_GATE_HEIGHT (12100)` and `> V13 (12000)`,
  e.g. **12500** (order preserved by construction: `Phase2 7100 < V13 12000 < DTD 12100 < V15 12500 < first-J 12500+offset`).
- **Touch zero cASERT/Phase2/V13/DTD constants** → no consensus-history risk, no cASERT/sbpow
  test churn. The only cost is the harness mining ~12.5k regtest blocks (fine at regtest difficulty).
- Rebase the V15-family tests to **relative offsets** (`V15_HEIGHT + k`, not literal `300`):
  `test_v14_fork_gates` (the `V15_HEIGHT==300` static_assert), `test_popc_v15_soak`,
  `test_popc_v15_eligibility`, `test_lottery_rollover`. This is the §6-groupA "tests consume
  the parameter" change, small and self-contained.
- Keep mainnet locked: `V15=25000, first-J=25290, cadence=288, eligibility=30000`.

**APPLIED (2026-08-04, commit `9f7ed835`):** testnet `V15` = 12500, first jackpot = 12792
(draw-aligned), testnet ordering `static_assert`s added; five tests rebased to the schedule
(`v14_fork_gates`, `popc_v15_soak`, `popc_v15_eligibility`, `lottery_rollover`, `tx_validation`).
**Both builds green: mainnet ctest 101/101, testnet ctest 101/101.** No ancient fork moved.

### Runtime-harness feasibility — the SbPoW time-hard blocker (2026-08-04)
There is **no independent regtest network** (only `SOST_TESTNET_FORKS` on/off) and, critically,
**no fast/simulated mining mode**: the miner's `--realtime` flag is a no-op and `sim_time=true`
is unreachable via any flag, so blocks always carry real wall-clock timestamps. cASERT then
targets `TARGET_SPACING = 600 s` of *real* time per block (600 s on every profile — no testnet
override), and Phase2 SbPoW (from height 7100) is deliberately time-hard. Consequence: mining a
fresh chain to the first testnet jackpot at 12792 (≈5700 SbPoW blocks) is **not achievable in a
normal session** — and a "cached bootstrap fixture" doesn't help because generating it has the
same cost. This gates the real-node harness (acceptance/atomicity/disconnect/reorg/restart/
reindex over a mined chain). **The genuine prerequisite is a dev/regtest fast-mine capability**
(trivial PoW + relaxed time-gate + MTP, testnet/dev-only, never mainnet) — a bounded, consensus-
adjacent piece of node+miner work that must precede PART 10–20. Until then the jackpot is proven
at the module/integration level (test_jackpot 108 adversarial asserts) but not over the live
mined node path.

## Deliberately NOT enabled / done (by design)
- Mainnet BTC capability (gate hardwired OFF; code is dormant behind a build option).
- EVM contract change (held in a worktree for an audited PR).
- Any main-branch merge or production deploy (founder decision).
- No `$10`/fiat/purchase jackpot-eligibility rule (rejected on consensus grounds).
