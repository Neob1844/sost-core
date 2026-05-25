# Atomic Swap — EVM hardening (Phase D) — STOP report

**Status:** STOP. Phase D cannot run on the current production VPS.

**Reason:** the master command Phase D requires `forge test -vvv` as
its first verification step. The Foundry toolchain (`forge`, `cast`,
`anvil`, `chisel`) is not installed on the production VPS at
`/opt/sost`, and the operator policy is **not** to install developer
tooling on the production VPS without explicit approval. Per the
master command:

> "NO instalar Foundry en VPS si no está ya instalado sin pedirme
> confirmación."

This report captures every test, doc, and command Phase D needs to
land. It is intended to be executed verbatim in a dev environment
(WSL / ZBook / laptop) that already has Foundry, and the resulting
commits to be pushed back to `feat/atomic-swap-htlc-v13-candidate`
once verified.

**Companion artefacts already on the branch:**
- `contracts/atomic-swap/src/AtomicSwapHTLC.sol` (11.5 KB).
- `contracts/atomic-swap/test/AtomicSwapHTLC.t.sol` (15 KB, 29 tests).
- `contracts/atomic-swap/test/mocks/MockERC20.sol`.
- `docs/design/ATOMIC_SWAP_EVM_CONTRACT_REVIEW.md` (Phase 4B-1 review).
- `docs/design/ATOMIC_SWAP_EVM_IMPLEMENTATION_DECISION.md`.

**Safety state at the time this report is committed (verified):**
- Branch: `feat/atomic-swap-htlc-v13-candidate` (2 commits ahead of
  origin: Phase A `6fbed8c8` + Phase B `caa923a1`).
- `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (`include/sost/atomic_swap.h:107`).
- `SOST_BTC_HTLC_SIGNING` CMake option default `OFF`.
- `src/atomic_swap_btc_signing.cpp` returns `disabled_result()` from every external function.

---

## 1. Existing test coverage (already on the branch)

`forge test` baseline is **29 tests** in `AtomicSwapHTLC.t.sol`,
last reported as 28 unit + 1 fuzz (256 runs) all green at the time
of Phase 4B-1 (commit `52d2fcef`). Inventory:

```
NATIVE ETH path
  test_lockNative_happyPath
  test_lockNative_rejectsZeroAmount
  test_lockNative_rejectsZeroClaimer
  test_lockNative_rejectsZeroRefunder
  test_lockNative_rejectsRefundInPast
  test_lockNative_rejectsDuplicateSwapId
  test_claimNative_happyPath
  test_claimNative_rejectsWrongPreimage
  test_claimNative_rejectsAfterTimeout
  test_claimNative_cannotClaimTwice
  test_claimNative_cannotClaimUnknownSwap
  test_refundNative_happyPath
  test_refundNative_rejectsBeforeTimeout
  test_refundNative_cannotRefundTwice
  test_refundAfterClaim_rejected
  test_claimAfterRefund_rejected

ERC20 path
  test_lockERC20_happyPath
  test_claimERC20_happyPath
  test_refundERC20_happyPath
  test_claimERC20_rejectsWrongPreimage
  test_lockERC20_rejectsZeroToken
  test_lockERC20_rejectsFailingToken

Events
  test_event_LockCreated_native
  test_event_Claimed_native
  test_event_Refunded_native

Adversarial
  test_rejectsPlainEthTransfer
  test_reentrancy_blockedByGuardAndStateMachine
  test_noOwnerFunctionsExist_runtime

Fuzz
  testFuzz_claim_onlyAcceptsExactPreimage(bytes32)
```

Phase D **adds** the tests in section 2 to fill gaps the master
command flagged as missing, then ships an audit checklist
(section 3). The contract itself (`AtomicSwapHTLC.sol`) is **not**
modified unless a test reveals a real bug — per the master command
rules, hardening means more tests + better docs, not more code.

---

## 2. Tests Phase D MUST add

Per the master command's list. Each test below is described with
its intent so the dev-environment implementation cannot drift.

### 2.1 Exact balance conservation — native ETH

```solidity
function test_conservation_native_claim() public {
    // pre: swap is locked
    // claim
    // assert: claimer.balance increased by EXACTLY locked amount
    // assert: contract.balance decreased by EXACTLY locked amount
    // assert: contract.balance == 0 after if no other swaps
}

