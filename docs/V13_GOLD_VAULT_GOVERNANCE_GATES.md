# V13 Gold Vault Governance Gates — Audit

**Target:** V13 at block **12,000**.
**Fallback:** V14 at block **15,000** if any gate below is amber/red at the V13 RC freeze.
**Scope:** can the Gold Vault transition from single-key developer custody to consensus-enforced governance at block 12,000 under the **5-defense + Transitional Guardian** model?

**Bottom line:** the accumulation side (25% per block) is **already live since genesis**. The spend side has **partial infrastructure** (a 17-test `tests/test_gold_vault.cpp` suite that exercises a `classify_gv_spend()` function which is currently **dead code** — declared, tested in isolation, **never called from `src/tx_validation.cpp`**). The BIP9-style miner signaling primitives EXIST in `include/sost/proposals.h` but the RPC that exposes them is broken. The Heritage Reserve Ethereum contract is **not in the repo**. Transitional Guardian / Guardian auto-disconnect are **completely new** — no code exists yet.

This doc maps each of the six gates with `file:line` evidence and confirms what is missing for V13 activation.

This doc does **NOT** implement any gate. It only audits.

---

## Governance parameters (V13 target)

These are the parameters the Guardian model documented in the whitepaper appendix requires the V13 RC to satisfy:

| Parameter | Value | Notes |
|---|---|---|
| Signaling window | **67 blocks** | ~12h at the target 10.7-min block time |
| Approval threshold | **90 % of blocks in window** | `ceil(0.90 * 67) = 61` blocks with bit set |
| Threshold history | **75 % → 95 % → 90 %** | Whitepaper original → V6 internal review → V13 calibration |
| Signaling unit | **Block (BIP9-style)** | Sybil-resistant via PoW cost, NOT identity registration |
| Guardian role | **Transitional, authorise OR veto** | Bidirectional, NOT veto-only |
| Guardian pronouncement window | **10 blocks after signaling window closes** | Silence ⇒ miner result prevails |
| Guardian auto-disconnect | **Hard cap = block 25,000**, plus gold-backing milestone (A) and N-successful-spends (B) | Implemented at consensus level from V13 — no future fork |
| Fallback if any gate not green | **V14 at block 15,000** | Clean defer, no shame |

These parameters are referenced in the gate descriptions below.

---

## Summary table

| Gate | Description | Status | V13 Risk |
|---|---|---|---|
| G1 | Validator enforcement of purpose restriction | **RED — DEAD CODE** | Blocks V13 |
| G2 | Dual destination whitelists, both committed + cross-checked | **RED — DESIGN ONLY** | Blocks V13 |
| G3 | Per-spend cap + rate limit constants | **RED — DESIGN ONLY** | Blocks V13 |
| G4 | Miner signaling tx-type (67-block window, 90% threshold = 61 blocks, ceil) | **AMBER — INFRASTRUCTURE EXISTS, RPC BROKEN, NO 90 % WIRE-UP** | Blocks V13 |
| G5 | Transitional Guardian (authorise/veto, 10-block grace, auto-disconnect at block 25,000) | **RED — NOT STARTED** | Blocks V13 |
| G6 | Heritage Reserve on Ethereum (Zodiac + Reality.eth, open relayer set, Sepolia E2E green) | **RED — NO SOLIDITY IN REPO** | Off-chain, NOT agent work |

**Verdict.** All 6 gates are RED or AMBER. Activating Gold Vault governance at block **12,000** is **not realistic**. The honest call is: **defer Gold Vault governance to V14 / block 15,000**. The accumulation side is unaffected and continues to operate as it has since genesis.

---

## G1 — Purpose restriction (validator rejects non-reserve destinations)

**Status:** **RED — DEAD CODE**.

The vault address is correctly pinned:

- `include/sost/params.h:773` — `ADDR_GOLD_VAULT = "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"`
- `include/sost/params.h:774` — `ADDR_POPC_POOL  = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"`

