/* SOST Atomic Swap — EVM operative layer (founder-only, EVM-only; BTC deferred to V15).
 *
 * Dependency-free ABI codec for the real AtomicSwapHTLC contract. Every function the console
 * calls takes ONLY static 32-byte words (bytes32 / uint256 / address) — no dynamic types — so a
 * tiny hand-rolled encoder is exact and fully auditable (no 300KB library, no CDN, no supply-chain
 * risk). Selectors + event topics were computed with foundry `cast` from the real signatures in
 * contracts/atomic-swap/src/AtomicSwapHTLC.sol and must match it exactly.
 *
 * This module NEVER touches keys: it only builds calldata / parses return data. Signing +
 * broadcasting is done by the user's wallet (window.ethereum). Works in browser (window.ASWEVM)
 * and node (module.exports) so the codec is unit-testable.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ASWEVM = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // --- function selectors (from `cast sig`, against the real contract) ---
  var SEL = {
    lockNative: '0xbef939c1',   // lockNative(bytes32,bytes32,uint256,address,address)
    lockERC20:  '0x9cbaca50',   // lockERC20(bytes32,address,uint256,bytes32,uint256,address,address)
    claim:      '0x84cc9dfb',   // claim(bytes32,bytes32)
    refund:     '0x7249fbb6',   // refund(bytes32)
    getSwap:    '0x3da0e66e',   // getSwap(bytes32)
    approve:    '0x095ea7b3',   // approve(address,uint256)
    allowance:  '0xdd62ed3e',   // allowance(address,address)
    balanceOf:  '0x70a08231',   // balanceOf(address)
    decimals:   '0x313ce567',   // decimals()
    symbol:     '0x95d89b41'    // symbol()
  };

  // --- event topics (from `cast keccak`) ---
  var TOPIC = {
    LockCreated: '0x9724e5c4686b91fb671f4d4e23bb839305c31c6a1a529cdfae6013efccdf41b3',
    Claimed:     '0x0015b3054220238c69ba4e7f52013731fcb4fb9682ad1c2c1aedfb77353db201',
    Refunded:    '0x5e9f0820fcfb53b644becb775b651bae68c337106f21433e526551d1e02c1c0e'
  };

  var STATE = ['NONE', 'LOCKED', 'CLAIMED', 'REFUNDED'];

  // --- network + asset config. htlc=null => NOT DEPLOYED/configured => operations disabled.
  // Token addresses are REFERENCES for mainnet; the console MUST read symbol()+decimals() live
  // and the operator MUST verify on the official explorer. Never assume 18 decimals.
  var NETWORKS = {
    '0x1': {
      name: 'Ethereum', native: 'ETH', explorerTx: 'https://etherscan.io/tx/',
      blockTimeSec: 12, htlc: null,
      tokens: {
        USDT: { address: '0xdAC17F958D2ee523a2206206994597C13D831ec7' },
        USDC: { address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48' },
        PAXG: { address: '0x45804880De22913dAFE09f4980848ECE6EcbAf78' },
        XAUT: { address: '0x68749665FF8D2d112Fa859AA293F07A622782F38' }
      }
    },
    '0x38': {
      name: 'BNB Chain', native: 'BNB', explorerTx: 'https://bscscan.com/tx/',
      blockTimeSec: 3, htlc: null,
      tokens: {
        USDT: { address: '0x55d398326f99059fF775485246999027B3197955' },
        USDC: { address: '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d' }
      }
    }
  };

  // testnets (native-only) — recommended for first real tests before mainnet
  NETWORKS['0xaa36a7'] = { name: 'Sepolia (testnet)', native: 'ETH',
    explorerTx: 'https://sepolia.etherscan.io/tx/', blockTimeSec: 12, htlc: null, tokens: {} };
  NETWORKS['0x61'] = { name: 'BNB Chain testnet', native: 'tBNB',
    explorerTx: 'https://testnet.bscscan.com/tx/', blockTimeSec: 3, htlc: null, tokens: {} };

  // Native-first policy. ERC-20 is DISABLED by default: the minimal HTLC does not handle weird
  // tokens (no-bool return reverts at lock; fee-on-transfer gets STUCK) — the UI must enforce this.
  // Flip to true only after SafeERC20 wrapping + balance-delta accounting + tests are in place.
  var ERC20_ENABLED = false;

  // issuer-freeze warning (mirrors the contract comment)
  var FREEZE_RISK = ['USDT', 'USDC', 'PAXG', 'XAUT'];
  // fee-on-transfer tokens are UNSUPPORTED by the contract (funds get stuck) — hard blacklist.
  // PAXG (Paxos Gold) charges an on-chain transfer fee → never lock it in this HTLC.
  var FEE_ON_TRANSFER = ['PAXG'];

  // compare on-chain code to the repo build. expectedRuntime = ASW_HTLC_RUNTIME (vendored).
  function verifyCode(codeHex, expectedRuntime) {
    if (!codeHex || codeHex === '0x' || codeHex === '0x0') return 'EMPTY';
    if (!expectedRuntime) return 'UNKNOWN';
    return (codeHex.toLowerCase() === expectedRuntime.toLowerCase()) ? 'EXACT' : 'DIFFERS';
  }

  // ---------------- low-level hex/abi helpers ----------------
  function strip0x(h) { return (h || '').replace(/^0x/i, ''); }
  function isHexLen(h, n) { h = strip0x(h); return new RegExp('^[0-9a-fA-F]{' + n + '}$').test(h); }
  function isBytes32(h) { return isHexLen(h, 64); }
  function isAddress(h) { return isHexLen(h, 40); }

  function pad32(hexNo0x) {
    hexNo0x = hexNo0x.toLowerCase();
    if (hexNo0x.length > 64) throw new Error('word too long');
    while (hexNo0x.length < 64) hexNo0x = '0' + hexNo0x;
    return hexNo0x;
  }
  function encBytes32(h) {
    if (!isBytes32(h)) throw new Error('expected 32-byte hex');
    return strip0x(h).toLowerCase();
  }
  function encAddress(a) {
    if (!isAddress(a)) throw new Error('expected 20-byte address');
    return pad32(strip0x(a));
  }
  function encUint(v) { // v: decimal string | number | bigint
    var b = (typeof v === 'bigint') ? v : BigInt(v);
    if (b < 0n) throw new Error('negative uint');
    return pad32(b.toString(16));
  }
  function buildCall(selector, words) {
    return strip0x(selector) + words.join('');   // selector carries 0x; callers add a single 0x
  }

  // amount (human decimal string) -> base-unit BigInt, exact (no float). decimals = integer.
  function toBaseUnits(amountStr, decimals) {
    amountStr = String(amountStr).trim();
    if (!/^\d+(\.\d+)?$/.test(amountStr)) throw new Error('bad amount');
    var parts = amountStr.split('.');
    var whole = parts[0], frac = parts[1] || '';
    if (frac.length > decimals) throw new Error('too many decimals for this token (' + decimals + ')');
    frac = (frac + '0'.repeat(decimals)).slice(0, decimals);
    return BigInt(whole + (decimals ? frac : ''));
  }
  function fromBaseUnits(baseStr, decimals) {
    var b = BigInt(baseStr).toString();
    if (decimals === 0) return b;
    while (b.length <= decimals) b = '0' + b;
    var i = b.length - decimals;
    return (b.slice(0, i) + '.' + b.slice(i)).replace(/\.?0+$/, '') || '0';
  }

  // ---------------- calldata builders (return 0x… hex) ----------------
  function dataLockNative(swapId, hashlock, refundTime, claimer, refunder) {
    return '0x' + buildCall(SEL.lockNative, [
      encBytes32(swapId), encBytes32(hashlock), encUint(refundTime),
      encAddress(claimer), encAddress(refunder)]);
  }
  function dataLockERC20(swapId, token, amountBase, hashlock, refundTime, claimer, refunder) {
    return '0x' + buildCall(SEL.lockERC20, [
      encBytes32(swapId), encAddress(token), encUint(amountBase), encBytes32(hashlock),
      encUint(refundTime), encAddress(claimer), encAddress(refunder)]);
  }
  function dataClaim(swapId, preimage) {
    return '0x' + buildCall(SEL.claim, [encBytes32(swapId), encBytes32(preimage)]);
  }
  function dataRefund(swapId) {
    return '0x' + buildCall(SEL.refund, [encBytes32(swapId)]);
  }
  function dataGetSwap(swapId) {
    return '0x' + buildCall(SEL.getSwap, [encBytes32(swapId)]);
  }
  function dataApprove(spender, amountBase) {
    return '0x' + buildCall(SEL.approve, [encAddress(spender), encUint(amountBase)]);
  }
  function dataAllowance(owner, spender) {
    return '0x' + buildCall(SEL.allowance, [encAddress(owner), encAddress(spender)]);
  }
  function dataBalanceOf(owner) {
    return '0x' + buildCall(SEL.balanceOf, [encAddress(owner)]);
  }
  function dataDecimals() { return SEL.decimals; }
  function dataSymbol() { return SEL.symbol; }

  // ---------------- return-data decoders ----------------
  function word(hex, i) { hex = strip0x(hex); return hex.slice(i * 64, i * 64 + 64); }
  function decUint(hex) { var h = strip0x(hex); return h ? BigInt('0x' + h).toString() : '0'; }
  function decAddressWord(w) { return '0x' + w.slice(24); }

  // getSwap returns the static tuple (state,token,amount,hashlock,refundTime,claimer,refunder)
  function decodeGetSwap(retHex) {
    var h = strip0x(retHex);
    if (h.length < 64 * 7) throw new Error('short getSwap return');
    var stateIdx = parseInt(word(h, 0).slice(-2) || '0', 16);
    return {
      state: STATE[stateIdx] || ('UNKNOWN(' + stateIdx + ')'),
      stateIndex: stateIdx,
      token: decAddressWord(word(h, 1)),
      amountBase: BigInt('0x' + word(h, 2)).toString(),
      hashlock: '0x' + word(h, 3),
      refundTime: BigInt('0x' + word(h, 4)).toString(),
      claimer: decAddressWord(word(h, 5)),
      refunder: decAddressWord(word(h, 6))
    };
  }

  // classify a swap for the dashboard given current EVM block number
  function classifySwap(sw, currentBlock) {
    if (!sw || sw.stateIndex === 0) return 'NONE';
    if (sw.stateIndex === 2) return 'CLAIMED';
    if (sw.stateIndex === 3) return 'REFUNDED';
    // LOCKED:
    var rt = BigInt(sw.refundTime), cb = BigInt(currentBlock);
    return (cb < rt) ? 'CLAIMABLE' : 'REFUNDABLE';
  }

  return {
    SEL: SEL, TOPIC: TOPIC, STATE: STATE, NETWORKS: NETWORKS, FREEZE_RISK: FREEZE_RISK,
    ERC20_ENABLED: ERC20_ENABLED, FEE_ON_TRANSFER: FEE_ON_TRANSFER, verifyCode: verifyCode,
    strip0x: strip0x, isBytes32: isBytes32, isAddress: isAddress,
    toBaseUnits: toBaseUnits, fromBaseUnits: fromBaseUnits,
    dataLockNative: dataLockNative, dataLockERC20: dataLockERC20, dataClaim: dataClaim,
    dataRefund: dataRefund, dataGetSwap: dataGetSwap, dataApprove: dataApprove,
    dataAllowance: dataAllowance, dataBalanceOf: dataBalanceOf, dataDecimals: dataDecimals,
    dataSymbol: dataSymbol, decUint: decUint, decodeGetSwap: decodeGetSwap, classifySwap: classifySwap
  };
}));