function test_conservation_native_refund() public {
    // mirror of claim path, but refund after timeout
    // refunder.balance increased by EXACTLY locked amount
    // contract.balance decreased by EXACTLY locked amount
}
```

These exist implicitly inside the happy-path tests but are not
asserted as a hard invariant. Phase D makes them explicit assertions.

### 2.2 Exact balance conservation — ERC20

Mirror of 2.1 against `MockERC20`. Two new tests with explicit
`balanceOf` assertions before/after.

### 2.3 Fee-on-transfer token behaviour

```solidity
contract MockFeeOnTransferERC20 is MockERC20 {
    function transferFrom(...) public override returns (bool) {
        uint256 fee = amount / 100; // 1% fee
        uint256 net = amount - fee;
        // burn fee, transfer net
    }
}

function test_lockERC20_feeOnTransfer_documented() public {
    // Lock 1000 tokens, contract should receive 990 (after 1% fee).
    // Either:
    //   (a) contract rejects because received != amount, OR
    //   (b) contract records the actual received amount in swap.amount.
    // Phase D must pick ONE policy and document it.
    // Current contract uses transferFrom(... amount) without checking
    // post-transfer balance => silent under-fund. Phase D MUST either:
    //   - add a balance-delta check and revert if delta != amount
    //   - explicitly document that fee-on-transfer tokens are unsupported
}
```

**Decision required during Phase D:** pick (a) "reject silently
under-funded swaps" by comparing pre/post balanceOf, OR (b) document
fee-on-transfer as explicitly unsupported in the doc + reject these
tokens in the UI's asset list. Recommendation: (a), because it
fails closed without needing the UI to enumerate every weird token.

### 2.4 ERC20 returns false (already partially covered)

`test_lockERC20_rejectsFailingToken` exists. Add:

```solidity
function test_claimERC20_rejectsFailingTokenOnTransfer() public {
    // Lock OK with a normal token.
    // Mid-claim, token.transfer to claimer returns false.
    // Assert: claim reverts, swap stays Locked (state unchanged),
    // claimer.balance unchanged.
}

function test_refundERC20_rejectsFailingTokenOnTransfer() public {
    // Mirror for refund.
}
```

### 2.5 ERC20 without return value (non-bool)

Some legacy tokens (USDT, OMG, BNB) don't return a bool from
`transfer`/`transferFrom`. Test:

```solidity
contract MockERC20NoReturn {
    // transfer(...) returns nothing
    // transferFrom(...) returns nothing
}

function test_lockERC20_noReturnToken() public {
    // Depends on whether the contract uses SafeERC20.
    // If it does: must accept.
    // If it does NOT: must reject cleanly with a known revert
    // (not silently succeed by misreading uninitialised return data).
}
```

**Action:** read the AtomicSwapHTLC.sol IERC20 calls. If they trust
the return value naively (`require(IERC20(token).transferFrom(...))`),
then non-return tokens will revert or silently break. The contract
should either use `SafeERC20` or document non-bool tokens as
unsupported.

### 2.6 Direct ETH transfer rejected

`test_rejectsPlainEthTransfer` exists. Phase D additionally covers:

```solidity
function test_rejectsPlainEthTransfer_lowLevelCall() public {
    // Use address(htlc).call{value: 1 ether}("") and assert revert.
}

function test_rejectsPlainEthTransfer_withData() public {
    // Send ETH + random calldata that doesn't match a known selector.
}
```

### 2.7 Forced ETH via selfdestruct — documented, NOT countered

An attacker can `selfdestruct(payable(htlc))` from another contract
and force ETH into the HTLC. This is a known Solidity quirk and
cannot be prevented at the contract level (post-Dencun
`selfdestruct` is partially neutered but the legacy form remains
for already-deployed contracts).

```solidity
function test_forcedEthViaSelfdestruct_documented() public {
    // Deploy attacker contract.
    // Fund it with 1 ether.
    // Attacker calls selfdestruct(payable(htlc)).
    // Assert: htlc.balance == 1 ether (we cannot prevent the
    // injection).
    // Assert: no swap was created.
    // Assert: the forced ether is NOT accessible to anyone —
    // there is no admin / drain function.
    // Result: the ether is permanently locked, which is the
    // correct fail-closed behaviour. Document in the audit
    // checklist as a known impossibility.
}
```

### 2.8 Fuzz: refundTime boundary

```solidity
function testFuzz_refundTime_boundary(uint256 lockTime, uint256 refundOffset) public {
    // bound lockTime to [block.timestamp, block.timestamp + 30 days]
    // bound refundOffset to [1, 30 days]
    // refundTime = lockTime + refundOffset
    //
    // assert: refund at exactly refundTime - 1  -> reverts
    // assert: refund at exactly refundTime       -> succeeds
    // assert: refund at refundTime + 1           -> succeeds
    // assert: claim at refundTime - 1            -> succeeds
    // assert: claim at refundTime + 1            -> reverts
    //
    // This pins the timeout boundary in both directions across
    // a wide fuzz space.
}
```

### 2.9 Fuzz: random wrong preimage never claims

`testFuzz_claim_onlyAcceptsExactPreimage(bytes32)` already covers
this with 256 runs. Phase D bumps the run count via foundry.toml
or function-level annotation to 10000 runs to harden the assurance,
and adds a sibling test that fuzzes the `hashlock` value at lock
time.

### 2.10 Reentrancy variants

`test_reentrancy_blockedByGuardAndStateMachine` exists. Add:

```solidity
function test_reentrancy_maliciousReceiverNative() public {
    // Receiver contract reenters claim() during its receive().
    // Assert: reverts (nonReentrant guard fires).
}

