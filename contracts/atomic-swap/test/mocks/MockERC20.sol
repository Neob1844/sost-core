// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// Minimal compliant ERC-20 for testing AtomicSwapHTLC.
/// NOT FOR PRODUCTION. transferFrom returns true on success.
contract MockERC20 {
    string public name;
    string public symbol;
    uint8  public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory _name, string memory _symbol) {
        name = _name;
        symbol = _symbol;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
        emit Transfer(address(0), to, amount);
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "BAL");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "ALLOW");
        require(balanceOf[from] >= amount, "BAL");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}

/// ERC-20 that returns FALSE on transferFrom — used to test the
/// AtomicSwapHTLC ok-check rejection path.
contract MockFailERC20 {
    function transfer(address, uint256) external pure returns (bool) {
        return false;
    }
    function transferFrom(address, address, uint256) external pure returns (bool) {
        return false;
    }
    function approve(address, uint256) external pure returns (bool) {
        return true;
    }
}

/// Malicious receiver that re-enters AtomicSwapHTLC.claim during the
/// native-ETH transfer in claim. The reentrancy guard in AtomicSwapHTLC
/// MUST cause the re-entry to revert.
interface IClaimable {
    function claim(bytes32 swapId, bytes32 preimage) external;
}

contract MaliciousClaimReceiver {
    IClaimable public htlc;
    bytes32    public targetSwap;
    bytes32    public targetPreimage;
    bool       public reentered;

    constructor(address _htlc) {
        htlc = IClaimable(_htlc);
    }

    function setTarget(bytes32 swapId, bytes32 preimage) external {
        targetSwap = swapId;
        targetPreimage = preimage;
    }

    receive() external payable {
        // Attempt to re-enter the contract during native transfer.
        if (!reentered) {
            reentered = true;
            // This call MUST revert because of the nonReentrant guard.
            htlc.claim(targetSwap, targetPreimage);
        }
    }
}

// =============================================================================
// Phase D hardening — additional weird-ERC20 mocks
// =============================================================================
//
// Each mock isolates one real-world ERC-20 misbehaviour that AtomicSwapHTLC
// must either reject at lock time or fail safely later. The tests using
// these mocks live alongside the existing happy-path tests in
// AtomicSwapHTLC.t.sol and are mapped 1-to-1 in
// docs/design/ATOMIC_SWAP_EVM_AUDIT_CHECKLIST.md.

/// ERC-20 whose transferFrom does NOT return a bool. Some legacy tokens
/// (notably old USDT) omit the return value. With solidity 0.8.x and the
/// IERC20 interface signature `returns (bool)`, the call decode fails on
/// empty return data and reverts. AtomicSwapHTLC therefore safely refuses
/// to escrow this kind of token at lock time.
contract MockNoReturnERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external {
        allowance[msg.sender][spender] = amount;
    }

    /// Transfers value but returns nothing. The IERC20 view of the contract
    /// expects `returns (bool)`; the empty return data fails to decode and
    /// the calling site reverts.
    function transferFrom(address from, address to, uint256 amount) external {
        require(allowance[from][msg.sender] >= amount, "ALLOW");
        require(balanceOf[from] >= amount, "BAL");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }

    function transfer(address to, uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "BAL");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }
}

/// ERC-20 with a fixed fee burned on every transferFrom. The contract
/// records `amount` in state but only receives `amount - fee` into escrow.
/// The asymmetry is detected at claim time, when the contract tries to
/// send back `amount` from a balance of `amount - fee` and the underlying
/// transfer reverts with "BAL". Fee-on-transfer tokens are therefore
/// UNSUPPORTED — the lock succeeds but any subsequent claim or refund
/// reverts, locking the funds in escrow until the user pulls them out via
/// the (eventually) opened refund path which will also fail. The audit
/// checklist documents this so the wallet UI can blacklist FoT tokens
/// at compose time.
contract MockFeeOnTransferERC20 {
    uint256 public constant FEE = 10;  // flat 10 units burned per transfer

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "ALLOW");
        require(balanceOf[from] >= amount, "BAL");
        require(amount > FEE, "FEE>AMOUNT");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        // FEE units burned; recipient gets amount - FEE.
        balanceOf[to] += (amount - FEE);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "BAL");
        require(amount > FEE, "FEE>AMOUNT");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += (amount - FEE);
        return true;
    }
}

/// ERC-20 that re-enters AtomicSwapHTLC.lockERC20 during the transferFrom
/// callback. The contract's nonReentrant guard MUST block the re-entry.
/// The outer call reverts at the inner REENTRANT check, propagated up
/// through the lockERC20 transferFrom success path.
interface ILockable {
    function lockERC20(
        bytes32 swapId,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 refundTime,
        address claimer,
        address refunder
    ) external;
}

contract MaliciousReentrantERC20 {
    ILockable public htlc;
    bool      public reentered;
    bytes32   public targetSwap;
    bytes32   public targetHash;
    uint256   public targetRefund;
    address   public targetClaimer;
    address   public targetRefunder;
    uint256   public targetAmount;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(address _htlc) {
        htlc = ILockable(_htlc);
    }

    function arm(
        bytes32 swapId, bytes32 h, uint256 rt,
        address claimer, address refunder, uint256 amt
    ) external {
        targetSwap     = swapId;
        targetHash     = h;
        targetRefund   = rt;
        targetClaimer  = claimer;
        targetRefunder = refunder;
        targetAmount   = amt;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "BAL");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        // Try the re-entry once during the lockERC20 callback.
        if (!reentered) {
            reentered = true;
            // This MUST revert because of the nonReentrant guard.
            htlc.lockERC20(
                targetSwap, address(this), targetAmount, targetHash,
                targetRefund, targetClaimer, targetRefunder
            );
        }
        require(allowance[from][msg.sender] >= amount, "ALLOW");
        require(balanceOf[from] >= amount, "BAL");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// Tiny helper that accepts ETH on construction and selfdestructs to a
/// target address. Used to test that forced ETH (EIP-6780 / Cancun
/// semantics: SELFDESTRUCT in same tx as creation transfers balance)
/// does NOT corrupt the HTLC state machine. The HTLC's receive() guard
/// is bypassed by selfdestruct by design at the protocol level; we
/// verify the contract is robust to this pathway.
contract SelfdestructForcer {
    constructor(address payable target) payable {
        // Selfdestruct in the same tx as construction → balance is moved
        // to `target` even when target has no payable receive(). This is
        // an EIP-6780 carve-out preserved post-Cancun.
        selfdestruct(target);
    }
}
