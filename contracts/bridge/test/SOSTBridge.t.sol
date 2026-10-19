// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {SOSTBridge} from "../src/SOSTBridge.sol";
import {WSOST} from "../src/WSOST.sol";
import {GoldAccessKey} from "../src/GoldAccessKey.sol";
import {GoldReserveV2} from "../src/GoldReserveV2.sol";
import {QuarantineVault} from "../src/QuarantineVault.sol";
import {ReserveBase} from "../src/ReserveBase.sol";

/// Mock XAUT — 6 decimals like Tether Gold on Ethereum (verified: Etherscan "Token Contract (WITH 6 Decimals)").
/// TEST ONLY. `freeze` simulates an issuer-side freeze/blacklist.
contract MockXAUT {
    string public constant name = "Mock Tether Gold (TEST ONLY)";
    string public constant symbol = "mXAUT";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;
    bool public frozen;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address to, uint256 v) external { balanceOf[to] += v; totalSupply += v; }
    function freeze() external { frozen = true; }
    function approve(address s, uint256 v) external returns (bool) { allowance[msg.sender][s] = v; return true; }
    function transfer(address to, uint256 v) external returns (bool) { return _t(msg.sender, to, v); }
    function transferFrom(address f, address to, uint256 v) external virtual returns (bool) {
        require(allowance[f][msg.sender] >= v, "allowance"); allowance[f][msg.sender] -= v; return _t(f, to, v);
    }
    function _t(address f, address to, uint256 v) internal returns (bool) {
        require(!frozen, "frozen"); require(balanceOf[f] >= v, "balance"); balanceOf[f] -= v; balanceOf[to] += v; return true;
    }
}

/// Fee-on-transfer token: proves the bridge refuses a reserve delta different from the fee.
contract FeeOnTransferXAUT is MockXAUT {
    function transferFrom(address f, address to, uint256 v) external override returns (bool) {
        require(allowance[f][msg.sender] >= v, "allowance"); allowance[f][msg.sender] -= v;
        balanceOf[f] -= v; balanceOf[to] += v - (v > 0 ? 1 : 0); return true;
    }
}

contract FeeHarness {
    function fee(uint256 vNum, uint256 vDen, uint256 x) external pure returns (uint256) { return GoldAccessKey.feeXaut(vNum, vDen, x); }
    function feeEur8(uint256 vNum, uint256 vDen) external pure returns (uint256) { return GoldAccessKey.feeEur8(vNum, vDen); }
}