function test_reentrancy_maliciousReceiverERC20() public {
    // ERC20 with a callback in transfer (e.g. ERC777) reenters
    // claim().
    // Assert: reverts.
}

function test_reentrancy_acrossLockAndClaim() public {
    // Attacker locks, immediately tries to claim from inside their
    // own lock's receive() callback path.
    // Assert: reverts (state machine + guard).
}
```

### 2.11 No-admin proof (already covered, expand)

`test_noOwnerFunctionsExist_runtime` exists. Add a static proof:

```solidity
function test_noAdminSelectors_static() public {
    // Enumerate every public/external function selector on the
    // contract. Compare against a hardcoded whitelist:
    //   - getSwap(bytes32)
    //   - lockNative(bytes32, address, address, uint256, uint256)
    //   - lockERC20(bytes32, address, address, address, uint256, uint256)
    //   - claim(bytes32, bytes32)
    //   - refund(bytes32)
    //   - (any view methods)
    // If any selector outside the whitelist is found, fail loudly.
}
```

Catches drift where a future commit adds a hidden function.

---

## 3. Audit checklist doc to ship in this same commit

Path: `docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md`

Must cover:

1. **Invariants** the external auditor must verify:
   - `address(this).balance == sum of all Swap.amount where Swap.status == Locked` (modulo forced selfdestruct ETH, see §2.7).
   - Sum of ERC20 token balances per token address obeys the same invariant for each token.
   - `Swap.status` only transitions via the documented state diagram: `None -> Locked -> Claimed | Refunded`.
   - No two distinct swap IDs share storage.
   - `block.timestamp >= refundTime` is the only condition under which refund can fire.

2. **Known unsupported token types** (document explicitly):
   - Fee-on-transfer (rejected; see §2.3)
   - Rebasing (untested; behaviour undefined)
   - Tokens with hooks/callbacks (ERC777, ERC1363) — should be tested under §2.10
   - Tokens with non-standard `decimals()` — works but UI should warn

3. **Stablecoin freeze risk** disclosure:
   - USDT, USDC, PAXG, XAUT can be frozen by issuer.
   - Counterparty's tokens being frozen mid-swap = stuck swap.
   - Refund still works (no token transfer occurs).
   - Claim cannot complete if claimer's address is frozen.
   - UI must show "ISSUER-RISK" badge on these assets (already done
     per Phase 4D).

4. **Reentrancy posture**:
   - `nonReentrant` on `claim` and `refund` (lockNative does not
     need it because no external call before state update).
   - State machine prevents double-spend even if guard is removed
     in error.

5. **Timeout assumptions**:
   - Block timestamp is the consensus reference.
   - Minimum recommended refund offset = 24 h to absorb network
     congestion.
   - Maximum recommended = 7 days to avoid long-tail counterparty
     abandonment.
   - These are UI policy, not contract enforcement.

6. **No-admin design statement**:
   - No owner, no admin, no pauser, no upgrader, no drainer.
   - No proxy pattern. The contract is permanently immutable once
     deployed.
   - There is no recovery mechanism for forced ETH (§2.7) or for
     funds locked under an unrecoverable preimage. This is by
     design — see "Immutability rationale" subsection.

7. **Testnet deployment checklist**:
   - Deploy to Sepolia (Ethereum) AND BSC testnet.
   - Verify on Etherscan / BscScan with full source.
   - Run end-to-end SOST↔ETH swap and SOST↔BNB swap.
   - Run with each ERC20 testnet token from the OTC asset list.
   - Document the deployed addresses in
     `docs/release/ATOMIC_SWAP_TESTNET_DEPLOYMENT.md` (Phase G).

8. **External audit checklist** (for the auditor's reference):
   - Provide this document + `ATOMIC_SWAP_EVM_CONTRACT_REVIEW.md` +
     full `AtomicSwapHTLC.t.sol` + the foundry.toml.
   - Provide the build artefacts (bytecode + ABI + sources_metadata).
   - Provide the EVM-side coordinator scaffolding
     (`include/sost/atomic_swap_coordinator.h`) so the auditor sees
     the full swap state machine.
   - Provide the BTC-side scope explicitly (Phase 4A: scaffolded but
     disabled; not in audit scope unless auditor expands).

---

## 4. Exact dev-environment commands (WSL / ZBook)

```bash
# 0. Have Foundry installed:
curl -L https://foundry.paradigm.xyz | bash
foundryup
forge --version    # must print

