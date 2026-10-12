// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Test.sol";
import "../src/AtomicSwapHTLCv2.sol";

// ---- mock tokens exercising the weird-ERC20 surface --------------------------
contract Base {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address to, uint256 a) external { balanceOf[to] += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function _move(address f, address t, uint256 a) internal { require(balanceOf[f] >= a, "BAL"); balanceOf[f]-=a; balanceOf[t]+=a; }
    function _spend(address f, uint256 a) internal { if (allowance[f][msg.sender] != type(uint256).max) { require(allowance[f][msg.sender] >= a, "ALLOW"); allowance[f][msg.sender]-=a; } }
}
contract StdToken is Base { // returns true
    function transfer(address t, uint256 a) external returns (bool) { _move(msg.sender,t,a); return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) { _spend(f,a); _move(f,t,a); return true; }
}
contract NoReturnToken is Base { // USDT-style: no return data
    function transfer(address t, uint256 a) external { _move(msg.sender,t,a); }
    function transferFrom(address f, address t, uint256 a) external { _spend(f,a); _move(f,t,a); }
}
contract FalseToken is Base { // returns false
    function transfer(address, uint256) external pure returns (bool) { return false; }
    function transferFrom(address, address, uint256) external pure returns (bool) { return false; }
}
contract RevertToken is Base {
    function transfer(address, uint256) external pure returns (bool) { revert("NOPE"); }
    function transferFrom(address, address, uint256) external pure returns (bool) { revert("NOPE"); }
}
contract FeeToken is Base { // PAXG-style 1% fee-on-transfer (fee burned)
    function transfer(address t, uint256 a) external returns (bool) { uint256 fee=a/100; _move(msg.sender,t,a-fee); balanceOf[msg.sender]-=fee; return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) { _spend(f,a); uint256 fee=a/100; _move(f,t,a-fee); balanceOf[f]-=fee; return true; }
}
contract ReentrantToken is Base {
    AtomicSwapHTLCv2 public htlc; bytes32 public swapId; bytes32 public preimage; bool armed;
    function set(AtomicSwapHTLCv2 h, bytes32 id, bytes32 p) external { htlc=h; swapId=id; preimage=p; armed=true; }
    function transfer(address t, uint256 a) external returns (bool) {
        if (armed) { armed=false; htlc.claimERC20(swapId, preimage, 0); } // re-enter
        _move(msg.sender,t,a); return true;
    }
    function transferFrom(address f, address t, uint256 a) external returns (bool) { _spend(f,a); _move(f,t,a); return true; }
}

