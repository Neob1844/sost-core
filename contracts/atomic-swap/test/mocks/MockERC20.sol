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
