// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
// Echidna property harness for F-1 (asset isolation) in AtomicSwapHTLCv2. Local fuzzing only.
//   echidna echidna/EchidnaHTLCv2F1.sol --contract EchidnaHTLCv2F1Fixed  --config echidna/echidna-htlc.yaml   # expected: passing
//   echidna echidna/EchidnaHTLCv2F1.sol --contract EchidnaHTLCv2F1Legacy --config echidna/echidna-htlc.yaml   # expected: falsified (pre-fix code)
// (run from contracts/atomic-swap)
import {AtomicSwapHTLCv2} from "../src/AtomicSwapHTLCv2.sol";
import {AtomicSwapHTLCv2Vulnerable} from "../test/legacy/AtomicSwapHTLCv2Vulnerable.sol";

interface IHTLC {
    function lockNative(bytes32, bytes32, uint256, address, address) external payable;
    function lockERC20(bytes32, address, uint256, bytes32, uint256, address, address) external;
    function claimNative(bytes32, bytes32) external;
    function claimERC20(bytes32, bytes32, uint256) external;
    function refundNative(bytes32) external;
    function refundERC20(bytes32) external;
}

contract EJunk {
    mapping(address => uint256) public balanceOf;
    function mint(address to, uint256 v) external { balanceOf[to] += v; }
    function transferFrom(address f, address t, uint256 v) external returns (bool) { balanceOf[f] -= v; balanceOf[t] += v; return true; }
    function transfer(address t, uint256 v) external returns (bool) { balanceOf[msg.sender] -= v; balanceOf[t] += v; return true; }
}

abstract contract EchidnaHTLCv2F1Base {
    IHTLC h;
    EJunk junk = new EJunk();
    bytes32 constant PRE = bytes32(uint256(0x5ec7e7));
    address constant HONEST = address(0x10000);       // claimer and refunder of honest native swaps (never this harness)
    uint256 public honestNativeOpen;
    uint256 public ownNativeOpen;                       // native swaps the harness (attacker) locked for itself
    uint256 n;
    bytes32[] atkIds;

    receive() external payable {}

    function honestLock(uint64 amt) public {
        if (amt == 0 || address(this).balance < amt) return;
        h.lockNative{value: amt}(keccak256(abi.encode("honest", n++)), sha256(abi.encodePacked(PRE)), block.number + 1e9, HONEST, HONEST);
        honestNativeOpen += amt;
    }
    function atkLockJunk(uint64 amt, bool shortLived) public {
        if (amt == 0) return;
        bytes32 id = keccak256(abi.encode("atkJ", n++));
        junk.mint(address(this), amt);
        h.lockERC20(id, address(junk), amt, sha256(abi.encodePacked(PRE)), block.number + (shortLived ? 1 : 1e9), address(this), address(this));
        atkIds.push(id);
    }
    function atkLockNative(uint64 amt, bool shortLived) public {
        if (amt == 0 || address(this).balance < amt) return;
        bytes32 id = keccak256(abi.encode("atkN", n++));
        h.lockNative{value: amt}(id, sha256(abi.encodePacked(PRE)), block.number + (shortLived ? 1 : 1e9), address(this), address(this));
        atkIds.push(id); ownNativeOpen += amt;
    }
    // the attacker tries every path on any of his swaps; native settlements of his own native swaps are legit
    function atkSettle(uint256 i, uint8 path) public {
        if (atkIds.length == 0) return;
        bytes32 id = atkIds[i % atkIds.length];
        uint256 b = address(h).balance;
        path %= 4;
        if (path == 0) { try h.claimNative(id, PRE) {} catch {} }
        else if (path == 1) { try h.claimERC20(id, PRE, 0) {} catch {} }
        else if (path == 2) { try h.refundNative(id) {} catch {} }
        else { try h.refundERC20(id) {} catch {} }
        uint256 out = b - address(h).balance;
        ownNativeOpen = out > ownNativeOpen ? 0 : ownNativeOpen - out;
    }

    // honest native escrow is never reduced by anything the attacker does
    function echidna_honest_native_escrow_intact() public view returns (bool) {
        return address(h).balance >= honestNativeOpen;
    }
    // exact solvency: contract ETH == honest + attacker's own open native swaps
    function echidna_native_balance_exact() public view returns (bool) {
        return address(h).balance == honestNativeOpen + ownNativeOpen;
    }
}

contract EchidnaHTLCv2F1Fixed is EchidnaHTLCv2F1Base {
    constructor() payable { h = IHTLC(address(new AtomicSwapHTLCv2())); }
}

contract EchidnaHTLCv2F1Legacy is EchidnaHTLCv2F1Base {
    constructor() payable { h = IHTLC(address(new AtomicSwapHTLCv2Vulnerable())); }
}