contract AtomicSwapHTLCv2Test is Test {
    AtomicSwapHTLCv2 h;
    address alice = address(0xA11CE); // locker/refunder
    address bob   = address(0xB0B);   // claimer
    bytes32 pre = keccak256("preimage-secret");
    bytes32 hl;
    uint256 RT;

    function setUp() public { h = new AtomicSwapHTLCv2(); hl = sha256(abi.encodePacked(pre)); RT = block.number + 100; }

    function _lockStd(uint256 amt) internal returns (bytes32 id, StdToken tok) {
        tok = new StdToken(); tok.mint(alice, amt);
        vm.startPrank(alice); tok.approve(address(h), amt);
        id = keccak256("std"); h.lockERC20(id, address(tok), amt, hl, RT, bob, alice); vm.stopPrank();
    }

    function test_std_happy_lock_claim() public {
        (bytes32 id, StdToken tok) = _lockStd(1000);
        AtomicSwapHTLCv2.Swap memory s = h.getSwap(id);
        assertEq(s.lockedAmount, 1000, "std locked == amount");
        vm.prank(bob); h.claimERC20(id, pre, 1000);
        assertEq(tok.balanceOf(bob), 1000, "bob got 1000");
    }
    function test_std_refund() public {
        (bytes32 id, StdToken tok) = _lockStd(1000);
        vm.roll(RT); vm.prank(alice); h.refundERC20(id);
        assertEq(tok.balanceOf(alice), 1000, "refunded full");
    }
    function test_usdt_noReturn_lock_claim() public {
        NoReturnToken tok = new NoReturnToken(); tok.mint(alice, 500);
        vm.startPrank(alice); tok.approve(address(h), 500);
        bytes32 id = keccak256("usdt"); h.lockERC20(id, address(tok), 500, hl, RT, bob, alice); vm.stopPrank();
        assertEq(h.getSwap(id).lockedAmount, 500, "no-return locked == 500");
        vm.prank(bob); h.claimERC20(id, pre, 500);
        assertEq(tok.balanceOf(bob), 500, "no-return delivered 500");
    }
    function test_falseReturn_lock_reverts() public {
        FalseToken tok = new FalseToken(); tok.mint(alice, 100);
        vm.startPrank(alice); tok.approve(address(h), 100);
        vm.expectRevert(bytes("TOKEN_RETURNED_FALSE")); h.lockERC20(keccak256("f"), address(tok), 100, hl, RT, bob, alice); vm.stopPrank();
    }
    function test_revertToken_lock_reverts() public {
        RevertToken tok = new RevertToken(); tok.mint(alice, 100);
        vm.startPrank(alice); tok.approve(address(h), 100);
        vm.expectRevert(bytes("TOKEN_CALL_FAILED")); h.lockERC20(keccak256("r"), address(tok), 100, hl, RT, bob, alice); vm.stopPrank();
    }
    function test_feeToken_balanceDelta_and_slippage() public {
        FeeToken tok = new FeeToken(); tok.mint(alice, 1000);
        vm.startPrank(alice); tok.approve(address(h), 1000);
        bytes32 id = keccak256("fee"); h.lockERC20(id, address(tok), 1000, hl, RT, bob, alice); vm.stopPrank();
        assertEq(h.getSwap(id).lockedAmount, 990, "fee: locked = actual received (990)");
        vm.prank(bob); vm.expectRevert(bytes("SLIPPAGE")); h.claimERC20(id, pre, 1000); // demands too much
        vm.prank(bob); h.claimERC20(id, pre, 980); // realistic min
        assertEq(tok.balanceOf(bob), 981, "fee: bob receives locked minus claim fee (981)");
    }
    function test_reentrancy_guard() public {
        ReentrantToken tok = new ReentrantToken(); tok.mint(alice, 100);
        vm.startPrank(alice); tok.approve(address(h), 100);
        bytes32 id = keccak256("re"); h.lockERC20(id, address(tok), 100, hl, RT, bob, alice); vm.stopPrank();
        tok.set(h, id, pre);
        vm.prank(bob); vm.expectRevert(); h.claimERC20(id, pre, 0); // reentry blocked
    }
    function test_wrongPreimage() public {
        (bytes32 id, ) = _lockStd(10);
        vm.prank(bob); vm.expectRevert(bytes("BAD_PREIMAGE")); h.claimERC20(id, keccak256("wrong"), 0);
    }
    function test_expiredClaim() public {
        (bytes32 id, ) = _lockStd(10);
        vm.roll(RT); vm.prank(bob); vm.expectRevert(bytes("EXPIRED")); h.claimERC20(id, pre, 0);
    }
    function test_earlyRefund() public {
        (bytes32 id, ) = _lockStd(10);
        vm.prank(alice); vm.expectRevert(bytes("NOT_YET")); h.refundERC20(id);
    }
    function test_doubleClaim() public {
        (bytes32 id, ) = _lockStd(10);
        vm.prank(bob); h.claimERC20(id, pre, 0);
        vm.prank(bob); vm.expectRevert(bytes("NOT_LOCKED")); h.claimERC20(id, pre, 0);
    }
    function test_zeroAmount() public {
        StdToken tok = new StdToken();
        vm.startPrank(alice); vm.expectRevert(bytes("ZERO_AMOUNT")); h.lockERC20(keccak256("z"), address(tok), 0, hl, RT, bob, alice); vm.stopPrank();
    }
    function test_native_happy_and_refund() public {
        vm.deal(alice, 5 ether);
        vm.prank(alice); h.lockNative{value: 2 ether}(keccak256("n1"), hl, RT, bob, alice);
        vm.prank(bob); h.claimNative(keccak256("n1"), pre);
        assertEq(bob.balance, 2 ether, "native claimed");
        vm.prank(alice); h.lockNative{value: 1 ether}(keccak256("n2"), hl, RT, bob, alice);
        vm.roll(RT); vm.prank(alice); h.refundNative(keccak256("n2"));
        assertEq(alice.balance, 3 ether, "native refunded");
    }
    function test_noPlainEth() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice); (bool ok, ) = address(h).call{value: 1 ether}("");
        assertTrue(!ok, "plain ETH rejected");
    }
}
