// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {GoldReserveVault} from "../src/GoldReserveVault.sol";
import {QuarantineVault} from "../src/QuarantineVault.sol";
import {ReserveBase} from "../src/ReserveBase.sol";

contract MockGold {
    string public name; string public symbol; uint8 public constant decimals = 6;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    bool public frozen;
    constructor(string memory n, string memory s) { name = n; symbol = s; }
    function mint(address to, uint256 v) external { balanceOf[to] += v; totalSupply += v; }
    function freeze() external { frozen = true; }   // issuer-side freeze simulation
    function approve(address s, uint256 v) external returns (bool) { allowance[msg.sender][s] = v; return true; }
    function transfer(address to, uint256 v) external returns (bool) { return _t(msg.sender, to, v); }
    function transferFrom(address f, address to, uint256 v) external returns (bool) {
        require(allowance[f][msg.sender] >= v, "allow"); allowance[f][msg.sender] -= v; return _t(f, to, v);
    }
    function _t(address f, address to, uint256 v) internal returns (bool) {
        require(!frozen, "frozen"); require(balanceOf[f] >= v, "bal"); balanceOf[f] -= v; balanceOf[to] += v; return true;
    }
}

contract GoldReserveTest is Test {
    MockGold xaut; MockGold paxg;
    GoldReserveVault vault; QuarantineVault quarantine; GoldReserveVault successor;
    address[5] g;
    address donor = address(0xD0);
    uint64 constant TL = 7 days;
    uint64 constant RESCUE_DELAY = 6 hours;

    function setUp() public {
        vm.warp(1_800_000_000);
        for (uint256 i = 0; i < 5; i++) g[i] = address(uint160(0x6000 + i));
        xaut = new MockGold("Tether Gold", "XAUT");
        paxg = new MockGold("Paxos Gold", "PAXG");
        address[] memory reg = new address[](2); reg[0] = address(xaut); reg[1] = address(paxg);
        quarantine = new QuarantineVault(g, reg, TL);
        vault = new GoldReserveVault(g, address(quarantine), address(xaut), address(paxg), TL, RESCUE_DELAY);
        // successor: a fresh reserve with its own quarantine (same code, reviewed off-chain)
        QuarantineVault q2 = new QuarantineVault(g, reg, TL);
        successor = new GoldReserveVault(g, address(q2), address(xaut), address(paxg), TL, RESCUE_DELAY);
        xaut.mint(donor, 1_000e6);
        vm.startPrank(donor); xaut.approve(address(vault), type(uint256).max); vault.contribute(address(xaut), 100e6); vm.stopPrank();
    }

    function _approve(ReserveBase r, bytes32 a, uint256 n) internal {
        for (uint256 i = 0; i < n; i++) { vm.prank(g[i]); r.approve(a); }
    }

    function _proposal(address source, address succ) internal view returns (ReserveBase.Proposal memory p) {
        p = ReserveBase.Proposal({proposalId: bytes32("GRV2-004"), sourceVault: source, sourceAsset: address(xaut),
            successorVault: succ, successorAsset: address(xaut), successorCodeHash: succ.codehash,
            snapshotHeight: 35_712, closeHeight: 36_000, timelock: TL, reasonHash: keccak256("XAUT protocol migration"), version: 1});
    }

    function _gov(ReserveBase r, ReserveBase.Proposal memory p, uint32 census, uint32 yes, uint32 no, uint32 abst)
        internal view returns (ReserveBase.GovResult memory)
    {
        return ReserveBase.GovResult({proposalHash: _ph(r, p), census: census, yes: yes, no: no, abstain: abst,
            finalHeight: 36_030, tallyHash: keccak256(abi.encode("tally", census, yes, no, abst))});
    }

    function _ph(ReserveBase r, ReserveBase.Proposal memory p) internal view returns (bytes32) {
        return r.proposalHash(p);
    }

    function _register(ReserveBase r, address succ) internal {
        _approve(r, r.registerSuccessorAction(succ, succ.codehash), 4);
        r.registerSuccessor(succ, succ.codehash);
    }

    // ---------------------------------------------------------------- basics
    function test_contributeXaut_balance() public view {
        assertEq(xaut.balanceOf(address(vault)), 100e6);
    }

    function test_paxgGatedOff() public {
        paxg.mint(donor, 10e6);
        vm.startPrank(donor); paxg.approve(address(vault), type(uint256).max);
        vm.expectRevert(ReserveBase.AssetNotAllowed.selector);
        vault.contribute(address(paxg), 1e6);
        vm.stopPrank();
    }

    function test_unregisteredAsset_rejected() public {
        MockGold fake = new MockGold("Fake", "FAKE");
        vm.expectRevert(ReserveBase.AssetNotAllowed.selector);
        vault.contribute(address(fake), 1);
    }

    function test_noArbitraryWithdrawal() public {
        // No withdraw-like selector exists: low-level calls to typical names fail.
        bytes[4] memory calls = [
            abi.encodeWithSignature("withdraw(address)", address(this)),
            abi.encodeWithSignature("withdraw(address,uint256)", address(this), 1),
            abi.encodeWithSignature("sweep(address,address)", address(xaut), address(this)),
            abi.encodeWithSignature("transfer(address,uint256)", address(this), 1)
        ];
        for (uint256 i = 0; i < 4; i++) {
            vm.prank(g[0]);
            (bool ok,) = address(vault).call(calls[i]);
            assertFalse(ok);
        }
        assertEq(xaut.balanceOf(address(vault)), 100e6);
    }

    // ---------------------------------------------------------------- pause
    function test_pause_oneGuardianFails_twoPass_movesNothing() public {
        bytes32 a = vault.pauseAction();
        _approve(vault, a, 1);
        vm.expectRevert(ReserveBase.NotApproved.selector);
        vault.pause();
        _approve(vault, a, 2);
        vault.pause();
        assertTrue(vault.paused());
        assertEq(xaut.balanceOf(address(vault)), 100e6);   // pause moves nothing
        vm.prank(donor);
        vm.expectRevert(GoldReserveVault.IsPaused.selector);
        vault.contribute(address(xaut), 1e6);
        // unpause needs 4-of-5
        bytes32 u = vault.unpauseAction();
        _approve(vault, u, 3);
        vm.expectRevert(ReserveBase.NotApproved.selector);
        vault.unpause();
        _approve(vault, u, 4);
        vault.unpause();
        assertFalse(vault.paused());
    }

    function test_nonGuardianCannotApprove() public {
        bytes32 a = vault.pauseAction();
        vm.prank(donor);
        vm.expectRevert(ReserveBase.NotGuardian.selector);
        vault.approve(a);
    }

    // ---------------------------------------------------------------- critical rescue
    function test_rescue_onlyToQuarantine_needs4_andDelay() public {
        bytes32 a = vault.rescueAction(address(xaut));
        _approve(vault, a, 3);
        vm.expectRevert(ReserveBase.NotApproved.selector);
        vault.queueRescue(address(xaut));
        _approve(vault, a, 4);
        vault.queueRescue(address(xaut));
        vm.expectRevert(GoldReserveVault.RescueDelayNotExpired.selector);
        vault.executeRescue(address(xaut));
        vm.warp(block.timestamp + RESCUE_DELAY);
        vault.executeRescue(address(xaut));
        assertEq(xaut.balanceOf(address(quarantine)), 100e6);
        assertEq(xaut.balanceOf(address(vault)), 0);
    }

    function test_rescueWorksWhilePaused() public {
        _approve(vault, vault.pauseAction(), 2); vault.pause();
        _approve(vault, vault.rescueAction(address(xaut)), 4); vault.queueRescue(address(xaut));
        vm.warp(block.timestamp + RESCUE_DELAY);
        vault.executeRescue(address(xaut));
        assertEq(xaut.balanceOf(address(quarantine)), 100e6);
    }

    function test_rescueApprovalCannotBeReused() public {
        bytes32 a = vault.rescueAction(address(xaut));
        _approve(vault, a, 4); vault.queueRescue(address(xaut));
        vm.expectRevert(ReserveBase.NotApproved.selector);   // nonce advanced: fresh action id needed
        vault.queueRescue(address(xaut));
    }

    function test_quarantine_arbitraryWithdrawalBlocked() public {
        _approve(vault, vault.rescueAction(address(xaut)), 4); vault.queueRescue(address(xaut));
        vm.warp(block.timestamp + RESCUE_DELAY); vault.executeRescue(address(xaut));
        address[4] memory targets = [address(0x1234), g[0], address(0xF0F0), address(0xE8C4)];
        for (uint256 i = 0; i < 4; i++) {
            vm.prank(g[i % 5]);
            (bool ok1,) = address(quarantine).call(abi.encodeWithSignature("withdraw(address)", targets[i]));
            (bool ok2,) = address(quarantine).call(abi.encodeWithSignature("transfer(address,uint256)", targets[i], 1));
            (bool ok3,) = address(quarantine).call(abi.encodeWithSignature("sweep(address,address)", address(xaut), targets[i]));
            assertFalse(ok1 || ok2 || ok3);
        }
        assertEq(xaut.balanceOf(address(quarantine)), 100e6);
    }

    // ---------------------------------------------------------------- final migration
    function test_migration_allFourKeys_pass() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 8, 2, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 4);
        vault.queueMigration(p, r);
        vm.expectRevert(ReserveBase.TimelockNotExpired.selector);
        vault.executeMigration(p);
        vm.warp(block.timestamp + TL);
        vault.executeMigration(p);
        assertEq(xaut.balanceOf(address(successor)), 100e6);
        assertEq(xaut.balanceOf(address(vault)), 0);
        vm.expectRevert(ReserveBase.AlreadyConsumed.selector);
        vault.executeMigration(p);
    }

    function test_migration_withoutVote_fails() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 0, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.GovernanceFailed.selector);
        vault.queueMigration(p, r);
    }

    function test_vote_7of12_fails_even_with_5of5_guardians() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 7, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.GovernanceFailed.selector);
        vault.queueMigration(p, r);
    }

    function test_vote_8yes_4abstain_passes() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 8, 0, 4);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 4);
        vault.queueMigration(p, r);
        assertGt(vault.migrationEta(_ph(vault, p)), 0);
    }

    function test_vote_impossibleTally_rejected() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 10, 3, 0);   // 13 votes > census 12
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 4);
        vm.expectRevert(ReserveBase.GovernanceFailed.selector);
        vault.queueMigration(p, r);
    }

    function test_insufficientGuardians_fails() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 9, 1, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 3);
        vm.expectRevert(ReserveBase.NotApproved.selector);
        vault.queueMigration(p, r);
    }

    function test_destinationEOA_rejected() public {
        address eoa = address(0xF0F0);
        bytes32 a = vault.registerSuccessorAction(eoa, bytes32(0));
        _approve(vault, a, 5);
        vm.expectRevert(ReserveBase.SuccessorCodeMismatch.selector);
        vault.registerSuccessor(eoa, bytes32(0));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        p.successorVault = eoa; p.successorCodeHash = eoa.codehash;
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 12, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.SuccessorNotRegistered.selector);
        vault.queueMigration(p, r);
    }

    function test_arbitrarySuccessor_notRegistered_rejected() public {
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));   // not registered
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 12, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.SuccessorNotRegistered.selector);
        vault.queueMigration(p, r);
    }

    function test_successorCodeHashMismatch_rejected() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        p.successorCodeHash = keccak256("different code");
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 12, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.SuccessorCodeMismatch.selector);
        vault.queueMigration(p, r);
    }

    function test_wrongProposal_resultForOtherHash_rejected() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 12, 0, 0);
        p.reasonHash = keccak256("material field changed after the vote");   // frozen proposal changed
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.BadProposal.selector);
        vault.queueMigration(p, r);
    }

    function test_proposalHash_changesWithEveryMaterialField() public view {
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        bytes32 h = _ph(vault, p);
        ReserveBase.Proposal memory q;
        q = p; q.proposalId = bytes32("GRV2-005"); assertTrue(_ph(vault, q) != h);
        q = _proposal(address(vault), address(successor)); q.successorVault = address(0x99); assertTrue(_ph(vault, q) != h);
        q = _proposal(address(vault), address(successor)); q.snapshotHeight = 35_713; assertTrue(_ph(vault, q) != h);
        q = _proposal(address(vault), address(successor)); q.closeHeight = 36_001; assertTrue(_ph(vault, q) != h);
        q = _proposal(address(vault), address(successor)); q.timelock = TL + 1; assertTrue(_ph(vault, q) != h);
        q = _proposal(address(vault), address(successor)); q.successorAsset = address(paxg); assertTrue(_ph(vault, q) != h);
    }

    function test_timelockShorterThanMinimum_rejected() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        p.timelock = 1 hours;
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 12, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 5);
        vm.expectRevert(ReserveBase.BadProposal.selector);
        vault.queueMigration(p, r);
    }

    function test_executeBlockedWhilePaused() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 8, 2, 2);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 4);
        vault.queueMigration(p, r);
        vm.warp(block.timestamp + TL);
        _approve(vault, vault.pauseAction(), 2); vault.pause();
        vm.expectRevert(GoldReserveVault.IsPaused.selector);
        vault.executeMigration(p);
    }

    // ---------------------------------------------------------------- XAUT deprecation scenario
    function test_xautDeprecation_rescueThenGovernedMigrationFromQuarantine() public {
        // 1. issuer warns of a freeze: guardians rescue to quarantine
        _approve(vault, vault.rescueAction(address(xaut)), 4); vault.queueRescue(address(xaut));
        vm.warp(block.timestamp + RESCUE_DELAY); vault.executeRescue(address(xaut));
        // 2. quarantine cannot move without the governed path
        ReserveBase.Proposal memory p = _proposal(address(quarantine), address(successor));
        vm.expectRevert(ReserveBase.NotQueued.selector);
        quarantine.executeMigration(p);
        // 3. full governed migration from quarantine to the registered successor
        _register(quarantine, address(successor));
        ReserveBase.GovResult memory r = _gov(quarantine, p, 12, 8, 2, 2);
        _approve(quarantine, quarantine.migrationAction(_ph(quarantine, p), r.tallyHash), 4);
        quarantine.queueMigration(p, r);
        vm.warp(block.timestamp + TL);
        quarantine.executeMigration(p);
        assertEq(xaut.balanceOf(address(successor)), 100e6);
    }

    function test_frozenToken_migrationRevertsCleanly() public {
        _register(vault, address(successor));
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        ReserveBase.GovResult memory r = _gov(vault, p, 12, 9, 0, 0);
        _approve(vault, vault.migrationAction(_ph(vault, p), r.tallyHash), 4);
        vault.queueMigration(p, r);
        vm.warp(block.timestamp + TL);
        xaut.freeze();
        vm.expectRevert();
        vault.executeMigration(p);
        assertEq(xaut.balanceOf(address(vault)), 100e6);   // nothing lost, state not marked executed
        assertFalse(vault.migrationExecuted(_ph(vault, p)));
    }

    function test_governancePassed_arithmetic() public view {
        ReserveBase.Proposal memory p = _proposal(address(vault), address(successor));
        assertTrue(vault.governancePassed(_gov(vault, p, 12, 8, 2, 0)));
        assertFalse(vault.governancePassed(_gov(vault, p, 12, 7, 0, 0)));
        assertTrue(vault.governancePassed(_gov(vault, p, 12, 8, 0, 4)));
        assertFalse(vault.governancePassed(_gov(vault, p, 3, 1, 0, 2)));
        assertTrue(vault.governancePassed(_gov(vault, p, 3, 2, 1, 0)));
        assertFalse(vault.governancePassed(_gov(vault, p, 0, 0, 0, 0)));
    }
}