abstract contract BridgeBase is Test {
    // ---- TEST-ONLY keys (never used outside this test suite)
    uint256 internal constant AUTH_PK = 0xA11CE;
    uint256 internal constant AUTH2_PK = 0xA11CF;
    uint256 internal constant AUTH3_PK = 0xA11D0;
    uint256 internal constant PRICE_PK = 0xB0B;
    uint256 internal constant ATTACKER_PK = 0xBAD;

    uint256 internal constant XAUT_EUR8 = 371_313_000_000;        // 1 XAUT = 3,713.13 EUR (fixed, dated test value)
    uint256 internal constant SOST_EUR8 = 100_000_000;            // 1 SOST = 1.00 EUR  (TEST FIXTURE — no approved methodology exists)
    bytes32 internal constant TEST_METHODOLOGY = keccak256("TEST-ONLY SOST/EUR methodology - NOT APPROVED");
    string internal constant VAULT_ADDR = "sost1abababababababababababababababababababab";
    string internal constant USER_SOST = "sost1cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd";

    MockXAUT xaut;
    GoldReserveV2 reserve;
    QuarantineVault quarantine;
    SOSTBridge bridge;
    WSOST token;
    address[5] g;
    address admin = address(0xAD);
    address pauser = address(0x9A);
    address user = address(0x1234);
    address authAddr;
    address priceAddr;
    uint256 nextNonce = 1;

    function setUp() public virtual {
        vm.warp(1_800_000_000);
        for (uint256 i = 0; i < 5; i++) g[i] = address(uint160(0x6000 + i));
        authAddr = vm.addr(AUTH_PK);
        priceAddr = vm.addr(PRICE_PK);
        xaut = new MockXAUT();
        address[] memory reg = new address[](1); reg[0] = address(xaut);
        quarantine = new QuarantineVault(g, reg, 7 days);
        reserve = new GoldReserveV2(g, address(quarantine), address(xaut), address(0), 7 days, 6 hours);
        bridge = _deployBridge(TEST_METHODOLOGY, _single(authAddr), 1);
        token = bridge.token();
        xaut.mint(user, 100e6);
        vm.prank(user); xaut.approve(address(bridge), type(uint256).max);
    }

    function _single(address a) internal pure returns (address[] memory r) { r = new address[](1); r[0] = a; }

    function _params(bytes32 methodology) internal pure returns (SOSTBridge.Params memory p) {
        p = SOSTBridge.Params({
            minConfirmations: 30,
            perMintCap: 1_000_000e8,
            dailyMintCap: 5_000_000e8,
            exposureCap: 20_000_000e8,
            maxPriceAge: 15 minutes,
            maxAuthTtl: 1 hours,
            minXautEur8: 1_000e8,
            maxXautEur8: 10_000e8,
            minSostEur8: 100,
            maxSostEur8: 100e8,
            maxDeviationBps: 500,
            approvedMethodology: methodology,
            minReleaseStocks: 1e6,
            releaseNetworkFeeStocks: 1e4
        });
    }

    function _cfg(bytes32 methodology, address[] memory auths, uint8 thr) internal view returns (SOSTBridge.Config memory c) {
        c.admin = admin; c.authorizers = auths; c.threshold = thr; c.priceSigner = priceAddr;
        c.pausers = _single(pauser); c.p = _params(methodology);
    }

    function _deployBridge(bytes32 methodology, address[] memory auths, uint8 thr) internal returns (SOSTBridge b) {
        b = new SOSTBridge(address(xaut), address(reserve), keccak256(bytes(VAULT_ADDR)), _cfg(methodology, auths, thr));
    }

    function _quote(uint256 x, uint256 s) internal view returns (SOSTBridge.PriceQuote memory q) {
        q = SOSTBridge.PriceQuote({xautEur8: x, sostEur8: s, methodology: TEST_METHODOLOGY, observedAt: uint64(block.timestamp), quoteId: keccak256(abi.encode(x, s, block.timestamp))});
    }

    function _auth(SOSTBridge b, uint256 amount, bytes32 txid, uint32 vout, SOSTBridge.PriceQuote memory q)
        internal returns (SOSTBridge.MintAuthorization memory a)
    {
        uint256 fee = (amount * q.sostEur8 >= GoldAccessKey.MIN_OPERATION_EUR8 * 1e8)
            ? GoldAccessKey.feeXautForAmount(amount, q.sostEur8, q.xautEur8) : 0;
        a = SOSTBridge.MintAuthorization({
            requestId: keccak256(abi.encode("req", txid, vout)), recipient: user, amount: amount,
            depositTxid: txid, depositVout: vout, bridgeVault: keccak256(bytes(VAULT_ADDR)),
            sostBlockHash: keccak256(abi.encode("blk", txid)), sostBlockHeight: 41_000, confirmations: 30,
            feeXaut: fee, priceHash: b.priceStructHash(q), expiry: uint64(block.timestamp + 30 minutes), nonce: nextNonce++
        });
    }

    function _sig(uint256 pk, bytes32 digest) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _sigs1(SOSTBridge b, SOSTBridge.MintAuthorization memory a, uint256 pk) internal view returns (bytes[] memory s) {
        s = new bytes[](1); s[0] = _sig(pk, b.mintDigest(a));
    }

    function _psig(SOSTBridge b, SOSTBridge.PriceQuote memory q) internal view returns (bytes memory) {
        return _sig(PRICE_PK, b.priceDigest(q));
    }

    function _mint(SOSTBridge.MintAuthorization memory a, SOSTBridge.PriceQuote memory q) internal {
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        bridge.mint(a, q, s, ps);
    }

    function _mintExpectRevert(SOSTBridge.MintAuthorization memory a, SOSTBridge.PriceQuote memory q, bytes4 sel) internal {
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        vm.expectRevert(sel);
        bridge.mint(a, q, s, ps);
    }
}

