// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

interface IERC20Min {
    function balanceOf(address) external view returns (uint256);
    function transfer(address to, uint256 v) external returns (bool);
    function transferFrom(address from, address to, uint256 v) external returns (bool);
}

/// @title ReserveBase — shared rules of Gold Reserve V2 and its Quarantine Vault (C701, development only)
/// @notice There is NO withdraw(address) and no function that accepts an arbitrary destination.
///         Assets can leave only by (a) a guardian rescue to the vault's fixed Quarantine Vault
///         (GoldReserveVault only) or (b) a final migration to the EXACT successor vault named in a
///         frozen proposal, approved by 4-of-5 guardians, carrying a passing SOST governance result
///         (YES >= ceil(2/3 x full census)), after the proposal timelock, to a successor whose runtime
///         code hash was registered in advance.
/// @dev    What is enforced on Ethereum: guardian thresholds, frozen proposal hash, the 2/3-of-census
///         arithmetic on the submitted result, timelock, registered successor code hash, no EOA.
///         What is verified OFF-chain: that the submitted governance result really is the canonical
///         SOST tally (Ethereum cannot read SOST). Guardians attest it; anyone can recount it.
abstract contract ReserveBase {
    uint8 public constant GUARDIANS = 5;
    uint8 public constant MIGRATE_THRESHOLD = 4;
    uint8 public constant REGISTER_THRESHOLD = 4;
    uint32 public constant PROPOSAL_VERSION = 1;

    address[5] public guardians;
    mapping(address => bool) public isGuardian;
    uint64 public immutable minMigrationTimelock;

    mapping(bytes32 => mapping(address => bool)) public approvedBy;
    mapping(bytes32 => uint8) public approvals;
    mapping(bytes32 => bool) public consumed;

    struct AssetCfg { bool registered; bool enabled; }
    mapping(address => AssetCfg) public assets;

    mapping(address => bytes32) public successorCodeHash;   // registered successor vault -> runtime code hash

    struct Proposal {
        bytes32 proposalId;
        address sourceVault;
        address sourceAsset;
        address successorVault;
        address successorAsset;
        bytes32 successorCodeHash;
        uint64 snapshotHeight;
        uint64 closeHeight;
        uint64 timelock;          // seconds after queueing
        bytes32 reasonHash;
        uint32 version;
    }

    struct GovResult {
        bytes32 proposalHash;
        uint32 census;            // eligible identities fixed at the snapshot
        uint32 yes;
        uint32 no;
        uint32 abstain;
        uint64 finalHeight;       // SOST height at which the result became final
        bytes32 tallyHash;        // hash of the full canonical tally (per-identity votes)
    }

    mapping(bytes32 => uint256) public migrationEta;   // proposalHash -> earliest execution time
    mapping(bytes32 => bool) public migrationExecuted;

    event Approved(bytes32 indexed actionId, address indexed guardian, uint8 approvals);
    event ApprovalRevoked(bytes32 indexed actionId, address indexed guardian, uint8 approvals);
    event SuccessorRegistered(address indexed vault, bytes32 codeHash);
    event AssetEnabled(address indexed asset, bool enabled);
    event MigrationQueued(bytes32 indexed proposalHash, bytes32 proposalId, address successorVault, uint256 eta, bytes32 tallyHash);
    event MigrationExecuted(bytes32 indexed proposalHash, address indexed asset, address indexed successorVault, uint256 amount);

    error NotGuardian();
    error BadGuardians();
    error NotApproved();
    error AlreadyConsumed();
    error BadProposal();
    error GovernanceFailed();
    error SuccessorNotRegistered();
    error SuccessorCodeMismatch();
    error TimelockNotExpired();
    error NotQueued();
    error AssetNotAllowed();
    error TransferFailed();

    modifier onlyGuardian() {
        if (!isGuardian[msg.sender]) revert NotGuardian();
        _;
    }

    constructor(address[5] memory g, uint64 minTimelock) {
        for (uint256 i = 0; i < 5; i++) {
            if (g[i] == address(0) || isGuardian[g[i]]) revert BadGuardians();
            isGuardian[g[i]] = true;
            guardians[i] = g[i];
        }
        minMigrationTimelock = minTimelock;
    }

    // ------------------------------------------------------------------ guardian approvals
    function approve(bytes32 actionId) external onlyGuardian {
        if (consumed[actionId]) revert AlreadyConsumed();
        if (!approvedBy[actionId][msg.sender]) {
            approvedBy[actionId][msg.sender] = true;
            approvals[actionId] += 1;
        }
        emit Approved(actionId, msg.sender, approvals[actionId]);
    }

    function revoke(bytes32 actionId) external onlyGuardian {
        if (approvedBy[actionId][msg.sender]) {
            approvedBy[actionId][msg.sender] = false;
            approvals[actionId] -= 1;
        }
        emit ApprovalRevoked(actionId, msg.sender, approvals[actionId]);
    }

    /// @dev C701 audit fix: approvals are RE-COUNTED over the CURRENT guardian set at consumption
    ///      time, so an approval left by a guardian that was later rotated out never counts.
    function _consume(bytes32 actionId, uint8 needed) internal {
        if (consumed[actionId]) revert AlreadyConsumed();
        if (liveApprovals(actionId) < needed) revert NotApproved();
        consumed[actionId] = true;
    }

    function liveApprovals(bytes32 actionId) public view returns (uint8 n) {
        for (uint256 i = 0; i < 5; i++) {
            if (approvedBy[actionId][guardians[i]]) n++;
        }
    }

    // ------------------------------------------------------------------ guardian recovery (extraordinary)
    /// Replacing a lost or compromised guardian: 4-of-5 approvals, then a long fixed delay during
    /// which ANY 2 guardians can cancel. Rotation never moves assets and never changes thresholds.
    uint8 public constant ROTATE_THRESHOLD = 4;
    uint8 public constant ROTATE_CANCEL_THRESHOLD = 2;
    uint256 public rotationNonce;
    struct Rotation { uint8 index; address oldGuardian; address newGuardian; uint256 eta; }
    mapping(uint256 => Rotation) public rotations;   // nonce -> queued rotation

    event GuardianRotationQueued(uint256 indexed nonce, uint8 index, address oldGuardian, address newGuardian, uint256 eta);
    event GuardianRotationCancelled(uint256 indexed nonce);
    event GuardianRotated(uint256 indexed nonce, uint8 index, address oldGuardian, address newGuardian);

    error RotationNotReady();

    function rotateAction(uint8 index, address oldG, address newG, uint256 nonce) public view returns (bytes32) {
        return keccak256(abi.encode("ROTATE_GUARDIAN", address(this), index, oldG, newG, nonce));
    }

    function cancelRotationAction(uint256 nonce) public view returns (bytes32) {
        return keccak256(abi.encode("CANCEL_ROTATION", address(this), nonce));
    }

    function queueGuardianRotation(uint8 index, address newG) external {
        if (index >= 5 || newG == address(0) || isGuardian[newG]) revert BadGuardians();
        address oldG = guardians[index];
        uint256 n = rotationNonce;
        _consume(rotateAction(index, oldG, newG, n), ROTATE_THRESHOLD);
        rotationNonce = n + 1;
        uint256 eta = block.timestamp + minMigrationTimelock;     // same floor as a final migration
        rotations[n] = Rotation(index, oldG, newG, eta);
        emit GuardianRotationQueued(n, index, oldG, newG, eta);
    }

    function cancelGuardianRotation(uint256 nonce) external {
        if (rotations[nonce].eta == 0) revert RotationNotReady();
        _consume(cancelRotationAction(nonce), ROTATE_CANCEL_THRESHOLD);
        delete rotations[nonce];
        emit GuardianRotationCancelled(nonce);
    }

    function executeGuardianRotation(uint256 nonce) external {
        Rotation memory r = rotations[nonce];
        if (r.eta == 0 || block.timestamp < r.eta) revert RotationNotReady();
        if (guardians[r.index] != r.oldGuardian || isGuardian[r.newGuardian]) revert BadGuardians();
        delete rotations[nonce];
        isGuardian[r.oldGuardian] = false;
        isGuardian[r.newGuardian] = true;
        guardians[r.index] = r.newGuardian;
        emit GuardianRotated(nonce, r.index, r.oldGuardian, r.newGuardian);
    }

    // ------------------------------------------------------------------ successor registry
    function registerSuccessorAction(address vault, bytes32 codeHash) public pure returns (bytes32) {
        return keccak256(abi.encode("REGISTER_SUCCESSOR", vault, codeHash));
    }

    /// @notice Register a successor reserve vault by its exact runtime code hash (4-of-5).
    function registerSuccessor(address vault, bytes32 codeHash) external {
        _consume(registerSuccessorAction(vault, codeHash), REGISTER_THRESHOLD);
        if (vault == address(this) || vault.code.length == 0 || vault.codehash != codeHash) revert SuccessorCodeMismatch();
        successorCodeHash[vault] = codeHash;
        emit SuccessorRegistered(vault, codeHash);
    }

    // ------------------------------------------------------------------ frozen proposals
    function proposalHash(Proposal calldata p) public pure returns (bytes32) {
        return keccak256(abi.encode(
            "SOSTGOV1-GRV2-MIGRATION", p.proposalId, p.sourceVault, p.sourceAsset, p.successorVault,
            p.successorAsset, p.successorCodeHash, p.snapshotHeight, p.closeHeight, p.timelock, p.reasonHash, p.version
        ));
    }

    function migrationAction(bytes32 pHash, bytes32 tallyHash) public pure returns (bytes32) {
        return keccak256(abi.encode("MIGRATE", pHash, tallyHash));
    }

    /// @notice YES must reach ceil(2/3 of the FULL census) — not of the votes cast. ABSTAIN is never YES.
    function governancePassed(GovResult calldata g) public pure returns (bool) {
        if (g.census == 0) return false;
        if (uint256(g.yes) + g.no + g.abstain > g.census) return false;
        return uint256(g.yes) * 3 >= uint256(g.census) * 2;
    }

    function queueMigration(Proposal calldata p, GovResult calldata g) external {
        bytes32 ph = proposalHash(p);
        if (p.version != PROPOSAL_VERSION || p.sourceVault != address(this) || p.timelock < minMigrationTimelock
            || p.closeHeight <= p.snapshotHeight || g.finalHeight <= p.closeHeight) revert BadProposal();
        if (g.proposalHash != ph) revert BadProposal();
        if (!governancePassed(g)) revert GovernanceFailed();
        if (successorCodeHash[p.successorVault] == bytes32(0)) revert SuccessorNotRegistered();
        if (successorCodeHash[p.successorVault] != p.successorCodeHash) revert SuccessorCodeMismatch();
        if (!assets[p.sourceAsset].registered) revert AssetNotAllowed();
        if (migrationEta[ph] != 0 || migrationExecuted[ph]) revert AlreadyConsumed();
        _consume(migrationAction(ph, g.tallyHash), MIGRATE_THRESHOLD);
        uint256 eta = block.timestamp + p.timelock;
        migrationEta[ph] = eta;
        emit MigrationQueued(ph, p.proposalId, p.successorVault, eta, g.tallyHash);
    }

    function executeMigration(Proposal calldata p) external {
        bytes32 ph = proposalHash(p);
        uint256 eta = migrationEta[ph];
        if (eta == 0) revert NotQueued();
        if (migrationExecuted[ph]) revert AlreadyConsumed();
        if (block.timestamp < eta) revert TimelockNotExpired();
        _beforeMigrationExecute();
        // re-check the successor at execution time: code must still be exactly the registered one
        if (p.successorVault.code.length == 0 || p.successorVault.codehash != p.successorCodeHash
            || successorCodeHash[p.successorVault] != p.successorCodeHash) revert SuccessorCodeMismatch();
        migrationExecuted[ph] = true;
        uint256 amount = IERC20Min(p.sourceAsset).balanceOf(address(this));
        _safeTransfer(p.sourceAsset, p.successorVault, amount);
        emit MigrationExecuted(ph, p.sourceAsset, p.successorVault, amount);
    }

    function _beforeMigrationExecute() internal view virtual {}

    function _safeTransfer(address token, address to, uint256 amount) internal {
        if (amount == 0) return;
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSelector(IERC20Min.transfer.selector, to, amount));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed();
    }

    function guardianList() external view returns (address[5] memory) {
        return guardians;
    }
}
