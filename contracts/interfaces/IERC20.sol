// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ERC-20 Token Standard Interface
/// @dev Minimal interface for the ERC-20 standard (EIP-20).
///      Only the functions needed by SOSTEscrow are included.
interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
}