contract GoldAccessKeyTest is Test {
    FeeHarness h = new FeeHarness();
    uint256 constant X = 371_313_000_000;   // 1 XAUT = 3,713.13 EUR

    /// The 20 example values (EUR) at 1 XAUT = 3,713.13 EUR, ceiling to 6 decimals.
    /// Expected values computed independently with exact rationals (python fractions).
    function test_feeTable_20_examples() public {
        uint256[20] memory eur = [uint256(0), 10, 50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 7500, 10000, 15000, 25000, 50000, 100000, 500000, 1000000];
        uint256[20] memory units = [uint256(0), 0, 0, 135, 135, 135, 202, 270, 404, 539, 808, 1347, 2020, 2694, 4040, 6733, 13466, 13466, 13466, 13466];
        for (uint256 i = 0; i < 20; i++) {
            if (eur[i] < 100) {
                vm.expectRevert(GoldAccessKey.BelowMinimumOperation.selector);
                h.fee(eur[i] * 1e8, 1, X);
            } else {
                assertEq(h.fee(eur[i] * 1e8, 1, X), units[i], "fee table row");
            }
        }
    }

    function test_feeEur_band() public view {
        assertEq(h.feeEur8(100e8, 1), 50_000_000);         // 0.50 floor
        assertEq(h.feeEur8(750e8, 1), 75_000_000);         // 0.10 %
        assertEq(h.feeEur8(50_000e8, 1), 5_000_000_000);   // exactly 50
        assertEq(h.feeEur8(1_000_000e8, 1), 5_000_000_000); // cap
    }

    function test_minimumBoundary() public {
        vm.expectRevert(GoldAccessKey.BelowMinimumOperation.selector);
        h.fee(100e8 - 1, 1, X);
        assertEq(h.fee(100e8, 1, X), 135);
    }

    function test_zeroPrice_reverts() public {
        vm.expectRevert(GoldAccessKey.ZeroPrice.selector);
        h.fee(1000e8, 1, 0);
    }

    /// Ceiling property: fee is the smallest integer number of XAUT units worth >= the exact EUR fee.
    function testFuzz_feeRounding_isExactCeiling(uint256 amount, uint256 sostEur8, uint256 x) public view {
        amount = bound(amount, 1, 1e17);
        sostEur8 = bound(sostEur8, 1, 1e12);
        x = bound(x, 1e8, 1e14);
        uint256 vNum = amount * sostEur8;
        if (vNum < 100e8 * 1e8) return;
        uint256 f = h.fee(vNum, 1e8, x);
        // exact fee in EUR8 as rational n/d
        uint256 n; uint256 d;
        if (vNum < 5e7 * 1000 * 1e8) { n = 5e7; d = 1; }
        else if (vNum > 5e9 * 1000 * 1e8) { n = 5e9; d = 1; }
        else { n = vNum; d = 1e8 * 1000; }
        // f * x * d >= n * 1e6  and  (f-1) * x * d < n * 1e6
        assertGe(f * x * d, n * 1e6);
        assertLt((f - 1) * x * d, n * 1e6);
        // never more than the 50 EUR cap, never less than the 0.50 EUR floor
        assertLe(f, (5e9 * 1e6 + x - 1) / x);
        assertGe(f, (5e7 * 1e6 + x - 1) / x);
    }

    /// Monotonic in value.
    function testFuzz_feeMonotonic(uint256 v1, uint256 v2) public view {
        v1 = bound(v1, 100e8, 1e20);
        v2 = bound(v2, v1, 1e20);
        assertLe(h.fee(v1, 1, X), h.fee(v2, 1, X));
    }
}

