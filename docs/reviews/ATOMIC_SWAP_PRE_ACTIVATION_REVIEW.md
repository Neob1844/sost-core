# Atomic Swap HTLC — Pre-Activation Safety Review

**Status of branch `feat/atomic-swap-htlc-v13-candidate` as of this review:**
SOST-side consensus + wallet/RPC/CLI scaffolding **complete and tested**.
Counterparty integration (BTC, EVM) **not started**. External review
**not performed**. Gate `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX`.

**Activation decision (this review):** **DO NOT FLIP THE GATE.**
The branch is **code-complete on the SOST side** but the system is
**NOT safe to activate** until Phase 4 (counterparty legs) ships and
Phase 5 (external cryptographic + economic review) signs off.

---

## Branch state — 10 commits since main

```
845f8e53  cli: add gated atomic swap HTLC commands                 (3C-2)
d94aa474  rpc: wire atomic swap HTLC parameter parsing             (3C-1)
5c84cdf5  wallet: add gated atomic swap HTLC helpers               (3C)
4450982c  protocol: add HTLC refund validation for atomic swaps    (3B-2)
92dfc3a1  protocol: add HTLC claim validation for atomic swaps     (3B-1b)
c22eb4b3  protocol: phase 3B-1a HTLC_CLAIM_WITNESS scaffolding     (3B-1a)
e92db44d  protocol: keep atomic swap HTLC gate disabled            (SAFETY)
3d19c2a5  website: bump explorer version v298 -> v299              (cache-buster)
c8a315a5  protocol: add gated HTLC transaction primitives          (3A)
ea65d0fc  protocol: add atomic swap HTLC v13 candidate scaffolding (0+1+2)
```

~3,500 lines added (code + tests + docs).

---

## The 12 review questions

### 1. Is SOST consensus changed?

**Yes, additively, but gated.** The validator (`src/tx_validation.cpp`)
contains new branches for:

- `OUT_HTLC_LOCK` output structural validation (R17)
- `OUT_HTLC_CLAIM_WITNESS` output structural validation (R18)
- `TX_TYPE_HTLC_CLAIM` transaction type (R2 extension + R19-R22)
- `TX_TYPE_HTLC_REFUND` transaction type (R2 extension + R23-R24)
- R20 — `OUT_HTLC_LOCK` may only be spent by HTLC_CLAIM/REFUND tx_type

**Every new branch is gated by `atomic_swap_htlc_active_at(height)`.**
This helper returns `false` for every finite height while the
activation constant is `INT64_MAX`. With the gate closed, every
HTLC-related rule short-circuits to "inactive" exactly as if the
patch were not present.

### 2. Are historical blocks unaffected?

**Yes, bit-identical.** All HTLC rules are gated. Pre-V14 chain
replay executes the exact same code path as the pre-patch binary:

- R2 still rejects any `tx_type` other than STANDARD/COINBASE.
- R11 still rejects `OUT_HTLC_LOCK` and `OUT_HTLC_CLAIM_WITNESS`.
- The standard tx and coinbase tx paths are unchanged.

### 3. Can any HTLC be created before activation?

**No.** With the gate at INT64_MAX:

- R11 rejects `OUT_HTLC_LOCK` outputs in any block.
- R11 rejects `OUT_HTLC_CLAIM_WITNESS` outputs in any block.
- R2 rejects `TX_TYPE_HTLC_CLAIM` and `TX_TYPE_HTLC_REFUND` tx_types.
- S9 rejects HTLC output types from appearing inside a STANDARD tx.

Defense in depth: even if one of these gates had a bug, the others
catch the violation.

### 4. Can funds be locked without a claim/refund path?

**Today (gate INT64_MAX): No.** No LOCK can be created, so no funds
can become "stuck".

**Hypothetical post-flip with current code: Would be Yes** if the gate
were flipped to a finite value while only HTLC_LOCK existed and
CLAIM/REFUND did not. That hypothetical is explicitly prevented by
the safety-close commit (e92db44d) which reverted the gate to
INT64_MAX after Phase 3A and documented the three-condition
re-flip checklist in `include/sost/atomic_swap.h`:

