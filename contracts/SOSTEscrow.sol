// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// ============================================================================
// SOSTEscrow — PoPC Model B Timelocked Gold Escrow
//
// Specification: SOST Whitepaper Section 6.8
//   "Model B — Timelocked Escrow, No Audits"
//
// Properties (constitutional, immutable):
//   - NO admin key
//   - NO upgrade proxy (no UUPS, no transparent proxy, no beacon)
//   - NO pause function
//   - NO emergency withdrawal
//   - NO extension or modification of existing deposits
//   - ONLY the original depositor can withdraw
//   - ONLY after the timelock expires
//   - Source code published and verified on block explorer
//
// Accepted tokens: XAUT (Tether Gold) and PAXG (Paxos Gold)
// Both are ERC-20 tokens on Ethereum mainnet.
//
// Architecture:
//   1. User calls deposit(token, amount, unlockTime)
//   2. Contract transfers ERC-20 tokens from user to itself
//   3. Tokens are locked until block.timestamp >= unlockTime
//   4. After unlock: user calls withdraw(depositId) to reclaim tokens
//   5. No one else can touch the tokens. Ever.
//
// Trust model:
//   - The contract itself is trustless (immutable, no admin)
//   - The SOST reward payout is handled OFF-CHAIN by the watcher
//   - If the watcher fails, the user still gets their gold back at expiry
//   - The contract emits events that the watcher reads
//
// SOST Protocol — Copyright (c) 2026 SOST Protocol
// MIT License. See LICENSE file.
// ============================================================================

import {IERC20} from "./interfaces/IERC20.sol";
import {ReentrancyGuard} from "./security/ReentrancyGuard.sol";

// ============================================================================
// Main contract
// ============================================================================

