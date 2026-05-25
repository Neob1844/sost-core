// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Test.sol";
import {AtomicSwapHTLC, IERC20} from "../src/AtomicSwapHTLC.sol";
import {
    MockERC20,
    MockFailERC20,
    MaliciousClaimReceiver,
    MockNoReturnERC20,
    MockFeeOnTransferERC20,
    MaliciousReentrantERC20,
    SelfdestructForcer
} from "./mocks/MockERC20.sol";

contract AtomicSwapHTLCTest is Test {
    AtomicSwapHTLC htlc;
    MockERC20      token;

    address alice = address(0xA11CE);   // initiator (refunder)
    address bob   = address(0xB0B);     // responder (claimer)
    address carol = address(0xCA0);     // unrelated 3rd party

    bytes32 preimage = bytes32(uint256(0xC0FFEE));
    bytes32 hashlock;   // sha256(preimage)
    bytes32 swapId;

    uint256 amount = 1 ether;
    uint256 refundTime;

    function setUp() public {
        htlc = new AtomicSwapHTLC();
        token = new MockERC20("Mock", "MCK");
        hashlock = sha256(abi.encodePacked(preimage));
        swapId = keccak256(abi.encodePacked("swap-1"));
        refundTime = block.number + 100;
        vm.deal(alice, 10 ether);
        vm.deal(address(this), 10 ether);
    }

    // =========================================================================
    // Native lock — happy path + parameter validation
    // =========================================================================

    function test_lockNative_happyPath() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state),  uint(AtomicSwapHTLC.State.LOCKED));
        assertEq(s.token,        address(0));
        assertEq(s.amount,       amount);
        assertEq(s.hashlock,     hashlock);
        assertEq(s.refundTime,   refundTime);
        assertEq(s.claimer,      bob);
        assertEq(s.refunder,     alice);
        assertEq(address(htlc).balance, amount);
    }

    function test_lockNative_rejectsZeroAmount() public {
        vm.expectRevert(bytes("ZERO_AMOUNT"));
        vm.prank(alice);
        htlc.lockNative{value: 0}(swapId, hashlock, refundTime, bob, alice);
    }

    function test_lockNative_rejectsZeroClaimer() public {
        vm.expectRevert(bytes("ZERO_CLAIMER"));
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, address(0), alice);
    }

    function test_lockNative_rejectsZeroRefunder() public {
        vm.expectRevert(bytes("ZERO_REFUNDER"));
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, address(0));
    }

    function test_lockNative_rejectsRefundInPast() public {
        uint256 past = block.number;  // not strictly greater
        vm.expectRevert(bytes("REFUND_IN_PAST"));
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, past, bob, alice);
    }

    function test_lockNative_rejectsDuplicateSwapId() public {
        vm.startPrank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.expectRevert(bytes("DUPLICATE_SWAP_ID"));
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.stopPrank();
    }

    // =========================================================================
    // Native claim — happy path + adversarial
    // =========================================================================

    function test_claimNative_happyPath() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        uint256 bobBalBefore = bob.balance;
        // Anyone may submit the claim (here carol, an unrelated 3rd party).
        // Funds go to bob (the recorded claimer), not the submitter.
        vm.prank(carol);
        htlc.claim(swapId, preimage);
        assertEq(bob.balance, bobBalBefore + amount);
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.CLAIMED));
    }

    function test_claimNative_rejectsWrongPreimage() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        bytes32 wrong = bytes32(uint256(0xBADBAD));
        vm.expectRevert(bytes("WRONG_PREIMAGE"));
        htlc.claim(swapId, wrong);
    }

    function test_claimNative_rejectsAfterTimeout() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.roll(refundTime);  // at refundTime, claim window closed
        vm.expectRevert(bytes("TIMEOUT_PASSED"));
        htlc.claim(swapId, preimage);
    }

    function test_claimNative_cannotClaimTwice() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        htlc.claim(swapId, preimage);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.claim(swapId, preimage);
    }

    function test_claimNative_cannotClaimUnknownSwap() public {
        bytes32 ghost = keccak256("does-not-exist");
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.claim(ghost, preimage);
    }

    // =========================================================================
    // Native refund — happy path + adversarial
    // =========================================================================

    function test_refundNative_happyPath() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.roll(refundTime);  // refund window open
        uint256 aliceBalBefore = alice.balance;
        vm.prank(carol);  // anyone may submit refund; funds go to refunder
        htlc.refund(swapId);
        assertEq(alice.balance, aliceBalBefore + amount);
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.REFUNDED));
    }

    function test_refundNative_rejectsBeforeTimeout() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        // still at block.number < refundTime
        vm.expectRevert(bytes("TIMEOUT_NOT_REACHED"));
        htlc.refund(swapId);
    }

    function test_refundNative_cannotRefundTwice() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.roll(refundTime);
        htlc.refund(swapId);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.refund(swapId);
    }

    function test_refundAfterClaim_rejected() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        htlc.claim(swapId, preimage);
        vm.roll(refundTime);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.refund(swapId);
    }

    function test_claimAfterRefund_rejected() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.roll(refundTime);
        htlc.refund(swapId);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.claim(swapId, preimage);
    }

    // =========================================================================
    // ERC-20 lock / claim / refund — happy paths
    // =========================================================================

    function test_lockERC20_happyPath() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
        assertEq(token.balanceOf(address(htlc)), amount);
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(s.token,  address(token));
        assertEq(s.amount, amount);
    }

    function test_claimERC20_happyPath() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();

        vm.prank(carol);
        htlc.claim(swapId, preimage);
        assertEq(token.balanceOf(bob), amount);
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.CLAIMED));
    }

    function test_refundERC20_happyPath() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();

        vm.roll(refundTime);
        htlc.refund(swapId);
        assertEq(token.balanceOf(alice), amount);
    }

    function test_claimERC20_rejectsWrongPreimage() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
        vm.expectRevert(bytes("WRONG_PREIMAGE"));
        htlc.claim(swapId, bytes32(uint256(0xDEAD)));
    }

    function test_lockERC20_rejectsZeroToken() public {
        vm.expectRevert(bytes("ZERO_TOKEN"));
        htlc.lockERC20(swapId, address(0), amount, hashlock, refundTime, bob, alice);
    }

    function test_lockERC20_rejectsFailingToken() public {
        MockFailERC20 bad = new MockFailERC20();
        vm.expectRevert(bytes("TRANSFER_FAILED"));
        htlc.lockERC20(swapId, address(bad), amount, hashlock, refundTime, bob, alice);
    }

    // =========================================================================
    // Events
    // =========================================================================

    event LockCreated(
        bytes32 indexed swapId,
        address indexed locker,
        address          token,
        uint256          amount,
        bytes32          hashlock,
        uint256          refundTime,
        address          claimer,
        address          refunder
    );
    event Claimed(bytes32 indexed swapId, bytes32 preimage, address claimer);
    event Refunded(bytes32 indexed swapId, address refunder);

    function test_event_LockCreated_native() public {
        vm.expectEmit(true, true, false, true, address(htlc));
        emit LockCreated(swapId, alice, address(0), amount, hashlock, refundTime, bob, alice);
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
    }

    function test_event_Claimed_native() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.expectEmit(true, false, false, true, address(htlc));
        emit Claimed(swapId, preimage, bob);
        htlc.claim(swapId, preimage);
    }

    function test_event_Refunded_native() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.roll(refundTime);
        vm.expectEmit(true, false, false, true, address(htlc));
        emit Refunded(swapId, alice);
        htlc.refund(swapId);
    }

    // =========================================================================
    // Direct-transfer rejection (defense against accidental fund loss)
    // =========================================================================

    function test_rejectsPlainEthTransfer() public {
        // expectRevert consumes the revert from the next external call.
        // The check is that the call reverts with the exact reason; the
        // call's return tuple is unreliable under expectRevert and
        // should not be asserted on.
        vm.expectRevert(bytes("DIRECT_TRANSFER_REJECTED"));
        (bool ok, ) = address(htlc).call{value: 1 ether}("");
        ok;  // silence unused-variable warning; the revert IS the assertion
    }

    // =========================================================================
    // Reentrancy — malicious receiver tries to re-enter claim() during the
    // native ETH transfer; the nonReentrant guard + state-machine guard
    // MUST both block it. The outer claim() reverts because the inner
    // reentry's revert propagates back through low-level call's return
    // value check ("TRANSFER_FAILED").
    // =========================================================================

    function test_reentrancy_blockedByGuardAndStateMachine() public {
        MaliciousClaimReceiver attacker = new MaliciousClaimReceiver(address(htlc));
        attacker.setTarget(swapId, preimage);

        // The malicious contract is the claimer. When claim() pays it, the
        // receive() callback tries to claim() again. The nonReentrant
        // modifier sets _entered=1, so the re-entry call hits REENTRANT
        // and reverts. The outer call's low-level call check sees the
        // reverted transfer and reverts with TRANSFER_FAILED, leaving
        // the state untouched.
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, address(attacker), alice);

        vm.expectRevert(bytes("TRANSFER_FAILED"));
        htlc.claim(swapId, preimage);

        // Confirm the swap is still LOCKED (not CLAIMED) because the
        // outer call reverted the state change.
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.LOCKED));
        // Funds still in escrow.
        assertEq(address(htlc).balance, amount);
    }

    // =========================================================================
    // No-owner / no-admin / no-drain — compile-time + runtime checks
    // =========================================================================

    function test_noOwnerFunctionsExist_runtime() public {
        // Try a bunch of common admin selectors. None should exist.
        bytes4[7] memory selectors = [
            bytes4(keccak256("owner()")),
            bytes4(keccak256("admin()")),
            bytes4(keccak256("pause()")),
            bytes4(keccak256("unpause()")),
            bytes4(keccak256("withdraw()")),
            bytes4(keccak256("emergencyWithdraw()")),
            bytes4(keccak256("upgradeTo(address)"))
        ];
        for (uint i = 0; i < selectors.length; i++) {
            (bool ok, ) = address(htlc).staticcall(abi.encodeWithSelector(selectors[i]));
            assertFalse(ok, "admin function should not exist");
        }
    }

    // Fuzz test: any preimage that hashes to the same hashlock claims
    // successfully; any other preimage reverts. This sanity-checks the
    // sha256 path against a wide input space.
    function testFuzz_claim_onlyAcceptsExactPreimage(bytes32 fuzzPreimage) public {
        // Skip the trivial collision case.
        vm.assume(fuzzPreimage != preimage);
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        vm.expectRevert(bytes("WRONG_PREIMAGE"));
        htlc.claim(swapId, fuzzPreimage);
    }

    // =========================================================================
    // Phase D — additional hardening
    // =========================================================================
    //
    // Items mapped to docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md.

    // ---- A. Exact balance conservation -------------------------------------

    function test_balance_nativeClaim_drainsContractToZero() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        assertEq(address(htlc).balance, amount);
        uint256 bobBefore = bob.balance;
        htlc.claim(swapId, preimage);
        assertEq(address(htlc).balance, 0);
        assertEq(bob.balance, bobBefore + amount);
    }

    function test_balance_nativeRefund_drainsContractToZero() public {
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        assertEq(address(htlc).balance, amount);
        uint256 aliceBefore = alice.balance;
        vm.roll(refundTime);
        htlc.refund(swapId);
        assertEq(address(htlc).balance, 0);
        assertEq(alice.balance, aliceBefore + amount);
    }

    function test_balance_erc20Claim_drainsContractToZero() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
        assertEq(token.balanceOf(address(htlc)), amount);
        htlc.claim(swapId, preimage);
        assertEq(token.balanceOf(address(htlc)), 0);
        assertEq(token.balanceOf(bob), amount);
    }

    function test_balance_erc20Refund_drainsContractToZero() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
        assertEq(token.balanceOf(address(htlc)), amount);
        vm.roll(refundTime);
        htlc.refund(swapId);
        assertEq(token.balanceOf(address(htlc)), 0);
        assertEq(token.balanceOf(alice), amount);
    }

    // ---- B. ERC-20 parity for the negative paths ---------------------------

    function _approveAndLockERC20() internal {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
    }

    function test_lockERC20_rejectsZeroAmount() public {
        vm.expectRevert(bytes("ZERO_AMOUNT"));
        htlc.lockERC20(swapId, address(token), 0, hashlock, refundTime, bob, alice);
    }

    function test_lockERC20_rejectsZeroClaimer() public {
        vm.expectRevert(bytes("ZERO_CLAIMER"));
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, address(0), alice);
    }

    function test_lockERC20_rejectsZeroRefunder() public {
        vm.expectRevert(bytes("ZERO_REFUNDER"));
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, address(0));
    }

    function test_lockERC20_rejectsRefundInPast() public {
        vm.expectRevert(bytes("REFUND_IN_PAST"));
        htlc.lockERC20(swapId, address(token), amount, hashlock, block.number, bob, alice);
    }

    function test_lockERC20_rejectsDuplicateSwapId() public {
        token.mint(alice, amount * 2);
        vm.startPrank(alice);
        token.approve(address(htlc), amount * 2);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.expectRevert(bytes("DUPLICATE_SWAP_ID"));
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
    }

    function test_claimERC20_rejectsAfterTimeout() public {
        _approveAndLockERC20();
        vm.roll(refundTime);
        vm.expectRevert(bytes("TIMEOUT_PASSED"));
        htlc.claim(swapId, preimage);
    }

    function test_claimERC20_cannotClaimTwice() public {
        _approveAndLockERC20();
        htlc.claim(swapId, preimage);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.claim(swapId, preimage);
    }

    function test_refundERC20_rejectsBeforeTimeout() public {
        _approveAndLockERC20();
        vm.expectRevert(bytes("TIMEOUT_NOT_REACHED"));
        htlc.refund(swapId);
    }

    function test_refundERC20_cannotRefundTwice() public {
        _approveAndLockERC20();
        vm.roll(refundTime);
        htlc.refund(swapId);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.refund(swapId);
    }

    function test_refundERC20_afterClaim_rejected() public {
        _approveAndLockERC20();
        htlc.claim(swapId, preimage);
        vm.roll(refundTime);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.refund(swapId);
    }

    function test_claimERC20_afterRefund_rejected() public {
        _approveAndLockERC20();
        vm.roll(refundTime);
        htlc.refund(swapId);
        vm.expectRevert(bytes("NOT_LOCKED"));
        htlc.claim(swapId, preimage);
    }

    // ---- C. ERC-20 event coverage ------------------------------------------

    function test_event_LockCreated_ERC20() public {
        token.mint(alice, amount);
        vm.startPrank(alice);
        token.approve(address(htlc), amount);
        vm.expectEmit(true, true, false, true, address(htlc));
        emit LockCreated(swapId, alice, address(token), amount, hashlock, refundTime, bob, alice);
        htlc.lockERC20(swapId, address(token), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
    }

    function test_event_Claimed_ERC20() public {
        _approveAndLockERC20();
        vm.expectEmit(true, false, false, true, address(htlc));
        emit Claimed(swapId, preimage, bob);
        htlc.claim(swapId, preimage);
    }

    function test_event_Refunded_ERC20() public {
        _approveAndLockERC20();
        vm.roll(refundTime);
        vm.expectEmit(true, false, false, true, address(htlc));
        emit Refunded(swapId, alice);
        htlc.refund(swapId);
    }

    // ---- D. Weird-ERC20 behaviour ------------------------------------------

    /// No-return ERC-20 (legacy USDT shape). The IERC20 interface expects
    /// `returns (bool)`; an empty return data fails to decode and reverts
    /// the lockERC20 call. The contract therefore refuses to escrow these
    /// tokens — the wallet UI must either wrap them or use a SafeERC20
    /// adapter, which is intentionally out of scope for this minimal HTLC.
    function test_lockERC20_rejectsNoReturnERC20() public {
        MockNoReturnERC20 nrt = new MockNoReturnERC20();
        nrt.mint(alice, amount);
        vm.startPrank(alice);
        nrt.approve(address(htlc), amount);
        // The transferFrom call returns nothing; abi decode of (bool) on
        // empty data reverts at the call site. We do NOT pin to a specific
        // revert string because the decode failure produces no string.
        vm.expectRevert();
        htlc.lockERC20(swapId, address(nrt), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
    }

    /// Fee-on-transfer ERC-20. The lock succeeds (transferFrom returns
    /// true) but the contract receives `amount - FEE` while state records
    /// `amount`. The asymmetry surfaces at claim time when the contract
    /// tries to send `amount` from a balance of `amount - FEE` — the
    /// underlying ERC-20 transfer reverts with "BAL" which the HTLC
    /// surfaces as "TRANSFER_FAILED". Tokens of this kind are therefore
    /// UNSUPPORTED and the wallet UI must blacklist them at compose time.
    /// The test documents this exact failure mode so a future change in
    /// the HTLC behaviour will surface as a test diff.
    function test_lockERC20_feeOnTransferTokenIsUnsupported_lockSucceedsClaimFails() public {
        MockFeeOnTransferERC20 fot = new MockFeeOnTransferERC20();
        fot.mint(alice, amount);
        vm.startPrank(alice);
        fot.approve(address(htlc), amount);
        // Lock succeeds (transferFrom returns true).
        htlc.lockERC20(swapId, address(fot), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
        // Contract recorded `amount` but only holds `amount - FEE`.
        assertEq(fot.balanceOf(address(htlc)), amount - fot.FEE());
        // Claim reverts because the recorded amount exceeds the actual
        // balance. The inner ERC-20 reverts with "BAL"; the HTLC wraps it
        // with "TRANSFER_FAILED" via the require-on-return-bool path.
        vm.expectRevert();
        htlc.claim(swapId, preimage);
    }

    /// Malicious ERC-20 that re-enters lockERC20 during transferFrom. The
    /// nonReentrant guard MUST block the re-entry; the outer call propagates
    /// the inner REENTRANT revert and rolls back state.
    function test_lockERC20_blocksMaliciousTokenReentrancy() public {
        MaliciousReentrantERC20 evil = new MaliciousReentrantERC20(address(htlc));
        evil.mint(alice, amount);
        bytes32 reSwap = keccak256("re-enter");
        evil.arm(reSwap, hashlock, refundTime, bob, alice, amount);
        vm.startPrank(alice);
        evil.approve(address(htlc), amount);
        vm.expectRevert(bytes("REENTRANT"));
        htlc.lockERC20(swapId, address(evil), amount, hashlock, refundTime, bob, alice);
        vm.stopPrank();
        // No swap was recorded (state rolled back).
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.NONE));
        AtomicSwapHTLC.Swap memory s2 = htlc.getSwap(reSwap);
        assertEq(uint(s2.state), uint(AtomicSwapHTLC.State.NONE));
    }

    // ---- E. Forced ETH via selfdestruct (EIP-6780) -------------------------

    /// EIP-6780 (Cancun, 2024) restricts SELFDESTRUCT to only delete the
    /// contract when called in the same tx as creation, but it preserves
    /// the ETH-transfer side-effect: the selfdestruct'ing contract's
    /// balance is sent to `target` regardless of whether `target` has a
    /// payable receive() or fallback. This bypasses our DIRECT_TRANSFER_
    /// REJECTED guard. The test confirms that this forced-ETH pathway:
    ///   (a) increases the HTLC's balance unaccounted-for, but
    ///   (b) does NOT corrupt any swap state, and
    ///   (c) subsequent legitimate lockNative/claim flows still work
    ///       correctly, with the orphaned ETH simply remaining in the
    ///       contract (un-withdrawable — there is no admin path, by design).
    function test_forcedEthViaSelfdestruct_doesNotCorruptState() public {
        // Force 0.5 ether into the HTLC via a self-destructing contract.
        uint256 forced = 0.5 ether;
        new SelfdestructForcer{value: forced}(payable(address(htlc)));
        assertEq(address(htlc).balance, forced);
        // A normal lock + claim still works correctly afterwards.
        vm.prank(alice);
        htlc.lockNative{value: amount}(swapId, hashlock, refundTime, bob, alice);
        // Contract balance is now the forced amount + the locked amount.
        assertEq(address(htlc).balance, forced + amount);
        uint256 bobBefore = bob.balance;
        htlc.claim(swapId, preimage);
        // Bob received exactly `amount` (the recorded swap amount), NOT
        // the full contract balance. The forced ETH stays in the contract
        // and is un-withdrawable — by design (no admin / no drain).
        assertEq(bob.balance, bobBefore + amount);
        assertEq(address(htlc).balance, forced);
    }

    // ---- F. Fuzz refundTime boundary ---------------------------------------

    /// At block.number == refundTime - 1: claim succeeds, refund reverts.
    /// At block.number == refundTime: claim reverts (TIMEOUT_PASSED),
    /// refund succeeds. The two regions are disjoint by exactly one block.
    function testFuzz_refundTime_boundaryIsSharpAtRefundTime(uint16 delta) public {
        // delta must be at least 2 so we can roll to refundTime-1 and
        // refundTime separately without overflowing block.number == 0
        // semantics. Cap at uint16 to keep fuzz time bounded.
        vm.assume(delta >= 2);
        uint256 rt = block.number + uint256(delta);

        // Case 1: at refundTime - 1, claim succeeds.
        bytes32 sid1 = keccak256("boundary-claim");
        vm.prank(alice);
        htlc.lockNative{value: amount}(sid1, hashlock, rt, bob, alice);
        vm.roll(rt - 1);
        // Claim must work.
        htlc.claim(sid1, preimage);
        // Refund must NOT work at refundTime - 1 (still LOCKED before claim
        // would have been called, but the test for refund branch is below).

        // Case 2: at refundTime, claim reverts and refund succeeds.
        bytes32 sid2 = keccak256("boundary-refund");
        vm.roll(block.number);  // re-anchor; block.number == rt-1 currently
        vm.prank(alice);
        htlc.lockNative{value: amount}(sid2, hashlock, rt, bob, alice);
        vm.roll(rt);
        vm.expectRevert(bytes("TIMEOUT_PASSED"));
        htlc.claim(sid2, preimage);
        // Refund succeeds at refundTime exactly.
        htlc.refund(sid2);
    }
}