```
1. HTLC_CLAIM validation + adversarial tests
2. HTLC_REFUND validation + adversarial tests
3. External cryptographic + economic review
```

Conditions 1+2 are DONE (commits 92dfc3a1 + 4450982c). Condition 3
is PENDING. The gate stays at INT64_MAX.

### 5. Is there any automatic broadcast?

**No.** Grep audit on the 4 HTLC code files (`atomic_swap_helpers.cpp`,
`atomic_swap_helpers.h`, the test files, and the new HTLC CLI block in
`sost-cli.cpp`) finds only COMMENTS stating what the code does NOT do:
"None of these helpers broadcast", "caller signs before broadcast",
"--sign/--broadcast flags require protocol activation".

Build helpers produce UNSIGNED `Transaction` objects (signature +
pubkey zero-filled). The wallet owner must sign and only then
optionally call `sendrawtransaction`. No HTLC code path invokes
broadcast or mempool functions.

### 6. Is there any custody by SOST?

**No, by construction.**

- SOST Protocol holds no keys for `SOSTEscrow.sol`.
- SOST DEX has no admin role to release escrow.
- The new atomic-swap HTLC code introduces zero custodial surface:
  build functions produce unsigned tx for the user to sign locally;
  CLAIM/REFUND release on-chain directly to user pubkey-hashes via
  consensus validation; no "operator unlock" path exists.

### 7. Is there any external-chain dependency inside consensus?

**No.** SOST consensus validates HTLC purely on SOST-chain state:

- Hashlock comparison reads only the LOCK utxo payload and the CLAIM
  witness output.
- Timeout check reads only the current block height and the LOCK
  payload refund_height.
- Signature verification uses the LOCK's claim_pkh or refund_pkh.
- No node code path reads from BTC or Ethereum at validation time.

The atomicity guarantee between SOST and the counterparty chain is
enforced ENTIRELY off-chain by the wallet that constructs both legs.
The wallet must use the same hashlock on both sides and timeouts
such that `T1_SOST > T2_counterparty + safety_margin`. Both rules
are documented in `ATOMIC_SWAP_HTLC_IMPLEMENTATION_PLAN.md` sections
12-13.

### 8. Can BTC path recover after timeout?

**Not implemented yet.** Phase 4A has not been written. The BTC
counterparty leg is documented as Bitcoin Script HTLC (P2WSH or
Taproot) using OP_SHA256 + OP_CLTV. The actual builder, address
derivation, witness encoding, and broadcast logic do not exist.

**Pre-activation requirement:** Phase 4A must ship and its tests
must pass before any user is invited to use SOST<->BTC.

### 9. Can EVM path recover after timeout?

**Not implemented yet.** Phase 4B has not been written. The EVM
counterparty leg is documented as a Solidity contract with lock /
claim / refund functions. The actual contract source, deployment
tooling, and SOST DEX wallet integration do not exist.

**Pre-activation requirement:** Phase 4B must ship and its tests
(reentrancy / owner-drain absence / event correctness) must pass
before any user is invited to use SOST<->ETH/BNB/USDT/USDC/PAXG/XAUT.

### 10. What are issuer risks for USDT / USDC / PAXG / XAUT?

**Material risk for all four assets:**

| Asset | Issuer | Freeze risk |
|---|---|---|
| USDT | Tether Limited | Tether can freeze any USDT address |
| USDC | Circle | Circle operates an active blacklist; has frozen funds in court/sanction orders |
| PAXG | Paxos | Paxos can freeze any PAXG address; physical gold custody by Paxos |
| XAUT | TG Commodities | Can freeze any XAUT address; physical gold custody risk |

**Consequence for atomic swaps:** if the issuer freezes the
counterparty side mid-swap, the swap loses atomicity:

- SOST side can still refund (cryptographic atomicity holds).
- Counterparty side becomes uncollectible until (or unless) the
  issuer manually unfreezes.

The OTC / P2P UI **must** label these four assets as "ISSUER-RISK"
and must not claim "perfect atomicity" for them. Trust-minimized
assets are BTC, ETH, and BNB (with BNB-Chain governance caveat
noted; BNB itself is not issuer-freezable).

