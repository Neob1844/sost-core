// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// =============================================================================
// SOST Atomic Swap — EVM counterparty HTLC contract (Phase 4B-1 / 4D-safe-erc20)
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
// the cross-chain timeout ordering — that is the wallet's job (see the
// canonical policy in src/atomic_swap_policy.cpp::EvaluateTimeoutOrder).
//
// swapId collision-resistance (anti-squatting): the swapId is caller-
// supplied, so a naive fixed id (e.g. keccak("swap-1")) can be
// FRONT-RUN — an attacker locks a dust swap under the victim's intended
// id, causing the victim's lock to revert DUPLICATE_SWAP_ID (a griefing
// DoS). Wallets MUST derive the swapId from computeSwapId(...) below,
// which binds it to the participants, token, amount, hashlock, refundTime
// and a locally-random 32-byte nonce that is NOT revealed before the
// lock is broadcast. An attacker cannot reproduce the id without the
// nonce, and reproducing the exact tuple would only lock THEIR funds to
// the victim's benefit — so squatting is defeated. The C++ coordinator
// mirrors this derivation bit-for-bit in DeriveSwapId(...).
//
// Supported assets:
//   - native chain currency: ETH (Ethereum), BNB (BNB Chain) — pass
//     token = address(0).
//   - ERC-20 tokens: USDT, USDC, PAXG, XAUT (and any other compliant
//     ERC-20). The contract is asset-agnostic and uses a SafeERC20-style
//     path (below) that tolerates the two most common real-world quirks:
//       (a) no-bool-return tokens (legacy USDT): accepted (empty return
//           data is treated as success, non-empty is decoded and must be
//           true), and
//       (b) fee-on-transfer / rebasing tokens (e.g. PAXG when its transfer
//           fee is non-zero): lockERC20 records the ACTUAL amount received
//           via a balanceOf delta, so claim/refund always pay out exactly
//           what the escrow holds and never revert on a balance shortfall.
//     Tokens that actively return false on failure are still rejected.
//
// ISSUER-RISK WARNING for USDT / USDC / PAXG / XAUT: the token issuer
// (Tether / Circle / Paxos / TG Commodities) can freeze any address
// including this contract's balance. If a freeze happens mid-swap the
// SOST side still refunds correctly (cryptographic atomicity holds on
// the SOST chain) but the EVM side becomes uncollectible until the
// issuer unfreezes. The UI MUST surface this risk to users.
//
// AUDIT / DEPLOY STATUS: this contract has NOT been externally audited.
// The SafeERC20 path and balance-delta accounting added here are standard,
// well-understood patterns but MUST still be reviewed before any mainnet
// deployment. The SOST-side activation gate
// (ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT in include/sost/atomic_swap.h) is
// V14.5: the EVM-only atomic swap is enabled for FOUNDER-ONLY use, at the
// founder's own risk, with no public or audited guarantee. SOST<->BTC is
// deferred to V15 (BTC HTLC signing is not active). Deploying this contract
// to any mainnet/testnet is a separate, explicit founder action; the web
// console refuses to operate against an unset contract address.
//
// =============================================================================

