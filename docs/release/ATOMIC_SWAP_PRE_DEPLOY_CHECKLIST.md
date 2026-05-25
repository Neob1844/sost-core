# Atomic Swap — pre-deploy release checklist

**Status:** PLAN ONLY. Defines what MUST be green before
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` is flipped from `INT64_MAX`
to `V14_HEIGHT` AND `SOST_BTC_HTLC_SIGNING` is flipped from `OFF`
to `ON` on `main`. This document does not flip anything.

**Companion artefacts** (all on `feat/atomic-swap-htlc-v13-candidate`):
- `include/sost/atomic_swap.h` — the consensus gate.
- `CMakeLists.txt` — the `SOST_BTC_HTLC_SIGNING` build flag.
- `docs/design/ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md` — Phase A.
- `docs/design/ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md` — Phase B.
- `docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md` — Phase C halt.
- `docs/design/ATOMIC_SWAP_EVM_HARDENING_STOP_REPORT.md` — Phase D plan.
- `docs/design/ATOMIC_SWAP_COORDINATOR_REVIEW.md` — Phase 4C-1 review.
- `docs/design/ATOMIC_SWAP_EVM_CONTRACT_REVIEW.md` — Phase 4B-1 review.
- `tests/test_atomic_swap_e2e_sim.cpp` — Phase E local sim.

**Audit posture:** every gate flip requires written sign-off from the
external auditor. There is no admin override, no emergency unlock,
no manual escrow release. The two flips listed in section 14 are the
ONLY changes the activation PR makes.

---

## 1. SOST consensus checks (must be GREEN)

```
[ ] The atomic-swap branch is rebased on a current main.
[ ] include/sost/atomic_swap.h: ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT
    is still INT64_MAX in this commit. (The activation PR is the
    one that flips it.)
[ ] include/sost/atomic_swap.h: V14_HEIGHT is set to the agreed
    activation block (currently 15000).
[ ] HTLC validation rules R17, R18, R19, R20, R21, R22, R23, R24
    are present in src/tx_validation.cpp and have:
        - 37 + 22 + 16 unit-test assertions per their test files
        - 0 failures on the current build
[ ] OUT_HTLC_LOCK (0x12) and OUT_HTLC_CLAIM_WITNESS (0x13) marker
    types are recognised by the validator only when
    height >= ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT.
[ ] HTLC_CLAIM and HTLC_REFUND tx_type values (0x10, 0x11) are
    recognised only above the gate.
[ ] Trinity test suite: 1861 passed, 38 skipped (or newer, with
    zero regression vs the current bit-identical baseline).
```

## 2. BTC libwally-core integration (must be GREEN)

```
[ ] vendor/libwally-core/ submodule present at the commit hash pinned
    in docs/design/ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md
    section 3.
[ ] git verify-tag on the libwally release tag matches the
    maintainer key fingerprint declared in §3 of the integration
    review.
[ ] cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
        -DSOST_BTC_HTLC_SIGNING=ON
    succeeds with: "-- SOST_BTC_HTLC_SIGNING=ON — libwally-core
    found via pkg-config (version=X.Y.Z)" or the manual-probe
    equivalent.
[ ] cmake --build build with the flag ON compiles cleanly.
[ ] SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY=1 is defined in the resulting
    sost-core target.
```

## 3. BTC test vectors (must be GREEN)

```
[ ] The full BIP-173 Bech32 battery (valid + invalid) listed in
    docs/design/ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md §1 passes
    through the new libwally-backed encoder/decoder.
[ ] The full BIP-350 Bech32m battery (§2) passes if Taproot is in
    scope; otherwise §2 is deferred and documented.
[ ] The BIP-143 SegWit v0 sighash Native P2WSH vector (§5) produces
    the expected sighash byte-for-byte:
        82dde6e4f1e94d02c2b7ad03d2115d691f48d064e9d52f58194a6637e4194391
[ ] P2WSH witness program (§3) still matches sha256(redeem_script)
    for the canonical HTLC redeem script. Expected witness program
    for the canonical test inputs (Phase B harness output):
        6d2f9629af2887188cd641b9cd5f7d1dc95c883f3fbf4a88bfb751e8d9a2c1a6
[ ] HTLC redeem script determinism (§4) still passes.
[ ] Six HTLC-specific adversarial vectors (§6) all pass under
    libwally (CLAIM with wrong preimage, REFUND before timeout, etc.).
```

## 4. BTC testnet end-to-end (must be GREEN)

```
[ ] At least one full SOST <-> BTC testnet swap completed end-to-end
    using bitcoin-core regtest as the BTC counterparty:
        - happy path: both sides claim
        - timeout path: SOST side refunds
        - wrong preimage path: rejected
        - counterparty disappears: SOST refund works
[ ] Same set repeated with BTC testnet3 (a different network) to
    catch any regtest-only assumptions.
