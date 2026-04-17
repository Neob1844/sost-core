// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../SOSTEscrow.sol";
import "./MockERC20.sol";

contract SOSTEscrowTest is Test {
    SOSTEscrow public escrow;
    MockERC20 public xaut;
    MockERC20 public paxg;
    MockERC20 public unauthorized; // not allowlisted

    address public alice = makeAddr("alice");
    address public bob = makeAddr("bob");

    uint256 constant ONE_OZ_XAUT = 1e6;  // 6 decimals
    uint256 constant ONE_OZ_PAXG = 1e18; // 18 decimals
    uint256 constant THIRTY_DAYS = 30 days;
    uint256 constant ONE_YEAR = 365 days;

    function setUp() public {
        xaut = new MockERC20("Tether Gold", "XAUT", 6);
        paxg = new MockERC20("Paxos Gold", "PAXG", 18);
        unauthorized = new MockERC20("Fake Token", "FAKE", 18);

        escrow = new SOSTEscrow(address(xaut), address(paxg));

        // Give Alice some tokens
        xaut.mint(alice, 10 * ONE_OZ_XAUT);
        paxg.mint(alice, 10 * ONE_OZ_PAXG);
        unauthorized.mint(alice, 10e18);

        // Give Bob some tokens
        xaut.mint(bob, 5 * ONE_OZ_XAUT);
    }

    // ---- Test: successful deposit ----
    function test_deposit_xaut() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + ONE_YEAR;
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();

        assertEq(id, 0);
        assertEq(escrow.depositCount(), 1);
        assertEq(xaut.balanceOf(address(escrow)), ONE_OZ_XAUT);

        (address depositor, address token, uint256 amount, uint256 unlock, bool withdrawn) = escrow.getDeposit(0);
        assertEq(depositor, alice);
        assertEq(token, address(xaut));
        assertEq(amount, ONE_OZ_XAUT);
        assertEq(unlock, unlockTime);
        assertFalse(withdrawn);
    }

    function test_deposit_paxg() public {
        vm.startPrank(alice);
        paxg.approve(address(escrow), ONE_OZ_PAXG);
        uint256 id = escrow.deposit(address(paxg), ONE_OZ_PAXG, block.timestamp + ONE_YEAR);
        vm.stopPrank();

        assertEq(id, 0);
        assertEq(paxg.balanceOf(address(escrow)), ONE_OZ_PAXG);
    }

    // ---- Test: successful withdraw after unlock ----
    function test_withdraw_after_unlock() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + ONE_YEAR;
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();

        // Fast forward past unlock
        vm.warp(unlockTime + 1);

        vm.prank(alice);
        escrow.withdraw(id);

        (, , , , bool withdrawn) = escrow.getDeposit(id);
        assertTrue(withdrawn);
        assertEq(xaut.balanceOf(alice), 10 * ONE_OZ_XAUT); // got it all back
        assertEq(xaut.balanceOf(address(escrow)), 0);
    }

    // ---- Test: withdraw BEFORE unlock must FAIL ----
    function test_withdraw_before_unlock_reverts() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + ONE_YEAR;
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();

        // Try to withdraw immediately (before unlock)
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(SOSTEscrow.StillLocked.selector, unlockTime, block.timestamp)
        );
        escrow.withdraw(id);
    }

    // ---- Test: withdraw by THIRD PARTY must FAIL ----
    function test_withdraw_by_nondepositor_reverts() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + ONE_YEAR;
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();

        vm.warp(unlockTime + 1);

        // Bob tries to withdraw Alice's deposit
        vm.prank(bob);
        vm.expectRevert(
            abi.encodeWithSelector(SOSTEscrow.NotDepositor.selector, bob, alice)
        );
        escrow.withdraw(id);
    }

    // ---- Test: unauthorized token must FAIL ----
    function test_deposit_unauthorized_token_reverts() public {
        vm.startPrank(alice);
        unauthorized.approve(address(escrow), 1e18);
        vm.expectRevert(
            abi.encodeWithSelector(SOSTEscrow.TokenNotAllowed.selector, address(unauthorized))
        );
        escrow.deposit(address(unauthorized), 1e18, block.timestamp + ONE_YEAR);
        vm.stopPrank();
    }

    // ---- Test: multiple deposits by same user ----
    function test_multiple_deposits() public {
        vm.startPrank(alice);

        xaut.approve(address(escrow), 3 * ONE_OZ_XAUT);
        uint256 id0 = escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + THIRTY_DAYS);
        uint256 id1 = escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + 90 days);
        uint256 id2 = escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + ONE_YEAR);

        vm.stopPrank();

        assertEq(id0, 0);
        assertEq(id1, 1);
        assertEq(id2, 2);
        assertEq(escrow.depositCount(), 3);
        assertEq(xaut.balanceOf(address(escrow)), 3 * ONE_OZ_XAUT);

        uint256[] memory ids = escrow.getUserDepositIds(alice);
        assertEq(ids.length, 3);
    }

    // ---- Test: double withdraw must FAIL ----
    function test_double_withdraw_reverts() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + THIRTY_DAYS);
        vm.stopPrank();

        vm.warp(block.timestamp + THIRTY_DAYS + 1);

        vm.prank(alice);
        escrow.withdraw(id);

        // Second withdraw should fail
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(SOSTEscrow.AlreadyWithdrawn.selector, id));
        escrow.withdraw(id);
    }

    // ---- Test: lock duration too short ----
    function test_deposit_lock_too_short_reverts() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        vm.expectRevert(); // LockDurationTooShort
        escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + 1 days);
        vm.stopPrank();
    }

    // ---- Test: lock duration too long ----
    function test_deposit_lock_too_long_reverts() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        vm.expectRevert(); // LockDurationTooLong
        escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + 400 days);
        vm.stopPrank();
    }

    // ---- Test: amount below minimum ----
    function test_deposit_below_minimum_reverts() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), 100); // way below XAUT_MIN_AMOUNT (1000)
        vm.expectRevert(); // AmountBelowMinimum
        escrow.deposit(address(xaut), 100, block.timestamp + THIRTY_DAYS);
        vm.stopPrank();
    }

    // ---- Test: canWithdraw view function ----
    function test_canWithdraw() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + ONE_YEAR;
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();

        assertFalse(escrow.canWithdraw(id));

        vm.warp(unlockTime);
        assertTrue(escrow.canWithdraw(id));
    }

    // ---- Test: nonexistent deposit ----
    function test_withdraw_nonexistent_reverts() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(SOSTEscrow.DepositNotFound.selector, 999));
        escrow.withdraw(999);
    }

    // ---- Test: events emitted correctly ----
    function test_deposit_emits_event() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + ONE_YEAR;

        vm.expectEmit(true, true, true, true);
        emit SOSTEscrow.GoldDeposited(0, alice, address(xaut), ONE_OZ_XAUT, unlockTime);

        escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();
    }

    function test_withdraw_emits_event() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), ONE_OZ_XAUT);
        uint256 unlockTime = block.timestamp + THIRTY_DAYS;
        uint256 id = escrow.deposit(address(xaut), ONE_OZ_XAUT, unlockTime);
        vm.stopPrank();

        vm.warp(unlockTime + 1);

        vm.expectEmit(true, true, false, true);
        emit SOSTEscrow.GoldWithdrawn(id, alice, address(xaut), ONE_OZ_XAUT);

        vm.prank(alice);
        escrow.withdraw(id);
    }

    // ---- Test: totalLocked view ----
    function test_totalLocked() public {
        vm.startPrank(alice);
        xaut.approve(address(escrow), 3 * ONE_OZ_XAUT);
        escrow.deposit(address(xaut), ONE_OZ_XAUT, block.timestamp + THIRTY_DAYS);
        escrow.deposit(address(xaut), 2 * ONE_OZ_XAUT, block.timestamp + ONE_YEAR);
        vm.stopPrank();

        assertEq(escrow.totalLocked(address(xaut)), 3 * ONE_OZ_XAUT);
        assertEq(escrow.totalLocked(address(paxg)), 0);
    }
}
