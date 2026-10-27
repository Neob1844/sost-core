// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// F-1 (C713): asset isolation in AtomicSwapHTLCv2.
// Adversarial unit tests, fuzz tests and a handler-driven invariant suite.
// Each adversarial case is also run against the pre-fix code
// (test/legacy/AtomicSwapHTLCv2Vulnerable.sol) to show the difference.

import "forge-std/Test.sol";
import "../src/AtomicSwapHTLCv2.sol";
import "./legacy/AtomicSwapHTLCv2Vulnerable.sol";

// ---------------------------------------------------------------- tokens
contract IsoToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    uint256 public feeBps; // 0 = standard; >0 = fee-on-transfer, fee burned from the sender
    constructor(uint256 f) { feeBps = f; }
    function mint(address to, uint256 a) external { balanceOf[to] += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function _move(address f, address t, uint256 a) internal {
        require(balanceOf[f] >= a, "BAL");
        uint256 fee = a * feeBps / 10000;
        balanceOf[f] -= a; balanceOf[t] += a - fee;
    }
    function transfer(address t, uint256 a) external returns (bool) { _move(msg.sender, t, a); return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        require(allowance[f][msg.sender] >= a, "ALLOW"); allowance[f][msg.sender] -= a; _move(f, t, a); return true;
    }
}

// A hostile token: on every transfer out of the HTLC it tries to re-enter a
// DIFFERENT function on a DIFFERENT swap (cross-function reentrancy).
contract HostileToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    AtomicSwapHTLCv2 public h; bytes32 public victimId; bytes32 public victimPre; bool public armed; bool public reentryOk;
    function mint(address to, uint256 a) external { balanceOf[to] += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function arm(AtomicSwapHTLCv2 _h, bytes32 id, bytes32 pre) external { h = _h; victimId = id; victimPre = pre; armed = true; }
    function transfer(address t, uint256 a) external returns (bool) {
        if (armed) {
            armed = false;
            try h.claimNative(victimId, victimPre) { reentryOk = true; } catch {}
            try h.refundNative(victimId) { reentryOk = true; } catch {}
        }
        balanceOf[msg.sender] -= a; balanceOf[t] += a; return true;
    }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        allowance[f][msg.sender] -= a; balanceOf[f] -= a; balanceOf[t] += a; return true;
    }
}

// A claimer/refunder contract that re-enters on ETH receipt.
contract ReenteringParty {
    AtomicSwapHTLCv2 public h; bytes32 public otherId; bytes32 public otherPre; bool public reentryOk; uint256 public hits;
    function set(AtomicSwapHTLCv2 _h, bytes32 id, bytes32 pre) external { h = _h; otherId = id; otherPre = pre; }
    function claimNative(bytes32 id, bytes32 pre) external { h.claimNative(id, pre); }
    function refundNative(bytes32 id) external { h.refundNative(id); }
    receive() external payable {
        hits++;
        if (hits == 1) {
            try h.claimNative(otherId, otherPre) { reentryOk = true; } catch {}
            try h.refundNative(otherId) { reentryOk = true; } catch {}
            try h.claimERC20(otherId, otherPre, 0) { reentryOk = true; } catch {}
        }
    }
}