### 11. What remains unaudited?

- **Phase 4A** (Bitcoin Script HTLC): not written, not reviewed.
- **Phase 4B** (Solidity HTLC): not written, not reviewed.
- **Phase 4C** (cross-chain coordinator state machine): not written.
- **Phase 4D** (OTC / P2P UI integration): not yet shipped.
- **External cryptographic review:** R17-R24 written + unit-tested
  by this team; not reviewed by an independent cryptographer.
- **External economic review:** timeout-margin math documented but
  not formally modelled against counterparty re-org distributions.
- **Mainnet/testnet simulation:** gated rules exercised in the
  existing test suite; no end-to-end SOST<->BTC or SOST<->EVM swap
  has been executed on testnet.

### 12. Is activation safe? yes/no

**NO.** Activation is NOT safe today. Required prerequisites:

1. Phase 4A — Bitcoin Script HTLC builder + deterministic-vector tests.
2. Phase 4B — Solidity HTLC contract + Hardhat/Foundry test suite.
3. Phase 4C — Cross-chain coordinator state machine.
4. Phase 4D — OTC / P2P UI integration with explicit ISSUER-RISK
   labelling for USDT/USDC/PAXG/XAUT.
5. End-to-end testnet swaps (SOST<->BTC testnet, SOST<->Sepolia ETH,
   SOST<->Sepolia ERC-20) showing happy path AND timeout-refund path.
6. External cryptographic review of R17-R24 + counterparty contracts.
7. External economic review of timeout margins against real-world
   re-org distributions of each counterparty chain.

Once all seven are GREEN, a separate activation commit may set
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_HEIGHT` (15000) and ship
in a hard-fork-compatible release. Until then, the gate STAYS at
INT64_MAX.

---

## Activation decision

**`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` REMAINS `INT64_MAX`.**

This review **does not propose an activation commit.** The SOST-side
foundation is solid and well-tested, but the system is not usable
for atomic swaps until the counterparty legs (Phase 4) ship and
external review (Phase 5) signs off.

When the seven prerequisites above are met, the activation commit
should be a single one-line change:

```
-inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX;
+inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_HEIGHT;
```

with commit message:

```
protocol: schedule atomic swap HTLC activation at V14_HEIGHT
```

The commit must be accompanied by:

- A full `ctest` run showing 0 failures on changed tests.
- This review document updated with answer to Q12 = "Yes".
- Release notes documenting the V14 activation height + supported
  asset list + ISSUER-RISK labelling for USDT/USDC/PAXG/XAUT.

Until that day, the SOST chain accepts no HTLC transaction. Period.

---

## Test inventory (current branch state)

| Test binary | Pass | Fail | Notes |
|---|---|---|---|
| test-atomic-swap-htlc-lock | 37 | 0 | LOCK structural + R11/R17 gate boundaries |
| test-atomic-swap-htlc-helpers | 22 | 0 | Build/Decode/Status pure-helper tests |
| test-atomic-swap-htlc-rpc | 16 | 0 | RPC param parsing + validation |
| test-tx-signer | 22 | 0 | Regression — unchanged from main |
| test-transaction | 15 | 0 | Regression — unchanged from main |
| test-mempool | 25 | 0 | Regression — unchanged from main |
| test-merkle-block | 35 | 0 | Regression — unchanged from main |
| test-bond-lock | 9 | 5 | Pre-existing on main (verified) |
| test-escrow | 10 | 1 | Pre-existing on main (verified) |
| test-popc | 27 | 4 | Pre-existing on main (verified) |
| test-dynamic-rewards | 17 | 1 | Pre-existing on main (verified) |

**Total NEW assertions added by this branch: 75 (37 + 22 + 16),
all PASSING.** Pre-existing failures on main remain unchanged
(verified by reproducing them on a clean main checkout).

---

*Generated as part of the Phase 6 sprint deliverable. To re-run the
audit, see `tests/test_atomic_swap_htlc_*.cpp` and the grep audits
documented in commit messages c8a315a5 through d94aa474.*