contract SOSTBridgeTest is BridgeBase {
    bytes32 constant TX1 = keccak256("deposit-tx-1");

    // ---------------------------------------------------------------- happy path: one tx, fee -> reserve, exact mint
    function test_mint_oneTx_feeToReserve_exactAmount() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);   // 1,000 SOST = 1,000 EUR (fixture)
        assertEq(a.feeXaut, 270);
        uint256 userX = xaut.balanceOf(user);
        _mint(a, q);
        assertEq(token.balanceOf(user), 1_000e8, "exactly amount wSOST");
        assertEq(token.totalSupply(), 1_000e8);
        assertEq(xaut.balanceOf(address(reserve)), 270, "fee in reserve");
        assertEq(xaut.balanceOf(user), userX - 270);
        assertEq(xaut.balanceOf(address(bridge)), 0, "bridge never holds XAUT");
        assertEq(bridge.totalFeesXaut(), 270);
        assertTrue(bridge.depositUsed(bridge.depositIdOf(TX1, 0)));
    }

    function test_mint_noApprovedMethodology_blocksEverything() public {
        SOSTBridge b = _deployBridge(bytes32(0), _single(authAddr), 1);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(b, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(b, a, AUTH_PK);
        bytes memory ps = _psig(b, q);
        vm.prank(user); xaut.approve(address(b), type(uint256).max);
        vm.prank(user);
        vm.expectRevert(SOSTBridge.NoApprovedValuation.selector);
        b.mint(a, q, s, ps);
    }

    function test_mint_wrongMethodology() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        q.methodology = keccak256("other");
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.WrongMethodology.selector);
    }

    function test_mint_belowMinimumOperation() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 99e8, TX1, 0, q);       // 99 EUR
        a.feeXaut = 135;
        _mintExpectRevert(a, q, SOSTBridge.BelowMinimumOperation.selector);
    }

    function test_mint_feeMismatch() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        a.feeXaut = 269;   // one unit short
        _mintExpectRevert(a, q, SOSTBridge.FeeMismatch.selector);
    }

    // ---------------------------------------------------------------- replay / double mint
    function test_replay_sameAuthorization() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mint(a, q);
        _mintExpectRevert(a, q, SOSTBridge.DepositAlreadyUsed.selector);
        assertEq(token.totalSupply(), 1_000e8);
    }

    function test_doubleMint_sameDeposit_freshNonceAndRequest() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        SOSTBridge.MintAuthorization memory a2 = _auth(bridge, 1_000e8, TX1, 0, q);
        a2.requestId = keccak256("another request");
        _mintExpectRevert(a2, q, SOSTBridge.DepositAlreadyUsed.selector);
    }

    function test_reusedNonce_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mint(a, q);
        SOSTBridge.MintAuthorization memory a2 = _auth(bridge, 1_000e8, keccak256("tx2"), 0, q);
        a2.nonce = a.nonce;
        _mintExpectRevert(a2, q, SOSTBridge.NonceAlreadyUsed.selector);
    }

    function test_reusedRequest_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mint(a, q);
        SOSTBridge.MintAuthorization memory a2 = _auth(bridge, 1_000e8, keccak256("tx2"), 0, q);
        a2.requestId = a.requestId;
        _mintExpectRevert(a2, q, SOSTBridge.RequestAlreadyUsed.selector);
    }

    function test_differentVout_isDifferentDeposit() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        _mint(_auth(bridge, 1_000e8, TX1, 1, q), q);
        assertEq(token.totalSupply(), 2_000e8);
    }

    // ---------------------------------------------------------------- signature binding
    function test_wrongChain_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        vm.chainId(11155111);
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadSignatures.selector);
        bridge.mint(a, q, s, ps);
    }

    function test_wrongContract_rejected() public {
        SOSTBridge other = _deployBridge(TEST_METHODOLOGY, _single(authAddr), 1);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(other, a, AUTH_PK);       // signed for a different verifyingContract
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadSignatures.selector);
        bridge.mint(a, q, s, ps);
    }

    function test_attackerSignature_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, ATTACKER_PK);
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadSignatures.selector);
        bridge.mint(a, q, s, ps);
    }

    function test_priceSignedByAuthorizer_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _sig(AUTH_PK, bridge.priceDigest(q));   // authorizer cannot also be the price oracle
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadPriceSignature.selector);
        bridge.mint(a, q, s, ps);
    }

    function test_mintAuthSignedByPriceSigner_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, PRICE_PK);
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadSignatures.selector);
        bridge.mint(a, q, s, ps);
    }

    /// Any change to any bound field after signing invalidates the authorization.
    function testFuzz_signatureBinding(uint8 field, uint256 delta) public {
        delta = bound(delta, 1, type(uint32).max);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        field = uint8(bound(field, 0, 7));
        if (field == 0) a.recipient = address(uint160(a.recipient) ^ uint160(delta));
        else if (field == 1) a.depositTxid = bytes32(uint256(a.depositTxid) ^ delta);
        else if (field == 2) a.depositVout = uint32(a.depositVout ^ uint32(delta));
        else if (field == 3) a.expiry = uint64(block.timestamp + 1 + (delta % 1800));
        else if (field == 4) a.nonce = a.nonce + delta;
        else if (field == 5) a.requestId = bytes32(uint256(a.requestId) ^ delta);
        else if (field == 6) a.sostBlockHash = bytes32(uint256(a.sostBlockHash) ^ delta);
        else a.confirmations = a.confirmations + uint32(delta % 1000) + 1;
        if (field == 3 && a.expiry == uint64(block.timestamp + 30 minutes)) a.expiry += 1;
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadSignatures.selector);
        bridge.mint(a, q, s, ps);
        assertEq(token.totalSupply(), 0);
        assertEq(xaut.balanceOf(address(reserve)), 0);
    }

    function testFuzz_amountTamper_rejected(uint256 newAmount) public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        newAmount = bound(newAmount, 100e8, 1_000_000e8);
        vm.assume(newAmount != a.amount);
        a.amount = newAmount;
        a.feeXaut = GoldAccessKey.feeXautForAmount(newAmount, SOST_EUR8, XAUT_EUR8);   // even with a "consistent" fee
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadSignatures.selector);
        bridge.mint(a, q, s, ps);
    }

    function test_priceTamper_afterSigning_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        q.xautEur8 = XAUT_EUR8 + 1;    // cheaper fee attempt
        vm.prank(user);
        vm.expectRevert(SOSTBridge.BadPriceHash.selector);
        bridge.mint(a, q, s, ps);
    }

    function test_malleableHighS_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        (uint8 v, bytes32 r, bytes32 sv) = vm.sign(AUTH_PK, bridge.mintDigest(a));
        uint256 n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        bytes[] memory s = new bytes[](1);
        s[0] = abi.encodePacked(r, bytes32(n - uint256(sv)), v == 27 ? uint8(28) : uint8(27));
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        vm.expectRevert();
        bridge.mint(a, q, s, ps);
    }

    // ---------------------------------------------------------------- expiry / price freshness / bounds
    function test_expiredQuote_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        vm.warp(block.timestamp + 30 minutes + 1);
        // even with a FRESH price re-bound and re-signed, the expired authorization is dead
        SOSTBridge.PriceQuote memory q2 = _quote(XAUT_EUR8, SOST_EUR8);
        a.priceHash = bridge.priceStructHash(q2);
        _mintExpectRevert(a, q2, SOSTBridge.Expired.selector);
        // and the stale original quote is refused on its own
        _mintExpectRevert(a, q, SOSTBridge.StalePrice.selector);
    }

    function test_ttlTooLong_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        a.expiry = uint64(block.timestamp + 2 hours);
        _mintExpectRevert(a, q, SOSTBridge.TtlTooLong.selector);
    }

    function test_stalePrice_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        q.observedAt = uint64(block.timestamp - 16 minutes);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.StalePrice.selector);
    }

    function test_futurePrice_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        q.observedAt = uint64(block.timestamp + 1);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.StalePrice.selector);
    }

    function test_priceOutOfBounds_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(20_000e8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.PriceOutOfBounds.selector);
        SOSTBridge.PriceQuote memory q2 = _quote(XAUT_EUR8, 1_000e8);
        SOSTBridge.MintAuthorization memory a2 = _auth(bridge, 1_000e8, TX1, 0, q2);
        _mintExpectRevert(a2, q2, SOSTBridge.PriceOutOfBounds.selector);
    }

    function test_priceDeviation_rejected() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        SOSTBridge.PriceQuote memory q2 = _quote(XAUT_EUR8 * 106 / 100, SOST_EUR8);   // +6 % > 5 %
        SOSTBridge.MintAuthorization memory a2 = _auth(bridge, 1_000e8, keccak256("tx2"), 0, q2);
        _mintExpectRevert(a2, q2, SOSTBridge.PriceDeviation.selector);
        SOSTBridge.PriceQuote memory q3 = _quote(XAUT_EUR8 * 104 / 100, SOST_EUR8);   // +4 % ok
        _mint(_auth(bridge, 1_000e8, keccak256("tx3"), 0, q3), q3);
    }

    function test_notEnoughConfirmations() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        a.confirmations = 29;
        _mintExpectRevert(a, q, SOSTBridge.NotEnoughConfirmations.selector);
    }

    function test_wrongVault() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        a.bridgeVault = keccak256("sost1ffffffffffffffffffffffffffffffffffffffff");
        _mintExpectRevert(a, q, SOSTBridge.BadVault.selector);
    }

    // ---------------------------------------------------------------- caps
    function test_perMintCap() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000_000e8 + 1, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.PerMintCapExceeded.selector);
    }

    function test_dailyCap_thenNextDay() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        xaut.mint(user, 1_000e6);
        for (uint256 i = 0; i < 5; i++) _mint(_auth(bridge, 1_000_000e8, keccak256(abi.encode(i)), 0, q), q);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 100e8, keccak256("over"), 0, q);
        _mintExpectRevert(a, q, SOSTBridge.DailyCapExceeded.selector);
        vm.warp(block.timestamp + 1 days);
        SOSTBridge.PriceQuote memory q2 = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 100e8, keccak256("nextday"), 0, q2), q2);
    }

    function test_exposureCap() public {
        xaut.mint(user, 1_000e6);
        for (uint256 d = 0; d < 4; d++) {
            SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
            for (uint256 i = 0; i < 5; i++) _mint(_auth(bridge, 1_000_000e8, keccak256(abi.encode(d, i)), 0, q), q);
            vm.warp(block.timestamp + 1 days);
        }
        assertEq(token.totalSupply(), 20_000_000e8);
        SOSTBridge.PriceQuote memory q3 = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 100e8, keccak256("over"), 0, q3);
        _mintExpectRevert(a, q3, SOSTBridge.ExposureCapExceeded.selector);
    }

    // ---------------------------------------------------------------- pause
    function test_pause_blocksMint_notBurn() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        vm.prank(pauser); bridge.pauseMint();
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, keccak256("tx2"), 0, q);
        _mintExpectRevert(a, q, SOSTBridge.MintIsPaused.selector);
        vm.prank(user); bridge.burnForRelease(500e8, USER_SOST);      // holders can always exit
        assertEq(token.totalSupply(), 500e8);
        vm.prank(pauser);
        vm.expectRevert(SOSTBridge.NotAdmin.selector);
        bridge.unpauseMint();
        vm.prank(admin); bridge.unpauseMint();
        _mint(a, q);
    }

    function test_pause_strangerCannot() public {
        vm.prank(address(0xBEEF));
        vm.expectRevert(SOSTBridge.NotPauser.selector);
        bridge.pauseMint();
    }

    function test_reservePaused_blocksMint() public {
        bytes32 act = reserve.pauseAction();
        vm.prank(g[0]); reserve.approve(act);
        vm.prank(g[1]); reserve.approve(act);
        reserve.pause();
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.ReserveIsPaused.selector);
        assertFalse(bridge.depositUsed(bridge.depositIdOf(TX1, 0)), "revert rolled back the deposit mark");
    }

    // ---------------------------------------------------------------- XAUT failures: nothing half-done
    function test_insufficientXaut_atomicRevert() public {
        address poor = address(0x5555);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        vm.prank(poor); xaut.approve(address(bridge), type(uint256).max);
        vm.prank(poor);
        vm.expectRevert(SOSTBridge.FeeTransferFailed.selector);
        bridge.mint(a, q, s, ps);
        assertEq(token.totalSupply(), 0);
        assertFalse(bridge.depositUsed(bridge.depositIdOf(TX1, 0)));
        _mint(a, q);   // the same authorization still works for a payer with XAUT
        assertEq(token.balanceOf(user), 1_000e8);
    }

    function test_noAllowance_atomicRevert() public {
        vm.prank(user); xaut.approve(address(bridge), 0);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.FeeTransferFailed.selector);
        assertEq(token.totalSupply(), 0);
    }

    function test_frozenXaut_atomicRevert() public {
        xaut.freeze();
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.FeeTransferFailed.selector);
    }

    // ---------------------------------------------------------------- refund guard
    function test_revoke_thenMintImpossible() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        vm.prank(authAddr); bridge.revokeDeposit(TX1, 0, keccak256("amount mismatch"));
        assertTrue(bridge.depositRevoked(bridge.depositIdOf(TX1, 0)));
        _mintExpectRevert(a, q, SOSTBridge.DepositAlreadyUsed.selector);
    }

    function test_revoke_afterMint_impossible() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        vm.prank(authAddr);
        vm.expectRevert(SOSTBridge.DepositAlreadyUsed.selector);
        bridge.revokeDeposit(TX1, 0, bytes32(0));
    }

    function test_revoke_strangerCannot() public {
        vm.prank(address(0xBEEF));
        vm.expectRevert(SOSTBridge.NotAuthorizer.selector);
        bridge.revokeDeposit(TX1, 0, bytes32(0));
    }

    // ---------------------------------------------------------------- burn -> release
    function test_burn_release_accounting_anyHolder() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        address buyer = address(0xE7C);             // e.g. bought on an exchange
        vm.prank(user); token.transfer(buyer, 400e8);
        uint256 reserveBefore = xaut.balanceOf(address(reserve));
        vm.prank(buyer);
        bytes32 rid = bridge.burnForRelease(400e8, USER_SOST);
        assertEq(token.totalSupply(), 600e8);
        assertEq(bridge.totalBurned(), 400e8);
        assertEq(bridge.outstandingObligationStocks(), 1_000e8, "supply + pending release");
        assertEq(xaut.balanceOf(address(reserve)), reserveBefore, "no second XAUT payment");
        assertEq(xaut.balanceOf(buyer), 0);
        vm.prank(authAddr); bridge.recordRelease(rid, keccak256("sost-release-tx"));
        assertEq(bridge.outstandingObligationStocks(), 600e8);
        vm.prank(authAddr);
        vm.expectRevert(SOSTBridge.AlreadyReleased.selector);
        bridge.recordRelease(rid, keccak256("again"));
    }

    function test_burn_badAddress_and_minimum() public {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        _mint(_auth(bridge, 1_000e8, TX1, 0, q), q);
        vm.startPrank(user);
        vm.expectRevert(SOSTBridge.BadSostAddress.selector);
        bridge.burnForRelease(10e8, "sost1ABABABABABABABABABABABABABABABABABABABAB");
        vm.expectRevert(SOSTBridge.BadSostAddress.selector);
        bridge.burnForRelease(10e8, "0x1234");
        vm.expectRevert(SOSTBridge.BelowMinimumRelease.selector);
        bridge.burnForRelease(1e4, USER_SOST);
        vm.expectRevert(WSOST.InsufficientBalance.selector);
        bridge.burnForRelease(1_001e8, USER_SOST);
        vm.stopPrank();
    }

    function test_recordRelease_unknown_and_stranger() public {
        vm.prank(authAddr);
        vm.expectRevert(SOSTBridge.UnknownRelease.selector);
        bridge.recordRelease(keccak256("nope"), bytes32(0));
        vm.prank(address(0xBEEF));
        vm.expectRevert(SOSTBridge.NotAuthorizer.selector);
        bridge.recordRelease(keccak256("nope"), bytes32(0));
    }

    function test_tokenMintBurn_onlyBridge() public {
        vm.expectRevert(WSOST.NotBridge.selector);
        token.mint(address(this), 1);
        vm.expectRevert(WSOST.NotBridge.selector);
        token.burn(user, 1);
    }

    function testFuzz_mintBurn_accounting(uint256 m1, uint256 m2, uint256 b1) public {
        m1 = bound(m1, 100e8, 1_000_000e8);
        m2 = bound(m2, 100e8, 1_000_000e8);
        xaut.mint(user, 1_000e6);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a1 = _auth(bridge, m1, keccak256("f1"), 0, q);
        SOSTBridge.MintAuthorization memory a2 = _auth(bridge, m2, keccak256("f2"), 3, q);
        _mint(a1, q); _mint(a2, q);
        b1 = bound(b1, 1e6, m1 + m2);
        vm.prank(user); bridge.burnForRelease(b1, USER_SOST);
        assertEq(token.totalSupply(), m1 + m2 - b1);
        assertEq(bridge.totalMinted() - bridge.totalBurned(), token.totalSupply());
        assertEq(xaut.balanceOf(address(reserve)), a1.feeXaut + a2.feeXaut);
        assertEq(bridge.totalFeesXaut(), a1.feeXaut + a2.feeXaut);
        assertEq(token.balanceOf(user), m1 + m2 - b1, "XAUT never reduced the minted amount");
    }

    // ---------------------------------------------------------------- threshold authorizers (internal HSM split)
    function test_threshold2of3_sortedDistinct() public {
        address[] memory auths = new address[](3);
        auths[0] = vm.addr(AUTH_PK); auths[1] = vm.addr(AUTH2_PK); auths[2] = vm.addr(AUTH3_PK);
        SOSTBridge b = _deployBridge(TEST_METHODOLOGY, auths, 2);
        vm.prank(user); xaut.approve(address(b), type(uint256).max);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(b, 1_000e8, TX1, 0, q);
        bytes32 d = b.mintDigest(a);
        bytes memory ps = _sig(PRICE_PK, b.priceDigest(q));
        (uint256 lo, uint256 hi) = vm.addr(AUTH_PK) < vm.addr(AUTH2_PK) ? (AUTH_PK, AUTH2_PK) : (AUTH2_PK, AUTH_PK);
        bytes[] memory one = new bytes[](1); one[0] = _sig(lo, d);
        vm.prank(user); vm.expectRevert(SOSTBridge.BadSignatures.selector); b.mint(a, q, one, ps);
        bytes[] memory dup = new bytes[](2); dup[0] = _sig(lo, d); dup[1] = _sig(lo, d);
        vm.prank(user); vm.expectRevert(SOSTBridge.BadSignatures.selector); b.mint(a, q, dup, ps);
        bytes[] memory unsorted = new bytes[](2); unsorted[0] = _sig(hi, d); unsorted[1] = _sig(lo, d);
        vm.prank(user); vm.expectRevert(SOSTBridge.BadSignatures.selector); b.mint(a, q, unsorted, ps);
        bytes[] memory ok = new bytes[](2); ok[0] = _sig(lo, d); ok[1] = _sig(hi, d);
        vm.prank(user); b.mint(a, q, ok, ps);
        assertEq(b.token().balanceOf(user), 1_000e8);
    }

    // ---------------------------------------------------------------- timelocked configuration
    function test_config_timelock() public {
        SOSTBridge.Config memory c = _cfg(TEST_METHODOLOGY, _single(vm.addr(AUTH2_PK)), 1);
        vm.prank(address(0xBEEF)); vm.expectRevert(SOSTBridge.NotAdmin.selector); bridge.proposeConfig(c);
        vm.prank(admin); bridge.proposeConfig(c);
        vm.prank(admin); vm.expectRevert(SOSTBridge.ConfigNotReady.selector); bridge.applyConfig(c);
        vm.warp(block.timestamp + 2 days);
        vm.prank(admin); bridge.applyConfig(c);
        assertFalse(bridge.isAuthorizer(authAddr));
        assertTrue(bridge.isAuthorizer(vm.addr(AUTH2_PK)));
        // old key can no longer authorize
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 1_000e8, TX1, 0, q);
        _mintExpectRevert(a, q, SOSTBridge.BadSignatures.selector);
    }

    function test_config_rejectsRoleOverlap() public {
        SOSTBridge.Config memory c = _cfg(TEST_METHODOLOGY, _single(priceAddr), 1);   // authorizer == price signer
        vm.expectRevert(SOSTBridge.BadConfig.selector);
        new SOSTBridge(address(xaut), address(reserve), keccak256(bytes(VAULT_ADDR)), c);
        SOSTBridge.Config memory c2 = _cfg(TEST_METHODOLOGY, _single(admin), 1);      // authorizer == admin
        vm.expectRevert(SOSTBridge.BadConfig.selector);
        new SOSTBridge(address(xaut), address(reserve), keccak256(bytes(VAULT_ADDR)), c2);
    }

    function test_feeOnTransferToken_rejected() public {
        FeeOnTransferXAUT fx = new FeeOnTransferXAUT();
        address[] memory reg = new address[](1); reg[0] = address(fx);
        QuarantineVault qv = new QuarantineVault(g, reg, 7 days);
        GoldReserveV2 r2 = new GoldReserveV2(g, address(qv), address(fx), address(0), 7 days, 6 hours);
        SOSTBridge b = new SOSTBridge(address(fx), address(r2), keccak256(bytes(VAULT_ADDR)), _cfg(TEST_METHODOLOGY, _single(authAddr), 1));
        fx.mint(user, 10e6);
        vm.prank(user); fx.approve(address(b), type(uint256).max);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(b, 1_000e8, TX1, 0, q);
        bytes[] memory s = _sigs1(b, a, AUTH_PK);
        bytes memory ps = _sig(PRICE_PK, b.priceDigest(q));
        vm.prank(user);
        vm.expectRevert(SOSTBridge.FeeTransferFailed.selector);
        b.mint(a, q, s, ps);
    }

    function test_domainSeparator_matchesEip712() public view {
        bytes32 expected = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("SOST Automated Bridge"), keccak256("1"), block.chainid, address(bridge)));
        assertEq(bridge.DOMAIN_SEPARATOR(), expected);
    }
}