# 1. Sync the branch:
cd ~/SOST/sostcore/sost-core
git fetch origin
git checkout feat/atomic-swap-htlc-v13-candidate
git pull --ff-only origin feat/atomic-swap-htlc-v13-candidate

# 2. Baseline:
cd contracts/atomic-swap
forge test -vvv 2>&1 | tee /tmp/phase-d-baseline.log
# Expect: 29 passed, 0 failed, 1 fuzz at 256 runs.

# 3. Add the new tests (per §2 above).
#    Edit test/AtomicSwapHTLC.t.sol.
#    Add test/mocks/MockFeeOnTransferERC20.sol if needed for §2.3.
#    Add test/mocks/MockERC20NoReturn.sol if needed for §2.5.
#    Add test/mocks/ReentrantReceiver.sol if needed for §2.10.

# 4. Verify all new tests pass:
forge test -vvv 2>&1 | tee /tmp/phase-d-final.log
# Expect: ~45-50 passed (29 baseline + 16-21 new), 0 failed.

# 5. Audit checklist doc:
cd ../..
cat > docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md <<'EOF'
... (per §3 above) ...
EOF

# 6. Verify the SOST C++ side still compiles and all atomic-swap
#    test binaries still pass (no consensus regression):
cmake --build build-v13-main -j$(nproc)
./build-v13-main/test-atomic-swap-htlc-lock
./build-v13-main/test-atomic-swap-htlc-helpers
./build-v13-main/test-atomic-swap-htlc-rpc
./build-v13-main/test-atomic-swap-btc-script
./build-v13-main/test-atomic-swap-btc-signing
./build-v13-main/test-atomic-swap-btc-test-vectors
./build-v13-main/test-atomic-swap-coordinator
python3 -m pytest tests/trinity/ -q

# 7. Safety greps:
grep -n 'ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT' include/sost/atomic_swap.h
# expect: INT64_MAX
grep -A2 '^option(SOST_BTC_HTLC_SIGNING' CMakeLists.txt | head -3
# expect: default OFF
grep -RniE 'owner|onlyOwner|upgrade|proxy|pause|emergency|drain' \
    contracts/atomic-swap/src/ contracts/atomic-swap/test/ \
    | grep -v 'noOwner\|no_owner\|noAdmin'
# expect: only the negative-assertion tests should match

# 8. Commit (only if every step above succeeded):
git add contracts/atomic-swap/test/AtomicSwapHTLC.t.sol \
        contracts/atomic-swap/test/mocks/*.sol \
        docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md
git commit -m "atomic-swap: harden EVM HTLC contract tests"

# 9. Final report:
forge --version
forge test 2>&1 | tail -1   # "Suite result: ok. N passed; 0 failed; ..."
git log --oneline -3
git diff --stat HEAD~1..HEAD
```

---

## 5. Why not install Foundry on the VPS

The VPS at `/opt/sost` is the production seed node host. Installing
Foundry there would:

1. Pull ~50-100 MB of binaries from `foundry.paradigm.xyz`
   (`forge`, `cast`, `anvil`, `chisel`).
2. Add a `~/.foundry/` directory to `/root`.
3. Possibly require Rust toolchain (`rustup`) for source builds.
4. Not be needed for any node operation — the node does not need
   Foundry to validate, mine, or serve RPC.
5. Increase the attack surface of the production host with
   developer tooling that has no production role.

The dev environment (WSL / ZBook) already has Foundry per the
operator's previous build of the EVM contract during Phase 4B-1.
Running Phase D there and pushing the resulting commit to the
shared branch is the correct path. The VPS will see the new tests
when it pulls the branch but will not need to execute them — only
the SOST C++ side runs on the VPS.

---

## 6. STOP rule honoured

Per the master command:

> "5. Si algo no pasa, STOP y no sigas."

Phase D's first step is `forge test -vvv`. That step cannot run
on the current host. Therefore Phase D STOPs cleanly, this report
captures every action that the dev-environment run must take, and
no Solidity source / test file is modified by this commit — the
risk of shipping unverified Solidity is zero because no Solidity
was edited.

---

**Files this commit ships:** 1 new, 0 modified.
  - `docs/design/ATOMIC_SWAP_EVM_HARDENING_STOP_REPORT.md` (this file)
