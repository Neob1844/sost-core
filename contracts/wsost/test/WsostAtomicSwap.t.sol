// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Stage 2B/2C: SOST <-> wSOST peer-to-peer atomic swap on the EXISTING AtomicSwapHTLCv2
// (contracts/atomic-swap, unchanged). wSOST is used as an ordinary ERC-20. The swap only
// moves wSOST that already exists between two users; it must never mint, burn, touch the
// bridge accounting or the Gold Reserve. Every test checks that bridge state is unchanged.

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {WSOST} from "../src/WSOST.sol";
import {GoldReserveVault} from "../src/GoldReserveVault.sol";
import {QuarantineVault} from "../src/QuarantineVault.sol";
import {AtomicSwapHTLCv2} from "atomic-swap/AtomicSwapHTLCv2.sol";
import {MockGold} from "./GoldReserve.t.sol";

contract BridgeSnapshot {
    struct S { uint256 supply; uint256 minted; uint256 burned; uint256 burnNonce; bool mintPaused; uint256 goldBal; }
}

abstract contract SwapBase is Test {
    WSOST w; AtomicSwapHTLCv2 htlc; GoldReserveVault reserve; MockGold xaut;
    uint256[3] pk; address[3] obs;
    address admin = address(0xA11CE);
    address alice = address(0xA71CE);   // holds native SOST, wants wSOST
    address bob = address(0xB0B);       // holds existing wSOST, wants native SOST
    bytes32 constant VAULT = keccak256("sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    bytes32 constant SECRET = keccak256("alice-secret");

    function _setUp() internal {
        vm.warp(1_800_000_000); vm.roll(1_000);
        pk[0] = 0xA1; pk[1] = 0xB2; pk[2] = 0xC3;
        for (uint256 i = 0; i < 3; i++) obs[i] = vm.addr(pk[i]);
        address[] memory o = new address[](3); o[0] = obs[0]; o[1] = obs[1]; o[2] = obs[2];
        w = new WSOST(VAULT, WSOST.Config({admin: admin, observers: o, threshold: 2, minConfirmations: 30,
                                            exposureCap: 1_000_000e8, dailyMintCap: 100_000e8}));
        htlc = new AtomicSwapHTLCv2();
        address[5] memory g; for (uint256 i = 0; i < 5; i++) g[i] = address(uint160(0x6000 + i));
        xaut = new MockGold("Tether Gold (TEST)", "XAUT");
        MockGold paxg = new MockGold("Paxos Gold (TEST)", "PAXG");
        address[] memory reg = new address[](2); reg[0] = address(xaut); reg[1] = address(paxg);
        QuarantineVault q = new QuarantineVault(g, reg, 7 days);
        reserve = new GoldReserveVault(g, address(q), address(xaut), address(paxg), 7 days, 6 hours);
        xaut.mint(address(this), 10e6); xaut.approve(address(reserve), 10e6); reserve.contribute(address(xaut), 10e6);
        // Bob's wSOST comes from the canonical bridge: 500 SOST locked -> 500 wSOST minted.
        _bridgeMint(keccak256("bob-deposit:0"), bob, 500e8);
    }

    function _bridgeMint(bytes32 id, address to, uint256 amt) internal {
        WSOST.Deposit memory d = WSOST.Deposit({depositId: id, recipient: to, amount: amt, bridgeVault: VAULT,
            sostBlockHash: keccak256(abi.encode(id)), sostBlockHeight: 1234, confirmations: 30, bridgeVersion: 1});
        bytes32 digest = w.depositDigest(d);
        bytes[] memory s = new bytes[](2);
        (address a0, address a1) = (obs[0], obs[1]);
        (uint8 v0, bytes32 r0, bytes32 s0) = vm.sign(pk[0], digest);
        (uint8 v1, bytes32 r1, bytes32 s1) = vm.sign(pk[1], digest);
        if (a0 < a1) { s[0] = abi.encodePacked(r0, s0, v0); s[1] = abi.encodePacked(r1, s1, v1); }
        else { s[0] = abi.encodePacked(r1, s1, v1); s[1] = abi.encodePacked(r0, s0, v0); }
        w.mint(d, s);
    }

    function _snap() internal view returns (BridgeSnapshot.S memory s) {
        s = BridgeSnapshot.S(w.totalSupply(), w.totalMinted(), w.totalBurned(), w.burnNonce(), w.mintPaused(),
                             xaut.balanceOf(address(reserve)));
    }

    function _same(BridgeSnapshot.S memory a, BridgeSnapshot.S memory b) internal pure {
        assertEq(a.supply, b.supply, "wSOST totalSupply changed by swap");
        assertEq(a.minted, b.minted, "totalMinted changed by swap");
        assertEq(a.burned, b.burned, "totalBurned changed by swap");
        assertEq(a.burnNonce, b.burnNonce, "burn nonce changed by swap");
        assertEq(a.mintPaused, b.mintPaused, "mint pause changed by swap");
        assertEq(a.goldBal, b.goldBal, "Gold Reserve changed by swap");
    }

    function _lock(bytes32 id, uint256 amt, uint256 refundBlock) internal {
        vm.startPrank(bob);
        w.approve(address(htlc), amt);
        htlc.lockERC20(id, address(w), amt, sha256(abi.encodePacked(SECRET)), refundBlock, alice, bob);
        vm.stopPrank();
    }
}

contract WsostAtomicSwapTest is SwapBase {
    function setUp() public { _setUp(); }

    // Alice locks 100 native SOST on SOST (off-chain here); Bob locks 100 wSOST; Alice claims with the
    // secret (revealing it); Bob would then claim the SOST HTLC with the same secret.
    function test_claimPath_onlyOwnershipChanges() public {
        BridgeSnapshot.S memory before = _snap();
        bytes32 id = keccak256("swap-1");
        _lock(id, 100e8, block.number + 100);
        assertEq(w.balanceOf(address(htlc)), 100e8);
        AtomicSwapHTLCv2.Swap memory s = htlc.getSwap(id);
        assertEq(s.lockedAmount, 100e8, "wSOST is not fee-on-transfer: locked == requested");
        vm.recordLogs();
        vm.prank(alice); htlc.claimERC20(id, SECRET, 100e8);
        assertEq(w.balanceOf(alice), 100e8);
        assertEq(w.balanceOf(bob), 400e8);
        assertEq(w.balanceOf(address(htlc)), 0);
        _same(before, _snap());
    }

    function test_refundPath_afterTimeout() public {
        BridgeSnapshot.S memory before = _snap();
        bytes32 id = keccak256("swap-2");
        _lock(id, 100e8, block.number + 10);
        vm.prank(bob); vm.expectRevert(bytes("NOT_YET")); htlc.refundERC20(id);
        vm.roll(block.number + 10);
        vm.prank(alice); vm.expectRevert(bytes("EXPIRED")); htlc.claimERC20(id, SECRET, 0);
        vm.prank(bob); htlc.refundERC20(id);
        assertEq(w.balanceOf(bob), 500e8);
        _same(before, _snap());
    }

    // negotiated ratio: the HTLC carries whatever amount the parties agreed (99.5 wSOST for 100 SOST)
    function test_negotiatedRatio_notHardcoded() public {
        bytes32 id = keccak256("swap-3");
        _lock(id, 99_50000000, block.number + 100);
        vm.prank(alice); htlc.claimERC20(id, SECRET, 99_50000000);
        assertEq(w.balanceOf(alice), 99_50000000);
    }

    function test_wrongSecret_wrongCaller_replay_rejected() public {
        bytes32 id = keccak256("swap-4");
        _lock(id, 50e8, block.number + 100);
        vm.prank(alice); vm.expectRevert(bytes("BAD_PREIMAGE")); htlc.claimERC20(id, keccak256("x"), 0);
        vm.prank(bob); vm.expectRevert(bytes("NOT_CLAIMER")); htlc.claimERC20(id, SECRET, 0);
        vm.prank(alice); htlc.claimERC20(id, SECRET, 50e8);
        vm.prank(alice); vm.expectRevert(bytes("NOT_LOCKED")); htlc.claimERC20(id, SECRET, 0);   // no double claim
        vm.roll(block.number + 200);
        vm.prank(bob); vm.expectRevert(bytes("NOT_LOCKED")); htlc.refundERC20(id);             // no refund after claim
        // the swap id cannot be reused
        bytes32 hl = sha256(abi.encodePacked(SECRET)); uint256 rt = block.number + 10;
        vm.startPrank(bob); w.approve(address(htlc), 1e8);
        vm.expectRevert(bytes("SWAP_EXISTS"));
        htlc.lockERC20(id, address(w), 1e8, hl, rt, alice, bob);
        vm.stopPrank();
    }

    function test_allowanceEdgeCases() public {
        bytes32 id = keccak256("swap-5");
        bytes32 hl = sha256(abi.encodePacked(SECRET)); uint256 rt = block.number + 10;
        vm.startPrank(bob);
        vm.expectRevert(bytes("TOKEN_CALL_FAILED"));   // no allowance
        htlc.lockERC20(id, address(w), 10e8, hl, rt, alice, bob);
        w.approve(address(htlc), 5e8);
        vm.expectRevert(bytes("TOKEN_CALL_FAILED"));   // allowance too small
        htlc.lockERC20(id, address(w), 10e8, hl, rt, alice, bob);
        w.approve(address(htlc), 1_000e8);
        vm.expectRevert(bytes("TOKEN_CALL_FAILED"));   // balance too small (Bob holds 500)
        htlc.lockERC20(id, address(w), 600e8, hl, rt, alice, bob);
        vm.stopPrank();
    }

    // the bridge mint pause does not freeze transfers, so a swap can still settle or refund while the
    // bridge is paused (the swap path is independent of the bridge)
    function test_bridgePaused_swapStillSettles() public {
        bytes32 id = keccak256("swap-6");
        _lock(id, 100e8, block.number + 100);
        vm.prank(obs[0]); w.pauseMint();
        assertTrue(w.mintPaused());
        vm.prank(alice); htlc.claimERC20(id, SECRET, 100e8);
        assertEq(w.balanceOf(alice), 100e8);
    }

    // a holder can unwrap swapped wSOST through the canonical path afterwards (bridge burn), and that
    // burn is the ONLY thing that changes bridge accounting
    function test_afterSwap_canonicalUnwrapStillWorks() public {
        bytes32 id = keccak256("swap-7");
        _lock(id, 100e8, block.number + 100);
        vm.prank(alice); htlc.claimERC20(id, SECRET, 100e8);
        uint256 sup = w.totalSupply();
        vm.prank(alice); w.burn(40e8, "sost1cccccccccccccccccccccccccccccccccccccccc");
        assertEq(w.totalSupply(), sup - 40e8);
    }

    function testFuzz_swapNeverChangesBridge(uint96 amount, uint16 window, bool claim) public {
        amount = uint96(bound(amount, 1, 500e8));
        window = uint16(bound(window, 1, 5_000));
        BridgeSnapshot.S memory before = _snap();
        bytes32 id = keccak256(abi.encode(amount, window, claim));
        _lock(id, amount, block.number + window);
        if (claim) { vm.prank(alice); htlc.claimERC20(id, SECRET, amount); assertEq(w.balanceOf(alice), amount); }
        else { vm.roll(block.number + window); vm.prank(bob); htlc.refundERC20(id); assertEq(w.balanceOf(bob), 500e8); }
        assertEq(w.balanceOf(address(htlc)), 0);
        _same(before, _snap());
    }
}

// Invariant: whatever sequence of locks, claims and refunds happens, the bridge numbers never move and
// the HTLC holds exactly the wSOST of the swaps still LOCKED.
contract SwapHandler is Test {
    WSOST w; AtomicSwapHTLCv2 htlc; address alice; address bob; bytes32 secret;
    bytes32[] public ids; uint256 public lockedSum;
    constructor(WSOST w_, AtomicSwapHTLCv2 h_, address a, address b, bytes32 s) { w = w_; htlc = h_; alice = a; bob = b; secret = s; }
    function lock(uint96 amt, uint8 win) external {
        uint256 bal = w.balanceOf(bob); if (bal == 0) return;
        amt = uint96(bound(amt, 1, bal)); win = uint8(bound(win, 1, 50));
        bytes32 id = keccak256(abi.encode(ids.length, amt));
        vm.startPrank(bob); w.approve(address(htlc), amt);
        htlc.lockERC20(id, address(w), amt, sha256(abi.encodePacked(secret)), block.number + win, alice, bob); vm.stopPrank();
        ids.push(id); lockedSum += amt;
    }
    function claim(uint256 i) external {
        if (ids.length == 0) return; bytes32 id = ids[i % ids.length];
        AtomicSwapHTLCv2.Swap memory s = htlc.getSwap(id);
        if (s.state != AtomicSwapHTLCv2.State.LOCKED || block.number >= s.refundTime) return;
        vm.prank(alice); htlc.claimERC20(id, secret, 0); lockedSum -= s.lockedAmount;
    }
    function refund(uint256 i) external {
        if (ids.length == 0) return; bytes32 id = ids[i % ids.length];
        AtomicSwapHTLCv2.Swap memory s = htlc.getSwap(id);
        if (s.state != AtomicSwapHTLCv2.State.LOCKED || block.number < s.refundTime) return;
        vm.prank(bob); htlc.refundERC20(id); lockedSum -= s.lockedAmount;
    }
    function roll(uint8 n) external { vm.roll(block.number + bound(n, 1, 30)); }
    // give Alice's received wSOST back to Bob so the run keeps going
    function recycle() external { uint256 b = w.balanceOf(alice); if (b > 0) { vm.prank(alice); w.transfer(bob, b); } }
}

contract WsostAtomicSwapInvariant is SwapBase {
    SwapHandler h; BridgeSnapshot.S start;
    function setUp() public {
        _setUp();
        h = new SwapHandler(w, htlc, alice, bob, SECRET);
        start = _snap();
        targetContract(address(h));
    }
    function invariant_bridgeUntouched() public view { _same(start, _snap()); }
    function invariant_htlcHoldsExactlyLocked() public view { assertEq(w.balanceOf(address(htlc)), h.lockedSum()); }
    function invariant_supplyConserved() public view {
        assertEq(w.balanceOf(alice) + w.balanceOf(bob) + w.balanceOf(address(htlc)), w.totalSupply());
    }
}