[ ] Capture in docs/release/ATOMIC_SWAP_TESTNET_DEPLOYMENT.md:
    txid for each leg, address pair, preimage, hashlock, refund
    height, observed gas fees, confirmation counts.
```

## 5. EVM Foundry tests (must be GREEN)

```
[ ] forge test -vvv in contracts/atomic-swap/ runs the FULL set
    described in docs/design/ATOMIC_SWAP_EVM_HARDENING_STOP_REPORT.md
    section 2 (29 baseline + at minimum the 16 new tests outlined).
[ ] Total Foundry pass count documented in this checklist next to
    the date of the run.
[ ] Fuzz tests use >= 10000 runs.
[ ] No "PENDING" markers in the test output.
```

## 6. EVM Sepolia / BSC testnet deployment (must be GREEN)

```
[ ] AtomicSwapHTLC.sol deployed to Sepolia (Ethereum testnet).
    Address recorded in docs/release/.
[ ] AtomicSwapHTLC.sol deployed to BSC testnet. Address recorded.
[ ] Both deployments verified on their respective block explorers
    (Etherscan / BscScan) with full source + build metadata.
[ ] At least one SOST <-> Sepolia ETH swap completed end-to-end
    AND at least one SOST <-> Sepolia ERC-20 (using a testnet mock
    of each issuer-risk token: USDT, USDC, PAXG, XAUT).
[ ] At least one SOST <-> BSC BNB swap completed end-to-end.
```

## 7. Stablecoin freeze-risk disclosure (must be present)

```
[ ] website/sost-otc.html supply row contains ISSUER-RISK badge
    cards for USDT, USDC, PAXG, XAUT (already shipped in Phase 4D,
    re-verify still present).
[ ] The OTC wizard preview (Phase F) section continues to surface
    the per-asset freeze warning for the same four assets.
[ ] docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md (will be added
    by the EVM hardening commit when forge work lands) contains
    the Stablecoin Freeze Risk section verbatim:
        - USDT (Tether Limited can freeze any address)
        - USDC (Circle operates an active blacklist)
        - PAXG (Paxos can freeze; physical custody risk)
        - XAUT (TG Commodities can freeze; physical custody risk)
        - Refund cryptographic guarantee survives even when the
          counterparty side is frozen.
```

## 8. Coordinator recovery tests (must be GREEN)

```
[ ] test-atomic-swap-coordinator: 39 assertions pass.
[ ] test-atomic-swap-e2e-sim: 10 scenarios, 43 assertions pass.
[ ] All recovery branches verified by the e2e sim:
        - timeout-order rejected at CreateSession
        - party disappears -> RefundAvailable + recovery_path()
        - preimage leak before BothLocked -> ClaimReady on late lock
        - stablecoin freeze -> standard timeout-refund branch
[ ] Coordinator next_safe_action() and recovery_path() return
    non-empty strings at every state where the operator UI would
    render guidance.
```

## 9. UI no-mainnet guard (must hold)

```
[ ] website/sost-otc.html atomic-swap-wizard section: all 6 step
    buttons remain disabled. Spot-check that each button still has
    disabled + aria-disabled + a title attribute explaining why.
[ ] Forbidden-words grep on website/sost-otc.html returns zero
    matches inside the wizard section (lines 537-705 of the
    current commit):
        - "risk free" / "risk-free"
        - "guaranteed"
        - "official escrow"
        - "SOST custody"
        - "live mainnet"
[ ] The "MAINNET NOT ACTIVE" / "PRIVATE BETA" / "TESTNET ONLY"
    badges are present at the top of the wizard.
[ ] The closing block "WHEN DO THE BUTTONS UNLOCK?" is unchanged
    and points operators at the gating phases that must complete.
```

## 10. External cryptographic audit (must be SIGNED)

```
[ ] An independent auditor with proven Bitcoin / EVM cryptography
    background has reviewed:
        - src/atomic_swap_helpers.cpp (SOST HTLC tx builder)
        - src/atomic_swap_btc.cpp (BTC redeem script builder)
        - src/atomic_swap_btc_signing.cpp (libwally wiring, once
          Phase C lands)
        - src/atomic_swap_coordinator.cpp (state machine)
        - include/sost/atomic_swap_*.h headers
        - src/tx_validation.cpp HTLC paths (R17-R24)
[ ] Audit report signed by the auditor's GPG key.
[ ] Every Critical and High finding is fixed AND re-reviewed.
[ ] Medium findings are either fixed or documented as
    accepted-risk with explicit justification.