/// Minimal IERC20 interface — no full SafeERC20 dependency. `balanceOf`
/// is used for fee-on-transfer-safe delta accounting; transfer/transferFrom
/// are declared `returns (bool)` but the SafeERC20 path below also tolerates
/// tokens that return nothing (legacy USDT).
interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract AtomicSwapHTLC {
    // -------------------------------------------------------------------------
    // State machine
    // -------------------------------------------------------------------------

    enum State { NONE, LOCKED, CLAIMED, REFUNDED }

    struct Swap {
        State    state;       // current state of this swap
        address  token;       // address(0) for native ETH/BNB; ERC-20 otherwise
        uint256  amount;      // escrowed amount ACTUALLY held (post-fee for FoT)
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
    // Read-only helpers
    // -------------------------------------------------------------------------

    function getSwap(bytes32 swapId) external view returns (Swap memory) {
        return swaps[swapId];
    }

    /// Collision-resistant swapId derivation (anti-squatting). Pure; wallets
    /// call this off-chain (or on-chain) to obtain the id they then pass to
    /// lockNative/lockERC20. The `nonce` MUST be a locally-random 32 bytes
    /// kept secret until the lock is broadcast — this is what prevents an
    /// attacker from pre-registering (front-running) the id. Uses sha256 so
    /// the derivation is bit-identical to the SOST-side DeriveSwapId(...)
    /// (sha256 is the shared hashlock primitive across both chains).
    ///
    ///   chainId : this contract's chain id (1 = Ethereum, 56 = BNB, ...);
    ///             binds the id to the chain so the same tuple on two chains
    ///             yields two distinct ids.
    ///   token   : address(0) for native, ERC-20 address otherwise (binds asset).
    function computeSwapId(
        address locker,
        address claimer,
        address refunder,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 refundTime,
        uint256 chainId,
        bytes32 nonce
    ) public pure returns (bytes32) {
        return sha256(abi.encodePacked(
            "SOST-ATOMIC-SWAP-ID-v1",
            locker, claimer, refunder, token,
            amount, hashlock, refundTime, chainId, nonce
        ));
    }

    // -------------------------------------------------------------------------
    // SafeERC20-style internal transfer helpers
    // -------------------------------------------------------------------------
    //
    // Tolerates no-bool-return tokens (legacy USDT) and rejects tokens that
    // return false. Bubbles the underlying revert reason on a hard failure
    // (so e.g. an inner REENTRANT / BAL / ALLOW surfaces unchanged), and
    // otherwise reverts with "TRANSFER_FAILED".

    function _callOptionalReturn(address token, bytes memory data) private {
        (bool success, bytes memory ret) = token.call(data);
        if (!success) {
            // Bubble the inner revert reason verbatim when present.
            if (ret.length > 0) {
                assembly {
                    revert(add(32, ret), mload(ret))
                }
            }
            revert("TRANSFER_FAILED");
        }
        // Non-empty return data must decode to true; empty data (legacy
        // USDT) is treated as success.
        if (ret.length > 0) {
            require(abi.decode(ret, (bool)), "TRANSFER_FAILED");
        }
    }

    function _safeTransfer(address token, address to, uint256 amount) private {
        _callOptionalReturn(token, abi.encodeWithSelector(IERC20.transfer.selector, to, amount));
    }

    function _safeTransferFrom(address token, address from, address to, uint256 amount) private {
        _callOptionalReturn(token, abi.encodeWithSelector(IERC20.transferFrom.selector, from, to, amount));
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
    // `token` before calling lockERC20. The contract pulls the funds via a
    // SafeERC20-style transferFrom and records the ACTUAL amount received
    // (measured with a balanceOf delta). This makes the escrow correct for
    // fee-on-transfer / rebasing tokens: claim/refund always pay out exactly
    // what is held, never reverting on a balance shortfall. Tokens that
    // return false are rejected; no-bool-return tokens are accepted.
    //
    // NOTE ON ORDERING: the swap struct is written AFTER the external
    // transferFrom (we can only learn the received amount post-transfer).
    // This is safe because (a) the global nonReentrant mutex blocks any
    // re-entry into lock/claim/refund during the transfer, and (b) the
    // state==NONE / DUPLICATE_SWAP_ID guard is evaluated BEFORE the transfer,
    // so an existing swap can never be overwritten.

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

        // Interaction (guarded by nonReentrant): pull funds and measure the
        // actual amount that landed in escrow.
        uint256 balBefore = IERC20(token).balanceOf(address(this));
        _safeTransferFrom(token, msg.sender, address(this), amount);
        uint256 received = IERC20(token).balanceOf(address(this)) - balBefore;
        require(received > 0, "NO_TOKENS_RECEIVED");

        // Effects: record the escrow using the ACTUAL received amount.
        swaps[swapId] = Swap({
            state:      State.LOCKED,
            token:      token,
            amount:     received,
            hashlock:   hashlock,
            refundTime: refundTime,
            claimer:    claimer,
            refunder:   refunder
        });

        emit LockCreated(swapId, msg.sender, token, received,
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
            _safeTransfer(tok, to, amt);
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
            _safeTransfer(tok, to, amt);
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
