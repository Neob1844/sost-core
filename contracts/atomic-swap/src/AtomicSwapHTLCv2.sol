// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// =============================================================================
// SOST Atomic Swap — EVM counterparty HTLC v2 (weird-ERC20-safe)
// =============================================================================
//
// A versioned successor to AtomicSwapHTLC (v1). Same non-custodial hashlock +
// timelock escrow, same sha256(preimage) primitive and absolute-block timeout,
// no owner/admin/pause/drain. v2 adds SAFE handling of non-standard ERC-20s so
// that USDT-style (no boolean return) and fee-on-transfer tokens (PAXG-style)
// can be escrowed correctly instead of being blacklisted at the UI:
//
//   * _safeTransfer / _safeTransferFrom accept a call that returns true OR
//     returns no data (SafeERC20 semantics); they REVERT on an explicit false
//     return or on a low-level revert.
//   * ERC-20 locks measure the contract's balance delta and record the amount
//     ACTUALLY received (lockedAmount), so a fee-on-transfer token cannot make
//     the escrow claim its face value.
//   * claimERC20 takes a caller-supplied minReceive and reverts (SLIPPAGE) if
//     the claimer's measured balance delta is below it — the claimer is never
//     told they will receive X unless the transfer actually delivers >= X.
//
// v1 is NOT modified and stays deployed/valid; v2 is a separate deployment.
// NOT externally audited. Deploying to any network is an explicit operator step
// requiring gas and credentials NOT stored in this repo.
// =============================================================================

interface IERC20v2 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address who) external view returns (uint256);
}

