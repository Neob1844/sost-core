/*
 * sost-wallet-bridge.js — SOST web-wallet <-> DEX dashboard postMessage bridge.
 * ---------------------------------------------------------------------------
 * PURE protocol + security core. Contains NO private key, NO seed, NO crypto,
 * NO DOM. The real signing / key access / node RPC live in sost-wallet.html and
 * are injected into createResponder() as callbacks. This split lets the whole
 * message-handling + security surface be unit-tested headlessly under node
 * (see sost-wallet-bridge.test.js) without a browser.
 *
 * The DEX dashboard (sost-dex-dashboard.html via js/dex-wallets.js connectSost
 * and js/dex-devnet-flow.js makeSostBridge) opens the wallet at
 *     sost-wallet.html#<action>=<reqId>        (action = connect|address|build|sign)
 * and awaits a postMessage back whose { reqId, type } match. This module both:
 *   - bootstraps that hash-triggered request (handleHash), and
 *   - serves request MESSAGES posted by the opener (handleMessage), which is how
 *     the build/sign PAYLOADS reach the wallet (the hash alone carries no params).
 *
 * Response shapes (exactly what the dashboard reads — see dex-wallets.js /
 * dex-devnet-flow.js):
 *   connect  ->  { reqId, type:'sost:connect', address, balanceStocks? }
 *   address  ->  { reqId, type:'sost:address', address, balanceStocks? }
 *   build    ->  { reqId, type:'sost:build',   rawUnsignedHex, summary, spend }
 *   sign     ->  { reqId, type:'sost:sign',    signedHex, hex, txid?, vout? }
 *   error    ->  { reqId?, error:'bad_request'|'bad_origin'|'user_reject'|... }
 *
 * SECURITY (all enforced here):
 *   - origin allowlist: messages from any other origin are logged + dropped with
 *     NO response (silent), so a hostile frame learns nothing.
 *   - type + payload schema + reqId are validated; malformed/unknown -> bad_request.
 *   - a private key / seed NEVER appears in a response: responses are built from
 *     explicit fields only, and every outgoing object is additionally scrubbed by
 *     scrubSecrets() as defence-in-depth.
 *   - signing is never silent: the sign path calls authorizeSign() and only signs
 *     on an explicit truthy user authorization; a falsy result -> user_reject.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTWalletBridge = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Devnet dashboard is served from the local static server on :8899.
  var DEFAULT_ALLOWED_ORIGINS = [
    'http://127.0.0.1:8899',
    'http://localhost:8899'
  ];

  // Canonical actions and the request types we accept (bare, as in the URL hash,
  // and 'sost:'-prefixed, as a posted request message might carry).
  var ACTIONS = ['connect', 'address', 'build', 'sign'];
  var BUILD_KINDS = ['htlc_lock', 'htlc_claim', 'htlc_refund'];

  // Keys that must never ride in a response. Used by scrubSecrets().
  var SECRET_KEY_RE = /priv|seed|mnemonic|passphrase|password|secret|wif|xprv|xpriv|entropy|keystore/i;

  // ---- origin helpers ------------------------------------------------------
  function normOrigin(o) {
    if (o == null) return '';
    return String(o).replace(/\/+$/, '').toLowerCase();
  }
  function isOriginAllowed(origin, allowlist, selfOrigin) {
    var o = normOrigin(origin);
    if (!o || o === 'null') return false;                 // opaque / file:// origins
    if (selfOrigin && o === normOrigin(selfOrigin)) return true; // same-origin
    var list = allowlist || DEFAULT_ALLOWED_ORIGINS;
    for (var i = 0; i < list.length; i++) {
      if (o === normOrigin(list[i])) return true;
    }
    return false;
  }

  // ---- hash parsing --------------------------------------------------------
  // "#build=req-123"  ->  { action:'build', reqId:'req-123' }
  // Extra &k=v pairs are ignored (reserved for a future inline payload channel).
  function parseHashRequest(hash) {
    if (!hash) return null;
    var h = String(hash).replace(/^#/, '');
    if (!h) return null;
    var first = h.split('&')[0];
    var eq = first.indexOf('=');
    if (eq < 0) return null;
    var action = first.slice(0, eq).toLowerCase();
    var reqId = first.slice(eq + 1);
    if (ACTIONS.indexOf(action) < 0) return null;
    if (!reqId) return null;
    return { action: action, reqId: reqId };
  }

  // ---- message normalization ----------------------------------------------
  // Accepts a raw postMessage data object; returns { reqId, action, payload }
  // or null when it is not a well-formed bridge request.
  function normalizeRequest(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    var reqId = data.reqId;
    if (typeof reqId !== 'string' || !reqId) return null;
    var t = data.type || data.action;
    if (typeof t !== 'string' || !t) return null;
    var action = t.replace(/^sost:/, '').toLowerCase();
    if (ACTIONS.indexOf(action) < 0) return null;
    // payload may be nested under .payload or carried as top-level fields.
    var payload = (data.payload && typeof data.payload === 'object') ? data.payload : data;
    return { reqId: reqId, action: action, payload: payload };
  }

  // ---- payload schema validation ------------------------------------------
  function isHex(s, bytes) {
    if (typeof s !== 'string') return false;
    var h = s.replace(/^0x/i, '');
    if (!/^[0-9a-fA-F]*$/.test(h)) return false;
    if (bytes != null) return h.length === bytes * 2;
    return h.length > 0 && h.length % 2 === 0;
  }
  function isSostAddr(a) {
    return typeof a === 'string' && /^sost1[0-9a-fA-F]{40}$/.test(a);
  }
  function isNonNegInt(n) {
    return typeof n === 'number' && isFinite(n) && n >= 0 && Math.floor(n) === n;
  }
  function isPosInt(n) { return isNonNegInt(n) && n > 0; }

  // Returns { ok:true } or { ok:false, error:'bad_request', detail:'...' }.
  function validatePayload(action, payload) {
    if (action === 'address' || action === 'connect') return { ok: true };

    if (!payload || typeof payload !== 'object') {
      return { ok: false, error: 'bad_request', detail: 'missing payload' };
    }

    if (action === 'build') {
      var kind = payload.kind;
      if (BUILD_KINDS.indexOf(kind) < 0) {
        return { ok: false, error: 'bad_request', detail: 'kind must be one of ' + BUILD_KINDS.join('/') };
      }
      if (kind === 'htlc_lock') {
        if (!isPosInt(payload.amount)) return { ok: false, error: 'bad_request', detail: 'amount must be a positive integer (stocks)' };
        if (!isHex(payload.hashlock, 32)) return { ok: false, error: 'bad_request', detail: 'hashlock must be 32 bytes hex' };
        if (!isNonNegInt(payload.refund_height)) return { ok: false, error: 'bad_request', detail: 'refund_height must be a non-negative integer' };
        if (!isSostAddr(payload.claim_address)) return { ok: false, error: 'bad_request', detail: 'claim_address must be sost1 + 40 hex' };
        if (!isSostAddr(payload.refund_address)) return { ok: false, error: 'bad_request', detail: 'refund_address must be sost1 + 40 hex' };
        return { ok: true };
      }
      if (kind === 'htlc_claim') {
        if (!isHex(payload.lock_txid, 32)) return { ok: false, error: 'bad_request', detail: 'lock_txid must be 32 bytes hex' };
        if (!isNonNegInt(payload.lock_vout)) return { ok: false, error: 'bad_request', detail: 'lock_vout must be a non-negative integer' };
        if (!isHex(payload.preimage, 32)) return { ok: false, error: 'bad_request', detail: 'preimage must be 32 bytes hex' };
        return { ok: true };
      }
      // htlc_refund
      if (!isHex(payload.lock_txid, 32)) return { ok: false, error: 'bad_request', detail: 'lock_txid must be 32 bytes hex' };
      if (!isNonNegInt(payload.lock_vout)) return { ok: false, error: 'bad_request', detail: 'lock_vout must be a non-negative integer' };
      return { ok: true };
    }

    if (action === 'sign') {
      // The dashboard calls sign with { tx: <build result> }; also accept a bare
      // build-result object or a raw hex string.
      var tx = payload.tx != null ? payload.tx : payload;
      if (typeof tx === 'string') {
        return isHex(tx) ? { ok: true } : { ok: false, error: 'bad_request', detail: 'tx hex invalid' };
      }
      if (!tx || typeof tx !== 'object') return { ok: false, error: 'bad_request', detail: 'sign requires a tx' };
      if (!isHex(tx.rawUnsignedHex)) return { ok: false, error: 'bad_request', detail: 'tx.rawUnsignedHex must be hex' };
      return { ok: true };
    }

    return { ok: false, error: 'bad_request', detail: 'unknown action' };
  }

  // ---- response scrubbing (defence in depth) -------------------------------
  // Deep-clones `obj` dropping any key whose name looks like a secret. Guarantees
  // no private-key/seed field can ride out even if a callback mistakenly returned
  // one. Cycles are broken defensively.
  function scrubSecrets(obj, _seen) {
    if (obj == null || typeof obj !== 'object') return obj;
    _seen = _seen || [];
    if (_seen.indexOf(obj) >= 0) return undefined;
    _seen.push(obj);
    if (Array.isArray(obj)) {
      return obj.map(function (v) { return scrubSecrets(v, _seen); });
    }
    var out = {};
    Object.keys(obj).forEach(function (k) {
      if (SECRET_KEY_RE.test(k)) return; // drop secret-looking field entirely
      out[k] = scrubSecrets(obj[k], _seen);
    });
    return out;
  }

  function mapError(e) {
    var msg = (e && e.message) ? e.message : String(e || 'internal_error');
    if (/locked|unlock/i.test(msg)) return 'wallet_locked';
    if (/not loaded|no wallet|watch-only|watch only/i.test(msg)) return 'wallet_not_loaded';
    if (/reject|cancel|denied/i.test(msg)) return 'user_reject';
    return msg;
  }

  // ---- responder factory ---------------------------------------------------
  // deps:
  //   allowlist     : array of allowed origins (defaults to the devnet set)
  //   selfOrigin    : this page's origin (same-origin is always allowed)
  //   getAddress    : async () => { address, balanceStocks? }
  //   buildHtlc     : async (payload) => { rawUnsignedHex, summary, spend }
  //   signTx        : async (payload) => { signedHex, txid?, vout? }
  //   authorizeSign : async (payload, summary) => boolean  (shows UI; MUST be explicit)
  //   post          : (targetWindow, targetOrigin, message) => void
  //   log           : (level, ...args) => void   (optional)
  function createResponder(deps) {
    deps = deps || {};
    var allowlist = deps.allowlist || DEFAULT_ALLOWED_ORIGINS;
    var selfOrigin = deps.selfOrigin || '';
    var log = deps.log || function () {};

    function send(target, origin, msg) {
      var clean = scrubSecrets(msg);
      if (typeof deps.post === 'function') deps.post(target, origin, clean);
      return clean;
    }

    // Core dispatch — shared by handleMessage and handleHash. Returns a promise
    // resolving to { sent } (the scrubbed response) or { dropped, reason }.
    async function dispatch(req, target, origin) {
      if (!req) {
        var bad = send(target, origin, { error: 'bad_request' });
        return { sent: bad, error: 'bad_request' };
      }
      var reqId = req.reqId, action = req.action, payload = req.payload;

      var v = validatePayload(action, payload);
      if (!v.ok) {
        var r = send(target, origin, { reqId: reqId, error: 'bad_request', detail: v.detail });
        return { sent: r, error: 'bad_request' };
      }

      try {
        if (action === 'address' || action === 'connect') {
          var info = (await deps.getAddress()) || {};
          return { sent: send(target, origin, {
            reqId: reqId, type: 'sost:' + action,
            address: info.address || null,
            balanceStocks: (info.balanceStocks != null ? info.balanceStocks : null)
          }) };
        }

        if (action === 'build') {
          var b = (await deps.buildHtlc(payload)) || {};
          return { sent: send(target, origin, {
            reqId: reqId, type: 'sost:build',
            rawUnsignedHex: b.rawUnsignedHex || null,
            summary: b.summary || null,
            spend: b.spend || null
          }) };
        }

        if (action === 'sign') {
          var summary = payload && payload.tx && payload.tx.summary ? payload.tx.summary
                      : (payload && payload.summary ? payload.summary : null);
          var approved = await deps.authorizeSign(payload, summary);
          if (!approved) {
            return { sent: send(target, origin, { reqId: reqId, error: 'user_reject' }) };
          }
          var s = (await deps.signTx(payload)) || {};
          return { sent: send(target, origin, {
            reqId: reqId, type: 'sost:sign',
            signedHex: s.signedHex || null,
            hex: s.signedHex || null,            // alias read by dex broadcast()
            txid: (s.txid != null ? s.txid : null),
            vout: (s.vout != null ? s.vout : null)
          }) };
        }

        return { sent: send(target, origin, { reqId: reqId, error: 'bad_request' }), error: 'bad_request' };
      } catch (e) {
        log('error', 'bridge dispatch failed', e);
        return { sent: send(target, origin, { reqId: reqId, error: mapError(e) }), error: mapError(e) };
      }
    }

    // Inbound postMessage handler. Enforces the origin allowlist (silent drop on
    // mismatch), then normalizes + dispatches.
    async function handleMessage(event) {
      var origin = event && event.origin;
      var target = event && event.source;
      if (!isOriginAllowed(origin, allowlist, selfOrigin)) {
        log('warn', 'bridge dropped message from disallowed origin', origin);
        return { dropped: true, reason: 'bad_origin' };
      }
      var req = normalizeRequest(event && event.data);
      if (!req) {
        // Malformed from an allowed origin. Only answer with bad_request when the
        // message actually LOOKS like bridge traffic (carries a reqId or a 'sost:'
        // type) — otherwise stay silent so unrelated same-origin postMessage
        // chatter (libraries, other widgets) is not answered.
        var data = event && event.data;
        var looksBridge = !!(data && typeof data === 'object' && !Array.isArray(data) &&
          (typeof data.reqId === 'string' ||
           (typeof data.type === 'string' && /^sost:/i.test(data.type))));
        if (!looksBridge) return { ignored: true };
        var reqId = (typeof data.reqId === 'string') ? data.reqId : undefined;
        var msg = reqId ? { reqId: reqId, error: 'bad_request' } : { error: 'bad_request' };
        return { sent: send(target, origin, msg), error: 'bad_request' };
      }
      return dispatch(req, target, origin);
    }

    // Hash bootstrap. For connect/address (no params needed) it responds
    // immediately to the opener. For build/sign it returns { pending:true } so the
    // page can show an "awaiting request from the DEX" state until the opener
    // posts the request payload (handled by handleMessage).
    async function handleHash(hash, opener, openerOrigin) {
      var hr = parseHashRequest(hash);
      if (!hr) return { pending: false, matched: false };
      var origin = openerOrigin || (allowlist[0]);
      if (hr.action === 'connect' || hr.action === 'address') {
        await dispatch({ reqId: hr.reqId, action: hr.action, payload: {} }, opener, origin);
        return { pending: false, matched: true, action: hr.action, reqId: hr.reqId };
      }
      return { pending: true, matched: true, action: hr.action, reqId: hr.reqId };
    }

    return {
      handleMessage: handleMessage,
      handleHash: handleHash,
      dispatch: dispatch
    };
  }

  return {
    DEFAULT_ALLOWED_ORIGINS: DEFAULT_ALLOWED_ORIGINS,
    ACTIONS: ACTIONS,
    BUILD_KINDS: BUILD_KINDS,
    SECRET_KEY_RE: SECRET_KEY_RE,
    normOrigin: normOrigin,
    isOriginAllowed: isOriginAllowed,
    parseHashRequest: parseHashRequest,
    normalizeRequest: normalizeRequest,
    validatePayload: validatePayload,
    scrubSecrets: scrubSecrets,
    mapError: mapError,
    createResponder: createResponder
  };
});
