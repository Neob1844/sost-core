// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {WSOST} from "../src/WSOST.sol";
import {SigLib} from "../src/SigLib.sol";

contract WSOSTTest is Test {
    WSOST w;
    uint256[3] pk;
    address[3] obs;
    address admin = address(0xA11CE);
    address juan = address(0xBEEF);
    bytes32 constant VAULT = keccak256("sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    string constant JUAN_SOST = "sost1bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    function setUp() public {
        pk[0] = 0xA1; pk[1] = 0xB2; pk[2] = 0xC3;
        for (uint256 i = 0; i < 3; i++) obs[i] = vm.addr(pk[i]);
        w = _deploy();
        vm.warp(1_800_000_000);
    }

    function _cfg() internal view returns (WSOST.Config memory c) {
        address[] memory o = new address[](3);
        o[0] = obs[0]; o[1] = obs[1]; o[2] = obs[2];
        c = WSOST.Config({admin: admin, observers: o, threshold: 2, minConfirmations: 30,
                          exposureCap: 1_000_000e8, dailyMintCap: 100_000e8});
    }

    function _deploy() internal returns (WSOST) {
        return new WSOST(VAULT, _cfg());
    }

    function _dep(bytes32 id, address to, uint256 amt) internal pure returns (WSOST.Deposit memory d) {
        d = WSOST.Deposit({depositId: id, recipient: to, amount: amt, bridgeVault: VAULT,
                           sostBlockHash: keccak256("block"), sostBlockHeight: 1234, confirmations: 30, bridgeVersion: 1});
    }

    function _sig(WSOST target, uint256 key, WSOST.Deposit memory d) internal view returns (bytes memory) {
        bytes32 digest = target.depositDigest(d);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    /// signatures from the given observer indexes, sorted by signer address
    function _sigs(WSOST target, WSOST.Deposit memory d, uint256[] memory idx) internal view returns (bytes[] memory out) {
        out = new bytes[](idx.length);
        address[] memory a = new address[](idx.length);
        for (uint256 i = 0; i < idx.length; i++) { a[i] = vm.addr(pk[idx[i]]); out[i] = _sig(target, pk[idx[i]], d); }
        for (uint256 i = 0; i < idx.length; i++) for (uint256 j = i + 1; j < idx.length; j++) if (a[j] < a[i]) {
            (a[i], a[j]) = (a[j], a[i]); (out[i], out[j]) = (out[j], out[i]);
        }
    }

    function _two() internal pure returns (uint256[] memory i) { i = new uint256[](2); i[0] = 0; i[1] = 1; }

    // ---------------------------------------------------------------- happy path
    function test_wrapMint500_thenBurn200_invariants() public {
        WSOST.Deposit memory d = _dep(keccak256("tx1:0"), juan, 500e8);
        w.mint(d, _sigs(w, d, _two()));
        assertEq(w.balanceOf(juan), 500e8);
        assertEq(w.totalSupply(), 500e8);
        assertTrue(w.depositUsed(d.depositId));

        vm.prank(juan);
        bytes32 burnId = w.burn(200e8, JUAN_SOST);
        assertEq(w.totalSupply(), 300e8);
        assertEq(w.totalMinted() - w.totalBurned(), w.totalSupply());
        (address from, uint128 amount, uint64 nonce, bytes32 ah) = w.burns(burnId);
        assertEq(from, juan); assertEq(amount, 200e8); assertEq(nonce, 1); assertEq(ah, keccak256(bytes(JUAN_SOST)));
    }

    // ---------------------------------------------------------------- bridge adversarial
    function test_duplicateMint_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx1:0"), juan, 500e8);
        bytes[] memory s = _sigs(w, d, _two());
        w.mint(d, s);
        vm.expectRevert(WSOST.DepositAlreadyUsed.selector);
        w.mint(d, s);
    }

    function test_sameDepositId_differentAmount_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx1:0"), juan, 500e8);
        w.mint(d, _sigs(w, d, _two()));
        WSOST.Deposit memory d2 = _dep(keccak256("tx1:0"), juan, 1e8);
        bytes[] memory s2 = _sigs(w, d2, _two());
        vm.expectRevert(WSOST.DepositAlreadyUsed.selector);
        w.mint(d2, s2);
    }

    function test_oneObserverOnly_cannotMint() public {
        WSOST.Deposit memory d = _dep(keccak256("tx2:0"), juan, 1e8);
        uint256[] memory one = new uint256[](1); one[0] = 2;
        bytes[] memory s = _sigs(w, d, one);
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_sameObserverTwice_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx3:0"), juan, 1e8);
        bytes[] memory s = new bytes[](2);
        s[0] = _sig(w, pk[0], d); s[1] = _sig(w, pk[0], d);
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_nonObserverSignature_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx4:0"), juan, 1e8);
        bytes[] memory s = new bytes[](2);
        bytes memory a = _sig(w, pk[0], d);
        bytes memory b = _sig(w, 0xDEAD, d);       // relayer / outsider key
        if (vm.addr(pk[0]) < vm.addr(0xDEAD)) { s[0] = a; s[1] = b; } else { s[0] = b; s[1] = a; }
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_relayerAlone_cannotMint() public {
        WSOST.Deposit memory d = _dep(keccak256("tx5:0"), juan, 1e8);
        bytes[] memory none = new bytes[](0);
        vm.prank(address(0x5E1A7));
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, none);
    }

    function test_amountMismatch_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx6:0"), juan, 500e8);
        bytes[] memory s = _sigs(w, d, _two());
        d.amount = 600e8;
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_recipientMismatch_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx7:0"), juan, 500e8);
        bytes[] memory s = _sigs(w, d, _two());
        d.recipient = address(0xBAD);
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_staleBlockHash_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx8:0"), juan, 500e8);
        bytes[] memory s = _sigs(w, d, _two());
        d.sostBlockHash = keccak256("other-branch");
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_wrongChainId_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx9:0"), juan, 1e8);
        bytes[] memory s = _sigs(w, d, _two());
        vm.chainId(999);                                  // replay on another chain
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
    }

    function test_wrongContract_replayFromOtherDeployment_reverts() public {
        WSOST other = _deploy();
        WSOST.Deposit memory d = _dep(keccak256("tx10:0"), juan, 1e8);
        bytes[] memory s = _sigs(other, d, _two());        // signed for the other deployment
        vm.expectRevert(WSOST.BadSignatures.selector);
        w.mint(d, s);
        other.mint(d, s);                                 // valid only where it was signed
        assertEq(other.balanceOf(juan), 1e8);
    }

    function test_wrongBridgeVersion_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx11:0"), juan, 1e8);
        d.bridgeVersion = 2;
        bytes[] memory s = _sigs(w, d, _two());
        vm.expectRevert(WSOST.BadVersion.selector);
        w.mint(d, s);
    }

    function test_wrongVault_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx12:0"), juan, 1e8);
        d.bridgeVault = keccak256("sost1-attacker-vault");
        bytes[] memory s = _sigs(w, d, _two());
        vm.expectRevert(WSOST.BadVault.selector);
        w.mint(d, s);
    }

    function test_notEnoughConfirmations_reverts() public {
        WSOST.Deposit memory d = _dep(keccak256("tx13:0"), juan, 1e8);
        d.confirmations = 29;
        bytes[] memory s = _sigs(w, d, _two());
        vm.expectRevert(WSOST.NotEnoughConfirmations.selector);
        w.mint(d, s);
    }

    function test_dailyCap_andNextDay() public {
        WSOST.Deposit memory d1 = _dep(keccak256("a"), juan, 100_000e8);
        w.mint(d1, _sigs(w, d1, _two()));
        WSOST.Deposit memory d2 = _dep(keccak256("b"), juan, 1);
        bytes[] memory s2 = _sigs(w, d2, _two());
        vm.expectRevert(WSOST.DailyCapExceeded.selector);
        w.mint(d2, s2);
        vm.warp(block.timestamp + 1 days);
        w.mint(d2, s2);
        assertEq(w.totalSupply(), 100_000e8 + 1);
    }

    function test_exposureCap() public {
        for (uint256 i = 0; i < 10; i++) {
            vm.warp(block.timestamp + 1 days);
            WSOST.Deposit memory d = _dep(keccak256(abi.encode(i)), juan, 100_000e8);
            w.mint(d, _sigs(w, d, _two()));
        }
        vm.warp(block.timestamp + 1 days);
        WSOST.Deposit memory x = _dep(keccak256("over"), juan, 1);
        bytes[] memory s = _sigs(w, x, _two());
        vm.expectRevert(WSOST.ExposureCapExceeded.selector);
        w.mint(x, s);
    }

    function test_pauseMint_transfersAndBurnsStillWork() public {
        WSOST.Deposit memory d = _dep(keccak256("p"), juan, 10e8);
        w.mint(d, _sigs(w, d, _two()));
        vm.prank(obs[2]);                                  // any observer may stop new mints
        w.pauseMint();
        WSOST.Deposit memory d2 = _dep(keccak256("p2"), juan, 1e8);
        bytes[] memory s2 = _sigs(w, d2, _two());
        vm.expectRevert(WSOST.MintIsPaused.selector);
        w.mint(d2, s2);
        vm.prank(juan); w.transfer(address(0xCAFE), 3e8);
        vm.prank(juan); w.burn(2e8, JUAN_SOST);
        assertEq(w.balanceOf(address(0xCAFE)), 3e8);
        vm.prank(obs[0]);
        vm.expectRevert(WSOST.NotAdmin.selector);
        w.unpauseMint();
        vm.prank(admin); w.unpauseMint();
        w.mint(d2, s2);
    }

    function test_outsiderCannotPause() public {
        vm.prank(juan);
        vm.expectRevert(WSOST.NotPauser.selector);
        w.pauseMint();
    }

    function test_burnRequiresValidSostAddress() public {
        WSOST.Deposit memory d = _dep(keccak256("b"), juan, 10e8);
        w.mint(d, _sigs(w, d, _two()));
        vm.startPrank(juan);
        vm.expectRevert(WSOST.BadSostAddress.selector);
        w.burn(1e8, "sost1ZZZZbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
        vm.expectRevert(WSOST.BadSostAddress.selector);
        w.burn(1e8, "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
        vm.expectRevert(WSOST.InsufficientBalance.selector);
        w.burn(11e8, JUAN_SOST);
        bytes32 b1 = w.burn(1e8, JUAN_SOST);
        bytes32 b2 = w.burn(1e8, JUAN_SOST);
        vm.stopPrank();
        assertTrue(b1 != b2);                               // every burn has a unique id
    }

    function test_compromisedTwoObservers_canMint_butCapsBound() public {
        // Documented trust assumption: a threshold of observers CAN mint. The caps bound the damage
        // and the indexer reconciliation flags CRITICAL (Python side).
        WSOST.Deposit memory d = _dep(keccak256("fake"), juan, 100_000e8);
        w.mint(d, _sigs(w, d, _two()));
        WSOST.Deposit memory d2 = _dep(keccak256("fake2"), juan, 1);
        bytes[] memory s2 = _sigs(w, d2, _two());
        vm.expectRevert(WSOST.DailyCapExceeded.selector);
        w.mint(d2, s2);
    }

    function test_unavailableObserver_twoOfThreeStillWork() public {
        WSOST.Deposit memory d = _dep(keccak256("u"), juan, 1e8);
        uint256[] memory i = new uint256[](2); i[0] = 1; i[1] = 2;   // observer 0 offline
        w.mint(d, _sigs(w, d, i));
        assertEq(w.balanceOf(juan), 1e8);
    }

    function test_malleableHighS_rejected() public {
        WSOST.Deposit memory d = _dep(keccak256("m"), juan, 1e8);
        bytes32 digest = w.depositDigest(d);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk[0], digest);
        uint256 n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        bytes32 sHigh = bytes32(n - uint256(s));
        uint8 vFlip = v == 27 ? 28 : 27;
        bytes[] memory sigs = new bytes[](2);
        bytes memory good = _sig(w, pk[1], d);
        bytes memory bad = abi.encodePacked(r, sHigh, vFlip);
        if (vm.addr(pk[0]) < vm.addr(pk[1])) { sigs[0] = bad; sigs[1] = good; } else { sigs[0] = good; sigs[1] = bad; }
        vm.expectRevert(SigLib.BadSignature.selector);
        w.mint(d, sigs);
    }

    // ---------------------------------------------------------------- timelocked admin
    function test_configChange_needsTimelock() public {
        WSOST.Config memory c = _cfg();
        c.minConfirmations = 60;
        vm.prank(juan);
        vm.expectRevert(WSOST.NotAdmin.selector);
        w.proposeConfig(c);
        vm.prank(admin); w.proposeConfig(c);
        vm.prank(admin);
        vm.expectRevert(WSOST.ConfigNotReady.selector);
        w.applyConfig(c);
        vm.warp(block.timestamp + 2 days);
        WSOST.Config memory other = _cfg(); other.minConfirmations = 1;
        vm.prank(admin);
        vm.expectRevert(WSOST.ConfigNotReady.selector);
        w.applyConfig(other);                              // only the exact proposed config
        vm.prank(admin); w.applyConfig(c);
        assertEq(w.minConfirmations(), 60);
    }

    function test_config_rejectsMinorityThreshold() public {
        WSOST.Config memory c = _cfg();
        c.threshold = 1;                                   // 1-of-3 is not a strict majority
        vm.expectRevert(WSOST.BadConfig.selector);
        new WSOST(VAULT, c);
    }

    // ---------------------------------------------------------------- fuzz
    function testFuzz_supplyEqualsMintedMinusBurned(uint96 a, uint96 b) public {
        uint256 amt = bound(uint256(a), 1, 100_000e8);
        uint256 burnAmt = bound(uint256(b), 1, amt);
        WSOST.Deposit memory d = _dep(keccak256(abi.encode(a, b)), juan, amt);
        w.mint(d, _sigs(w, d, _two()));
        vm.prank(juan); w.burn(burnAmt, JUAN_SOST);
        assertEq(w.totalSupply(), amt - burnAmt);
        assertEq(w.totalMinted() - w.totalBurned(), w.totalSupply());
    }
}
