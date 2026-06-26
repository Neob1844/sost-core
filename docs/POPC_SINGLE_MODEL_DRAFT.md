# DRAFT: PoPC single-model consensus schedule

Status: **DRAFT — consensus-DEFERRED. Do not merge until the three blockers below are closed.**
Whitepaper reference: §6.0 ("Redesigned PoPC — One Native Bond, Gold as Boost").

## What this is

Unifies the former two-model PoPC (Model A — native SOST bond; Model B — gold-vault
escrow) into **one SOST-native protocol**:

- **One bond, posted in SOST** — the only collateral and the only thing that can be slashed.
- **Gold is an optional reward boost**, never collateral and never slashed.

The change is height-gated with **two decoupled gates**:

- **Base single model → tied to V15** (`POPC_SINGLE_MODEL_HEIGHT = V15_HEIGHT`, mainnet 20000 /
  testnet 300). The single native-SOST bond replaces the old Model A/B at the same height PoPC
  goes live, so no superseded architecture is ever launched.
- **Gold Boost → its own deferred gate** (`POPC_GOLD_BOOST_HEIGHT`, mainnet `INT64_MAX` until
  verification is ready; testnet dry-runs at V15). Gold reads external-chain state, so it stays
  non-critical and is enabled independently — never gating the native bond.

> **Decision:** V15 activates PoPC as the single native SOST-bond model at block 20,000. Gold Boost
> is enabled at the same height only if verification is ready; otherwise it remains deferred and
> non-critical.

The settle-time payout **is now wired** (app-layer, in the `popc_complete` handler — the V15
auto-settle in `popc_v15.h` only decides *status*, not the reward amount). Even so there is **no
behavioural change on mainnet today**: the base reward path is untouched, and the boost is a no-op
until *both* gates are active — base is set to V15 (20000) and the Gold Boost stays deferred
(`INT64_MAX`), so the boost is always 0 on mainnet until that gate is set to a finite height.

## Explicit guarantees (what this PR does NOT do)

```
No consensus change takes effect until the activation height.
No new auto-slash is activated — auto-slash/settle stays V15-gated
    (DTD_POPC_ELIGIBILITY_HEIGHT) and is untouched here.
Gold is never converted into collateral.
Gold is never slashable.
The coinbase emission split is unchanged (50% miner / 25% Metals Reserve /
    25% PoPC Pool). emission.cpp does not change.
The Gold Boost is funded from the PoPC Pool (capped, surplus-only); the Metals
    Protocol Reserve (§5) is never touched.
```

> **Gold verification may be automated, but until ZK state proofs are available it
> remains non-critical: it can grant or deny a boost, but it can never slash, seize,
> or affect native PoPC consensus safety.**

## Economics (active only at/after the activation height)

Base reward (native SOST bond), by lock duration — **unchanged** from the existing table:

| Lock | 1mo | 3mo | 6mo | 9mo | 12mo |
|------|-----|-----|-----|-----|------|
| Base | 1%  | 4%  | 9%  | 14% | 20%  |

Gold Boost — multiplier **on top of** the base reward, by continuously-verified gold days:

| Gold verified | 0–30 days | 31–90 days | 91+ days |
|---------------|-----------|------------|----------|
| Boost         | +0%       | +10%       | +20%     |

- Operational cap: **+20%**. Technical maximum (governance headroom, hard-clamped): **+25%**.
- Worked example: 12-month bond = 20% base; with gold 91+ days → 20% × 1.20 = **24%**.
- Withdraw gold (or if verification is briefly unavailable) → revert to base reward, no penalty.

## Automation roadmap (layered — never put Ethereum inside SOST consensus)

