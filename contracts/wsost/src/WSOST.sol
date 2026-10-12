// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {SigLib} from "./SigLib.sol";

/// @title wSOST — 1:1 ERC-20 representation of native SOST (Stage 1, research / devnet only)
/// @notice 1 wSOST = 1 native SOST locked in the SOST Bridge Vault.
///         wSOST is minted ONLY against a native SOST deposit attested by a threshold of
///         bridge observers (EIP-712), and burned ONLY by its holder to request the release
///         of native SOST. There is no owner mint, no confiscation and no upgrade path.
///         Native SOST is never burned. Gold never mints wSOST (this contract has no gold path).
/// @dev    8 decimals, mirroring the SOST "stock" (1 SOST = 100,000,000 stocks).
contract WSOST {
    // ------------------------------------------------------------------ ERC-20
    string public constant name = "Wrapped SOST";
    string public constant symbol = "wSOST";
    uint8 public constant decimals = 8;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    // ------------------------------------------------------------------ bridge constants
    uint32 public constant BRIDGE_VERSION = 1;
    uint256 public constant ADMIN_DELAY = 2 days;
    uint256 public constant MAX_OBSERVERS = 16;

    bytes32 public constant DEPOSIT_TYPEHASH = keccak256(
        "Deposit(bytes32 depositId,address recipient,uint256 amount,bytes32 bridgeVault,bytes32 sostBlockHash,uint64 sostBlockHeight,uint32 confirmations,uint32 bridgeVersion)"
    );
    bytes32 private constant EIP712_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant NAME_HASH = keccak256("SOST wSOST Bridge");
    bytes32 private constant VERSION_HASH = keccak256("1");

    /// @notice keccak256 of the SOST Bridge Vault address string (e.g. "sost1…"); fixed per deployment.
    bytes32 public immutable bridgeVault;

    // ------------------------------------------------------------------ bridge state
    struct Deposit {
        bytes32 depositId;       // keccak256("SOST-WSOST-DEPOSIT-V1" || txid || vout)
        address recipient;
        uint256 amount;          // stocks (8 decimals)
        bytes32 bridgeVault;     // must equal this.bridgeVault
        bytes32 sostBlockHash;   // block that contains the deposit
        uint64 sostBlockHeight;
        uint32 confirmations;    // confirmations observed when attesting
        uint32 bridgeVersion;    // must equal BRIDGE_VERSION
    }

    address public admin;                       // guardian multisig / timelock owner of configuration
    address[] private _observers;
    mapping(address => bool) public isObserver;
    uint8 public threshold;

    uint32 public minConfirmations;             // provisional policy (30 for the pilot), not a constant
    uint256 public exposureCap;                 // max totalSupply (stocks)
    uint256 public dailyMintCap;                // max minted per UTC day (stocks)
    mapping(uint256 => uint256) public mintedOnDay;

    bool public mintPaused;
    mapping(bytes32 => bool) public depositUsed;

    uint256 public totalMinted;
    uint256 public totalBurned;
    uint256 public burnNonce;

    struct BurnRecord { address from; uint128 amount; uint64 nonce; bytes32 sostAddressHash; }
    mapping(bytes32 => BurnRecord) public burns;

    // timelocked configuration change
    struct Config {
        address admin;
        address[] observers;
        uint8 threshold;
        uint32 minConfirmations;
        uint256 exposureCap;
        uint256 dailyMintCap;
    }
    bytes32 public pendingConfigHash;
    uint256 public pendingConfigEta;

    event Minted(bytes32 indexed depositId, address indexed recipient, uint256 amount, bytes32 sostBlockHash, uint64 sostBlockHeight);
    event BurnedForRelease(bytes32 indexed burnId, address indexed from, uint256 amount, string sostAddress, uint256 nonce);
    event MintPaused(address indexed by);
    event MintUnpaused(address indexed by);
    event ConfigProposed(bytes32 indexed configHash, uint256 eta);
    event ConfigCancelled(bytes32 indexed configHash);
    event ConfigApplied(bytes32 indexed configHash, address admin, uint8 threshold, uint256 observers, uint32 minConfirmations, uint256 exposureCap, uint256 dailyMintCap);

    error NotAdmin();
    error NotPauser();
    error MintIsPaused();
    error BadVersion();
    error BadVault();
    error NotEnoughConfirmations();
    error DepositAlreadyUsed();
    error ZeroAmount();
    error ZeroRecipient();
    error ExposureCapExceeded();
    error DailyCapExceeded();
    error BadSignatures();
    error BadConfig();
    error ConfigNotReady();
    error BadSostAddress();
    error InsufficientBalance();
    error InsufficientAllowance();

    uint256 private immutable _cachedChainId;
    bytes32 private immutable _cachedDomainSeparator;

    constructor(bytes32 bridgeVault_, Config memory c) {
        bridgeVault = bridgeVault_;
        _apply(c);
        _cachedChainId = block.chainid;
        _cachedDomainSeparator = _buildDomainSeparator();
    }

    // ================================================================== ERC-20
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
        if (to == address(0)) revert ZeroRecipient();
        uint256 b = balanceOf[from];
        if (b < value) revert InsufficientBalance();
        unchecked { balanceOf[from] = b - value; }
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }

    // ================================================================== EIP-712
    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return block.chainid == _cachedChainId ? _cachedDomainSeparator : _buildDomainSeparator();
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(abi.encode(EIP712_DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this)));
    }

    function depositDigest(Deposit calldata d) public view returns (bytes32) {
        bytes32 structHash = keccak256(abi.encode(
            DEPOSIT_TYPEHASH, d.depositId, d.recipient, d.amount, d.bridgeVault,
            d.sostBlockHash, d.sostBlockHeight, d.confirmations, d.bridgeVersion
        ));
        return keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
    }

    // ================================================================== mint (wrap)
    /// @param sigs observer signatures over depositDigest(d), ordered by strictly increasing signer address.
    function mint(Deposit calldata d, bytes[] calldata sigs) external {
        if (mintPaused) revert MintIsPaused();
        if (d.bridgeVersion != BRIDGE_VERSION) revert BadVersion();
        if (d.bridgeVault != bridgeVault) revert BadVault();
        if (d.confirmations < minConfirmations) revert NotEnoughConfirmations();
        if (d.amount == 0) revert ZeroAmount();
        if (d.recipient == address(0)) revert ZeroRecipient();
        if (depositUsed[d.depositId]) revert DepositAlreadyUsed();
        if (totalSupply + d.amount > exposureCap) revert ExposureCapExceeded();
        uint256 day = block.timestamp / 1 days;
        if (mintedOnDay[day] + d.amount > dailyMintCap) revert DailyCapExceeded();

        _verifyThreshold(depositDigest(d), sigs);

        depositUsed[d.depositId] = true;
        mintedOnDay[day] += d.amount;
        totalMinted += d.amount;
        totalSupply += d.amount;
        balanceOf[d.recipient] += d.amount;
        emit Transfer(address(0), d.recipient, d.amount);
        emit Minted(d.depositId, d.recipient, d.amount, d.sostBlockHash, d.sostBlockHeight);
    }

    function _verifyThreshold(bytes32 digest, bytes[] calldata sigs) internal view {
        if (sigs.length < threshold) revert BadSignatures();
        address last = address(0);
        uint256 valid;
        for (uint256 i = 0; i < sigs.length; i++) {
            address s = SigLib.recover(digest, sigs[i]);
            if (s <= last || !isObserver[s]) revert BadSignatures();   // sorted, distinct, observer
            last = s;
            valid++;
        }
        if (valid < threshold) revert BadSignatures();
    }

    // ================================================================== burn (unwrap)
    /// @notice Burn wSOST to request the release of the same amount of native SOST
    ///         (minus the published release fee allowance) to `sostAddress`.
    function burn(uint256 amount, string calldata sostAddress) external returns (bytes32 burnId) {
        if (amount == 0) revert ZeroAmount();
        if (!_validSostAddress(bytes(sostAddress))) revert BadSostAddress();
        uint256 b = balanceOf[msg.sender];
        if (b < amount) revert InsufficientBalance();
        unchecked { balanceOf[msg.sender] = b - amount; }
        totalSupply -= amount;
        totalBurned += amount;
        uint256 n = ++burnNonce;
        burnId = keccak256(abi.encode("SOST-WSOST-BURN-V1", block.chainid, address(this), n));
        burns[burnId] = BurnRecord(msg.sender, uint128(amount), uint64(n), keccak256(bytes(sostAddress)));
        emit Transfer(msg.sender, address(0), amount);
        emit BurnedForRelease(burnId, msg.sender, amount, sostAddress, n);
    }

    /// sost1 + 40 lowercase hex characters (45 bytes)
    function _validSostAddress(bytes calldata a) internal pure returns (bool) {
        if (a.length != 45) return false;
        if (a[0] != "s" || a[1] != "o" || a[2] != "s" || a[3] != "t" || a[4] != "1") return false;
        for (uint256 i = 5; i < 45; i++) {
            bytes1 c = a[i];
            if (!((c >= "0" && c <= "9") || (c >= "a" && c <= "f"))) return false;
        }
        return true;
    }

    // ================================================================== pause (mint only)
    /// @notice Any observer or the admin can stop NEW mints. Transfers and burns keep working.
    function pauseMint() external {
        if (!isObserver[msg.sender] && msg.sender != admin) revert NotPauser();
        mintPaused = true;
        emit MintPaused(msg.sender);
    }

    function unpauseMint() external {
        if (msg.sender != admin) revert NotAdmin();
        mintPaused = false;
        emit MintUnpaused(msg.sender);
    }

    // ================================================================== timelocked configuration
    function configHash(Config calldata c) public pure returns (bytes32) {
        return keccak256(abi.encode(c.admin, c.observers, c.threshold, c.minConfirmations, c.exposureCap, c.dailyMintCap));
    }

    function proposeConfig(Config calldata c) external {
        if (msg.sender != admin) revert NotAdmin();
        _check(c.admin, c.observers, c.threshold);
        pendingConfigHash = configHash(c);
        pendingConfigEta = block.timestamp + ADMIN_DELAY;
        emit ConfigProposed(pendingConfigHash, pendingConfigEta);
    }

    function cancelConfig() external {
        if (msg.sender != admin) revert NotAdmin();
        emit ConfigCancelled(pendingConfigHash);
        pendingConfigHash = bytes32(0);
        pendingConfigEta = 0;
    }

    function applyConfig(Config calldata c) external {
        if (msg.sender != admin) revert NotAdmin();
        bytes32 h = configHash(c);
        if (h != pendingConfigHash || pendingConfigEta == 0 || block.timestamp < pendingConfigEta) revert ConfigNotReady();
        pendingConfigHash = bytes32(0);
        pendingConfigEta = 0;
        for (uint256 i = 0; i < _observers.length; i++) isObserver[_observers[i]] = false;
        delete _observers;
        _apply(c);
    }

    function _check(address admin_, address[] memory obs, uint8 thr) internal pure {
        if (admin_ == address(0) || obs.length == 0 || obs.length > MAX_OBSERVERS) revert BadConfig();
        if (thr == 0 || thr > obs.length || uint256(thr) * 2 <= obs.length) revert BadConfig(); // strict majority
    }

    function _apply(Config memory c) internal {
        _check(c.admin, c.observers, c.threshold);
        for (uint256 i = 0; i < c.observers.length; i++) {
            address o = c.observers[i];
            if (o == address(0) || isObserver[o]) revert BadConfig();
            isObserver[o] = true;
            _observers.push(o);
        }
        admin = c.admin;
        threshold = c.threshold;
        minConfirmations = c.minConfirmations;
        exposureCap = c.exposureCap;
        dailyMintCap = c.dailyMintCap;
        emit ConfigApplied(keccak256(abi.encode(c.admin, c.observers, c.threshold, c.minConfirmations, c.exposureCap, c.dailyMintCap)),
            c.admin, c.threshold, c.observers.length, c.minConfirmations, c.exposureCap, c.dailyMintCap);
    }

    function observers() external view returns (address[] memory) {
        return _observers;
    }
}
