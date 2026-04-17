// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Reentrancy Guard
/// @dev Prevents reentrant calls to functions marked `nonReentrant`.
///      Based on OpenZeppelin's ReentrancyGuard v5.0 (simplified).
///      Uses transient storage where available (EIP-1153, Cancun+),
///      falls back to regular storage for pre-Cancun chains.
///
///      Why inline instead of importing OpenZeppelin?
///      SOSTEscrow is designed to be fully self-contained with zero
///      external dependencies. Every line of deployed bytecode is
///      auditable in this repository. No npm, no remappings, no
///      version drift risk.
abstract contract ReentrancyGuard {
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;

    uint256 private _status;

    constructor() {
        _status = _NOT_ENTERED;
    }

    modifier nonReentrant() {
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }
}