Full automation does **not** mean observing Ethereum from SOST consensus (that would
import an external chain's safety into ours). It is automated in layers, hardest part last:

**Phase 1 — PoPC Core, fully automatic now.** Lives entirely in SOST, no humans, no
external chain, no watcher: stake SOST, lock period, audits, base-reward computation,
slashing of the SOST bond, distribution from the PoPC Pool, height-gated activation.

**Phase 2 — Gold Boost, automatic but non-critical (OFF-consensus).** A watcher /
attestation verifies XAUT/PAXG (minimum amount + age) and grants the boost; if it cannot
verify, there is simply no boost. Invariant:

```
verification failure = loses the bonus
never = slash
never = PoPC lock
never = penalty
```

**Phase 3 — Gold Boost, trustless via ZK.** The user submits a succinct proof that
`balanceOf(XAUT/PAXG) >= minimum` at a given Ethereum block; SOST verifies the proof with
no trusted watcher. This is the preferred end-state (over an in-consensus Ethereum light
client). Tracked in whitepaper §6.14 (ZK Proof Extension).

This sequencing delivers real automation without an architectural mistake: the native bond
is trustless from day one, and the only part that cannot yet be trustless (external-chain
gold state) is confined to an upside-only, non-consensus path until ZK proofs mature.

## Gold Boost funding & protection (decided)

> **The Gold Boost is funded from the PoPC Pool and capped so it cannot dilute the base PoPC reward.
> The Metals Protocol Reserve remains untouched.**

**Eligibility.** The boost requires tokenized gold worth at least the greater of **25% of the SOST
bond value** or **0.25 PAXG/XAUT** (≈ 0.25 troy oz), held continuously for the verified period. Dust
(e.g. 0.001 PAXG) never qualifies; larger bonds require proportionally more gold. No fiat threshold
is hard-coded — the floor is gold-native (`popc_gold_boost_eligible`).

The Metals Reserve (§5) is constitutional — it accumulates SOST toward future gold backing. The Gold
Boost is a PoPC reward, so it is paid from the PoPC Pool (§6), never from the Metals Reserve. The
coinbase split is genuinely unchanged: **50% miner / 25% Metals Reserve / 25% PoPC Pool**.

Protection rules (encoded in `popc_gold_boost_payout_stocks`):

```
1. base_reward = mandatory PoPC payment, absolute priority.
2. gold_boost  = optional extra, paid ONLY from PoPC Pool surplus after the base is covered.
3. the boost can NEVER reduce the base reward.
4. if surplus is insufficient, the boost is scaled down or paid as 0.
5. cap +20% operational, +25% technical maximum (hard-clamped).
```

Example: base = 100 SOST, gold +20% → target 120 SOST. If the PoPC Pool can only safely cover the
base, the user receives 100 SOST, not 120 — the base is never sacrificed for a boost.

## Files in this change

| File | Change |
|------|--------|
| `include/sost/params.h` | `POPC_SINGLE_MODEL_HEIGHT = V15_HEIGHT` + `popc_single_model_active(h)`; separate `POPC_GOLD_BOOST_HEIGHT` (mainnet `INT64_MAX`, testnet V15) + `popc_gold_boost_active(h)` |
| `include/sost/popc.h` | Gold-boost constants + `popc_gold_boost_bps()` + `popc_apply_gold_boost()` + surplus-aware `popc_gold_boost_payout_stocks()`; `ESCROW_REWARD_RATES` marked deprecated |
| `include/sost/popc.h` (cont.) | `popc_settle_reward_stocks()` — full settle composition (base always paid, gated surplus-aware boost); `popc_gold_boost_eligible()` — `max(25% bond value, 0.25 PAXG/XAUT)` threshold |
| `src/sost-node.cpp` | `popc_complete` handler wired to `popc_settle_reward_stocks` (base + optional boost from PoPC Pool surplus); base path untouched |
| `tests/test_popc_single_model.cpp` | 41 transition tests (gates + boost math + surplus payout + settle matrix + eligibility threshold) |
| `CMakeLists.txt` | registers `test-popc-single-model` (ctest `popc-single-model`) |

The wired path is the **app-layer** `popc_complete` handler (the PoPC payout is application-layer;
only the 25% pool inflow is consensus). The base reward formula is untouched — the boost is purely
additive. `emission.cpp` is **not** touched.

## Transition tests (`ctest -R popc-single-model`)

```
base height == V15_HEIGHT  -> single model tied to V15 (replaces Model A/B)
height == activation       -> single model active
height <  activation       -> inert (byte-identical to today)
gold gate >= base gate     -> gold never activates before the native bond
gold gate active/inert     -> boost gate works independently
gold 0–30 days             -> +0% boost
gold 31–90 days            -> +10% boost
gold 91+ days              -> +20% boost
boost                      -> never exceeds +20% operational cap
boosted reward             -> never exceeds base * 1.25 (technical max)
base reward table          -> unchanged (1/4/9/14/20%)
```

41/41 pass; the node binary compiles with the wiring. Existing `test-popc` (31/31) and
`test-popc-v15` (29/29) unaffected.

## Blockers before merge

1. **Activation height.** Base is set to V15 (block 20000) and the settle path is wired. Confirm the
   **live chain height is still below 20000** before leaving draft. Decide the **Gold Boost** height
   separately (`POPC_GOLD_BOOST_HEIGHT`): same 20000 only if verification is ready, otherwise keep
   deferred. Validate the full path on testnet (`-DSOST_TESTNET_FORKS=ON`, both gates at block 300).
2. **Wallet / gateway compatibility.** `website/js/sost-gateway.js` + `sost-wallet.html` already
   describe the single model (OFF by default); confirm UI and any RPC surface agree with the
   activated reward math before flipping the height.
3. **`ESCROW_REWARD_RATES` migration.** Decide how the legacy Model-B standalone yield table is
   retired/migrated for any pre-activation contracts so nothing is stranded across the boundary.

## How to activate (later)

The base model is already scheduled at V15 (`POPC_SINGLE_MODEL_HEIGHT = V15_HEIGHT`) and the settle
path is wired. Going live means: (1) confirm live height < 20000, (2) soak on testnet, (3) ship in a
coordinated release. The Gold Boost stays off on mainnet until `POPC_GOLD_BOOST_HEIGHT` is set.

Gold Boost is enabled separately in `include/sost/params.h`:

```cpp
inline constexpr int64_t POPC_GOLD_BOOST_HEIGHT = <HEIGHT>;  // was INT64_MAX (deferred)
```

Rollback for Gold Boost is the same single-line change back to `INT64_MAX`. The base model can be
re-deferred by setting `POPC_SINGLE_MODEL_HEIGHT` to `INT64_MAX` if V15 itself is rescheduled.
