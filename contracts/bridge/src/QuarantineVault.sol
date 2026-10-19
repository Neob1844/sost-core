// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ReserveBase} from "./ReserveBase.sol";

/// @title Quarantine Vault (C701, development only — NOT deployed)
/// @notice Temporary safe custody for Gold Reserve V2 assets after a critical rescue. It has no
///         deposit function, no withdraw function and no arbitrary destination. Assets leave ONLY
///         through the same final-migration path as the reserve itself (ReserveBase): 4-of-5
///         guardians + passing SOST governance + timelock + a registered successor named in a
///         frozen proposal whose sourceVault is THIS quarantine vault.
contract QuarantineVault is ReserveBase {
    constructor(address[5] memory g, address[] memory registeredAssets, uint64 minTimelock) ReserveBase(g, minTimelock) {
        for (uint256 i = 0; i < registeredAssets.length; i++) {
            assets[registeredAssets[i]] = AssetCfg(true, false);   // registered for migration only; no deposits exist
            emit AssetEnabled(registeredAssets[i], false);
        }
    }
}
