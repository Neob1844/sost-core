// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// ============================================================================
// Minimal forge-std stub
//
// This file provides just enough of the forge-std Test interface to make
// SOSTEscrow.t.sol compile.  When running real tests, install forge-std
// properly with `forge install foundry-rs/forge-std` and delete this stub.
// ============================================================================

// Vm cheatcode interface — only the methods our tests use
interface Vm {
    function prank(address msgSender) external;
    function startPrank(address msgSender) external;
    function stopPrank() external;
    function warp(uint256 newTimestamp) external;
    function expectRevert() external;
    function expectRevert(bytes calldata revertData) external;
    function expectEmit(bool checkTopic1, bool checkTopic2, bool checkTopic3, bool checkData) external;
    function envUint(string calldata name) external view returns (uint256);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
    function addr(uint256 privateKey) external pure returns (address);
}

// console.log support
library console {
    address constant CONSOLE_ADDRESS = 0x000000000000000000636F6e736F6c652e6c6f67;

    function log(string memory s) internal pure {
        (bool ignored,) = CONSOLE_ADDRESS.staticcall(abi.encodeWithSignature("log(string)", s));
        ignored;
    }

    function log(string memory s, address a) internal pure {
        (bool ignored,) = CONSOLE_ADDRESS.staticcall(abi.encodeWithSignature("log(string,address)", s, a));
        ignored;
    }

    function log(string memory s, uint256 n) internal pure {
        (bool ignored,) = CONSOLE_ADDRESS.staticcall(abi.encodeWithSignature("log(string,uint256)", s, n));
        ignored;
    }
}

// Base test contract
abstract contract Test {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    // Assertion helpers
    function assertTrue(bool condition) internal pure {
        require(condition, "assertion failed: expected true");
    }

    function assertFalse(bool condition) internal pure {
        require(!condition, "assertion failed: expected false");
    }

    function assertEq(uint256 a, uint256 b) internal pure {
        require(a == b, "assertion failed: uint256 not equal");
    }

    function assertEq(address a, address b) internal pure {
        require(a == b, "assertion failed: address not equal");
    }

    function assertEq(bool a, bool b) internal pure {
        require(a == b, "assertion failed: bool not equal");
    }

    function assertEq(bytes32 a, bytes32 b) internal pure {
        require(a == b, "assertion failed: bytes32 not equal");
    }

    // makeAddr helper
    function makeAddr(string memory name) internal pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encodePacked(name)))));
    }
}