The accumulation side is consensus-enforced (CB5/CB6 rules in `src/tx_validation.cpp:509-832` ; CB6 rejects any block whose `outputs[1].pubkey_hash` does not equal the gold vault pubkey hash).

**But the spend side is NOT enforced.** A `classify_gv_spend()` helper exists, is unit-tested by 17 tests in `tests/test_gold_vault.cpp` (lines 40-221, GV01..GV17), and **is never called from any production validation path**:

- `docs/internal/phase-2-vault-governance.md:51-55` — "grep confirms: `classify_gv_spend` is referenced exactly once outside of test files: nowhere in src/."

This is the load-bearing fact for the gap analysis: the rule exists and is tested in isolation, but the actual validator (`src/tx_validation.cpp` and `src/block_validation.cpp`) never calls it. The 17 passing tests demonstrate that the helper is correct; they do NOT demonstrate that the network enforces it. Today the network does not.

**What V13 needs for G1:** wire `classify_gv_spend()` into `src/tx_validation.cpp` so that any transaction that spends an input owned by `ADDR_GOLD_VAULT` is classified, and rejected if the classification is "unknown" or "non-whitelisted". This is a small code change but a load-bearing one — every miner and every full node MUST evaluate it identically.

---

## G2 — Dual destination whitelists, both committed and cross-checked

**Status:** **RED — DESIGN ONLY**.

The 5-defense model in `docs/internal/v6-signature-bound-pow.md:419-431` describes:

```cpp
GV_ALLOWED_RESERVE_DESTINATIONS[]   = { "sost1<otc_conversion_addr>", ... }
GV_ALLOWED_EMERGENCY_DESTINATIONS[] = { /* empty at V6 launch */ }
```

These constant tables **do not exist** in `include/sost/params.h` or `include/sost/consensus_constants.h`. There is no compile-time list of legal vault destinations and no validator-side check that destinations match the list.

**What V13 needs for G2:** the operator chooses 3-5 reserve-destination addresses (XAUT mint, PAXG mint, OTC conversion address, etc.), commits them to **both** `include/sost/params.h` (constants) and a parallel cross-check in `src/tx_validation.cpp` so they cannot drift, freezes both at the V13 fork. Any spend to an address not in BOTH lists is rejected.

The list must be **small** (per the whitepaper appendix: 5 addresses at most), **auditable publicly** (must appear in the whitepaper and the public site, not only in the commit message), and **immutable post-activation** (no path to add destinations after the V13 fork without another hard fork).

---

## G3 — Per-spend cap and rate limit

**Status:** **RED — DESIGN ONLY**.

`docs/internal/v6-signature-bound-pow.md:436-448` designs:

```
GV_HARD_MAX_SPEND_BPS = 200        ; 2% of vault balance per single spend
GV1 monthly cap       = 5%         ; aggregate over 30-day window
GV3 cooldown          = 30 days    ; between emergency spends
```

These constants do not exist in `include/sost/params.h`. There is no validator-side cap check, no rate-limit accounting, and no per-window aggregate tracking.

**What V13 needs for G3:** the operator finalises the numbers (the design draft proposes 2% / 5% / 30d but those targets must be re-evaluated against the actual vault balance at block 12,000), adds them as `constexpr` to `include/sost/params.h`, and wires the cap + the rate-limit accounting into `src/tx_validation.cpp`. The rate-limit accounting requires the validator to track "blocks since last vault spend" — that state lives in the chain (one extra field in `StoredBlock` or computed on the fly from `chain.json`).

---

## G4 — Miner signaling tx-type (67-block window, 90 % threshold = 61 blocks)

**Status:** **AMBER — INFRASTRUCTURE EXISTS, NEEDS REWIRE FOR 90 % AND 67-BLOCK WINDOW**.

BIP9-style block-version-bit signaling already exists:

