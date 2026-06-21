// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// =============================================================================
// SOST Atomic Swap — EVM counterparty HTLC contract (Phase 4B-1)
// =============================================================================
//
// Non-custodial Hashed Time-Locked Contract for SOST <-> EVM atomic swaps
// in the Community OTC / P2P Board flow. Holds funds in escrow under a
// hashlock + timelock; releases either to the claimer on preimage reveal
// (before timeout) or back to the refunder after timeout. No owner, no
// admin, no upgrade path, no pause, no emergency drain, no privileged
// role. The contract IS the escrow — there is no operator.
//
// Hashlock primitive: sha256(preimage). Matches the SOST consensus
// validator (src/tx_validation.cpp R21) and the BTC redeem-script
// builder (BIP-199-style OP_SHA256). A preimage that satisfies the
// SOST CLAIM also satisfies this EVM CLAIM and vice versa.
//
// Timeout primitive: absolute block.number (not block.timestamp). The
// SOST refund_height (T1) MUST exceed this contract's refundTime (T2)
// by a wallet-enforced safety margin so the responder cannot claim
// the SOST side after refunding here. The contract does NOT verify
// the cross-chain timeout ordering — that is the wallet's job.
//
// Supported assets:
//   - native chain currency: ETH (Ethereum), BNB (BNB Chain) — pass
//     token = address(0).
//   - ERC-20 tokens: USDT, USDC, PAXG, XAUT (and any other compliant
//     ERC-20). The contract is asset-agnostic.
//
// ISSUER-RISK WARNING for USDT / USDC / PAXG / XAUT: the token issuer
// (Tether / Circle / Paxos / TG Commodities) can freeze any address
// including this contract's balance. If a freeze happens mid-swap the
// SOST side still refunds correctly (cryptographic atomicity holds on
// the SOST chain) but the EVM side becomes uncollectible until the
// issuer unfreezes. The UI MUST surface this risk to users.
//
// AUDIT / DEPLOY STATUS: this contract has NOT been externally audited.
// The SOST-side activation gate (ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT in
// include/sost/atomic_swap.h) is now V14_HEIGHT (block 15,000): the
// EVM-only atomic swap is enabled at V14 for FOUNDER-ONLY use, at the
// founder's own risk, with no public or audited guarantee. SOST<->BTC is
// deferred to V15 (BTC HTLC signing is not active). Deploying this
// contract to any mainnet/testnet is a separate, explicit founder action;
// the web console refuses to operate against an unset contract address.
// ERC-20 weird-token handling (no-bool return, fee-on-transfer) is
// intentionally out of scope of this minimal HTLC and MUST be enforced by
// the wallet/UI (native-first; fee-on-transfer tokens blacklisted) — see
// docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md.
//
// =============================================================================