// ---------------------------------------------------------------- adversarial
contract AtomicSwapHTLCv2IsolationTest is Test {
    AtomicSwapHTLCv2 h;
    AtomicSwapHTLCv2Vulnerable old;
    address victimLocker = address(0xA11CE);
    address victimClaimer = address(0xB0B);
    address attacker = address(0xBAD);
    bytes32 victimPre = keccak256("victim-secret");
    bytes32 atkPre = keccak256("attacker-secret");
    uint256 RT;
    bytes32 vHl; bytes32 aHl; // precomputed: sha256 is a precompile CALL and would consume a vm.prank

    function setUp() public {
        h = new AtomicSwapHTLCv2(); old = new AtomicSwapHTLCv2Vulnerable();
        RT = block.number + 100; vHl = _hl(victimPre); aHl = _hl(atkPre);
        vm.deal(victimLocker, 1000 ether); vm.deal(attacker, 1 ether);
    }
    function _hl(bytes32 p) internal pure returns (bytes32) { return sha256(abi.encodePacked(p)); }

    // victim locks 10 ETH natively; attacker locks a worthless ERC-20 with amount = 10e18
    function _setupFixed() internal returns (bytes32 vid, bytes32 aid, IsoToken junk) {
        vid = keccak256("victim"); aid = keccak256("attacker");
        vm.prank(victimLocker); h.lockNative{value: 10 ether}(vid, vHl, RT, victimClaimer, victimLocker);
        junk = new IsoToken(0); junk.mint(attacker, 10 ether);
        vm.startPrank(attacker); junk.approve(address(h), 10 ether);
        h.lockERC20(aid, address(junk), 10 ether, aHl, RT, attacker, attacker); vm.stopPrank();
    }

    function test_F1_legacy_drain_reproduces() public {
        bytes32 vid = keccak256("victim"); bytes32 aid = keccak256("attacker");
        vm.prank(victimLocker); old.lockNative{value: 10 ether}(vid, vHl, RT, victimClaimer, victimLocker);
        IsoToken junk = new IsoToken(0); junk.mint(attacker, 10 ether);
        vm.startPrank(attacker); junk.approve(address(old), 10 ether);
        old.lockERC20(aid, address(junk), 10 ether, aHl, RT, attacker, attacker);
        uint256 before = attacker.balance;
        old.claimNative(aid, atkPre); vm.stopPrank();
        assertEq(attacker.balance - before, 10 ether, "legacy: attacker took the victim's ETH");
        assertEq(address(old).balance, 0);
        assertEq(junk.balanceOf(address(old)), 10 ether, "legacy: the junk tokens are still stuck in the HTLC");
        assertEq(uint8(old.getSwap(aid).state), 2, "legacy: ERC-20 swap marked CLAIMED");
        vm.prank(victimClaimer); vm.expectRevert(bytes("SEND_FAILED")); old.claimNative(vid, victimPre);
        vm.roll(RT); vm.prank(victimLocker); vm.expectRevert(bytes("SEND_FAILED")); old.refundNative(vid);
    }

    function test_F1_fixed_erc20_swap_cannot_claimNative() public {
        (bytes32 vid, bytes32 aid, IsoToken junk) = _setupFixed();
        uint256 before = attacker.balance;
        vm.prank(attacker); vm.expectRevert(bytes("NOT_NATIVE")); h.claimNative(aid, atkPre);
        assertEq(attacker.balance, before);
        assertEq(address(h).balance, 10 ether);
        assertEq(uint8(h.getSwap(aid).state), 1, "ERC-20 swap still LOCKED");
        // the attacker's own swap still works through the right path
        vm.prank(attacker); h.claimERC20(aid, atkPre, 10 ether);
        assertEq(junk.balanceOf(attacker), 10 ether);
        // the victim is unaffected
        vm.prank(victimClaimer); h.claimNative(vid, victimPre);
        assertEq(victimClaimer.balance, 10 ether);
        assertEq(address(h).balance, 0);
    }

    function test_F1_fixed_erc20_swap_cannot_refundNative() public {
        (bytes32 vid, bytes32 aid, ) = _setupFixed();
        vm.roll(RT);
        vm.prank(attacker); vm.expectRevert(bytes("NOT_NATIVE")); h.refundNative(aid);
        assertEq(address(h).balance, 10 ether);
        vm.prank(victimLocker); h.refundNative(vid);
        assertEq(address(h).balance, 0);
    }

    function test_native_swap_cannot_use_erc20_paths() public {
        (bytes32 vid, , ) = _setupFixed();
        vm.prank(victimClaimer); vm.expectRevert(bytes("NOT_ERC20")); h.claimERC20(vid, victimPre, 0);
        vm.roll(RT);
        vm.prank(victimLocker); vm.expectRevert(bytes("NOT_ERC20")); h.refundERC20(vid);
        assertEq(address(h).balance, 10 ether);
    }

    function test_erc20_lock_with_eoa_token_rejected() public {
        vm.prank(attacker); vm.expectRevert(bytes("NOT_CONTRACT"));
        h.lockERC20(keccak256("eoa"), address(0xDEAD), 1 ether, aHl, RT, attacker, attacker);
    }

    function test_hostile_token_cross_function_reentry_blocked() public {
        bytes32 vid = keccak256("victim"); bytes32 aid = keccak256("hostile");
        vm.prank(victimLocker); h.lockNative{value: 10 ether}(vid, vHl, RT, victimClaimer, victimLocker);
        HostileToken t = new HostileToken(); t.mint(attacker, 5 ether);
        vm.startPrank(attacker); t.approve(address(h), 5 ether);
        h.lockERC20(aid, address(t), 5 ether, aHl, RT, attacker, attacker); vm.stopPrank();
        t.arm(h, vid, victimPre);
        vm.prank(attacker); h.claimERC20(aid, atkPre, 0);
        assertFalse(t.reentryOk(), "re-entry must fail");
        assertEq(address(h).balance, 10 ether);
        assertEq(uint8(h.getSwap(vid).state), 1);
    }

    function test_reentering_claimer_cannot_touch_other_swaps() public {
        ReenteringParty p = new ReenteringParty();
        bytes32 a = keccak256("p-swap"); bytes32 b = keccak256("other");
        vm.startPrank(victimLocker);
        h.lockNative{value: 3 ether}(a, aHl, RT, address(p), address(p));
        h.lockNative{value: 7 ether}(b, vHl, RT, address(p), address(p)); // p is even the claimer of b
        vm.stopPrank();
        p.set(h, b, victimPre);
        p.claimNative(a, atkPre);
        assertFalse(p.reentryOk());
        assertEq(address(p).balance, 3 ether);
        assertEq(address(h).balance, 7 ether);
        assertEq(uint8(h.getSwap(b).state), 1);
        p.claimNative(b, victimPre); // the legitimate, non-reentrant claim still works
        assertEq(address(h).balance, 0);
    }

    function test_each_swap_settles_at_most_once() public {
        (bytes32 vid, bytes32 aid, ) = _setupFixed();
        vm.prank(victimClaimer); h.claimNative(vid, victimPre);
        vm.prank(victimClaimer); vm.expectRevert(bytes("NOT_LOCKED")); h.claimNative(vid, victimPre);
        vm.roll(RT);
        vm.prank(victimLocker); vm.expectRevert(bytes("NOT_LOCKED")); h.refundNative(vid);
        vm.prank(attacker); h.refundERC20(aid);
        vm.prank(attacker); vm.expectRevert(bytes("NOT_LOCKED")); h.refundERC20(aid);
        vm.prank(attacker); vm.expectRevert(bytes("NOT_LOCKED")); h.claimERC20(aid, atkPre, 0);
    }

    // fuzz: whatever the amounts, an ERC-20 swap's claimer/refunder never gets ETH
    function testFuzz_erc20_swap_never_releases_eth(uint96 native, uint96 tok, uint8 path, bool late) public {
        native = uint96(bound(native, 1, 500 ether)); tok = uint96(bound(tok, 1, type(uint96).max));
        bytes32 vid = keccak256("v"); bytes32 aid = keccak256("a");
        vm.prank(victimLocker); h.lockNative{value: native}(vid, vHl, RT, victimClaimer, victimLocker);
        IsoToken junk = new IsoToken(0); junk.mint(attacker, tok);
        vm.startPrank(attacker); junk.approve(address(h), tok);
        h.lockERC20(aid, address(junk), tok, aHl, RT, attacker, attacker);
        if (late) vm.roll(RT);
        uint256 ethBefore = attacker.balance;
        path = path % 2;
        if (path == 0) { vm.expectRevert(); h.claimNative(aid, atkPre); }
        else { vm.expectRevert(); h.refundNative(aid); }
        vm.stopPrank();
        assertEq(attacker.balance, ethBefore);
        assertEq(address(h).balance, native);
        assertEq(uint8(h.getSwap(aid).state), 1);
    }
}