- `include/sost/proposals.h:50` — `version_has_signal(version, bit)` — checks if bit N is set in a block's version field.
- `include/sost/proposals.h:58` — `count_version_signals(blocks, bit)` — counts blocks signaling in a window.
- `include/sost/proposals.h:71` — `check_activation(...)` — evaluates threshold (75% baseline) with foundation-bonus option.
- `include/sost/proposals.h:36, 70-73, 91` — `foundation_veto` field on `Proposal` struct, with `foundation_veto_active()` that expires at block 263,106 (Epoch 2 boundary).

This is BIP9 — exactly the model the whitepaper appendix proposes (block-counting, not identity-counting, Sybil-resistant via PoW cost). The infrastructure to count signaling bits in a window IS in the codebase.

**What is missing for G4:**

- **No vault-spend tx-type exists.** Today there is no transaction shape that says "this tx is a vault spend; here is the signaling window result; here is the Guardian pronouncement". The validator has no spend-side hook to evaluate.
- **The 90 % threshold (61 of 67 blocks) is not wired in.** The existing `check_activation()` uses 75 % baseline; the V13 vault rule needs `ceil(0.90 * 67) = 61` blocks with the bit set in the 67-block window immediately preceding the spend.
- **The signaling-window math currently assumes BIP9-style 2016-block windows.** It needs a 67-block specialisation for vault spends (different from any future soft-fork signaling).
- **The signaling RPC is broken.** `docs/internal/phase-2-vault-governance.md:66-74` confirms the RPC that exposes signal counts hardcodes all block versions to 1 and returns zero signals. This blocks any operator from observing the network's signaling state at all.

**What V13 needs for G4:** introduce a vault-spend tx-type with explicit `signaling_window_start_height` and `signaling_window_threshold` fields; specialise the signaling-window math for the 67-block / 90 % / 61-block-floor case; fix the broken RPC; cross-validator agreement test that proves three independently-built validator binaries reach the same accept/reject decision on the same set of signaling blocks.

---

## G5 — Transitional Guardian (authorise/veto, 10-block grace, auto-disconnect at block 25,000)

**Status:** **RED — NOT STARTED**.

A `foundation_veto` field exists on the `Proposal` struct (`include/sost/proposals.h:36`) — but that is the *Epoch-2-boundary-expiring* developer veto on protocol-level proposals, NOT the Transitional Guardian on vault spends. Different rule, different scope, different expiry.

The Transitional Guardian as described in the whitepaper appendix needs:

- A `Guardian` role at consensus level (separate from any wallet, mining, or release key)
- A pronouncement tx-type (Guardian signs an authorise OR veto for a specific candidate vault-spend tx)
- A **10-block grace window** after the signaling window closes — if no Guardian pronouncement lands within those 10 blocks, the miner signaling result prevails by default ("silence is consent to the miners' decision")
- **Auto-disconnect** at consensus level when ANY of:
  - **Condition A:** the Heritage Reserve on Ethereum holds ≥X SOST-equivalent in physical-gold attestations for ≥Y consecutive blocks
  - **Condition B:** ≥Z successful vault spends since V13 without the Guardian intervening against miner signaling
  - **Condition C (hard cap):** **block 25,000** — at this block the Guardian role is permanently disabled regardless of A or B
- The auto-disconnect MUST be implemented in V13 source code from day one — not as a future amendment, NOT requiring a future fork

**None of this exists in the codebase today.** This is genuinely new work.

**What V13 needs for G5:** define the Guardian pubkey constant (separate from Beacon and from any wallet); add the pronouncement tx-type; wire the 10-block grace + silence-consent rule into the signaling decision; implement the auto-disconnect checks (A, B, C) at every block. The hard cap C (block 25,000) is the simplest and the most important — without it the Guardian role could be extended indefinitely by inaction, which would void the "temporary" claim.

---

## G6 — Heritage Reserve on Ethereum (Zodiac + Reality.eth, Sepolia E2E green)

**Status:** **RED — NO SOLIDITY IN REPO**.

There is no Heritage Reserve Solidity contract anywhere in this repo. References live only in documentation:

