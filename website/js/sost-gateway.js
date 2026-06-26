/* SOST Payment Gateway — wallet skeleton (OFF by default).
 *
 * DESIGN/SKELETON ONLY. This module is INERT:
 *   - It NEVER moves funds, NEVER signs, NEVER touches the network, NEVER stores secrets.
 *   - Everything is gated behind feature flags that default to false.
 *
 * Modules are kept SEPARATE BY RISK on purpose. They may share small validation helpers,
 * but PAY (simple send), ESCROW (conditional lock), SWAP (cross-chain HTLC) and POPC_BOND
 * (guarantee with possible slashing) are distinct objects so a bug in one cannot reach the
 * others. See docs/SOST_GATEWAY_WALLET_ARCHITECTURE.md.
 *
 * Browser global: window.SOSTGateway.  Node: require('./sost-gateway.js').
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.SOSTGateway = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ---- Feature flags (ALL false = nothing visible, nothing active) ----------
  var FLAGS = {
    SOST_GATEWAY_ENABLED: false,            // master: hides the whole panel
    SOST_GATEWAY_HOLD_ENABLED: false,
    SOST_GATEWAY_PAY_ENABLED: false,
    SOST_GATEWAY_ESCROW_ENABLED: false,
    SOST_GATEWAY_ATOMIC_SWAP_ENABLED: false,
    SOST_GATEWAY_POPC_BOND_ENABLED: false
  };

  function flags() {
    var f = {};
    for (var k in FLAGS) { if (FLAGS.hasOwnProperty(k)) f[k] = FLAGS[k]; }
    return f;
  }
  // Test/dev helper only — production ships with all false.
  function _setFlags(patch) {
    for (var k in patch) { if (FLAGS.hasOwnProperty(k)) FLAGS[k] = !!patch[k]; }
    return flags();
  }
  function gatewayVisible() { return FLAGS.SOST_GATEWAY_ENABLED === true; }

  // Friendly dev/test override → internal flag names. The base library always ships OFF;
  // a page (or dev console) may set window.SOST_GATEWAY_CONFIG to flip flags WITHOUT editing
  // this file. If the global is absent, production stays fully invisible.
  var CONFIG_MAP = {
    enabled: 'SOST_GATEWAY_ENABLED',
    hold: 'SOST_GATEWAY_HOLD_ENABLED',
    pay: 'SOST_GATEWAY_PAY_ENABLED',
    escrow: 'SOST_GATEWAY_ESCROW_ENABLED',
    swap: 'SOST_GATEWAY_ATOMIC_SWAP_ENABLED',
    popcBond: 'SOST_GATEWAY_POPC_BOND_ENABLED'
  };
  function applyConfig(cfg) {
    if (!cfg || typeof cfg !== 'object') return flags();
    var patch = {};
    for (var key in CONFIG_MAP) {
      if (CONFIG_MAP.hasOwnProperty(key) && cfg.hasOwnProperty(key)) patch[CONFIG_MAP[key]] = !!cfg[key];
    }
    return _setFlags(patch);
  }

  // ---- Shared validation helpers (format pre-checks only; the authoritative ----
  // ---- check is the node's validateaddress RPC, which this skeleton never calls) -
  var STOCKS_PER_SOST = 100000000;          // 1 SOST = 1e8 stocks (8 decimals)
  var ADDR_RE = /^sost[13][0-9a-f]{40}$/;   // sost1 = P2PKH, sost3 = P2SH; 40 hex chars

  function validateAddress(a) {
    if (typeof a !== 'string') return { ok: false, reason: 'address must be a string' };
    if (!ADDR_RE.test(a)) return { ok: false, reason: 'not a valid sost1/sost3 address (expect prefix + 40 hex)' };
    return { ok: true };
  }

  // Returns { ok, stocks } or { ok:false, reason }. No floats in the result (integer stocks).
  function validateAmount(s) {
    var str = (typeof s === 'number') ? String(s) : s;
    if (typeof str !== 'string' || str.trim() === '') return { ok: false, reason: 'amount required' };
    str = str.trim();
    if (!/^\d+(\.\d{1,8})?$/.test(str)) return { ok: false, reason: 'amount must be a positive number with at most 8 decimals' };
    var parts = str.split('.');
    var whole = parts[0], frac = (parts[1] || '');
    while (frac.length < 8) frac += '0';
    var stocks = Number(whole) * STOCKS_PER_SOST + Number(frac);
    if (!isFinite(stocks) || stocks <= 0) return { ok: false, reason: 'amount must be greater than zero' };
    if (stocks > Number.MAX_SAFE_INTEGER) return { ok: false, reason: 'amount too large' };
    return { ok: true, stocks: stocks };
  }

  // Optional payment reference/memo: printable ASCII, no control chars, <= 64 chars.
  function validateReference(r) {
    if (r == null || r === '') return { ok: true, reference: '' };
    if (typeof r !== 'string') return { ok: false, reason: 'reference must be a string' };
    if (r.length > 64) return { ok: false, reason: 'reference too long (max 64)' };
    if (!/^[\x20-\x7E]*$/.test(r)) return { ok: false, reason: 'reference has non-printable characters' };
    return { ok: true, reference: r };
  }

  // ===========================================================================
  // HOLD — prove you hold SOST. No funds move. Reuses the existing sign-message.
  // Lowest risk. This object NEVER signs and NEVER holds a key.
  // ===========================================================================
  var Hold = {
    isEnabled: function () { return gatewayVisible() && FLAGS.SOST_GATEWAY_HOLD_ENABLED === true; },
    // The exact JSON shape the wallet's geaSignMessage() produces — for UI preview only.
    // Contains NO private key / seed. Signing itself is delegated to window.geaSignMessage.
    proofShape: function () {
      return ['address', 'pubkey', 'signature_der', 'message_sha256', 'timestamp'];
    },
    describe: function () {
      return 'Sign a challenge; the API reads your on-chain balance. No payment, no key sent, ' +
             'token expires so access cannot outlive your holding.';
    }
  };

  // ===========================================================================
  // PAY — buy access with SOST. Simple send, kept fully separate from ESCROW.
  // Skeleton builds DUMMY intents and previews verification locally; no network.
  // ===========================================================================
  var Pay = {
    isEnabled: function () { return gatewayVisible() && FLAGS.SOST_GATEWAY_PAY_ENABLED === true; },
    STATES: ['draft', 'signed', 'broadcast', 'paid', 'underpaid', 'wrong_destination',
             'insufficient_confirmations', 'expired'],
    // Build a DUMMY payment intent (kind:'dummy'). Throws on invalid input. No network.
    createDummyIntent: function (o) {
      o = o || {};
      var a = validateAddress(o.destination); if (!a.ok) throw new Error('destination: ' + a.reason);
      var m = validateAmount(o.amount_sost); if (!m.ok) throw new Error('amount: ' + m.reason);
      var r = validateReference(o.reference); if (!r.ok) throw new Error('reference: ' + r.reason);
      var conf = (o.required_confirmations == null) ? 3 : o.required_confirmations;
      if (!(Number.isInteger(conf) && conf >= 1 && conf <= 100)) throw new Error('required_confirmations: 1..100');
      return {
        kind: 'dummy',
        merchant: String(o.merchant || 'GeaSpirit'),
        concept: String(o.concept || ''),
        amount_sost: m.stocks / STOCKS_PER_SOST,
        amount_stocks: m.stocks,
        destination: o.destination,
        reference: r.reference,
        required_confirmations: conf,
        expires_at: (o.expires_at == null ? 0 : o.expires_at),
        state: 'draft'
      };
    },
    // Pure local preview of PAY v1 verification: by destination + amount + confirmations.
    // `observed` is dummy data the UI supplies; this NEVER queries the chain.
    evaluateLocal: function (intent, observed, now) {
      observed = observed || {}; now = (now == null ? 0 : now);
      if (intent.expires_at && now > intent.expires_at) return 'expired';
      var paidToDest = 0, outs = observed.outputs || [];
      for (var i = 0; i < outs.length; i++) {
        if (outs[i].address === intent.destination) paidToDest += Number(outs[i].amount_stocks || 0);
      }
      if (paidToDest === 0) return 'wrong_destination';
      if (paidToDest < intent.amount_stocks) return 'underpaid';
      if (Number(observed.confirmations || 0) < intent.required_confirmations) return 'insufficient_confirmations';
      return 'paid';
    }
  };

  // ===========================================================================
  // ESCROW — lock SOST as a guarantee. Conditional lock, separate from PAY.
  // Skeleton produces a SPEC object only — NO redeem-script, NO consensus change.
  // ===========================================================================
  var Escrow = {
    isEnabled: function () { return gatewayVisible() && FLAGS.SOST_GATEWAY_ESCROW_ENABLED === true; },
    STATES: ['draft', 'locked', 'released', 'refunded', 'expired', 'disputed'],
    TEMPLATES: ['multisig_2of3_cltv', 'hashlock_timelock'],
    // Build a draft escrow spec. Validation only; reuses existing P2SH/multisig + PSBT later.
    createSpec: function (o) {
      o = o || {};
      if (this.TEMPLATES.indexOf(o.template) === -1) throw new Error('template must be one of ' + this.TEMPLATES.join(', '));
      var p = validateAddress(o.payer); if (!p.ok) throw new Error('payer: ' + p.reason);
      var b = validateAddress(o.beneficiary); if (!b.ok) throw new Error('beneficiary: ' + b.reason);
      var m = validateAmount(o.amount_sost); if (!m.ok) throw new Error('amount: ' + m.reason);
      if (!(Number.isInteger(o.expiry_height) && o.expiry_height > 0)) throw new Error('expiry_height must be a positive integer block height');
      var arbiter = null;
      if (o.arbiter != null && o.arbiter !== '') {
        var ar = validateAddress(o.arbiter); if (!ar.ok) throw new Error('arbiter: ' + ar.reason);
        arbiter = o.arbiter;
      }
      if (o.template === 'multisig_2of3_cltv' && !arbiter) throw new Error('multisig_2of3_cltv requires an arbiter');
      return {
        kind: 'spec',
        escrow_id: null,                 // assigned on lock (out of scope for skeleton)
        template: o.template,
        payer: o.payer,
        beneficiary: o.beneficiary,
        arbiter: arbiter,
        amount_sost: m.stocks / STOCKS_PER_SOST,
        amount_stocks: m.stocks,
        purpose: String(o.purpose || ''),
        expiry_height: o.expiry_height,
        release_condition: o.template === 'multisig_2of3_cltv'
          ? '2-of-3 {payer, beneficiary, arbiter}'
          : 'beneficiary reveals preimage before expiry',
        refund_condition: 'refund to payer after expiry_height (CLTV)',
        status: 'draft'
      };
    }
  };

  // ===========================================================================
  // SWAP — get/sell SOST via Atomic Swap. ADVANCED module, link/embed only (v1).
  // No deep wallet integration: EVM HTLC is live (V14); SOST-native leg is V15.
  // ===========================================================================
  var Swap = {
    isEnabled: function () { return gatewayVisible() && FLAGS.SOST_GATEWAY_ATOMIC_SWAP_ENABLED === true; },
    PAIRS: ['SOST/ETH', 'SOST/BNB', 'SOST/USDC', 'SOST/USDT', 'SOST/PAXG', 'SOST/XAUT'],
    consoleUrl: function () { return '/atomic-swap.html'; },   // link/embed target (v1)
    note: function () {
      return 'Liquidity bridge, not the checkout. EVM HTLC live at V14 (ETH/BNB/ERC-20); ' +
             'SOST-native leg and BTC are V15. PAXG/XAUT only after SafeERC20 + balance-delta tests.';
    }
  };

  // ===========================================================================
  // PoPC BOND — guarantee with possible slashing. Explanation only in v1.
  // Unified, SOST-native model (whitepaper §6.0): ONE native SOST bond is the
  // only collateral and the only thing that can be slashed. Gold is an OPTIONAL
  // reward boost — held in the user's own wallet, never collateral, never slashed.
  // ===========================================================================
  var PopcBond = {
    isEnabled: function () { return gatewayVisible() && FLAGS.SOST_GATEWAY_POPC_BOND_ENABLED === true; },
    POINTS: {
      bond: 'Bond: one native SOST bond — the only collateral and the only thing that can be ' +
            'slashed. Base reward 1 / 4 / 9 / 14 / 20% for 1 / 3 / 6 / 9 / 12-month locks.',
      gold: 'Gold Boost (optional): gold stays in your own wallet and only ADDS reward ' +
            '(+0 / +10 / +20% on the base for 0-30 / 31-90 / 91+ verified days, cap +20%, ' +
            'technical max +25%). Never collateral, never slashed — withdraw it and you simply ' +
            'revert to the base reward.'
    },
    recommendation: function () {
      return 'PoPC is one native SOST bond: the only collateral and the only thing slashable. ' +
             'Gold is an optional boost on the base reward, funded from a dedicated reserve so it ' +
             'never dilutes the base pool. No external chain in the root of security. ' +
             'Auto-slash/settle is V15-gated. Everything OFF by default.';
    }
  };

  // ---- Which sub-tabs the UI should reveal (master flag is the gate) ----------
  var MODULES = { hold: Hold, pay: Pay, escrow: Escrow, swap: Swap, popc_bond: PopcBond };
  function visibleModules() {
    var out = [];
    if (!gatewayVisible()) return out;
    var order = ['hold', 'pay', 'escrow', 'swap', 'popc_bond'];
    for (var i = 0; i < order.length; i++) { if (MODULES[order[i]].isEnabled()) out.push(order[i]); }
    return out;
  }

  // Auto-apply a config global if a page defined one BEFORE loading this file (browser only).
  // Order-independent callers should use applyConfig() explicitly (the wallet glue does).
  if (typeof root !== 'undefined' && root && root.SOST_GATEWAY_CONFIG) {
    applyConfig(root.SOST_GATEWAY_CONFIG);
  }

  return {
    FLAGS: FLAGS, flags: flags, _setFlags: _setFlags, applyConfig: applyConfig,
    gatewayVisible: gatewayVisible, visibleModules: visibleModules,
    STOCKS_PER_SOST: STOCKS_PER_SOST,
    validateAddress: validateAddress, validateAmount: validateAmount, validateReference: validateReference,
    Hold: Hold, Pay: Pay, Escrow: Escrow, Swap: Swap, PopcBond: PopcBond
  };
}));