[ ] The audit report is published alongside the activation PR.
```

## 11. External smart-contract audit (must be SIGNED)

```
[ ] An independent Solidity audit firm has reviewed:
        - contracts/atomic-swap/src/AtomicSwapHTLC.sol
        - contracts/atomic-swap/test/AtomicSwapHTLC.t.sol (test
          coverage assessment)
        - contracts/atomic-swap/test/mocks/*.sol (test mocks
          assessment)
[ ] Audit report covers the invariants listed in
    docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md (when that
    doc ships) AND the forced-ETH-via-selfdestruct posture.
[ ] Same fix-or-document discipline as section 10.
```

## 12. Economic / game-theory review (must be SIGNED)

```
[ ] An independent reviewer has covered:
        - Initiator vs Responder incentive alignment.
        - Timeout-order asymmetry rationale.
        - Free-option / Zhao-style attack analysis under the
          specific timeout windows the OTC UI will recommend.
        - Stablecoin-freeze incentive analysis (mid-swap freeze
          economic consequences).
        - PoPC interaction (Atomic Swap does NOT touch the PoPC
          escrow but the reviewer confirms no economic cross-talk).
[ ] Reviewer report attached to the activation PR.
```

## 13. Release notes (must be DRAFTED)

```
[ ] docs/release/ATOMIC_SWAP_V14_RELEASE_NOTES.md drafted with:
        - Activation height (V14_HEIGHT) and ETA in calendar time.
        - List of features (SOST HTLC, BTC HTLC, EVM HTLC, OTC UI).
        - Asset list with per-asset risk label.
        - Upgrade window for miners (analogous to the V13 window
          described in docs/V13_MINER_OPERATOR_CHECKLIST.md).
        - Link to all three audit reports (sections 10, 11, 12).
        - Link to docs/design/ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md.
        - Link to docs/design/ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md.
        - Link to docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md.
        - Explicit fail-safe statement: "There is no admin
          override, no manual unlock, no escrow operator."
[ ] BitcoinTalk announcement drafted in the same style as the
    Block 10109 post-mortem.
[ ] Both posts queued for publication on the day of the activation
    PR merge, NOT before.
```

## 14. Activation PR (gate flips)

```
[ ] Single PR titled "atomic-swap: activate V14 HTLC consensus and
    BTC signing backend".
[ ] PR body links to all artefacts above (sections 1-13).
[ ] PR diff is exactly these lines (no other changes):

      include/sost/atomic_swap.h
        - inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT
              = INT64_MAX;
        + inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT
              = V14_HEIGHT;     // 15000

      CMakeLists.txt
        option(SOST_BTC_HTLC_SIGNING
            "Enable BTC HTLC signing backend (requires vendored
             libwally-core; default OFF)"
        -   OFF)
        +   ON)

[ ] PR is merged on a non-holiday weekday with at least two SOST
    maintainers online to monitor for the first 48 hours.
[ ] Tag the merge commit "atomic-swap-v14-activated" and push the
    tag.
```

## 15. Rollback plan

```
If something goes wrong AFTER the activation PR merges but BEFORE
height V14_HEIGHT is reached on-chain (i.e. there is still time
to backtrack), the rollback is:

  [ ] Open a follow-up PR that reverts both flips:

        include/sost/atomic_swap.h
          ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX

        CMakeLists.txt
          option(SOST_BTC_HTLC_SIGNING ... OFF)

  [ ] Rebuild and redistribute the SOST binaries with the rollback.
  [ ] Issue a status notice via BitcoinTalk and the explorer banner.
  [ ] Take the OTC wizard buttons back to disabled in
      website/sost-otc.html (Phase F preview state) if they were
      enabled by the activation PR.

If V14_HEIGHT has ALREADY been mined past, the rollback is a hard
fork. That requires:

  [ ] Coordination with every node operator.
  [ ] A second activation height (e.g. V14_ROLLBACK_HEIGHT) at
      which the gate closes again. This is NOT a normal operation —
      it implies a critical bug serious enough that re-closing the
      gate is the correct course despite the social cost of a
      coordinated rollback.

The bias is heavily toward NOT activating until every box above is
green. Re-closing the gate after activation is much harder than
delaying activation in the first place.

---

## Activation-day timeline (informational)

| T-Δ          | Action |
|--------------|--------|
| T-7 days     | All three audits signed. Release notes drafted. |
| T-3 days     | BitcoinTalk pre-announcement (no activation date yet). |
| T-1 day      | Final dry-run on testnet. Tag the activation commit. |
| T-0          | Merge activation PR to main. Push tag. Distribute binaries. |
| T+1 h        | First user-attempted swap on mainnet (test amount). |
| T+24 h       | Status report on BitcoinTalk: blocks accepted? swaps completed? |
| T+72 h       | Either declare stable, OR open rollback PR. |

This timeline is informational; the actual schedule is decided by
the maintainers when every checklist item above is green.

---

**Provenance:** this checklist is itself an artefact of master
command Phase G. It supersedes any ad-hoc activation plan and is
the SOLE reference the activation PR description must link to.
