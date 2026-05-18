# V13 PoPC + Escrow Auto-Activation Gap Analysis

**Target:** V13 at block **12,000**.
**Fallback:** V14 at block **15,000** if any gate below is amber/red at the V13 RC freeze.
**Scope:** can PoPC Model A + Model B + SOSTEscrow run a complete lifecycle (register → mature → audit → slash/settle → close) **without any operator RPC call between steps**, starting at block 12,000?

**Bottom line:** today **NO**. PoPC is implemented as an **application-layer** subsystem (registry + helpers + RPC handlers + Solidity contract on the Ethereum side), with **no consensus activation gate**, **no automatic audit scheduler**, **no auto-slash**, **no auto-settlement**, and **no end-to-end lifecycle test**. The Ethereum contract `contracts/SOSTEscrow.sol` exists in source but is not deployed, has no compiled artifacts in-repo, and has no event listener on the SOST side. This document maps each gap with `file:line` evidence so the operator can decide V13 vs V14.

This doc does **NOT** implement any of the gaps. It only audits the current state.

---

## Summary table

| Gate | Description | Status | V13 Risk |
|---|---|---|---|
| G-POPC-1 | `POPC_ACTIVATION_HEIGHT = 12000` consensus gate | **RED — MISSING** | Blocks V13 |
| G-POPC-2 | Audit daemon / scheduler | **RED — MISSING** | Blocks V13 |
| G-POPC-3 | Auto-slash after failed audit + grace period | **RED — MANUAL RPC** | Blocks V13 |
| G-POPC-4 | Auto-settlement / bond release | **RED — MANUAL RPC** | Blocks V13 |
| G-POPC-5 | Ethereum escrow deploy path | **AMBER — SOURCE ONLY** | Off-chain, NOT agent work |
| G-POPC-6 | Ethereum event listener (`GoldDeposited`, etc.) | **RED — MISSING** | Blocks V13 |
| G-POPC-7 | Bridge / indexer from Ethereum event → SOST state | **RED — MISSING** | Blocks V13 |
| G-POPC-8 | End-to-end lifecycle test (no human RPC) | **RED — MISSING** | Blocks V13 |
| G-POPC-9 | Safety around keys / wallets / signing | **GREEN** | Already isolated |

**Verdict.** Of nine gates, **7 are RED**, **1 is AMBER**, **1 is GREEN**. Activating PoPC+Escrow in fully-automatic mode at block **12,000** is **not realistic without a multi-sprint dedicated implementation push**. The honest call is: **defer PoPC+Escrow auto-activation to V14 / block 15,000** and use the time between V13 freeze and block 15,000 to close G-POPC-1 through G-POPC-8 with proper consensus tests. V13 can ship with PoPC as **application-layer** (current behaviour) without breaking anything; the consensus surface stays as it is today.

---

## G-POPC-1 — Consensus activation height

**Status:** **RED — MISSING**.

There is **no** `POPC_ACTIVATION_HEIGHT` (or `POPC_HEIGHT`, `POPC_FORK_HEIGHT`) constant anywhere in `include/sost/params.h`. PoPC today has **no consensus gate** — it is purely application-layer, gated only by the BOND_LOCK / ESCROW_LOCK script tags that have been active since block 5,000:

- `include/sost/params.h:774` — `BOND_LOCK (0x10) and ESCROW_LOCK (0x11) are active at height >= 5000`

There is no rule in `src/tx_validation.cpp` or `src/block_validation.cpp` that activates new PoPC-specific consensus behaviour at any future height.

**What V13 needs:** introduce `inline constexpr int64_t POPC_ACTIVATION_HEIGHT = 12000;` in `include/sost/params.h`, plus a validator-side check that any PoPC-related consensus rule (not yet defined) MUST be `INT64_MAX`-sentinel-disabled below that height and live at/above it. Without this gate, the V13 fork has no semantic anchor for "PoPC consensus turns on here".

---

## G-POPC-2 — Audit daemon / scheduler

**Status:** **RED — MISSING**.

There is **no** automatic audit scheduler in this codebase. `scripts/popc_daemon.py` exists but it is a **manual CLI tool**:

- `scripts/popc_daemon.py:1-26` — top-of-file docstring describes `--action activate / check-all / status / complete`. All actions are operator-invoked.

There is no cron, no systemd timer, no in-process loop, and no consensus rule that says "every N blocks, validators MUST evaluate PoPC audits". Auditing is RPC-triggered via `handle_popc_check()`:

- `src/sost-node.cpp:2805` — `handle_popc_check()` requires explicit RPC call with an `eth_address` argument; never invoked automatically.

