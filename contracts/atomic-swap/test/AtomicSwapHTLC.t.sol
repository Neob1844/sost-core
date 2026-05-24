// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Test.sol";
import {AtomicSwapHTLC, IERC20} from "../src/AtomicSwapHTLC.sol";
import {MockERC20, MockFailERC20, MaliciousClaimReceiver} from "./mocks/MockERC20.sol";

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
}
