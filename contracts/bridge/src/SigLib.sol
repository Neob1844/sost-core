// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice Minimal ECDSA recovery with malleability protection (low-s, v in {27,28}).
library SigLib {
    error BadSignature();

    uint256 private constant HALF_N =
        0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    function recover(bytes32 digest, bytes calldata sig) internal pure returns (address signer) {
        if (sig.length != 65) revert BadSignature();
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (uint256(s) > HALF_N) revert BadSignature();
        if (v != 27 && v != 28) revert BadSignature();
        signer = ecrecover(digest, v, r, s);
        if (signer == address(0)) revert BadSignature();
    }
}