contract SOSTEscrow is ReentrancyGuard {

    // ---- Structs ----

    struct Deposit {
        address depositor;      // original depositor (only one who can withdraw)
        address token;          // ERC-20 token address (XAUT or PAXG)
        uint256 amount;         // amount deposited (in token's smallest unit)
        uint256 unlockTime;     // Unix timestamp when withdrawal becomes possible
        bool    withdrawn;      // true after successful withdrawal
    }

    // ---- State ----

    // Allowlisted tokens. Set once at construction. Immutable.
    address public immutable XAUT;
    address public immutable PAXG;

    // Minimum lock duration: 28 days (1 month minimum per whitepaper)
    uint256 public constant MIN_LOCK_DURATION = 28 days;

    // Maximum lock duration: 366 days (12 months + 1 day buffer)
    uint256 public constant MAX_LOCK_DURATION = 366 days;

    // Minimum deposit amounts in each token's smallest unit.
    //
    // Both XAUT and PAXG represent 1 troy ounce per 1e(decimals) token units.
    //   XAUT: 6 decimals  -> 1 oz = 1e6,   0.001 oz = 1e3
    //   PAXG: 18 decimals -> 1 oz = 1e18,  0.001 oz = 1e15
    //
    // The 0.001 oz minimum (~$2-3 at current gold prices) exists to prevent
    // dust-deposit spam that would bloat the _userDepositIds arrays.
    uint256 public constant XAUT_MIN_AMOUNT = 1000;          // 0.001 oz (1e3 in 6-decimal token)
    uint256 public constant PAXG_MIN_AMOUNT = 1e15;           // 0.001 oz (1e15 in 18-decimal token)

    // Auto-incrementing deposit counter
    uint256 public depositCount;

    // All deposits by ID
    mapping(uint256 => Deposit) public deposits;

    // Active deposit IDs per user (for enumeration)
    mapping(address => uint256[]) internal _userDepositIds;

    // O(1) running total of locked (non-withdrawn) tokens per token address.
    // Updated on deposit (+) and withdraw (-). Avoids O(n) loop in totalLocked().
    mapping(address => uint256) public totalLockedByToken;

    // ---- Events ----

    // Emitted on every deposit. The watcher reads this to trigger SOST payout.
    event GoldDeposited(
        uint256 indexed depositId,
        address indexed depositor,
        address indexed token,
        uint256 amount,
        uint256 unlockTime
    );

    // Emitted on every withdrawal.
    event GoldWithdrawn(
        uint256 indexed depositId,
        address indexed depositor,
        address token,
        uint256 amount
    );

    // ---- Errors ----

    error TokenNotAllowed(address token);
    error AmountBelowMinimum(uint256 amount, uint256 minimum);
    error UnlockTimeNotInFuture(uint256 unlockTime, uint256 currentTime);
    error LockDurationTooShort(uint256 duration, uint256 minimum);
    error LockDurationTooLong(uint256 duration, uint256 maximum);
    error DepositNotFound(uint256 depositId);
    error NotDepositor(address caller, address depositor);
    error StillLocked(uint256 unlockTime, uint256 currentTime);
    error AlreadyWithdrawn(uint256 depositId);
    error TransferFailed();

    // ---- Constructor ----

    /// @param _xaut Address of the XAUT (Tether Gold) ERC-20 contract
    /// @param _paxg Address of the PAXG (Paxos Gold) ERC-20 contract
    constructor(address _xaut, address _paxg) {
        require(_xaut != address(0), "XAUT address cannot be zero");
        require(_paxg != address(0), "PAXG address cannot be zero");
        require(_xaut != _paxg, "XAUT and PAXG must be different");
        XAUT = _xaut;
        PAXG = _paxg;
    }

    // ---- Core functions ----

    /// @notice Deposit gold tokens into escrow with a timelock.
    /// @param token The ERC-20 token to deposit (must be XAUT or PAXG)
    /// @param amount The amount to deposit (in token's smallest unit)
    /// @param unlockTime Unix timestamp when withdrawal becomes possible
    /// @return depositId The unique ID of this deposit
    ///
    /// Requirements:
    /// - token must be XAUT or PAXG
    /// - amount must be above the per-token minimum
    /// - unlockTime must be between MIN_LOCK_DURATION and MAX_LOCK_DURATION from now
    /// - caller must have approved this contract for at least `amount` of `token`
    ///
    /// The caller's tokens are transferred to this contract and locked until
    /// unlockTime. No one — not even the contract deployer — can move them
    /// before that time. Only the original depositor can withdraw after unlock.
    function deposit(
        address token,
        uint256 amount,
        uint256 unlockTime
    )
        external
        nonReentrant
        returns (uint256 depositId)
    {
        // Validate token is allowlisted
        if (token != XAUT && token != PAXG) {
            revert TokenNotAllowed(token);
        }

        // Validate minimum amount
        uint256 minAmount = (token == XAUT) ? XAUT_MIN_AMOUNT : PAXG_MIN_AMOUNT;
        if (amount < minAmount) {
            revert AmountBelowMinimum(amount, minAmount);
        }

        // Validate unlockTime is strictly in the future BEFORE subtracting.
        // This prevents underflow and rejects unlockTime == block.timestamp
        // (which would mean "locked for zero seconds" — not a real lock).
        if (unlockTime <= block.timestamp) {
            revert UnlockTimeNotInFuture(unlockTime, block.timestamp);
        }

        // Safe to subtract now: unlockTime > block.timestamp is guaranteed above.
        uint256 duration = unlockTime - block.timestamp;
        if (duration < MIN_LOCK_DURATION) {
            revert LockDurationTooShort(duration, MIN_LOCK_DURATION);
        }
        if (duration > MAX_LOCK_DURATION) {
            revert LockDurationTooLong(duration, MAX_LOCK_DURATION);
        }

        // --- deposit() order: Checks → Interaction → Effects ---
        // For deposit, the external call (transferFrom) comes BEFORE state
        // changes. This ensures that if the transfer fails or the token
        // behaves unexpectedly, no deposit is recorded. nonReentrant
        // protects against reentrancy from malicious tokens.

        // INTERACTION: transfer tokens first
        bool success = IERC20(token).transferFrom(msg.sender, address(this), amount);
        if (!success) {
            revert TransferFailed();
        }

        // EFFECTS: record deposit only after successful transfer
        depositId = depositCount;
        depositCount++;

        deposits[depositId] = Deposit({
            depositor: msg.sender,
            token: token,
            amount: amount,
            unlockTime: unlockTime,
            withdrawn: false
        });

        _userDepositIds[msg.sender].push(depositId);
        totalLockedByToken[token] += amount;

        emit GoldDeposited(depositId, msg.sender, token, amount, unlockTime);
    }

    /// @notice Withdraw gold tokens after the timelock has expired.
    /// @param depositId The ID of the deposit to withdraw
    ///
    /// Requirements:
    /// - caller must be the original depositor
    /// - block.timestamp must be >= unlockTime
    /// - deposit must not have been withdrawn already
    ///
    /// On success: the full deposited amount is transferred back to the
    /// original depositor. No partial withdrawals. No fees.
    function withdraw(uint256 depositId) external nonReentrant {
        Deposit storage d = deposits[depositId];

        // --- CHECKS ---

        // Deposit must exist. A zero depositor means the struct was never
        // written (Solidity default). This is sufficient because deposit()
        // always stores msg.sender, which is never address(0).
        if (d.depositor == address(0)) {
            revert DepositNotFound(depositId);
        }

        // Only original depositor can withdraw
        if (msg.sender != d.depositor) {
            revert NotDepositor(msg.sender, d.depositor);
        }

        // Must not be already withdrawn
        if (d.withdrawn) {
            revert AlreadyWithdrawn(depositId);
        }

        // Must be at or past unlock time (>= allows withdrawal exactly at unlockTime)
        if (block.timestamp < d.unlockTime) {
            revert StillLocked(d.unlockTime, block.timestamp);
        }

        // --- EFFECTS (state changes before external call) ---

        d.withdrawn = true;
        totalLockedByToken[d.token] -= d.amount;

        // --- INTERACTIONS (external call last) ---

        bool success = IERC20(d.token).transfer(d.depositor, d.amount);
        if (!success) {
            revert TransferFailed();
        }

        emit GoldWithdrawn(depositId, d.depositor, d.token, d.amount);
    }

    // ---- View functions ----

    /// @notice Get all deposit IDs for a user
    function getUserDepositIds(address user) external view returns (uint256[] memory) {
        return _userDepositIds[user];
    }

    /// @notice Get full deposit details
    function getDeposit(uint256 depositId) external view returns (
        address depositor,
        address token,
        uint256 amount,
        uint256 unlockTime,
        bool withdrawn
    ) {
        Deposit storage d = deposits[depositId];
        return (d.depositor, d.token, d.amount, d.unlockTime, d.withdrawn);
    }

    /// @notice Check if a deposit can be withdrawn right now
    function canWithdraw(uint256 depositId) external view returns (bool) {
        Deposit storage d = deposits[depositId];
        if (d.depositor == address(0)) return false;
        if (d.withdrawn) return false;
        return block.timestamp >= d.unlockTime;
    }

    /// @notice Get the total gold locked for a specific token.
    /// @dev O(1) — reads from the running total maintained by deposit/withdraw.
    function totalLocked(address token) external view returns (uint256) {
        return totalLockedByToken[token];
    }
}
