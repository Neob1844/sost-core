// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ReserveBase, IERC20Min} from "./ReserveBase.sol";

/// @title Gold Reserve V2 (C701, development only — NOT deployed)
/// @notice A separate, publicly verifiable reserve of tokenized gold. It never mints SOST or wSOST,
///         is independent of the historical Gold Vault / PoPC / Jackpot reserve and of the Bridge
///         Vault, and has NO arbitrary withdrawal. XAUT is enabled at deployment; PAXG is registered
///         but feature-gated OFF until a legal / availability review enables it (4-of-5).
///
///         Powers (5 guardians):
///           pause            2-of-5   stops deposits and final-migration execution; moves nothing
///           unpause          4-of-5
///           critical rescue  4-of-5 + rescue delay   -> ONLY to the fixed Quarantine Vault
///           final migration  4-of-5 + governance PASS + timelock + registered successor (ReserveBase)
///         C701: the SOST Automated Bridge pays every Gold Access Key straight into this contract
///         (ERC-20 transferFrom user -> reserve inside the mint transaction). The bridge has NO role
///         here: bridge authorizers are not guardians and guardians cannot authorize mints.
///         Guardian recovery (ReserveBase): 4-of-5 + timelock, cancellable by any 2.
contract GoldReserveV2 is ReserveBase {
    uint8 public constant PAUSE_THRESHOLD = 2;
    uint8 public constant UNPAUSE_THRESHOLD = 4;
    uint8 public constant RESCUE_THRESHOLD = 4;
    uint8 public constant ENABLE_THRESHOLD = 4;

    address public immutable quarantineVault;
    uint64 public immutable rescueDelay;

    bool public paused;
    uint256 public pauseEpoch;
    mapping(address => uint256) public rescueEta;
    uint256 public rescueNonce;

    event Contributed(address indexed from, address indexed asset, uint256 amount);
    event Paused(uint256 epoch);
    event Unpaused(uint256 epoch);
    event RescueQueued(address indexed asset, uint256 eta, uint256 nonce);
    event RescuedToQuarantine(address indexed asset, address indexed quarantineVault, uint256 amount);

    error IsPaused();
    error ZeroAmount();
    error RescueNotQueued();
    error RescueDelayNotExpired();
    error BadQuarantine();

    constructor(address[5] memory g, address quarantine, address xaut, address paxg, uint64 minTimelock, uint64 rescueDelay_)
        ReserveBase(g, minTimelock)
    {
        if (quarantine == address(0) || quarantine == address(this)) revert BadQuarantine();
        quarantineVault = quarantine;
        rescueDelay = rescueDelay_;
        if (xaut != address(0)) { assets[xaut] = AssetCfg(true, true); emit AssetEnabled(xaut, true); }
        if (paxg != address(0)) { assets[paxg] = AssetCfg(true, false); emit AssetEnabled(paxg, false); }
    }

    // ------------------------------------------------------------------ contributions
    /// @notice Permanent contribution of an enabled gold asset. Confers no claim on the reserve.
    function contribute(address asset, uint256 amount) external {
        if (paused) revert IsPaused();
        AssetCfg memory a = assets[asset];
        if (!a.registered || !a.enabled) revert AssetNotAllowed();
        if (amount == 0) revert ZeroAmount();
        uint256 before = IERC20Min(asset).balanceOf(address(this));
        (bool ok, bytes memory ret) = asset.call(abi.encodeWithSelector(IERC20Min.transferFrom.selector, msg.sender, address(this), amount));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed();
        uint256 received = IERC20Min(asset).balanceOf(address(this)) - before;   // fee-on-transfer safe
        emit Contributed(msg.sender, asset, received);
    }

    // ------------------------------------------------------------------ asset gate
    function enableAssetAction(address asset, bool enabled) public pure returns (bytes32) {
        return keccak256(abi.encode("ENABLE_ASSET", asset, enabled));
    }

    function setAssetEnabled(address asset, bool enabled) external {
        if (!assets[asset].registered) revert AssetNotAllowed();
        _consume(enableAssetAction(asset, enabled), ENABLE_THRESHOLD);
        assets[asset].enabled = enabled;
        emit AssetEnabled(asset, enabled);
    }

    // ------------------------------------------------------------------ pause (moves nothing)
    function pauseAction() public view returns (bytes32) {
        return keccak256(abi.encode("PAUSE", address(this), pauseEpoch));
    }

    function unpauseAction() public view returns (bytes32) {
        return keccak256(abi.encode("UNPAUSE", address(this), pauseEpoch));
    }

    function pause() external {
        _consume(pauseAction(), PAUSE_THRESHOLD);
        paused = true;
        emit Paused(pauseEpoch);
    }

    function unpause() external {
        _consume(unpauseAction(), UNPAUSE_THRESHOLD);
        paused = false;
        emit Unpaused(pauseEpoch);
        pauseEpoch += 1;            // fresh action ids for the next pause/unpause cycle
    }

    // ------------------------------------------------------------------ critical rescue -> quarantine only
    function rescueAction(address asset) public view returns (bytes32) {
        return keccak256(abi.encode("RESCUE", address(this), asset, rescueNonce));
    }

    function queueRescue(address asset) external {
        if (!assets[asset].registered) revert AssetNotAllowed();
        _consume(rescueAction(asset), RESCUE_THRESHOLD);
        rescueNonce += 1;
        uint256 eta = block.timestamp + rescueDelay;
        rescueEta[asset] = eta;
        emit RescueQueued(asset, eta, rescueNonce);
    }

    /// @notice Moves the whole balance of `asset` to the fixed Quarantine Vault. No destination parameter.
    ///         Works while paused (a rescue is exactly what a pause buys time for).
    function executeRescue(address asset) external {
        uint256 eta = rescueEta[asset];
        if (eta == 0) revert RescueNotQueued();
        if (block.timestamp < eta) revert RescueDelayNotExpired();
        rescueEta[asset] = 0;
        uint256 amount = IERC20Min(asset).balanceOf(address(this));
        _safeTransfer(asset, quarantineVault, amount);
        emit RescuedToQuarantine(asset, quarantineVault, amount);
    }

    function _beforeMigrationExecute() internal view override {
        if (paused) revert IsPaused();
    }
}