// ---------------------------------------------------------------- invariants
contract IsoHandler is Test {
    AtomicSwapHTLCv2 public h;
    IsoToken[3] public toks; // standard, 1% fee, 0.5% fee
    address[4] public actors = [address(0x1001), address(0x1002), address(0x1003), address(0x1004)];
    bytes32[] public ids;
    mapping(bytes32 => bytes32) public preOf;
    mapping(bytes32 => uint256) public settleCount;
    uint256 public ghostNativeOpen;
    mapping(address => uint256) public ghostTokenOpen;
    uint256 public wrongKindSuccesses; // must stay 0
    uint256 public nonce;
    uint256 public locksNative; uint256 public locksToken; uint256 public settles; uint256 public wrongKindTries;

    constructor(AtomicSwapHTLCv2 _h) {
        h = _h;
        toks[0] = new IsoToken(0); toks[1] = new IsoToken(100); toks[2] = new IsoToken(50);
        for (uint i; i < 4; i++) vm.deal(actors[i], 1e30);
    }
    function tokenAt(uint i) external view returns (address) { return address(toks[i]); }
    function idsLength() external view returns (uint256) { return ids.length; }
    function _hl(bytes32 p) internal pure returns (bytes32) { return sha256(abi.encodePacked(p)); }

    function _newSwap(string memory tag) internal returns (bytes32 id, bytes32 hl) {
        id = keccak256(abi.encode(tag, nonce)); bytes32 pre = keccak256(abi.encode("p", nonce)); nonce++;
        preOf[id] = pre; ids.push(id); hl = _hl(pre);
    }
    function lockNative(uint256 a, uint8 who, uint8 claimer, uint16 dt) external {
        a = bound(a, 1, 1e24); address w = actors[who % 4]; address c = actors[claimer % 4];
        (bytes32 id, bytes32 hl) = _newSwap("n");
        vm.prank(w); h.lockNative{value: a}(id, hl, block.number + 1 + (dt % 50), c, w);
        locksNative++; ghostNativeOpen += a;
    }
    function lockToken(uint256 a, uint8 ti, uint8 who, uint8 claimer, uint16 dt) external {
        a = bound(a, 1000, 1e24); address w = actors[who % 4]; address c = actors[claimer % 4]; IsoToken t = toks[ti % 3];
        (bytes32 id, bytes32 hl) = _newSwap("t");
        t.mint(w, a);
        vm.startPrank(w); t.approve(address(h), a);
        h.lockERC20(id, address(t), a, hl, block.number + 1 + (dt % 50), c, w); vm.stopPrank();
        locksToken++; ghostTokenOpen[address(t)] += h.getSwap(id).lockedAmount;
    }
    function _pick(uint256 i) internal view returns (bytes32 id, AtomicSwapHTLCv2.Swap memory s) {
        id = ids[i % ids.length]; s = h.getSwap(id);
    }
    function claim(uint256 i) external {
        if (ids.length == 0) return;
        (bytes32 id, AtomicSwapHTLCv2.Swap memory s) = _pick(i);
        bool native = s.token == address(0);
        vm.prank(s.claimer);
        bool ok;
        if (native) { try h.claimNative(id, preOf[id]) { ok = true; } catch {} }
        else { try h.claimERC20(id, preOf[id], 0) { ok = true; } catch {} }
        if (ok) { settles++; settleCount[id]++; if (native) ghostNativeOpen -= s.lockedAmount; else ghostTokenOpen[s.token] -= s.lockedAmount; }
    }
    function refund(uint256 i) external {
        if (ids.length == 0) return;
        (bytes32 id, AtomicSwapHTLCv2.Swap memory s) = _pick(i);
        bool native = s.token == address(0);
        vm.prank(s.refunder);
        bool ok;
        if (native) { try h.refundNative(id) { ok = true; } catch {} }
        else { try h.refundERC20(id) { ok = true; } catch {} }
        if (ok) { settles++; settleCount[id]++; if (native) ghostNativeOpen -= s.lockedAmount; else ghostTokenOpen[s.token] -= s.lockedAmount; }
    }
    // the attack: call the path of the OTHER asset kind, with the right secret and the right sender
    function wrongKind(uint256 i, bool doRefund) external {
        if (ids.length == 0) return;
        (bytes32 id, AtomicSwapHTLCv2.Swap memory s) = _pick(i);
        bool native = s.token == address(0);
        bool ok; wrongKindTries++;
        if (!doRefund) {
            vm.prank(s.claimer);
            if (native) { try h.claimERC20(id, preOf[id], 0) { ok = true; } catch {} }
            else { try h.claimNative(id, preOf[id]) { ok = true; } catch {} }
        } else {
            vm.prank(s.refunder);
            if (native) { try h.refundERC20(id) { ok = true; } catch {} }
            else { try h.refundNative(id) { ok = true; } catch {} }
        }
        if (ok) wrongKindSuccesses++;
    }
    // replay: a second settlement of an already-settled swap (any path)
    function replay(uint256 i, uint8 path) external {
        if (ids.length == 0) return;
        (bytes32 id, AtomicSwapHTLCv2.Swap memory s) = _pick(i);
        if (s.state == AtomicSwapHTLCv2.State.LOCKED) return;
        bool ok; path = path % 4;
        vm.startPrank(path < 2 ? s.claimer : s.refunder);
        if (path == 0) { try h.claimNative(id, preOf[id]) { ok = true; } catch {} }
        if (path == 1) { try h.claimERC20(id, preOf[id], 0) { ok = true; } catch {} }
        if (path == 2) { try h.refundNative(id) { ok = true; } catch {} }
        if (path == 3) { try h.refundERC20(id) { ok = true; } catch {} }
        vm.stopPrank();
        if (ok) settleCount[id]++;
    }
    function roll(uint8 n) external { vm.roll(block.number + 1 + (n % 30)); }
}