/// Minimal IERC20 interface — no full SafeERC20 dependency.
interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract AtomicSwapHTLC {
    // -------------------------------------------------------------------------
    // State machine
    // -------------------------------------------------------------------------

    enum State { NONE, LOCKED, CLAIMED, REFUNDED }

    struct Swap {
        State    state;       // current state of this swap
        address  token;       // address(0) for native ETH/BNB; ERC-20 otherwise
        uint256  amount;      // locked amount in native units or ERC-20 units
        bytes32  hashlock;    // sha256(preimage); 32 bytes
        uint256  refundTime;  // absolute block.number at which refund opens
        address  claimer;     // entitled to claim with preimage before refundTime
        address  refunder;    // entitled to refund at/after refundTime
    }

    /// All swaps keyed by caller-supplied swapId. Public getter is
    /// generated automatically; getSwap() provides the named struct.
    mapping(bytes32 => Swap) public swaps;

    // -------------------------------------------------------------------------
    // Events
    // -------------------------------------------------------------------------

    event LockCreated(
        bytes32 indexed swapId,
        address indexed locker,
        address          token,
        uint256          amount,
        bytes32          hashlock,
        uint256          refundTime,
        address          claimer,
        address          refunder
    );
    event Claimed(bytes32 indexed swapId, bytes32 preimage, address claimer);
    event Refunded(bytes32 indexed swapId, address refunder);

    // -------------------------------------------------------------------------
    // Reentrancy guard (no external dep)
    // -------------------------------------------------------------------------

    uint256 private _entered;
    modifier nonReentrant() {
        require(_entered == 0, "REENTRANT");
        _entered = 1;
        _;
        _entered = 0;
    }

    // -------------------------------------------------------------------------
    // Read-only helper
    // -------------------------------------------------------------------------

    function getSwap(bytes32 swapId) external view returns (Swap memory) {
        return swaps[swapId];
    }

    // -------------------------------------------------------------------------
    // Lock — native (ETH on Ethereum, BNB on BNB Chain)
    // -------------------------------------------------------------------------
    //
    // The caller sends ETH/BNB along with the call (msg.value > 0). The
    // funds enter the contract's escrow and remain there until either
    // claim() reveals the preimage (before refundTime) or refund() is
    // triggered (at/after refundTime). No third party can move the funds.

    function lockNative(
        bytes32 swapId,
        bytes32 hashlock,
        uint256 refundTime,
        address claimer,
        address refunder
    ) external payable nonReentrant {
        require(msg.value > 0,                    "ZERO_AMOUNT");
        require(claimer != address(0),            "ZERO_CLAIMER");
        require(refunder != address(0),           "ZERO_REFUNDER");
        require(refundTime > block.number,        "REFUND_IN_PAST");
        require(swaps[swapId].state == State.NONE, "DUPLICATE_SWAP_ID");

        swaps[swapId] = Swap({
            state:      State.LOCKED,
            token:      address(0),
            amount:     msg.value,
            hashlock:   hashlock,
            refundTime: refundTime,
            claimer:    claimer,
            refunder:   refunder
        });

        emit LockCreated(swapId, msg.sender, address(0), msg.value,
                         hashlock, refundTime, claimer, refunder);
    }

    // -------------------------------------------------------------------------
    // Lock — ERC-20 (USDT, USDC, PAXG, XAUT, or any compliant ERC-20)
    // -------------------------------------------------------------------------
    //
    // Caller MUST have approved this contract for at least `amount` of
    // `token` before calling lockERC20. The contract uses transferFrom
    // to pull the funds into escrow. The transferFrom return value is
    // checked; tokens that return false on failure (e.g. some USDT
    // variants) are rejected at lock time rather than silently leaving
    // the swap in an inconsistent state.

    function lockERC20(
        bytes32 swapId,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 refundTime,
        address claimer,
        address refunder
    ) external nonReentrant {
        require(token    != address(0),           "ZERO_TOKEN");
        require(amount    > 0,                    "ZERO_AMOUNT");
        require(claimer  != address(0),           "ZERO_CLAIMER");
        require(refunder != address(0),           "ZERO_REFUNDER");
        require(refundTime > block.number,        "REFUND_IN_PAST");
        require(swaps[swapId].state == State.NONE, "DUPLICATE_SWAP_ID");

        // Effects: record the swap BEFORE the external transferFrom call
        // (checks-effects-interactions).
        swaps[swapId] = Swap({
            state:      State.LOCKED,
            token:      token,
            amount:     amount,
            hashlock:   hashlock,
            refundTime: refundTime,
            claimer:    claimer,
            refunder:   refunder
        });

        // Interaction.
        bool ok = IERC20(token).transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FAILED");

        emit LockCreated(swapId, msg.sender, token, amount,
                         hashlock, refundTime, claimer, refunder);
    }

    // -------------------------------------------------------------------------
    // Claim — anyone with the preimage can trigger; funds go to swap.claimer
    // -------------------------------------------------------------------------
    //
    // Validates sha256(preimage) == hashlock AND block.number < refundTime
    // AND state == LOCKED. State is transitioned to CLAIMED BEFORE the
    // external transfer (checks-effects-interactions). Reentrancy is
    // additionally blocked by the nonReentrant modifier and by the
    // state-machine guard (the second call would find state == CLAIMED
    // and revert at NOT_LOCKED).

    function claim(bytes32 swapId, bytes32 preimage) external nonReentrant {
        Swap storage s = swaps[swapId];
        require(s.state == State.LOCKED,                              "NOT_LOCKED");
        require(block.number < s.refundTime,                          "TIMEOUT_PASSED");
        require(sha256(abi.encodePacked(preimage)) == s.hashlock,     "WRONG_PREIMAGE");

        // Effects
        s.state = State.CLAIMED;
        address payable to = payable(s.claimer);
        uint256 amt = s.amount;
        address tok = s.token;

        // Interaction
        if (tok == address(0)) {
            (bool ok, ) = to.call{value: amt}("");
            require(ok, "TRANSFER_FAILED");
        } else {
            bool ok = IERC20(tok).transfer(to, amt);
            require(ok, "TRANSFER_FAILED");
        }

        emit Claimed(swapId, preimage, to);
    }

    // -------------------------------------------------------------------------
    // Refund — anyone can trigger after refundTime; funds go to swap.refunder
    // -------------------------------------------------------------------------

    function refund(bytes32 swapId) external nonReentrant {
        Swap storage s = swaps[swapId];
        require(s.state == State.LOCKED,         "NOT_LOCKED");
        require(block.number >= s.refundTime,    "TIMEOUT_NOT_REACHED");

        // Effects
        s.state = State.REFUNDED;
        address payable to = payable(s.refunder);
        uint256 amt = s.amount;
        address tok = s.token;

        // Interaction
        if (tok == address(0)) {
            (bool ok, ) = to.call{value: amt}("");
            require(ok, "TRANSFER_FAILED");
        } else {
            bool ok = IERC20(tok).transfer(to, amt);
            require(ok, "TRANSFER_FAILED");
        }

        emit Refunded(swapId, to);
    }

    // -------------------------------------------------------------------------
    // Receive — reject plain transfers to prevent accidental fund loss
    // -------------------------------------------------------------------------
    //
    // Native ETH/BNB enters this contract ONLY via lockNative(). Any
    // plain transfer (sending ETH to the contract address without a
    // function call) is rejected. This prevents a class of fund-loss
    // bugs where a user mistakes the contract address for a wallet.

    receive() external payable {
        revert("DIRECT_TRANSFER_REJECTED");
    }

    fallback() external payable {
        revert("UNKNOWN_CALLDATA");
    }
}
