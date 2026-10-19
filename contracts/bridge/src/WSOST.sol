// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title wSOST — 1:1 ERC-20 representation of native SOST locked in the SOST Bridge Vault
/// @notice C701, development only — NOT deployed. 8 decimals (1 wSOST unit = 1 SOST stock).
///         Minting and burning are reachable ONLY through the SOSTBridge contract that deployed this
///         token (immutable). There is no owner, no admin mint, no confiscation, no blacklist, no
///         upgrade path. A holder's balance can only be burned by that holder's own burn request.
contract WSOST {
    string public constant name = "Wrapped SOST";
    string public constant symbol = "wSOST";
    uint8 public constant decimals = 8;

    address public immutable bridge;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error NotBridge();
    error ZeroAddress();
    error InsufficientBalance();
    error InsufficientAllowance();

    constructor() {
        bridge = msg.sender;
    }

    modifier onlyBridge() {
        if (msg.sender != bridge) revert NotBridge();
        _;
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        if (a != type(uint256).max) {
            if (a < value) revert InsufficientAllowance();
            unchecked { allowance[from][msg.sender] = a - value; }
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) internal {
        if (to == address(0)) revert ZeroAddress();
        uint256 b = balanceOf[from];
        if (b < value) revert InsufficientBalance();
        unchecked { balanceOf[from] = b - value; }
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }

    /// @dev called by the bridge only after a fully verified, backed deposit.
    function mint(address to, uint256 value) external onlyBridge {
        if (to == address(0)) revert ZeroAddress();
        totalSupply += value;
        balanceOf[to] += value;
        emit Transfer(address(0), to, value);
    }

    /// @dev called by the bridge only, and the bridge only passes `from == msg.sender` of its caller.
    function burn(address from, uint256 value) external onlyBridge {
        uint256 b = balanceOf[from];
        if (b < value) revert InsufficientBalance();
        unchecked { balanceOf[from] = b - value; }
        totalSupply -= value;
        emit Transfer(from, address(0), value);
    }
}