/// forge-config: default.invariant.runs = 256
/// forge-config: default.invariant.depth = 128
contract AtomicSwapHTLCv2InvariantTest is Test {
    AtomicSwapHTLCv2 h; IsoHandler hd;
    function setUp() public {
        h = new AtomicSwapHTLCv2(); hd = new IsoHandler(h);
        targetContract(address(hd));
    }
    function invariant_eth_balance_equals_open_native_swaps() public view {
        assertEq(address(h).balance, hd.ghostNativeOpen());
        uint256 sum;
        for (uint i; i < hd.idsLength(); i++) {
            AtomicSwapHTLCv2.Swap memory s = h.getSwap(hd.ids(i));
            if (s.state == AtomicSwapHTLCv2.State.LOCKED && s.token == address(0)) sum += s.lockedAmount;
        }
        assertEq(address(h).balance, sum);
    }
    function invariant_token_balance_equals_open_token_swaps() public view {
        for (uint t; t < 3; t++) {
            address tok = hd.tokenAt(t);
            uint256 sum;
            for (uint i; i < hd.idsLength(); i++) {
                AtomicSwapHTLCv2.Swap memory s = h.getSwap(hd.ids(i));
                if (s.state == AtomicSwapHTLCv2.State.LOCKED && s.token == tok) sum += s.lockedAmount;
            }
            assertEq(IsoToken(tok).balanceOf(address(h)), sum);
            assertEq(sum, hd.ghostTokenOpen(tok));
        }
    }
    function invariant_each_swap_settled_at_most_once() public view {
        for (uint i; i < hd.idsLength(); i++) {
            bytes32 id = hd.ids(i);
            uint256 c = hd.settleCount(id);
            assertLe(c, 1);
            bool settled = h.getSwap(id).state != AtomicSwapHTLCv2.State.LOCKED;
            assertEq(c == 1, settled);
        }
    }
    function invariant_wrong_kind_never_succeeds() public view {
        assertEq(hd.wrongKindSuccesses(), 0);
    }
    function afterInvariant() public view {
        console.log("locksNative", hd.locksNative(), "locksToken", hd.locksToken());
        console.log("settles", hd.settles(), "wrongKindTries", hd.wrongKindTries());
    }
}
