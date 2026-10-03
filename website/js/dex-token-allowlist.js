/*
 * SOST DEX — TOKEN ALLOWLIST (section 7).
 * ===========================================================================
 * The canonical, per-chainId allowlist of assets the DEX will route. A token is
 * identified by its (chainId, contractAddress) — NEVER by the symbol/name a
 * wallet (e.g. MetaMask) reports, which is attacker-controlled. A token whose
 * symbol is "USDC" but whose contract is NOT the exact allowlisted one is
 * REJECTED. USDT / PAXG / XAUT are DISABLED. ETH is the chain-native asset.
 *
 * Entry shape:
 *   { chainId, contractAddress, symbol, decimals, token_type, compatibility_mode,
 *     tested_version, status, last_verified, code_hash? }
 * Statuses: SUPPORTED | SUPPORTED_WITH_HANDLING | DISABLED | UNVERIFIED.
 *
 * Pure web/lab. No consensus/node/STRATO change. Mainnet contract addresses for
 * DISABLED tokens are intentionally null (nothing is pinned for something we do
 * not route); a real USDC contract is pinned per-chainId where authorized.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexTokenAllowlist = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var STATUS = {
    SUPPORTED: 'SUPPORTED',
    SUPPORTED_WITH_HANDLING: 'SUPPORTED_WITH_HANDLING',
    DISABLED: 'DISABLED',
    UNVERIFIED: 'UNVERIFIED'
  };
  var NATIVE = '(native)'; // sentinel contractAddress for a chain-native asset

  function norm(a) { return String(a == null ? '' : a).trim().toLowerCase(); }

  // Canonical table. Keyed implicitly by (chainId, symbol); the contractAddress
  // is the real identity. Mainnet USDC is pinned to the exact Circle contract.
  var ENTRIES = [
    // ---- chainId 1 (Ethereum mainnet) — reference only (NOT deployed/traded) ----
    { chainId: 1, contractAddress: NATIVE, symbol: 'ETH', decimals: 18, token_type: 'native',
      compatibility_mode: 'native-value', tested_version: 'AtomicSwapHTLCv2', status: STATUS.SUPPORTED,
      last_verified: '2026-09-01' },
    { chainId: 1, contractAddress: '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', symbol: 'USDC', decimals: 6, token_type: 'erc20',
      compatibility_mode: 'standard-erc20', tested_version: 'AtomicSwapHTLCv2', status: STATUS.SUPPORTED_WITH_HANDLING,
      last_verified: '2026-09-01' },
    // DISABLED tokens: nothing pinned (we do not route them) — contract null on purpose.
    { chainId: 1, contractAddress: null, symbol: 'USDT', decimals: 6, token_type: 'erc20',
      compatibility_mode: 'no-return-value', tested_version: null, status: STATUS.DISABLED,
      last_verified: null, reason: 'USDT transfer returns no boolean — needs SafeERC20-style handling before enable' },
    { chainId: 1, contractAddress: null, symbol: 'PAXG', decimals: 18, token_type: 'erc20',
      compatibility_mode: 'fee-on-transfer', tested_version: null, status: STATUS.DISABLED,
      last_verified: null, reason: 'PAXG fee-on-transfer breaks fixed-amount escrow — needs balance-delta accounting' },
    { chainId: 1, contractAddress: null, symbol: 'XAUT', decimals: 6, token_type: 'erc20',
      compatibility_mode: 'unverified', tested_version: null, status: STATUS.DISABLED,
      last_verified: null, reason: 'XAUT real-contract behaviour not verified on a pinned fork' },

    // ---- chainId 31337 (Anvil devnet) ----
    { chainId: 31337, contractAddress: NATIVE, symbol: 'ETH', decimals: 18, token_type: 'native',
      compatibility_mode: 'native-value', tested_version: 'AtomicSwapHTLCv2', status: STATUS.SUPPORTED,
      last_verified: '2026-09-01' }
    // devnet USDC (if any) is added via registerFromConfig(DEVNET) — its exact
    // mock contract address is pinned from the local config, never assumed.
  ];

  function all() { return ENTRIES.slice(); }

  // Add/replace a devnet ERC20 entry from the pinned local config (exact address).
  function registerFromConfig(cfg) {
    cfg = cfg || {};
    var cid = cfg.evm_chain_id;
    var usdc = cfg.usdc_token || (cfg.tokens && cfg.tokens.USDC);
    if (cid && usdc) {
      upsert({ chainId: cid, contractAddress: norm(usdc), symbol: 'USDC', decimals: 6, token_type: 'erc20',
        compatibility_mode: 'standard-erc20', tested_version: 'AtomicSwapHTLCv2', status: STATUS.SUPPORTED_WITH_HANDLING,
        last_verified: 'devnet-config' });
    }
    return ENTRIES;
  }
  function upsert(e) {
    for (var i = 0; i < ENTRIES.length; i++) {
      if (ENTRIES[i].chainId === e.chainId && norm(ENTRIES[i].contractAddress) === norm(e.contractAddress) && ENTRIES[i].symbol === e.symbol) {
        ENTRIES[i] = e; return e;
      }
    }
    ENTRIES.push(e); return e;
  }

  // Lookup by the REAL identity (chainId + contractAddress). Native assets use
  // the NATIVE sentinel. Returns the entry or null.
  function lookupByContract(chainId, contractAddress) {
    var c = (contractAddress == null || contractAddress === NATIVE) ? NATIVE : norm(contractAddress);
    for (var i = 0; i < ENTRIES.length; i++) {
      if (ENTRIES[i].chainId === chainId && norm(ENTRIES[i].contractAddress) === norm(c)) return ENTRIES[i];
    }
    return null;
  }
  // The authorized entry for a symbol on a chain (there is at most ONE routable one).
  function authorizedFor(chainId, symbol) {
    var sym = String(symbol || '').toUpperCase();
    for (var i = 0; i < ENTRIES.length; i++) {
      if (ENTRIES[i].chainId === chainId && ENTRIES[i].symbol === sym && ENTRIES[i].status !== STATUS.DISABLED && ENTRIES[i].status !== STATUS.UNVERIFIED) return ENTRIES[i];
    }
    return null;
  }

  // THE GUARD. Decide whether (chainId, symbol, contractAddress, decimals?) may be
  // routed. NEVER trusts the wallet-reported symbol: the contract is the identity.
  //   - native asset: pass contractAddress NATIVE/null and a native symbol.
  //   - a DISABLED symbol is always rejected.
  //   - symbol 'USDC' with a contract != the allowlisted one => REJECT (fake token).
  //   - a decimals mismatch vs the pinned entry => REJECT.
  function checkToken(chainId, symbol, contractAddress, decimals) {
    var sym = String(symbol || '').toUpperCase();
    var isNative = (contractAddress == null || contractAddress === NATIVE);

    // 1) explicitly disabled symbol (regardless of contract)
    var disabled = null;
    for (var i = 0; i < ENTRIES.length; i++) {
      if (ENTRIES[i].chainId === chainId && ENTRIES[i].symbol === sym && ENTRIES[i].status === STATUS.DISABLED) { disabled = ENTRIES[i]; break; }
    }
    if (disabled) return { ok: false, status: STATUS.DISABLED, reason: sym + ' is DISABLED on chainId ' + chainId + (disabled.reason ? ' — ' + disabled.reason : '') };

    // 2) identify by the REAL contract on this chain
    var byContract = lookupByContract(chainId, contractAddress);

    if (isNative) {
      if (!byContract) return { ok: false, status: 'UNKNOWN', reason: 'no native asset allowlisted on chainId ' + chainId };
      if (byContract.symbol !== sym) return { ok: false, status: 'MISMATCH', reason: 'native asset on chainId ' + chainId + ' is ' + byContract.symbol + ', not ' + sym };
    } else {
      // ERC20: the contract MUST be the exact allowlisted one for this symbol.
      var authorized = authorizedFor(chainId, sym);
      if (!authorized) return { ok: false, status: 'UNKNOWN', reason: 'no routable ' + sym + ' allowlisted on chainId ' + chainId };
      if (norm(authorized.contractAddress) !== norm(contractAddress)) {
        return { ok: false, status: 'FAKE_TOKEN', reason: 'contract ' + contractAddress + ' claims to be ' + sym + ' but the ONLY authorized ' + sym + ' on chainId ' + chainId + ' is ' + authorized.contractAddress + ' — rejecting (wallet symbol is not trusted)' };
      }
      byContract = authorized;
    }

    // 3) decimals must match the pinned entry (escrow correctness)
    if (decimals != null && Number(decimals) !== Number(byContract.decimals)) {
      return { ok: false, status: 'DECIMALS_MISMATCH', reason: sym + ' decimals ' + decimals + ' != pinned ' + byContract.decimals + ' on chainId ' + chainId + ' — rejecting' };
    }

    if (byContract.status === STATUS.UNVERIFIED) return { ok: false, status: STATUS.UNVERIFIED, reason: sym + ' is UNVERIFIED on chainId ' + chainId };
    return { ok: true, status: byContract.status, entry: byContract,
      handling: byContract.status === STATUS.SUPPORTED_WITH_HANDLING ? (byContract.reason || byContract.compatibility_mode) : null };
  }

  return {
    STATUS: STATUS, NATIVE: NATIVE, all: all,
    registerFromConfig: registerFromConfig, upsert: upsert,
    lookupByContract: lookupByContract, authorizedFor: authorizedFor, checkToken: checkToken
  };
});