- `docs/internal/phase-2-vault-governance.md:5, 269, 615` — describes the architecture (SOST chain ← bot relayer → Reality.eth oracle on Ethereum → Zodiac Reality Module → Gnosis Safe custody).
- Reality.eth contract address `0xE78996A233895bE74a66F451f1019cA9734205cc` mentioned for reference, not deployed from this repo.

**What V13 needs for G6:** write the Heritage Reserve Solidity, deploy to Sepolia (testnet), run an end-to-end test (propose → 90 % signal → Guardian pronouncement → relay to Reality.eth → execute on Sepolia), then deploy to Ethereum mainnet. The Sepolia E2E green light is the binary gate. This is **operator-manual work** that the agent cannot perform (deploying to Ethereum costs real ETH and requires a signing key).

The open relayer set must be documented (anyone can run a relayer; relayers earn ETH bond rewards for posting correct undisputed answers).

---

## Existing tests

- `tests/test_gold_vault.cpp` — 17 tests (GV01..GV17 in `tests/test_gold_vault.cpp:40-221`). All pass on the current main. They test the `classify_gv_spend()` helper in isolation — they do **not** prove the network enforces anything, because the helper is not called from validation.
- `tests/test_tx_validation.cpp` — CB1..CB10 cover the accumulation rules (the 50/25/25 split). These are the rules that ARE live.

---

## "95 %" references in the repo (sweep targets for the 90 % update)

Every file below contains a "95 %" reference in a vault-governance context. If the threshold change from 95 % → 90 % is published, all of these need to be updated consistently. This is the load-bearing list for the future sweep commit:

- `docs/KNOWN_RISKS_AND_MITIGATIONS.md:53` — GV3 threshold
- `docs/SOST_GOVERNANCE_MODEL.md:160` — Bitcoin BIP9 comparison (95 %)
- `docs/internal/v6-signature-bound-pow.md:396, 461, 468, 509-510, 550, 589` — 5-defense design
- `docs/internal/phase-2-vault-governance.md:32, 615` — threshold constants and Zodiac integration plan
- `docs/internal/btctalk-ann-v2-block-10000.txt:67` — published BitcoinTalk ANN (also requires a public update post)
- `website/sost-whitepaper.html:711` — public whitepaper

References to "95 %" in `docs/btctalk_ann_2026-05-01.txt` and `website/index.html` are about **monetary policy** ("~95 % supply mined in ~12 epochs"), NOT governance — those must NOT be touched. The sweep must distinguish governance-context "95 %" from monetary-context "95 %".

---

## Recommendation

**Defer Gold Vault governance to V14 / block 15,000.**

Rationale:
1. 5 of 6 gates are RED, including G1 (dead-code wire-up), G2 (whitelist tables), G3 (cap + rate limit constants), G5 (Guardian role from scratch). G4 is AMBER and G6 is OFF-CHAIN MANUAL.
2. G5 (Transitional Guardian + auto-disconnect at block 25,000) is the largest new piece — no existing code, requires a new pubkey, a new tx-type, a new state machine. Shipping this hot for V13 RC freeze without testnet burn-in would be reckless.
3. G6 (Sepolia E2E + mainnet deploy) is multi-week even for a focused operator and is gated on G2 and G5 being design-final (you cannot deploy the Heritage Reserve until you have decided the whitelists and the Guardian model).
4. The accumulation side (25 % per block) is live since genesis and continues unchanged. Deferring spend-side governance does not regress any current behaviour — it only delays the transition from developer custody to protocol custody.
5. V14 (block 15,000) gives ~6 months of post-V13 runway at the current ~10-minute block time to:
   - Wire G1 (1 sprint)
   - Define + commit G2 + G3 constants (1 sprint)
   - Implement G4 90 %/67-block specialisation (1 sprint)
   - Implement G5 Guardian + auto-disconnect (2-3 sprints)
   - Deploy + Sepolia E2E G6 (parallel, operator-manual, 2 sprints)

If the operator publishes the threshold change 95 % → 90 % in V13 as a **documentation-only** sweep (no code change, no fork), that is independent of this gap analysis and can land in V13 without risk. Code consequences of the 90 % land at V14.

— NeoB