contract AtomicSwapHTLCv2 {
    enum State { NONE, LOCKED, CLAIMED, REFUNDED }

    struct Swap {
        State   state;
        address token;        // address(0) for native; ERC-20 otherwise
        uint256 requested;    // amount the locker asked to lock
        uint256 lockedAmount; // amount ACTUALLY received by the escrow (fee-aware)
        bytes32 hashlock;     // sha256(preimage)
        uint256 refundTime;   // absolute block.number at which refund opens
        address claimer;
        address refunder;
    }

    mapping(bytes32 => Swap) public swaps;

    event LockCreated(bytes32 indexed swapId, address indexed locker, address token, uint256 requested, uint256 lockedAmount, bytes32 hashlock, uint256 refundTime, address claimer, address refunder);
    event Claimed(bytes32 indexed swapId, bytes32 preimage, address claimer, uint256 delivered);
    event Refunded(bytes32 indexed swapId, address refunder, uint256 returned);

    uint256 private _entered;
    modifier nonReentrant() { require(_entered == 0, "REENTRANT"); _entered = 1; _; _entered = 0; }

    function getSwap(bytes32 swapId) external view returns (Swap memory) { return swaps[swapId]; }

    // ---- safe ERC-20 helpers (accept true OR empty return; revert on false/revert) ----
    function _safeCall(address token, bytes memory data) private {
        (bool ok, bytes memory ret) = token.call(data);
        require(ok, "TOKEN_CALL_FAILED");
        require(ret.length == 0 || abi.decode(ret, (bool)), "TOKEN_RETURNED_FALSE");
    }
    function _safeTransferFrom(address token, address from, address to, uint256 amount) private {
        _safeCall(token, abi.encodeWithSelector(IERC20v2.transferFrom.selector, from, to, amount));
    }
    function _safeTransfer(address token, address to, uint256 amount) private {
        _safeCall(token, abi.encodeWithSelector(IERC20v2.transfer.selector, to, amount));
    }

    // ---- native lock/claim/refund ----
    function lockNative(bytes32 swapId, bytes32 hashlock, uint256 refundTime, address claimer, address refunder) external payable nonReentrant {
        require(swaps[swapId].state == State.NONE, "SWAP_EXISTS");
        require(msg.value > 0, "ZERO_AMOUNT");
        require(refundTime > block.number, "BAD_REFUND_TIME");
        require(claimer != address(0) && refunder != address(0), "BAD_PARTY");
        swaps[swapId] = Swap(State.LOCKED, address(0), msg.value, msg.value, hashlock, refundTime, claimer, refunder);
        emit LockCreated(swapId, msg.sender, address(0), msg.value, msg.value, hashlock, refundTime, claimer, refunder);
    }

    function lockERC20(bytes32 swapId, address token, uint256 amount, bytes32 hashlock, uint256 refundTime, address claimer, address refunder) external nonReentrant {
        require(swaps[swapId].state == State.NONE, "SWAP_EXISTS");
        require(token != address(0), "BAD_TOKEN");
        require(amount > 0, "ZERO_AMOUNT");
        require(refundTime > block.number, "BAD_REFUND_TIME");
        require(claimer != address(0) && refunder != address(0), "BAD_PARTY");
        uint256 before = IERC20v2(token).balanceOf(address(this));
        _safeTransferFrom(token, msg.sender, address(this), amount);
        uint256 received = IERC20v2(token).balanceOf(address(this)) - before;
        require(received > 0, "NOTHING_RECEIVED");
        swaps[swapId] = Swap(State.LOCKED, token, amount, received, hashlock, refundTime, claimer, refunder);
        emit LockCreated(swapId, msg.sender, token, amount, received, hashlock, refundTime, claimer, refunder);
    }

    function _checkClaim(bytes32 swapId, bytes32 preimage) private view returns (Swap storage s) {
        s = swaps[swapId];
        require(s.state == State.LOCKED, "NOT_LOCKED");
        require(block.number < s.refundTime, "EXPIRED");
        require(sha256(abi.encodePacked(preimage)) == s.hashlock, "BAD_PREIMAGE");
    }

    function claimNative(bytes32 swapId, bytes32 preimage) external nonReentrant {
        Swap storage s = _checkClaim(swapId, preimage);
        require(msg.sender == s.claimer, "NOT_CLAIMER");
        uint256 amt = s.lockedAmount; s.state = State.CLAIMED;
        (bool ok, ) = s.claimer.call{value: amt}(""); require(ok, "SEND_FAILED");
        emit Claimed(swapId, preimage, s.claimer, amt);
    }

    // minReceive: the claimer's required minimum measured delivery (fee-on-transfer safety)
    function claimERC20(bytes32 swapId, bytes32 preimage, uint256 minReceive) external nonReentrant {
        Swap storage s = _checkClaim(swapId, preimage);
        require(msg.sender == s.claimer, "NOT_CLAIMER");
        require(s.token != address(0), "NOT_ERC20");
        uint256 amt = s.lockedAmount; s.state = State.CLAIMED;
        uint256 before = IERC20v2(s.token).balanceOf(s.claimer);
        _safeTransfer(s.token, s.claimer, amt);
        uint256 delivered = IERC20v2(s.token).balanceOf(s.claimer) - before;
        require(delivered >= minReceive, "SLIPPAGE");
        emit Claimed(swapId, preimage, s.claimer, delivered);
    }

    function refundNative(bytes32 swapId) external nonReentrant {
        Swap storage s = swaps[swapId];
        require(s.state == State.LOCKED, "NOT_LOCKED");
        require(s.token == address(0), "NOT_NATIVE");
        require(block.number >= s.refundTime, "NOT_YET");
        require(msg.sender == s.refunder, "NOT_REFUNDER");
        uint256 amt = s.lockedAmount; s.state = State.REFUNDED;
        (bool ok, ) = s.refunder.call{value: amt}(""); require(ok, "SEND_FAILED");
        emit Refunded(swapId, s.refunder, amt);
    }

    function refundERC20(bytes32 swapId) external nonReentrant {
        Swap storage s = swaps[swapId];
        require(s.state == State.LOCKED, "NOT_LOCKED");
        require(s.token != address(0), "NOT_ERC20");
        require(block.number >= s.refundTime, "NOT_YET");
        require(msg.sender == s.refunder, "NOT_REFUNDER");
        uint256 amt = s.lockedAmount; s.state = State.REFUNDED;
        _safeTransfer(s.token, s.refunder, amt);
        emit Refunded(swapId, s.refunder, amt);
    }

    receive() external payable { revert("NO_PLAIN_ETH"); }
}