**What V13 needs:** a consensus-side hook that, on every block at or above `POPC_ACTIVATION_HEIGHT`, deterministically evaluates which PoPC commitments are due for audit at that height and emits an audit-trigger record into the chain state — or, alternatively, a Trinity-side scheduler that wakes up every N blocks and posts audit-trigger transactions automatically. Either way, the trigger MUST be deterministic across validators (same height → same trigger set) so that audit decisions stay reorg-safe.

---

## G-POPC-3 — Auto-slash after failed audit + grace period

**Status:** **RED — MANUAL RPC**.

Slashing today is operator-only:

- `src/sost-node.cpp:2885-2933` — `handle_popc_slash()` requires the RPC call `popc_slash <commitment_id_hex> <reason>`.

There is no grace-period timer, no "audit failed N blocks ago → slash" rule, and no automatic invocation. The bond is **NOT** confiscated on-chain at consensus level on slash; it is "marked" in the registry and the actual bond return is deferred to whenever `build_bond_release_tx()` runs (`src/popc_tx_builder.cpp:50`).

**What V13 needs:** a per-commitment grace-period constant (e.g. `POPC_AUDIT_GRACE_BLOCKS = 144` = ~24h), and a validator-side rule that, when a commitment's audit verdict is "fail" AND the current height exceeds `audit_block + POPC_AUDIT_GRACE_BLOCKS`, the bond MUST be redirected to the slash destination by consensus (no operator action). This requires the audit verdict itself to be on-chain — see G-POPC-2 and G-POPC-7.

---

## G-POPC-4 — Auto-settlement / bond release

**Status:** **RED — MANUAL RPC**.

Settlement today is operator-only:

- `src/sost-node.cpp:2821` — `handle_popc_release()` requires explicit RPC call to release a bond.
- `scripts/popc_daemon.py:362-414` — `action_complete()` *prints `sost-cli` commands for the operator to execute*. No automatic execution.

There is no rule that says "on successful audit verdict, bond + reward are automatically released at consensus level".

**What V13 needs:** symmetric to G-POPC-3 — a validator-side rule that, when a commitment's audit verdict is "pass", the bond MUST be returned to the holder address and the reward MUST be paid out of the PoPC Pool address, by consensus, without any operator transaction. This also requires the verdict to be on-chain.

---

## G-POPC-5 — Ethereum escrow deploy path

**Status:** **AMBER — SOURCE EXISTS, NOT DEPLOYED**.

The Solidity contract is in source:

- `contracts/SOSTEscrow.sol:1` — Solidity `^0.8.24`.
- `contracts/SOSTEscrow.sol:99-104` — `event GoldDeposited(...)`.
- `contracts/SOSTEscrow.sol:107-112` — `event GoldWithdrawn(...)`.
- `contracts/script/DeployMainnet.s.sol` — deploy script (Foundry-style), takes XAUT + PAXG addresses.
- `contracts/test/SOSTEscrow.t.sol` — Foundry test template.

**Missing:**
- No compiled artifacts (`.json` ABIs) committed in the repo — verify with `find contracts -name "*.json"`.
- No deployment to Ethereum mainnet (or Sepolia testnet) yet — no deployed address pinned anywhere in `include/sost/params.h`.
- No `ETH_ESCROW_ADDRESS` constant on the SOST side that any consensus rule references.

This is **operator-manual work** that the agent cannot perform: deploying to Ethereum costs real ETH, requires a private key, and is outside the agent's safety surface. The amber status reflects that the source is ready but the deployment is a manual step.

**What V13 needs:** the operator deploys `SOSTEscrow.sol` to Sepolia (testnet end-to-end test) and then to mainnet; pins the deployed address in `include/sost/params.h` (`ETH_ESCROW_ADDRESS = "0x..."`); commits the compiled ABI under `contracts/abi/` for the Ethereum listener to consume.

---

## G-POPC-6 — Ethereum event listener

**Status:** **RED — MISSING**.

There is no event-driven listener for Ethereum logs:

- `scripts/popc_daemon.py:74-105` — `eth_call_balance()` polls ERC-20 `balanceOf` via JSON-RPC. This is a poll, not a listener.
- `scripts/popc_oracle.py:6` — "Ethereum mainnet balance ... compares". Same shape: poll, not listener.

There is no Python or C++ consumer of `GoldDeposited` / `GoldWithdrawn` / `BondPosted` events.

**What V13 needs:** a Trinity-side listener (Python is fine, the safety surface allows it because it only READS from a public RPC) that subscribes to `eth_getLogs` for the deployed `SOSTEscrow` contract, with confirmation depth, reorg handling, retries, and idempotency. Each accepted log must be translated into a deterministic SOST-side fact (a transaction that records the Ethereum event on-chain). See G-POPC-7 for the translation step.

---

## G-POPC-7 — Bridge / indexer from Ethereum event → SOST state

**Status:** **RED — MISSING**.

