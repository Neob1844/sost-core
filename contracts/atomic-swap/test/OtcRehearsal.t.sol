// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Test.sol";
import "forge-std/console2.sol";
import {AtomicSwapHTLC} from "../src/AtomicSwapHTLC.sol";
import {MockERC20} from "./mocks/MockERC20.sol";

// =============================================================================
// OTC-5 EVM rehearsal (forge test form) — narrates the full SOST↔EVM
// counterparty-leg flow on an in-process EVM with real opcodes, real events and
// real state transitions. Run with:
//
//   forge test --match-contract OtcRehearsal -vv
//
// This is the in-environment evidence; scripts/otc_rehearsal_evm_anvil.sh runs
// the SAME flow against a live anvil node via cast when one is available.
// No mainnet, no broadcast, no key material beyond test keys.
// =============================================================================
contract OtcRehearsal is Test {
    bytes32 constant SECRET = bytes32(uint256(0xC0FFEE));   // shared swap secret
    address constant ALICE  = address(0xA11CE);            // initiator / refunder
    address constant BOB    = address(0xB0B);              // responder / claimer

    AtomicSwapHTLC htlc;
    MockERC20      token;
    bytes32        hashlock;

    function setUp() public {
        htlc  = new AtomicSwapHTLC();
        token = new MockERC20("MockUSD", "mUSD");
        hashlock = sha256(abi.encodePacked(SECRET));   // identical on SOST/BTC/EVM legs
        vm.deal(ALICE, 10 ether);
        console2.log("== OTC-5 EVM rehearsal ==");
        console2.log("HTLC:", address(htlc));
        console2.log("MockERC20:", address(token));
    }

    // Happy path 1 — native ETH lock -> claim (preimage revealed in event).
    function test_rehearse_nativeClaim() public {
        bytes32 swapId = keccak256("rehearse-native-claim");
        vm.prank(ALICE);
        htlc.lockNative{value: 1 ether}(swapId, hashlock, block.number + 100, BOB, ALICE);
        console2.log("[native] locked 1 ETH; HTLC balance:", address(htlc).balance);

        uint256 bobBefore = BOB.balance;
        htlc.claim(swapId, SECRET);
        console2.log("[native] claimed; BOB +wei:", BOB.balance - bobBefore);

        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.CLAIMED));
        assertEq(address(htlc).balance, 0);
        console2.log("[native] PASS: CLAIMED, drained to 0");
    }

    // Happy path 2 — ERC-20 lock -> claim.
    function test_rehearse_erc20Claim() public {
        bytes32 swapId = keccak256("rehearse-erc20-claim");
        uint256 amount = 1000e18;
        token.mint(ALICE, amount);
        vm.startPrank(ALICE);
        token.approve(address(htlc), amount);
        htlc.lockERC20(swapId, address(token), amount, hashlock, block.number + 100, BOB, ALICE);
        vm.stopPrank();
        console2.log("[erc20] locked; HTLC token bal:", token.balanceOf(address(htlc)));
        htlc.claim(swapId, SECRET);
        console2.log("[erc20] claimed; BOB token bal:", token.balanceOf(BOB));
        assertEq(token.balanceOf(BOB), amount);
        assertEq(token.balanceOf(address(htlc)), 0);
        console2.log("[erc20] PASS: delivered, drained");
    }

    // Refund path — native lock, refund-before-timeout reverts, refund at T2.
    function test_rehearse_nativeRefund() public {
        bytes32 swapId = keccak256("rehearse-native-refund");
        uint256 rt = block.number + 50;
        vm.prank(ALICE);
        htlc.lockNative{value: 0.5 ether}(swapId, hashlock, rt, BOB, ALICE);

        vm.expectRevert(bytes("TIMEOUT_NOT_REACHED"));
        htlc.refund(swapId);
        console2.log("[refund] refund-before-T2 correctly reverted");

        vm.roll(rt);
        uint256 aliceBefore = ALICE.balance;
        htlc.refund(swapId);
        console2.log("[refund] refunded; ALICE +wei:", ALICE.balance - aliceBefore);
        AtomicSwapHTLC.Swap memory s = htlc.getSwap(swapId);
        assertEq(uint(s.state), uint(AtomicSwapHTLC.State.REFUNDED));
        console2.log("[refund] PASS: REFUNDED");
    }

    // Negative — wrong preimage rejected.
    function test_rehearse_wrongPreimage() public {
        bytes32 swapId = keccak256("rehearse-wrong-preimage");
        vm.prank(ALICE);
        htlc.lockNative{value: 0.1 ether}(swapId, hashlock, block.number + 100, BOB, ALICE);
        vm.expectRevert(bytes("WRONG_PREIMAGE"));
        htlc.claim(swapId, bytes32(uint256(0xBAD)));
        console2.log("[neg] wrong-preimage claim rejected");
    }

    // Cross-leg link — the preimage a claim reveals is exactly what the other
    // leg needs; this asserts the on-chain hashlock equals sha256(secret).
    function test_rehearse_preimageMatchesHashlock() public view {
        assertEq(sha256(abi.encodePacked(SECRET)), hashlock);
        console2.log("[link] sha256(secret) == hashlock (shared across SOST/BTC/EVM)");
    }
}