/// Invariant: wSOST supply == minted - burned, and Gold Reserve V2 XAUT == sum of all Gold Access Keys.
contract BridgeHandler is BridgeBase {
    uint256 public ghostFees;
    uint256 public calls;
    constructor(SOSTBridge b, MockXAUT x, GoldReserveV2 r) {
        bridge = b; token = b.token(); xaut = x; reserve = r;
        authAddr = vm.addr(AUTH_PK); priceAddr = vm.addr(PRICE_PK);
    }
    function setUp() public override {}
    function mintSome(uint256 amount, uint256 salt) external {
        amount = bound(amount, 100e8, 100_000e8);
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        SOSTBridge.MintAuthorization memory a = _auth(bridge, amount, keccak256(abi.encode(calls++)), 0, q);
        salt;
        if (token.totalSupply() + amount > 20_000_000e8 || bridge.mintedOnDay(block.timestamp / 1 days) + amount > 5_000_000e8) return;
        _mint(a, q);
        ghostFees += a.feeXaut;
    }
    function burnSome(uint256 amount) external {
        uint256 bal = token.balanceOf(user);
        if (bal < 1e6) return;
        amount = bound(amount, 1e6, bal);
        vm.prank(user); bridge.burnForRelease(amount, USER_SOST);
    }
    function tryReplay(uint256 salt) external {
        SOSTBridge.PriceQuote memory q = _quote(XAUT_EUR8, SOST_EUR8);
        if (calls == 0) return;
        bytes32 tx_ = keccak256(abi.encode(salt % calls));
        if (!bridge.depositUsed(bridge.depositIdOf(tx_, 0))) return;
        SOSTBridge.MintAuthorization memory a = _auth(bridge, 100e8, tx_, 0, q);
        bytes[] memory s = _sigs1(bridge, a, AUTH_PK);
        bytes memory ps = _psig(bridge, q);
        vm.prank(user);
        try bridge.mint(a, q, s, ps) { revert("replay minted"); } catch {}
    }
}

contract SOSTBridgeInvariantTest is BridgeBase {
    BridgeHandler handler;
    function setUp() public override {
        super.setUp();
        xaut.mint(user, 1_000_000e6);
        handler = new BridgeHandler(bridge, xaut, reserve);
        targetContract(address(handler));
        bytes4[] memory sels = new bytes4[](3);
        sels[0] = BridgeHandler.mintSome.selector; sels[1] = BridgeHandler.burnSome.selector; sels[2] = BridgeHandler.tryReplay.selector;
        targetSelector(FuzzSelector({addr: address(handler), selectors: sels}));
    }
    function invariant_supplyEqualsMintedMinusBurned() public view {
        assertEq(token.totalSupply(), bridge.totalMinted() - bridge.totalBurned());
    }
    function invariant_reserveEqualsFees() public view {
        assertEq(xaut.balanceOf(address(reserve)), bridge.totalFeesXaut());
        assertEq(bridge.totalFeesXaut(), handler.ghostFees());
        assertEq(xaut.balanceOf(address(bridge)), 0);
    }
}