Nothing in `src/` or `scripts/` translates Ethereum events into SOST state mutations. The existing application-layer flow is: operator runs `popc_daemon.py`, which prints `sost-cli` commands for the operator to execute manually.

**What V13 needs:** a new transaction type (or special script tag) that carries a verified Ethereum-side fact (`GoldDeposited` event hash + block + log index + signature from the listener) and that validators accept as a consensus-valid PoPC state input. The bridge must be:

- Deterministic across validators (same Ethereum chain state at height H → same SOST consensus decision)
- Reorg-safe on both sides (Ethereum reorgs and SOST reorgs)
- Idempotent (same event consumed twice → no double credit)
- Limited to a small allow-list of event types (no general-purpose oracle)

This is the largest single piece of work in PoPC auto-activation. Estimate: multi-sprint, with formal verification of the determinism property.

---

## G-POPC-8 — End-to-end lifecycle test (no human RPC)

**Status:** **RED — MISSING**.

Existing tests are unit-level only:

- `tests/test_popc.cpp` — 31 tests on registry: POPC13-22 (register/find/list), POPC19-20 (complete), POPC23-25 (reputation). All pass.
- `tests/test_escrow.cpp` — ESC01-ESC11 on Model B registry. All pass.

There is **no** test that runs the full lifecycle `register → deposit → mature → audit → slash/settle → close` WITHOUT operator intervention between steps. Existing tests test fragments; no test asserts "given height H and these on-chain facts, the system MUST reach state X at height H+N without any RPC".

**What V13 needs:** at least one integration test that simulates the full lifecycle deterministically (using synthetic Ethereum events for the bridge inputs) and asserts every state transition happens at the right height. This test is the binary gate for "PoPC is actually automatic" — without it, no claim of auto-activation is defensible.

---

## G-POPC-9 — Safety around keys / wallets / signing

**Status:** **GREEN**.

Private-key handling is properly isolated:

- `src/popc_tx_builder.cpp:50` — `build_bond_release_tx()` takes `const PrivKey& owner_privkey` as a parameter; the caller must provide it.
- `src/popc_tx_builder.cpp:137` — `build_reward_tx()` takes `const PrivKey& pool_privkey` as a parameter.

No private keys are hardcoded anywhere in PoPC code. No wallet is auto-opened. `scripts/popc_daemon.py` does not sign — it only generates CLI commands for the operator. No consensus code signs transactions automatically.

This is the one part of PoPC that does NOT need work for V13 auto-activation. The safety surface is correct as-is.

---

## Existing PoPC documentation

- `docs/V13_SPEC.md` — V13 hard fork specification (line 1-2)
- `docs/POPC_MODEL_A_SPECIFICATION.md` — Status: **DESIGN — Awaiting CTO approval** (line 3)
- `docs/POPC_IMPLEMENTATION_STATUS.md` — Dated 2026-03-29
- `docs/POPC_AUTO_DISTRIBUTE_GUIDE.md` — Manual reward distribution
- `docs/POPC_DEPLOY_GUIDE.md` — Deploy guide (operator manual)
- `docs/popc_model_b_roadmap.md` — Model B roadmap

Notably **MISSING:** any `docs/V13_POPC_*.md` document that pins the V13-specific PoPC consensus surface. The current Model A spec is in DESIGN status, awaiting approval.

---

## Recommendation

**Defer PoPC + Escrow auto-activation to V14 / block 15,000.**

Rationale:
1. 7 of 9 gates are RED, including the load-bearing G-POPC-1 (no consensus activation height), G-POPC-2 (no audit scheduler), G-POPC-7 (no bridge), and G-POPC-8 (no end-to-end test).
2. G-POPC-5 + G-POPC-6 + G-POPC-7 together represent the deepest new consensus work in V13 — bridging Ethereum events into SOST consensus with full reorg-safety is a multi-sprint design problem, not an implementation problem alone.
3. Pushing this into V13 forces shortcuts that would weaken either the safety surface (auto-signing) or the determinism guarantees (non-reorg-safe bridge). Both outcomes are worse than waiting.
4. The accumulation side (25% per block to the Gold Vault and PoPC Pool addresses) is already live at consensus level since genesis — deferring the SPEND side does not regress any existing rule.
5. V14 (block 15,000) gives ~6 months of post-V13 runway at the current ~10-minute block time to close G-POPC-1 through G-POPC-8 with proper consensus tests and a Sepolia end-to-end before mainnet activation.

V13 can ship the rest of its scope (cASERT, DTD cooldown 6, drift 10s, Beacon II-A, II-B, III if ready, Gold Vault governance if ready) without PoPC consensus changes. PoPC continues to operate application-layer, as today, until V14.

Memory-Lock per-instance anti-pool is **explicitly DEFERRED** from V13 and is not in scope for this gap analysis. See `docs/V13_SPEC.md` for the deferred-items list (to be added by the operator).

— NeoB
