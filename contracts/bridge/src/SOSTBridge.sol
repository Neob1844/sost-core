// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {SigLib} from "./SigLib.sol";
import {WSOST} from "./WSOST.sol";
import {GoldAccessKey} from "./GoldAccessKey.sol";

interface IERC20Like {
    function balanceOf(address) external view returns (uint256);
    function transferFrom(address from, address to, uint256 v) external returns (bool);
}

interface IGoldReserveV2 {
    function paused() external view returns (bool);
}

/// @title SOST Automated Bridge (C701, development only — NOT deployed, NOT production-approved)
/// @notice Native SOST locked in the SOST Bridge Vault  <->  wSOST on Ethereum, 1:1.
///
///   mint():  ONE transaction that (1) verifies an EIP-712 mint authorization issued by the bridge
///            verification engine after it confirmed the native deposit, (2) verifies a separately
///            signed, fresh and bounded price quote, (3) recomputes the Gold Access Key on-chain and
///            moves exactly that XAUT from the caller straight to Gold Reserve V2, and (4) mints
///            exactly `amount` wSOST to the bound recipient. The XAUT contribution never reduces the
///            minted amount. Any failure reverts everything.
///   burnForRelease(): any wSOST holder burns N wSOST and publishes the SOST destination; the vault
///            releases N SOST (the SOST network fee of the release transaction is the only deduction,
///            published in `releaseNetworkFeeStocks`). No second XAUT payment.
///
/// TRUST MODEL (explicit, NOT trustless): Ethereum cannot read SOST. Backing is asserted by the
/// authorizer key set. If all authorizer keys and the price signer are compromised, unbacked wSOST
/// can be minted up to the per-mint / daily / exposure caps until the reconciliation monitor pauses
/// minting. This contract LIMITS that damage; it does not remove it.
contract SOSTBridge {

    // ------------------------------------------------------------------ constants
    uint32 public constant BRIDGE_VERSION = 1;
    uint256 public constant ADMIN_DELAY = 2 days;
    uint256 public constant MAX_AUTHORIZERS = 8;
    uint256 public constant MAX_PAUSERS = 8;

    bytes32 public constant MINT_TYPEHASH = keccak256(
        "MintAuthorization(bytes32 requestId,address recipient,uint256 amount,bytes32 depositTxid,uint32 depositVout,bytes32 bridgeVault,bytes32 sostBlockHash,uint64 sostBlockHeight,uint32 confirmations,uint256 feeXaut,bytes32 priceHash,uint64 expiry,uint256 nonce)"
    );
    bytes32 public constant PRICE_TYPEHASH = keccak256(
        "PriceQuote(uint256 xautEur8,uint256 sostEur8,bytes32 methodology,uint64 observedAt,bytes32 quoteId)"
    );
    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant NAME_HASH = keccak256("SOST Automated Bridge");
    bytes32 private constant VERSION_HASH = keccak256("1");

    // ------------------------------------------------------------------ immutables
    WSOST public immutable token;
    address public immutable xaut;
    address public immutable goldReserve;
    /// keccak256 of the SOST Bridge Vault address string ("sost1…"), fixed per deployment
    bytes32 public immutable bridgeVault;
    uint256 private immutable _cachedChainId;
    bytes32 private immutable _cachedDomainSeparator;

    // ------------------------------------------------------------------ messages
    struct MintAuthorization {
        bytes32 requestId;       // engine request (committed in the SOST deposit capsule)
        address recipient;
        uint256 amount;          // stocks == wSOST base units
        bytes32 depositTxid;
        uint32 depositVout;
        bytes32 bridgeVault;
        bytes32 sostBlockHash;
        uint64 sostBlockHeight;
        uint32 confirmations;
        uint256 feeXaut;         // must equal the on-chain recomputation
        bytes32 priceHash;       // EIP-712 struct hash of the PriceQuote used
        uint64 expiry;
        uint256 nonce;
    }

    struct PriceQuote {
        uint256 xautEur8;        // EUR per 1 XAUT, 1e8
        uint256 sostEur8;        // EUR per 1 SOST, 1e8 (only under an APPROVED methodology)
        bytes32 methodology;     // SOST/EUR valuation methodology id
        uint64 observedAt;
        bytes32 quoteId;
    }

    struct Params {
        uint32 minConfirmations;
        uint256 perMintCap;          // stocks
        uint256 dailyMintCap;        // stocks per UTC day
        uint256 exposureCap;         // max wSOST supply (stocks)
        uint64 maxPriceAge;          // seconds
        uint64 maxAuthTtl;           // seconds an authorization may be valid for, measured at mint
        uint256 minXautEur8;
        uint256 maxXautEur8;
        uint256 minSostEur8;
        uint256 maxSostEur8;
        uint16 maxDeviationBps;      // vs last accepted XAUT price
        bytes32 approvedMethodology; // 0 = NO approved SOST/EUR methodology -> every mint blocked
        uint256 minReleaseStocks;
        uint256 releaseNetworkFeeStocks;
    }

    struct Config {
        address admin;
        address[] authorizers;
        uint8 threshold;
        address priceSigner;
        address[] pausers;
        Params p;
    }

    // ------------------------------------------------------------------ state
    address public admin;
    address public priceSigner;
    uint8 public threshold;
    address[] private _authorizers;
    mapping(address => bool) public isAuthorizer;
    address[] private _pausers;
    mapping(address => bool) public isPauser;
    Params internal params;

    function getParams() external view returns (Params memory) { return params; }

    bool public mintPaused;
    uint256 public lastXautEur8;

    mapping(bytes32 => bool) public depositUsed;     // keccak(txid, vout) -> minted or revoked
    mapping(bytes32 => bool) public depositRevoked;
    mapping(bytes32 => bool) public requestUsed;
    mapping(uint256 => bool) public nonceUsed;
    mapping(uint256 => uint256) public mintedOnDay;

    uint256 public totalMinted;
    uint256 public totalBurned;
    uint256 public totalFeesXaut;
    uint256 public releaseNonce;

    struct Release { address from; uint128 amount; uint64 nonce; bool released; bytes32 sostAddressHash; bytes32 sostTxid; }
    mapping(bytes32 => Release) public releases;

    bytes32 public pendingConfigHash;
    uint256 public pendingConfigEta;

    bool private _entered;

    // ------------------------------------------------------------------ events (public log)
    event BridgeMinted(
        bytes32 indexed depositId, bytes32 indexed requestId, address indexed recipient,
        uint256 amount, bytes32 sostBlockHash, uint64 sostBlockHeight
    );
    event GoldAccessKeyPaid(bytes32 indexed depositId, address indexed payer, address indexed goldReserve, uint256 feeXaut, uint256 xautEur8, uint256 sostEur8);
    event DepositRevoked(bytes32 indexed depositId, bytes32 depositTxid, uint32 depositVout, bytes32 reasonHash, address by);
    event BurnedForRelease(bytes32 indexed releaseId, address indexed from, uint256 amount, string sostAddress, uint256 networkFeeStocks, uint256 nonce);
    event ReleaseRecorded(bytes32 indexed releaseId, bytes32 sostTxid, address by);
    event MintPaused(address indexed by);
    event MintUnpaused(address indexed by);
    event ConfigProposed(bytes32 indexed configHash, uint256 eta);
    event ConfigCancelled(bytes32 indexed configHash);
    event ConfigApplied(bytes32 indexed configHash);

    // ------------------------------------------------------------------ errors
    error Reentrancy();
    error NotAdmin();
    error NotPauser();
    error NotAuthorizer();
    error MintIsPaused();
    error ReserveIsPaused();
    error NoApprovedValuation();
    error WrongMethodology();
    error Expired();
    error TtlTooLong();
    error StalePrice();
    error PriceOutOfBounds();
    error PriceDeviation();
    error BadPriceHash();
    error BadVault();
    error NotEnoughConfirmations();
    error DepositAlreadyUsed();
    error RequestAlreadyUsed();
    error NonceAlreadyUsed();
    error ZeroAmount();
    error ZeroRecipient();
    error BelowMinimumOperation();
    error FeeMismatch();
    error PerMintCapExceeded();
    error DailyCapExceeded();
    error ExposureCapExceeded();
    error BadSignatures();
    error BadPriceSignature();
    error FeeTransferFailed();
    error BadConfig();
    error ConfigNotReady();
    error BadSostAddress();
    error BelowMinimumRelease();
    error UnknownRelease();
    error AlreadyReleased();

    modifier nonReentrant() {
        if (_entered) revert Reentrancy();
        _entered = true;
        _;
        _entered = false;
    }

    constructor(address xaut_, address goldReserve_, bytes32 bridgeVault_, Config memory c) {
        if (xaut_ == address(0) || goldReserve_ == address(0) || bridgeVault_ == bytes32(0)) revert BadConfig();
        xaut = xaut_;
        goldReserve = goldReserve_;
        bridgeVault = bridgeVault_;
        token = new WSOST();
        _cachedChainId = block.chainid;
        _cachedDomainSeparator = _buildDomainSeparator();
        _apply(c);
    }

    // ================================================================== EIP-712
    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return block.chainid == _cachedChainId ? _cachedDomainSeparator : _buildDomainSeparator();
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this)));
    }

    function priceStructHash(PriceQuote calldata q) public pure returns (bytes32) {
        return keccak256(abi.encode(PRICE_TYPEHASH, q.xautEur8, q.sostEur8, q.methodology, q.observedAt, q.quoteId));
    }

    function priceDigest(PriceQuote calldata q) public view returns (bytes32) {
        return keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), priceStructHash(q)));
    }

    function mintDigest(MintAuthorization calldata a) public view returns (bytes32) {
        // abi.encode of static words == concatenation of two abi.encode halves (avoids stack-too-deep)
        bytes32 h = keccak256(bytes.concat(
            abi.encode(MINT_TYPEHASH, a.requestId, a.recipient, a.amount, a.depositTxid, a.depositVout, a.bridgeVault),
            abi.encode(a.sostBlockHash, a.sostBlockHeight, a.confirmations, a.feeXaut, a.priceHash, a.expiry, a.nonce)
        ));
        return keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), h));
    }

    function depositIdOf(bytes32 txid, uint32 vout) public pure returns (bytes32) {
        return keccak256(abi.encodePacked("SOST-C701-DEPOSIT-V1", txid, vout));
    }

    // ================================================================== views
    /// @notice Gold Access Key for `amountStocks` at the given quote; reverts below the 100 EUR minimum.
    function quoteFee(uint256 amountStocks, uint256 sostEur8, uint256 xautEur8) public pure returns (uint256) {
        return GoldAccessKey.feeXautForAmount(amountStocks, sostEur8, xautEur8);
    }

    function authorizers() external view returns (address[] memory) { return _authorizers; }
    function pausers() external view returns (address[] memory) { return _pausers; }

    /// @notice wSOST the vault must still back = supply + burned-but-not-yet-released.
    function outstandingObligationStocks() external view returns (uint256) {
        return token.totalSupply() + (totalBurned - _releasedTotal);
    }
    uint256 private _releasedTotal;
    function releasedTotal() external view returns (uint256) { return _releasedTotal; }

    // ================================================================== mint (wrap)
    function mint(
        MintAuthorization calldata a,
        PriceQuote calldata q,
        bytes[] calldata authSigs,
        bytes calldata priceSig
    ) external nonReentrant {
        if (mintPaused) revert MintIsPaused();
        _checkPrice(q, a.priceHash);
        bytes32 depositId = _checkDeposit(a);
        uint256 fee = _checkFeeAndCaps(a, q);

        // --- signatures (authorizer threshold + independent price signer)
        _verifyThreshold(mintDigest(a), authSigs);
        if (SigLib.recover(priceDigest(q), priceSig) != priceSigner) revert BadPriceSignature();

        // --- effects
        depositUsed[depositId] = true;
        requestUsed[a.requestId] = true;
        nonceUsed[a.nonce] = true;
        mintedOnDay[block.timestamp / 1 days] += a.amount;
        totalMinted += a.amount;
        totalFeesXaut += fee;
        lastXautEur8 = q.xautEur8;

        // --- interactions: XAUT straight from the payer to Gold Reserve V2 (exact delta), then mint
        _payGoldAccessKey(fee);
        token.mint(a.recipient, a.amount);

        _emitMinted(a, q, depositId, fee);
    }

    function _emitMinted(MintAuthorization calldata a, PriceQuote calldata q, bytes32 depositId, uint256 fee) internal {
        emit GoldAccessKeyPaid(depositId, msg.sender, goldReserve, fee, q.xautEur8, q.sostEur8);
        emit BridgeMinted(depositId, a.requestId, a.recipient, a.amount, a.sostBlockHash, a.sostBlockHeight);
    }

    /// price: approved methodology, signed (checked later), fresh, bounded, no jumps, hash-bound
    function _checkPrice(PriceQuote calldata q, bytes32 boundHash) internal view {
        Params storage p = params;
        if (p.approvedMethodology == bytes32(0)) revert NoApprovedValuation();
        if (q.methodology != p.approvedMethodology) revert WrongMethodology();
        if (q.observedAt > block.timestamp || block.timestamp - q.observedAt > p.maxPriceAge) revert StalePrice();
        if (q.xautEur8 < p.minXautEur8 || q.xautEur8 > p.maxXautEur8) revert PriceOutOfBounds();
        if (q.sostEur8 < p.minSostEur8 || q.sostEur8 > p.maxSostEur8) revert PriceOutOfBounds();
        uint256 last = lastXautEur8;
        if (last != 0) {
            uint256 diff = q.xautEur8 > last ? q.xautEur8 - last : last - q.xautEur8;
            if (diff * 10_000 > last * p.maxDeviationBps) revert PriceDeviation();
        }
        if (boundHash != priceStructHash(q)) revert BadPriceHash();
    }

    function _checkDeposit(MintAuthorization calldata a) internal view returns (bytes32 depositId) {
        Params storage p = params;
        if (block.timestamp > a.expiry) revert Expired();
        if (a.expiry - block.timestamp > p.maxAuthTtl) revert TtlTooLong();
        if (a.bridgeVault != bridgeVault) revert BadVault();
        if (a.confirmations < p.minConfirmations) revert NotEnoughConfirmations();
        if (a.amount == 0) revert ZeroAmount();
        if (a.recipient == address(0)) revert ZeroRecipient();
        depositId = depositIdOf(a.depositTxid, a.depositVout);
        if (depositUsed[depositId]) revert DepositAlreadyUsed();
        if (requestUsed[a.requestId]) revert RequestAlreadyUsed();
        if (nonceUsed[a.nonce]) revert NonceAlreadyUsed();
    }

    function _checkFeeAndCaps(MintAuthorization calldata a, PriceQuote calldata q) internal view returns (uint256 fee) {
        Params storage p = params;
        uint256 vNum = a.amount * q.sostEur8;
        if (!GoldAccessKey.meetsMinimum(vNum, GoldAccessKey.STOCKS_PER_SOST)) revert BelowMinimumOperation();
        fee = GoldAccessKey.feeXaut(vNum, GoldAccessKey.STOCKS_PER_SOST, q.xautEur8);
        if (fee != a.feeXaut) revert FeeMismatch();
        if (a.amount > p.perMintCap) revert PerMintCapExceeded();
        if (mintedOnDay[block.timestamp / 1 days] + a.amount > p.dailyMintCap) revert DailyCapExceeded();
        if (token.totalSupply() + a.amount > p.exposureCap) revert ExposureCapExceeded();
    }

    function _payGoldAccessKey(uint256 fee) internal {
        if (IGoldReserveV2(goldReserve).paused()) revert ReserveIsPaused();
        uint256 before = IERC20Like(xaut).balanceOf(goldReserve);
        (bool ok, bytes memory ret) = xaut.call(abi.encodeWithSelector(IERC20Like.transferFrom.selector, msg.sender, goldReserve, fee));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert FeeTransferFailed();
        if (IERC20Like(xaut).balanceOf(goldReserve) - before != fee) revert FeeTransferFailed();
    }

    function _verifyThreshold(bytes32 digest, bytes[] calldata sigs) internal view {
        if (sigs.length < threshold || sigs.length > _authorizers.length) revert BadSignatures();
        address prev = address(0);
        for (uint256 i = 0; i < sigs.length; i++) {
            address s = SigLib.recover(digest, sigs[i]);
            if (s <= prev || !isAuthorizer[s]) revert BadSignatures();   // strictly increasing, distinct
            prev = s;
        }
    }

    // ================================================================== refund guard
    /// @notice Permanently marks a native deposit as NOT mintable (wrong address, below minimum, expired
    ///         request, amount mismatch, user-requested refund). The SOST refund may be sent ONLY after
    ///         this transaction is final on Ethereum, so a depositor can never hold both the refund and
    ///         wSOST for the same deposit. Reverts if the deposit was already minted.
    function revokeDeposit(bytes32 txid, uint32 vout, bytes32 reasonHash) external {
        if (!isAuthorizer[msg.sender] && msg.sender != admin) revert NotAuthorizer();
        bytes32 id = depositIdOf(txid, vout);
        if (depositUsed[id]) revert DepositAlreadyUsed();
        depositUsed[id] = true;
        depositRevoked[id] = true;
        emit DepositRevoked(id, txid, vout, reasonHash, msg.sender);
    }

    // ================================================================== burn (unwrap) — never paused
    function burnForRelease(uint256 amount, string calldata sostAddress) external nonReentrant returns (bytes32 releaseId) {
        if (amount == 0) revert ZeroAmount();
        if (amount < params.minReleaseStocks || amount <= params.releaseNetworkFeeStocks) revert BelowMinimumRelease();
        if (!_validSostAddress(bytes(sostAddress))) revert BadSostAddress();
        token.burn(msg.sender, amount);
        totalBurned += amount;
        uint256 n = ++releaseNonce;
        releaseId = keccak256(abi.encode("SOST-C701-RELEASE-V1", block.chainid, address(this), n));
        releases[releaseId] = Release(msg.sender, uint128(amount), uint64(n), false, keccak256(bytes(sostAddress)), bytes32(0));
        emit BurnedForRelease(releaseId, msg.sender, amount, sostAddress, params.releaseNetworkFeeStocks, n);
    }

    /// @notice Public record that the vault paid a release on SOST (idempotence anchor for the engine).
    function recordRelease(bytes32 releaseId, bytes32 sostTxid) external {
        if (!isAuthorizer[msg.sender] && msg.sender != admin) revert NotAuthorizer();
        Release storage r = releases[releaseId];
        if (r.nonce == 0) revert UnknownRelease();
        if (r.released) revert AlreadyReleased();
        r.released = true;
        r.sostTxid = sostTxid;
        _releasedTotal += r.amount;
        emit ReleaseRecorded(releaseId, sostTxid, msg.sender);
    }

    /// sost1 + 40 lowercase hex characters (45 bytes)
    function _validSostAddress(bytes calldata s) internal pure returns (bool) {
        if (s.length != 45) return false;
        if (s[0] != "s" || s[1] != "o" || s[2] != "s" || s[3] != "t" || s[4] != "1") return false;
        for (uint256 i = 5; i < 45; i++) {
            bytes1 c = s[i];
            if (!((c >= "0" && c <= "9") || (c >= "a" && c <= "f"))) return false;
        }
        return true;
    }

    // ================================================================== pause (mint only)
    function pauseMint() external {
        if (!isPauser[msg.sender] && !isAuthorizer[msg.sender] && msg.sender != admin) revert NotPauser();
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
        return keccak256(abi.encode(c));
    }

    function proposeConfig(Config calldata c) external {
        if (msg.sender != admin) revert NotAdmin();
        _check(c);
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
        for (uint256 i = 0; i < _authorizers.length; i++) isAuthorizer[_authorizers[i]] = false;
        for (uint256 i = 0; i < _pausers.length; i++) isPauser[_pausers[i]] = false;
        delete _authorizers;
        delete _pausers;
        lastXautEur8 = 0;            // a reviewed config re-anchors the deviation reference
        _apply(c);
    }

    function _check(Config memory c) internal pure {
        if (c.admin == address(0) || c.priceSigner == address(0)) revert BadConfig();
        if (c.authorizers.length == 0 || c.authorizers.length > MAX_AUTHORIZERS || c.pausers.length > MAX_PAUSERS) revert BadConfig();
        if (c.threshold == 0 || c.threshold > c.authorizers.length) revert BadConfig();
        Params memory p = c.p;
        if (p.perMintCap == 0 || p.perMintCap > p.dailyMintCap || p.dailyMintCap > p.exposureCap) revert BadConfig();
        if (p.maxPriceAge == 0 || p.maxAuthTtl == 0 || p.minConfirmations == 0) revert BadConfig();
        if (p.minXautEur8 == 0 || p.minXautEur8 > p.maxXautEur8 || p.minSostEur8 == 0 || p.minSostEur8 > p.maxSostEur8) revert BadConfig();
        if (p.maxDeviationBps == 0 || p.maxDeviationBps > 5_000) revert BadConfig();
        if (p.minReleaseStocks <= p.releaseNetworkFeeStocks) revert BadConfig();
    }

    function _apply(Config memory c) internal {
        _check(c);
        for (uint256 i = 0; i < c.authorizers.length; i++) {
            address o = c.authorizers[i];
            if (o == address(0) || isAuthorizer[o] || o == c.priceSigner || o == c.admin) revert BadConfig();
            isAuthorizer[o] = true;
            _authorizers.push(o);
        }
        for (uint256 i = 0; i < c.pausers.length; i++) {
            address o = c.pausers[i];
            if (o == address(0) || isPauser[o]) revert BadConfig();
            isPauser[o] = true;
            _pausers.push(o);
        }
        admin = c.admin;
        threshold = c.threshold;
        priceSigner = c.priceSigner;
        params = c.p;
        emit ConfigApplied(keccak256(abi.encode(c)));
    }
}
