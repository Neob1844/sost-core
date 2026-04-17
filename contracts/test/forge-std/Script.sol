// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// ============================================================================
// Minimal forge-std Script stub
//
// This file provides just enough of the forge-std Script interface to make
// deployment scripts compile.  When running real deployments, install forge-std
// properly with `forge install foundry-rs/forge-std` and delete this stub.
// ============================================================================

import "./Test.sol";

abstract contract Script {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
}
