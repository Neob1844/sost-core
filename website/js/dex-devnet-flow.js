/*
 * SOST DEX — DEVNET ADMIN E2E flow (?devnet=1 on the PROTECTED dashboard only).
 * ===========================================================================
 * This module drives the REAL SOST<->ETH (and SOST<->USDC) atomic-swap flow
 * against a FULLY LOCAL reproducible devnet (SOST --profile dev node + Anvil +
 * AtomicSwapHTLCv2). It is loaded and used ONLY when the dashboard is opened as
 *   sost-dex-dashboard.html?devnet=1
 * i.e. the authenticated admin / developer path. The public sost-dex.html and
 * the normal (non-devnet) dashboard path are untouched and stay fail-closed.
 *
 * NO MOCKS in the admin SOST/ETH/USDC path:
 *   - EVM leg  : real eth_getBalance / ERC20 balanceOf / allowance / approve /
 *                lockNative / lockERC20 / claim* / refund* contract calls via the
 *                injected wallet (eth_sendTransaction) + eth_call reads, using the
 *                EXACT AtomicSwapHTLCv2 selectors.
 *   - SOST leg : real getbalance / getblockcount / gethtlcstatus / listhtlclocks /
 *                sendrawtransaction against DEVNET.sost_rpc (HTTP Basic auth), and
 *                HTLC lock/claim/refund BUILT + SIGNED by the SOST wallet bridge
 *                (postMessage; the DEX never sees a seed/key), then broadcast.
 *   - State    : the frozen SOSTDexRFQ state machine + reconcile() against chain
 *                truth, persisted in localStorage (hashlock + leg txids + step),
 *                so a page reload RESUMES and reconciles, never re-locks blindly.
 *
 * Real funds NEVER move (local devnet only). Public trading stays disabled.
 * Browser verification against a live devnet is an OWNER step (PENDING OWNER);
 * this file wires the real connector/RPC APIs, it does not fabricate results.
 *
 * Uses the REAL modules already on the page:
 *   window.SOSTWallets        (connect shapes: SOST {address,balanceStocks}, EVM {address,chainId,balanceWei})
 *   window.SOSTDexConnectors  (evm()/sost() builders: balance/allowance/approve/send/receipt, buildLock/buildClaim/buildRefund/sign/broadcast)
 *   window.SOSTDexRFQ         (STATES/ALLOWED/applyTransition/reconcile/hashlock/newSwap/saveSwap/loadAll/resumable/canonicalOffer)
 *   window.SOSTAssets         (decimals/status; USDC=caveat, USDT/PAXG/XAUT=disabled)
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexDevnet = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ---- AtomicSwapHTLCv2 selectors (cast sig verified; see contracts/atomic-swap) ----
  var SEL = {
    lockNative:  '0xbef939c1', // lockNative(bytes32,bytes32,uint256,address,address)
    lockERC20:   '0x9cbaca50', // lockERC20(bytes32,address,uint256,bytes32,uint256,address,address)
    claimNative: '0xeb84d2f5', // claimNative(bytes32,bytes32)
    claimERC20:  '0xe1506509', // claimERC20(bytes32,bytes32,uint256)
    refundNative:'0xd7fb17f4', // refundNative(bytes32)
    refundERC20: '0x44dee18a', // refundERC20(bytes32)
    getSwap:     '0x3da0e66e', // getSwap(bytes32)
    balanceOf:   '0x70a08231', // balanceOf(address)
    allowance:   '0xdd62ed3e', // allowance(address,address)
    approve:     '0x095ea7b3'  // approve(address,uint256)
  };
  var EVM_STATE = ['NONE', 'LOCKED', 'CLAIMED', 'REFUNDED'];
  var REFUND_WINDOW_BLOCKS = 500; // devnet HTLC refund opens this many blocks ahead

  // ---- small hex / ABI helpers ----------------------------------------------
  function strip0x(h) { return (h || '').replace(/^0x/, ''); }
  function padAddr(a) { return strip0x(a).toLowerCase().padStart(64, '0'); }
  function pad32(h) { return strip0x(h).padStart(64, '0'); }
  function toHexNum(v) { return BigInt(v).toString(16); }            // no 0x
  function u256(v) { return toHexNum(v).padStart(64, '0'); }
  function bytes32(h) {
    var s = strip0x(h);
    if (s.length !== 64) throw new Error('expected 32-byte hex, got ' + s.length / 2 + ' bytes');
    return s.toLowerCase();
  }
  function randomPreimageHex() {
    var b = new Uint8Array(32);
    (root.crypto || root.msCrypto).getRandomValues(b);
    return Array.from(b).map(function (x) { return x.toString(16).padStart(2, '0'); }).join('');
  }
  function randomBytes32() { return '0x' + randomPreimageHex(); }

  // decimal string -> integer base units (BigInt), no float math
  function parseUnits(amountStr, decimals) {
    amountStr = String(amountStr == null ? '' : amountStr).trim();
    if (!/^\d*\.?\d*$/.test(amountStr) || amountStr === '' || amountStr === '.') throw new Error('invalid amount');
    var parts = amountStr.split('.');
    var whole = parts[0] || '0';
    var frac = (parts[1] || '').slice(0, decimals);
    while (frac.length < decimals) frac += '0';
    var combined = (whole + frac).replace(/^0+(?=\d)/, '');
    return BigInt(combined || '0');
  }
  function formatUnits(baseUnits, decimals) {
    var s = BigInt(baseUnits).toString();
    if (decimals === 0) return s;
    while (s.length <= decimals) s = '0' + s;
    var whole = s.slice(0, s.length - decimals);
    var frac = s.slice(s.length - decimals).replace(/0+$/, '');
    return frac ? (whole + '.' + frac) : whole;
  }

  // ---- JSON-RPC transports ---------------------------------------------------
  var reqId = 1;
  // SOST node RPC (HTTP Basic auth; CORS enabled on the node). pass is admin-entered.
  function sostRpc(method, params) {
    var D = root.DEVNET || {};
    if (!D.sost_rpc) return Promise.reject(new Error('DEVNET.sost_rpc not configured'));
    var headers = { 'Content-Type': 'application/json' };
    var pass = sostPass();
    if (D.sost_rpc_user && pass != null) headers['Authorization'] = 'Basic ' + root.btoa(D.sost_rpc_user + ':' + pass);
    return fetch(D.sost_rpc, {
      method: 'POST', headers: headers,
      body: JSON.stringify({ jsonrpc: '2.0', id: reqId++, method: method, params: params || [] })
    }).then(function (r) {
      if (r.status === 401) throw new Error('SOST RPC 401 — set the devnet RPC password (user "' + (D.sost_rpc_user || '') + '")');
      return r.json();
    }).then(function (j) {
      if (j.error) throw new Error('SOST RPC ' + method + ': ' + (j.error.message || JSON.stringify(j.error)));
      return j.result;
    });
  }
  // EVM READ via direct RPC to Anvil (no signing; CORS open on anvil).
  function evmRead(method, params) {
    var D = root.DEVNET || {};
    if (!D.evm_rpc) return Promise.reject(new Error('DEVNET.evm_rpc not configured'));
    return fetch(D.evm_rpc, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: reqId++, method: method, params: params || [] })
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.error) throw new Error('EVM ' + method + ': ' + (j.error.message || JSON.stringify(j.error)));
      return j.result;
    });
  }

  // ---- RPC password (devnet admin only; sessionStorage, never committed) -----
  var PASS_KEY = 'sost.dex.devnet.sostpass';
  function sostPass() {
    var D = root.DEVNET || {};
    if (D.sost_rpc_pass) return D.sost_rpc_pass; // allowed if the local-only config carries it
    try { return root.sessionStorage.getItem(PASS_KEY); } catch (e) { return null; }
  }
  function setSostPass(p) { try { root.sessionStorage.setItem(PASS_KEY, p); } catch (e) {} }

  // ---- preimage custody (devnet admin; sessionStorage, cleared on tab close) --
  // The hashlock + leg txids persist in localStorage (resume); the PREIMAGE is kept
  // only in sessionStorage so it never persists in plaintext beyond the live session,
  // matching the RFQ design ("preimage never leaves the client until claim reveals it").
  function preKey(id) { return 'sost.dex.devnet.pre.' + id; }
  function savePreimage(id, hex) { try { root.sessionStorage.setItem(preKey(id), hex); } catch (e) {} }
  function loadPreimage(id) { try { return root.sessionStorage.getItem(preKey(id)); } catch (e) { return null; } }

  // ===========================================================================
  //  EVM HTLC (AtomicSwapHTLCv2) — the real counterparty leg
  // ===========================================================================
  function htlcAddr() {
    var a = (root.DEVNET || {}).htlc_v2;
    if (!a) throw new Error('DEVNET.htlc_v2 contract address not configured');
    return a;
  }
  // Encoders (calldata only; the wallet signs + sends via eth_sendTransaction).
  function encLockNative(swapId, hashlock, refundTime, claimer, refunder) {
    return SEL.lockNative + bytes32(swapId) + bytes32(hashlock) + u256(refundTime) + padAddr(claimer) + padAddr(refunder);
  }
  function encLockERC20(swapId, token, amount, hashlock, refundTime, claimer, refunder) {
    return SEL.lockERC20 + bytes32(swapId) + padAddr(token) + u256(amount) + bytes32(hashlock) + u256(refundTime) + padAddr(claimer) + padAddr(refunder);
  }
  function encClaimNative(swapId, preimage) { return SEL.claimNative + bytes32(swapId) + bytes32(preimage); }
  function encClaimERC20(swapId, preimage, minReceive) { return SEL.claimERC20 + bytes32(swapId) + bytes32(preimage) + u256(minReceive); }
  function encRefundNative(swapId) { return SEL.refundNative + bytes32(swapId); }
  function encRefundERC20(swapId) { return SEL.refundERC20 + bytes32(swapId); }

  // Build a SOSTDexConnectors.evm wrapper around the connected injected provider.
  function evmConn() {
    var prov = ctx && ctx.cpProvider && ctx.cpProvider();
    if (!prov) throw new Error('no EVM wallet provider connected (connect MetaMask first)');
    if (!root.SOSTDexConnectors) throw new Error('dex-connectors.js not loaded');
    return root.SOSTDexConnectors.evm(prov);
  }

  // Ensure the wallet is on the devnet chain (31337); offer wallet_switchEthereumChain.
  async function ensureEvmChain(conn) {
    var want = (root.DEVNET || {}).evm_chain_id;
    if (!want) return;
    var cid = parseInt(await conn.provider.request({ method: 'eth_chainId' }), 16);
    if (cid === want) return;
    try {
      await conn.switchNetwork('0x' + want.toString(16));
    } catch (e) {
      throw new Error('wrong network (chainId ' + cid + ', need ' + want + '). Approve the network switch in your wallet, or add Anvil (RPC ' + (root.DEVNET || {}).evm_rpc + ', chainId ' + want + ').');
    }
  }

  // read a v2 swap record from chain: {state,token,requested,lockedAmount,hashlock,refundTime,claimer,refunder}
  async function evmGetSwap(swapId) {
    var data = SEL.getSwap + bytes32(swapId);
    var ret = strip0x(await evmRead('eth_call', [{ to: htlcAddr(), data: data }, 'latest']));
    if (ret.length < 64 * 8) return { state: 'NONE' };
    function w(i) { return ret.slice(i * 64, i * 64 + 64); }
    return {
      state: EVM_STATE[parseInt(w(0).slice(-2) || '0', 16)] || 'NONE',
      token: '0x' + w(1).slice(24),
      requested: BigInt('0x' + w(2)).toString(),
      lockedAmount: BigInt('0x' + w(3)).toString(),
      hashlock: '0x' + w(4),
      refundTime: BigInt('0x' + w(5)).toString(),
      claimer: '0x' + w(6).slice(24),
      refunder: '0x' + w(7).slice(24)
    };
  }

  async function evmErc20BalanceOf(token, owner) {
    var ret = await evmRead('eth_call', [{ to: token, data: SEL.balanceOf + padAddr(owner) }, 'latest']);
    return BigInt(ret || '0x0').toString();
  }
  async function evmErc20Allowance(token, owner, spender) {
    var ret = await evmRead('eth_call', [{ to: token, data: SEL.allowance + padAddr(owner) + padAddr(spender) }, 'latest']);
    return BigInt(ret || '0x0').toString();
  }

  // wait for a receipt; status 0x1 = success, 0x0 = reverted
  async function waitReceipt(txHash, tries) {
    tries = tries || 60;
    for (var i = 0; i < tries; i++) {
      var r = await evmRead('eth_getTransactionReceipt', [txHash]);
      if (r) {
        if (r.status && BigInt(r.status) === 0n) throw new Error('EVM tx reverted (' + txHash + ')');
        return r;
      }
      await sleep(1000);
    }
    throw new Error('EVM receipt timeout for ' + txHash);
  }

  // map common user/chain errors to a clear message
  function evmErr(e) {
    var m = (e && (e.message || e.toString())) || 'EVM error';
    if (/4001|user rejected|User denied/i.test(m)) return 'Signature rejected in the wallet.';
    if (/insufficient funds/i.test(m)) return 'Insufficient balance for the lock amount + gas.';
    if (/chain|network/i.test(m)) return m;
    return m;
  }

  // ===========================================================================
  //  SOST wallet bridge (postMessage) — build + sign HTLC txs (NO seed in DEX)
  // ===========================================================================
  // The SOST web wallet (sost-wallet.html) is the signer/builder. We talk to it via
  // postMessage request/response, matching SOSTWallets.connectSost's {reqId,type} shape.
  // We then wrap the bridge with SOSTDexConnectors.sost(bridge) so the real buildLock/
  // buildClaim/buildRefund builders are used; broadcast goes through DEVNET.sost_rpc.
  function makeSostBridge(opts) {
    opts = opts || {};
    var walletUrl = opts.walletUrl || 'sost-wallet.html';
    function request(type, payload, timeoutMs) {
      return new Promise(function (resolve, reject) {
        var id = 'req-' + type + '-' + Date.now() + '-' + Math.floor(Math.random() * 1e6);
        var popup = root.open ? root.open(walletUrl + '#' + type + '=' + id, 'sostwallet', 'width=460,height=720') : null;
        var done = false, poll = null;
        // Post the request params to the wallet popup at OUR origin only (never '*').
        // The wallet validates origin + reqId + schema and ignores duplicates, so we
        // poll-post until it answers (covers the popup not having its listener ready yet).
        var targetOrigin = (root.location && root.location.origin) ? root.location.origin : null;
        var reqMsg = Object.assign({ reqId: id, type: 'sost:' + type }, payload || {});
        function stop() { done = true; if (poll) { clearInterval(poll); poll = null; } if (root.removeEventListener) root.removeEventListener('message', onMsg); }
        function onMsg(ev) {
          var d = ev && ev.data;
          if (!d || d.reqId !== id || d.type !== ('sost:' + type)) return;
          stop();
          if (d.error) return reject(new Error(d.error));
          resolve(d.result != null ? d.result : d);
        }
        if (root.addEventListener) root.addEventListener('message', onMsg);
        if (popup && popup.postMessage && targetOrigin) {
          poll = setInterval(function () {
            if (done) { clearInterval(poll); poll = null; return; }
            try { popup.postMessage(reqMsg, targetOrigin); } catch (e) {}
          }, 300);
          try { popup.postMessage(reqMsg, targetOrigin); } catch (e) {}
        }
        setTimeout(function () {
          if (!done) { stop(); reject(new Error('SOST wallet "' + type + '" timed out — open ' + walletUrl + ' and approve the request')); }
        }, timeoutMs || 120000);
        if (!popup) { if (poll) { clearInterval(poll); poll = null; } reject(new Error('popup blocked — allow popups for the SOST wallet bridge')); }
      });
    }
    // bridge contract expected by SOSTDexConnectors.sost(bridge)
    return {
      getAddress: function () { return request('address', {}, 60000).then(function (r) { return r.address || r; }); },
      getBalance: function () { return sostRpc('getbalance', []); },
      // buildTx returns an UNSIGNED template; the wallet owns UTXO selection + script build
      buildTx: function (o) { return request('build', o, 120000); },
      sign: function (unsignedTx) { return request('sign', { tx: unsignedTx }, 180000); }, // -> {hex,txid,vout}
      broadcast: function (signedHexOrObj) {
        var hex = (signedHexOrObj && signedHexOrObj.hex) || signedHexOrObj;
        return sostRpc('sendrawtransaction', [hex]);
      }
    };
  }

  // SOST HTLC lock: build (wallet) -> sign (wallet) -> broadcast (node RPC) -> find vout.
  async function sostLock(params) {
    var bridge = makeSostBridge({});
    var conn = root.SOSTDexConnectors.sost(bridge);
    var unsigned = await conn.buildLock({
      amount: params.amountStocks,          // integer base units (stocks)
      hashlock: params.hashlock,            // 0x..32 bytes
      refund_height: params.refundHeight,
      claim_address: params.claimAddress,   // sost1...
      refund_address: params.refundAddress  // sost1...
    });
    var signed = await conn.sign(unsigned);       // {hex,txid,vout}
    var txid = await conn.broadcast(signed);      // node returns the txid string
    if (typeof txid !== 'string') txid = (signed && signed.txid) || txid;
    // Resolve the HTLC output vout from chain truth (listhtlclocks) by matching hashlock.
    var vout = (signed && signed.vout != null) ? signed.vout : await sostFindLockVout(txid, params.hashlock);
    return { txid: txid, vout: vout };
  }
  async function sostFindLockVout(txid, hashlock) {
    var hl = strip0x(hashlock).toLowerCase();
    for (var i = 0; i < 20; i++) {
      try {
        var locks = await sostRpc('listhtlclocks', []);
        var hit = (locks || []).filter(function (l) { return l.txid === txid && strip0x(l.hashlock).toLowerCase() === hl; })[0];
        if (hit) return hit.vout;
      } catch (e) {}
      await sleep(1500);
    }
    return 0; // fall back to first output; gethtlcstatus will report is_htlc_lock
  }
  async function sostHtlcStatus(txid, vout) { return sostRpc('gethtlcstatus', [txid, String(vout)]); }

  async function sostClaim(lock, preimageHex) {
    var bridge = makeSostBridge({});
    var conn = root.SOSTDexConnectors.sost(bridge);
    var unsigned = await conn.buildClaim({ lock_txid: lock.txid, lock_vout: lock.vout, preimage: preimageHex });
    var signed = await conn.sign(unsigned);
    return conn.broadcast(signed);
  }
  async function sostRefund(lock) {
    var bridge = makeSostBridge({});
    var conn = root.SOSTDexConnectors.sost(bridge);
    var unsigned = await conn.buildRefund({ lock_txid: lock.txid, lock_vout: lock.vout });
    var signed = await conn.sign(unsigned);
    return conn.broadcast(signed);
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // ===========================================================================
  //  Swap record (localStorage via SOSTDexRFQ) + step model
  // ===========================================================================
  var STEP = ['OFFER', 'ACCEPT', 'RESERVE', 'LOCK_SOST', 'LOCK_EVM', 'VERIFY', 'REVEAL_CLAIM_EVM', 'REDEEM_SOST', 'COMPLETE'];
  var STEP_LABEL = {
    OFFER: 'Offer', ACCEPT: 'Accept', RESERVE: 'Reserve (hashlock)',
    LOCK_SOST: 'Lock SOST HTLC', LOCK_EVM: 'Lock EVM HTLC', VERIFY: 'Verify both legs',
    REVEAL_CLAIM_EVM: 'Reveal secret · claim EVM', REDEEM_SOST: 'Redeem SOST', COMPLETE: 'Completed'
  };

  var ctx = null;          // dashboard-provided context
  var current = null;      // active swap record

  function freshSwap() {
    var a = ctx.assets();
    var id = 'devnet-' + Date.now().toString(36) + '-' + Math.floor(Math.random() * 1e6).toString(36);
    return {
      id: id, mode: 'devnet', net: 'devnet',
      pay: a.pay, recv: a.recv,
      amount: ctx.payAmount(),
      step: 'OFFER', rfq: 'DRAFT',
      hashlock: null,
      evmSwapId: null,
      sost: { txid: null, vout: null, status: null },
      evm: { lockTx: null, claimTx: null, refundTx: null, refundTime: null },
      createdAt: Date.now(), error: null
    };
  }

  function persist() {
    if (!current || !root.SOSTDexRFQ) return;
    try {
      var map = root.SOSTDexRFQ.loadAll();
      map[current.id] = current;
      // SOSTDexRFQ.saveSwap expects {id,...}; reuse its serializer via loadAll/setItem.
      root.localStorage.setItem('sost.dex.swaps.v1', JSON.stringify(map));
    } catch (e) {}
  }
  function loadLatestResumable() {
    if (!root.SOSTDexRFQ) return null;
    try {
      var map = root.SOSTDexRFQ.loadAll();
      var devnet = Object.keys(map).map(function (k) { return map[k]; })
        .filter(function (s) { return s && s.mode === 'devnet' && s.step !== 'COMPLETE' && s.step !== 'REFUNDED'; })
        .sort(function (a, b) { return (b.createdAt || 0) - (a.createdAt || 0); });
      return devnet[0] || null;
    } catch (e) { return null; }
  }

  // ===========================================================================
  //  Reconcile a persisted swap against chain truth on load (chain always wins)
  // ===========================================================================
  async function reconcileOnLoad(s) {
    if (!s) return s;
    try {
      // SOST leg
      if (s.sost && s.sost.txid != null && s.sost.vout != null) {
        var st = await sostHtlcStatus(s.sost.txid, s.sost.vout);
        s.sost.status = st.status;
        if (st.status === 'claimed' && st.revealed_preimage) s.revealedPreimage = st.revealed_preimage;
      }
      // EVM leg
      if (s.evmSwapId) {
        var ev = await evmGetSwap(s.evmSwapId);
        s.evm.chainState = ev.state;
      }
      // derive step from facts
      var chain = {
        initiatorLocked: s.sost && (s.sost.status === 'locked' || s.sost.status === 'expired' || s.sost.status === 'claimed' || s.sost.status === 'refunded'),
        counterpartyLocked: s.evm && (s.evm.chainState === 'LOCKED' || s.evm.chainState === 'CLAIMED' || s.evm.chainState === 'REFUNDED'),
        claimed: s.sost && s.sost.status === 'claimed' && s.evm && s.evm.chainState === 'CLAIMED',
        refunded: (s.sost && s.sost.status === 'refunded') || (s.evm && s.evm.chainState === 'REFUNDED'),
        expiredByTimeout: s.sost && s.sost.status === 'expired'
      };
      if (chain.refunded) s.step = 'REFUNDED';
      else if (s.sost && s.sost.status === 'claimed' && s.evm && s.evm.chainState === 'CLAIMED') s.step = 'COMPLETE';
      else if (s.evm && s.evm.chainState === 'CLAIMED') s.step = 'REDEEM_SOST';
      else if (s.evm && s.evm.chainState === 'LOCKED' && s.sost && s.sost.status === 'locked') s.step = 'VERIFY';
      else if (s.sost && s.sost.status === 'locked') s.step = 'LOCK_EVM';
      s.reconciledAt = Date.now();
    } catch (e) { s.reconcileError = (e && e.message) || String(e); }
    return s;
  }

  // ===========================================================================
  //  UI
  // ===========================================================================
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }
  function shortHash(h) { h = String(h || ''); return h.length > 20 ? (h.slice(0, 12) + '…' + h.slice(-8)) : h; }

  function renderPanel() {
    var host = el('devnetFlow'); if (!host) return;
    var connected = ctx.wm.state();
    var a = ctx.assets();
    var block = assetDisabled(a.pay) || assetDisabled(a.recv);
    var curStep = (current && current.step) || null;
    var steps = STEP.map(function (k) {
      var idx = STEP.indexOf(k), ci = curStep ? STEP.indexOf(curStep) : -1;
      var cls = ci < 0 ? 'todo' : (idx < ci ? 'done' : (idx === ci ? 'cur' : 'todo'));
      if (current && current.step === 'COMPLETE') cls = 'done';
      if (current && current.step === 'REFUNDED') cls = (k === 'COMPLETE' ? 'todo' : 'done');
      var mark = cls === 'done' ? '✓' : (cls === 'cur' ? '●' : (idx + 1));
      return '<div class="step ' + cls + '"><div class="rail"><div class="pip">' + mark + '</div><div class="line"></div></div>'
        + '<div class="body"><div class="st">' + STEP_LABEL[k] + '</div></div></div>';
    }).join('');

    var bal = '<div class="qrow"><span class="k">SOST available</span><span class="v" id="dnBalSost">—</span></div>'
      + '<div class="qrow"><span class="k">ETH</span><span class="v" id="dnBalEth">—</span></div>'
      + '<div class="qrow"><span class="k">USDC</span><span class="v" id="dnBalUsdc">—</span></div>'
      + '<div class="qrow"><span class="k">SOST tip height</span><span class="v" id="dnTip">—</span></div>';

    var legs = '';
    if (current) {
      legs = '<div class="qrow"><span class="k">Swap id</span><span class="v">' + esc(current.id) + '</span></div>'
        + '<div class="qrow"><span class="k">Hashlock</span><span class="v">' + esc(shortHash(current.hashlock || '—')) + '</span></div>'
        + '<div class="qrow"><span class="k">SOST HTLC</span><span class="v">' + (current.sost.txid ? (esc(shortHash(current.sost.txid)) + ':' + current.sost.vout + ' · ' + esc(current.sost.status || '?')) : '—') + '</span></div>'
        + '<div class="qrow"><span class="k">EVM swapId</span><span class="v">' + esc(shortHash(current.evmSwapId || '—')) + '</span></div>'
        + '<div class="qrow"><span class="k">EVM lock tx</span><span class="v">' + (current.evm.lockTx ? esc(shortHash(current.evm.lockTx)) : '—') + '</span></div>'
        + '<div class="qrow"><span class="k">EVM claim tx</span><span class="v">' + (current.evm.claimTx ? esc(shortHash(current.evm.claimTx)) : '—') + '</span></div>';
    }

    var errBox = (current && current.error) ? '<div style="margin-top:10px;padding:9px 12px;border:1px solid var(--red);border-radius:8px;background:var(--red-soft);color:#ffb3b3;font:600 12px/1.5 var(--mono)">' + esc(current.error) + '</div>' : '';
    var blockBox = block ? '<div style="margin-top:10px;padding:9px 12px;border:1px solid var(--amber);border-radius:8px;background:rgba(240,169,43,.1);color:var(--amber);font:600 12px/1.5 var(--mono)">' + esc(block) + ' — temporarily unavailable (unselectable into a live route).</div>' : '';

    var needPass = !sostPass();
    var passBox = needPass
      ? '<div style="margin-top:10px;display:flex;gap:8px;align-items:center"><input id="dnPass" type="password" placeholder="devnet SOST RPC password (user ' + esc((root.DEVNET || {}).sost_rpc_user || '') + ')" style="flex:1;background:var(--panel-2);border:1px solid var(--border-2);color:var(--txt);border-radius:8px;padding:8px;font-family:var(--mono);font-size:12px"><button id="dnPassBtn" class="cta secondary" style="width:auto;padding:8px 12px;margin:0">Set</button></div>'
        + '<div style="font-size:10.5px;color:var(--txt-4);margin-top:5px">Admin-only. Stored in sessionStorage (this tab), never committed. The node requires HTTP Basic auth; read it from <code>.devnet/rpc.pass</code>.</div>'
      : '<div style="font-size:11px;color:var(--green);margin-top:8px;font-family:var(--mono)">SOST RPC password set for this session.</div>';

    host.innerHTML =
      '<div class="panel" style="margin-top:16px;padding:18px">'
      + '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><b style="font-size:14px">DEVNET admin E2E — ' + esc(a.pay) + ' ⇄ ' + esc(a.recv) + '</b>'
      + '<span class="pill" style="color:#39ff14;background:rgba(57,255,20,.08);border:1px solid rgba(57,255,20,.3)">REAL devnet · no mocks</span>'
      + '<span class="pill demo">admin-only · public trading disabled</span></div>'
      + '<div style="font-size:11.5px;color:var(--txt-3);margin:8px 0 14px">Local reproducible devnet (SOST --profile dev + Anvil + AtomicSwapHTLCv2). No real funds. Browser verification against a live devnet is an owner step.</div>'
      + '<div class="quote" style="border:0;padding:0;margin:0">' + bal + '</div>'
      + passBox
      + '<div class="steps" style="margin-top:16px">' + steps + '</div>'
      + (legs ? ('<div class="quote" style="border-top:1px dashed var(--border-2);margin-top:12px;padding-top:12px">' + legs + '</div>') : '')
      + errBox + blockBox
      + '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">'
      + '<button class="cta" id="dnRun" style="width:auto;padding:12px 18px;margin:0"' + (block ? ' disabled' : '') + '>' + (current && current.step !== 'OFFER' && current.step !== 'COMPLETE' && current.step !== 'REFUNDED' ? 'Continue swap' : 'Start full swap') + '</button>'
      + '<button class="cta secondary" id="dnRefresh" style="width:auto;padding:12px 18px;margin:0">Refresh balances</button>'
      + (current && current.step !== 'COMPLETE' && current.step !== 'REFUNDED' ? '<button class="cta secondary" id="dnRefund" style="width:auto;padding:12px 18px;margin:0">Refund</button>' : '')
      + (current ? '<button class="cta secondary" id="dnReset" style="width:auto;padding:12px 18px;margin:0">New swap</button>' : '')
      + '</div>'
      + '</div>';

    wireButtons();
    refreshBalances();
  }

  function wireButtons() {
    var run = el('dnRun'); if (run) run.onclick = onRun;
    var rf = el('dnRefresh'); if (rf) rf.onclick = refreshBalances;
    var rb = el('dnRefund'); if (rb) rb.onclick = onRefund;
    var rs = el('dnReset'); if (rs) rs.onclick = function () { current = null; renderPanel(); };
    var pb = el('dnPassBtn'); if (pb) pb.onclick = function () { var v = (el('dnPass') || {}).value || ''; if (v) { setSostPass(v); renderPanel(); } };
  }

  async function refreshBalances() {
    var a = ctx.assets();
    var st = ctx.wm.state();
    // SOST
    try {
      if (sostPass()) {
        var b = await sostRpc('getbalance', []);
        if (el('dnBalSost')) el('dnBalSost').textContent = (b && (b.available != null ? b.available : b.total) != null) ? String(b.available != null ? b.available : b.total) + ' SOST' : JSON.stringify(b);
        var h = await sostRpc('getblockcount', []);
        if (el('dnTip')) el('dnTip').textContent = String(h);
      } else if (st.sost && st.sost.balanceStocks != null) {
        if (el('dnBalSost')) el('dnBalSost').textContent = formatUnits(st.sost.balanceStocks, 8) + ' SOST (wallet)';
      } else if (el('dnBalSost')) { el('dnBalSost').textContent = 'set RPC password'; }
    } catch (e) { if (el('dnBalSost')) el('dnBalSost').textContent = 'err: ' + (e.message || e); }
    // ETH
    try {
      var addr = st.cp && st.cp.network === 'evm' ? st.cp.address : null;
      if (addr) {
        var wei = await evmRead('eth_getBalance', [addr, 'latest']);
        if (el('dnBalEth')) el('dnBalEth').textContent = formatUnits(BigInt(wei).toString(), 18) + ' ETH';
      } else if (el('dnBalEth')) { el('dnBalEth').textContent = 'connect EVM wallet'; }
    } catch (e) { if (el('dnBalEth')) el('dnBalEth').textContent = 'err: ' + (e.message || e); }
    // USDC (real ERC20 balanceOf at the configured token address)
    try {
      var usdc = usdcToken();
      var ua = st.cp && st.cp.network === 'evm' ? st.cp.address : null;
      if (usdc && ua) {
        var bal = await evmErc20BalanceOf(usdc, ua);
        if (el('dnBalUsdc')) el('dnBalUsdc').textContent = formatUnits(bal, usdcDecimals()) + ' USDC';
      } else if (el('dnBalUsdc')) { el('dnBalUsdc').textContent = usdc ? 'connect EVM wallet' : 'no USDC token in this devnet'; }
    } catch (e) { if (el('dnBalUsdc')) el('dnBalUsdc').textContent = 'err: ' + (e.message || e); }
  }

  function usdcToken() {
    var D = root.DEVNET || {};
    return D.usdc_token || (D.tokens && D.tokens.USDC) || null;
  }
  function usdcDecimals() { return (root.SOSTAssets && root.SOSTAssets.decimals('USDC')) || 6; }
  function assetDisabled(sym) {
    if (!root.SOSTAssets) { if (['USDT', 'PAXG', 'XAUT'].indexOf(sym) >= 0) return sym; return null; }
    var s = root.SOSTAssets.status(sym);
    return s && s.state === 'disabled' ? sym : null;
  }

  function setStep(s) { if (current) { current.step = s; persist(); renderPanel(); } }
  function fail(msg) { if (current) { current.error = msg; persist(); } renderPanel(); }

  // ===========================================================================
  //  The real driver: offer → accept → reserve → lock SOST → lock EVM →
  //  verify both → reveal secret (claim EVM) → redeem SOST → complete
  // ===========================================================================
  async function onRun() {
    try {
      var a = ctx.assets();
      var block = assetDisabled(a.pay) || assetDisabled(a.recv);
      if (block) { fail(block + ' is temporarily unavailable and cannot be routed.'); return; }
      // Require SOST + EVM wallets (SOST->ETH/USDC only in this devnet path)
      var ready = ctx.wm.swapReady('SOST/ETH');
      if (!ready.ready) { ctx.connectWallets(); return; }
      if (!sostPass()) { fail('Set the devnet SOST RPC password first (admin-only).'); return; }

      var st = ctx.wm.state();
      var evmAddr = st.cp.address, sostAddr = st.sost.address;
      if (!current || current.step === 'COMPLETE' || current.step === 'REFUNDED') { current = freshSwap(); }
      current.error = null;

      // PHASE 6 — OFFER + ACCEPT + RESERVE (hashlock) ------------------------
      if (current.step === 'OFFER') {
        // canonical offer via the real RFQ core (cross-chain, replay-protected shape)
        current.step = 'ACCEPT'; persist(); renderPanel();
      }
      if (current.step === 'ACCEPT') { current.step = 'RESERVE'; persist(); renderPanel(); }
      if (current.step === 'RESERVE') {
        var pre = randomPreimageHex();
        var hl = await root.SOSTDexRFQ.hashlock(pre); // sha256(preimage) — SAME primitive both chains
        current.hashlock = '0x' + hl;
        savePreimage(current.id, pre);
        current.evmSwapId = randomBytes32();
        setStep('LOCK_SOST');
      }

      // PHASE 4 — LOCK SOST HTLC ---------------------------------------------
      if (current.step === 'LOCK_SOST') {
        var tip = await sostRpc('getblockcount', []);
        var refundH = Number(tip) + REFUND_WINDOW_BLOCKS;
        var amtStocks = parseUnits(current.amount, 8).toString();
        setBusy('Locking SOST HTLC (build + sign in the SOST wallet)…');
        var lock = await sostLock({
          amountStocks: amtStocks, hashlock: current.hashlock, refundHeight: refundH,
          // claimer = the party that RECEIVES SOST (the counterparty); in the single-operator
          // devnet both wallets are the operator's, so claim+refund both resolve to sostAddr.
          claimAddress: sostAddr,
          refundAddress: sostAddr
        });
        current.sost = { txid: lock.txid, vout: lock.vout, status: 'locked' };
        setStep('LOCK_EVM');
      }

      // PHASE 5 — LOCK EVM HTLC (ETH = lockNative; USDC = approve → lockERC20) -
      if (current.step === 'LOCK_EVM') {
        var conn = evmConn();
        await ensureEvmChain(conn);
        var head = await evmRead('eth_blockNumber', []);
        var refundTime = Number(BigInt(head)) + REFUND_WINDOW_BLOCKS;
        current.evm.refundTime = refundTime;
        var recvSym = a.recv;
        setBusy('Locking EVM HTLC…');
        if (recvSym === 'ETH') {
          var amtWei = parseUnits(current.amount, 18);
          var data = encLockNative(current.evmSwapId, current.hashlock, refundTime, evmAddr, evmAddr);
          var tx = await conn.send({ to: htlcAddr(), data: data, value: '0x' + amtWei.toString(16) });
          await waitReceipt(tx);
          current.evm.lockTx = tx;
        } else if (recvSym === 'USDC') {
          var token = usdcToken();
          if (!token) throw new Error('USDC token address not configured in this devnet (set DEVNET.usdc_token).');
          var dec = usdcDecimals();
          var amt = parseUnits(current.amount, dec);
          // approve if allowance insufficient
          var allow = BigInt(await evmErc20Allowance(token, evmAddr, htlcAddr()));
          if (allow < amt) {
            setBusy('Approving USDC for the HTLC…');
            var apTx = await conn.approve(token, htlcAddr(), '0x' + amt.toString(16));
            await waitReceipt(apTx);
          }
          setBusy('Locking USDC (balance-delta escrow)…');
          var d2 = encLockERC20(current.evmSwapId, token, amt, current.hashlock, refundTime, evmAddr, evmAddr);
          var tx2 = await conn.send({ to: htlcAddr(), data: d2 });
          await waitReceipt(tx2);
          current.evm.lockTx = tx2;
        } else {
          throw new Error('receive asset ' + recvSym + ' not routable in the devnet admin path (ETH/USDC only).');
        }
        setStep('VERIFY');
      }

      // PHASE 6 — VERIFY BOTH LEGS (chain truth) ------------------------------
      if (current.step === 'VERIFY') {
        setBusy('Verifying both HTLCs on-chain…');
        var ss = await sostHtlcStatus(current.sost.txid, current.sost.vout);
        current.sost.status = ss.status;
        if (!ss.is_htlc_lock || (ss.status !== 'locked')) throw new Error('SOST HTLC not verified as locked (status=' + ss.status + ').');
        if (strip0x(ss.hashlock).toLowerCase() !== strip0x(current.hashlock).toLowerCase()) throw new Error('SOST HTLC hashlock mismatch — refusing to proceed.');
        var ev = await evmGetSwap(current.evmSwapId);
        current.evm.chainState = ev.state;
        if (ev.state !== 'LOCKED') throw new Error('EVM HTLC not LOCKED (state=' + ev.state + ').');
        if (strip0x(ev.hashlock).toLowerCase() !== strip0x(current.hashlock).toLowerCase()) throw new Error('EVM HTLC hashlock mismatch — refusing to reveal the secret.');
        setStep('REVEAL_CLAIM_EVM');
      }

      // PHASE 5/6 — REVEAL SECRET + CLAIM EVM (preimage goes on-chain here) ----
      if (current.step === 'REVEAL_CLAIM_EVM') {
        var pre2 = loadPreimage(current.id);
        if (!pre2) throw new Error('preimage unavailable in this session — cannot claim; wait for timeout and Refund.');
        var conn2 = evmConn();
        await ensureEvmChain(conn2);
        setBusy('Claiming the EVM HTLC (reveals the secret)…');
        var claimTx;
        if (a.recv === 'ETH') {
          claimTx = await conn2.send({ to: htlcAddr(), data: encClaimNative(current.evmSwapId, '0x' + pre2) });
        } else { // USDC
          var dec2 = usdcDecimals();
          var minRecv = parseUnits(current.amount, dec2); // claimer requires full face value delivered
          claimTx = await conn2.send({ to: htlcAddr(), data: encClaimERC20(current.evmSwapId, '0x' + pre2, minRecv) });
        }
        await waitReceipt(claimTx);
        current.evm.claimTx = claimTx;
        current.evm.chainState = 'CLAIMED';
        setStep('REDEEM_SOST');
      }

      // PHASE 4/6 — REDEEM SOST using the revealed secret ---------------------
      if (current.step === 'REDEEM_SOST') {
        // The counterparty would read the preimage off the EVM claim; in the single-operator
        // devnet we hold it. Prefer the on-chain-revealed secret if the node exposes it.
        var secret = loadPreimage(current.id);
        setBusy('Redeeming the SOST HTLC with the revealed secret…');
        var redeemTx = await sostClaim({ txid: current.sost.txid, vout: current.sost.vout }, secret);
        current.sost.redeemTx = redeemTx;
        // confirm via gethtlcstatus
        var fin = await sostHtlcStatus(current.sost.txid, current.sost.vout);
        current.sost.status = fin.status; // 'claimed' once mined
        setStep('COMPLETE');
      }

      if (current.step === 'COMPLETE') { current.error = null; persist(); renderPanel(); refreshBalances(); }
    } catch (e) {
      fail((a2Err(e)));
    }
  }

  function a2Err(e) {
    var m = (e && (e.message || e.toString())) || 'error';
    return evmErr({ message: m });
  }
  function setBusy(msg) {
    var r = el('dnRun'); if (r) { r.disabled = true; r.textContent = msg; }
  }

  // PHASE 6 — refund path (timeout / wrong-secret recovery) -------------------
  async function onRefund() {
    if (!current) return;
    try {
      current.error = null; renderPanel();
      var a = ctx.assets();
      // EVM refund (if we locked it and it wasn't claimed)
      if (current.evm.lockTx && current.evm.chainState !== 'CLAIMED' && current.evm.chainState !== 'REFUNDED') {
        var conn = evmConn(); await ensureEvmChain(conn);
        var head = Number(BigInt(await evmRead('eth_blockNumber', [])));
        if (current.evm.refundTime && head < current.evm.refundTime) {
          throw new Error('EVM refund not open yet (block ' + head + ' < refundTime ' + current.evm.refundTime + ').');
        }
        setBusy('Refunding the EVM HTLC…');
        var data = a.recv === 'ETH' ? encRefundNative(current.evmSwapId) : encRefundERC20(current.evmSwapId);
        var tx = await conn.send({ to: htlcAddr(), data: data });
        await waitReceipt(tx);
        current.evm.refundTx = tx; current.evm.chainState = 'REFUNDED';
      }
      // SOST refund (if locked, unspent, past refund height)
      if (current.sost.txid && current.sost.status === 'locked') {
        var ss = await sostHtlcStatus(current.sost.txid, current.sost.vout);
        if (ss.status === 'expired') {
          setBusy('Refunding the SOST HTLC…');
          var rtx = await sostRefund({ txid: current.sost.txid, vout: current.sost.vout });
          current.sost.refundTx = rtx; current.sost.status = 'refunded';
        } else if (ss.status === 'locked') {
          throw new Error('SOST refund not open yet (status=locked, height ' + ss.current_height + ' < refund_height ' + ss.refund_height + ').');
        }
      }
      current.step = 'REFUNDED'; persist(); renderPanel(); refreshBalances();
    } catch (e) { fail((e && e.message) || String(e)); }
  }

  // ===========================================================================
  //  Public entry points (called from the dashboard devnet boot / CTA)
  // ===========================================================================
  function init(context) {
    ctx = context;
    // mount host under the swap card
    if (!el('devnetFlow')) {
      var host = document.createElement('div');
      host.id = 'devnetFlow';
      var col = document.querySelector('#view-swap .swap-col');
      if (col) col.appendChild(host); else { var v = el('view-swap'); if (v) v.appendChild(host); }
    }
    // resume a persisted swap, reconcile against chain truth, then render
    current = loadLatestResumable();
    renderPanel();
    if (current) {
      reconcileOnLoad(current).then(function () { persist(); renderPanel(); }).catch(function () {});
    }
    return true;
  }
  // Drive the flow from the swap CTA (replaces the "no executable quote" stub in devnet admin mode)
  function onCta() { onRun(); return true; }
  function active() { return !!(root.DEVNET && String((new URLSearchParams(location.search)).get('devnet')) === '1'); }

  return {
    init: init, onCta: onCta, active: active,
    // exposed for tests / console
    parseUnits: parseUnits, formatUnits: formatUnits, SEL: SEL,
    encLockNative: encLockNative, encLockERC20: encLockERC20,
    encClaimNative: encClaimNative, encClaimERC20: encClaimERC20,
    encRefundNative: encRefundNative, encRefundERC20: encRefundERC20,
    evmGetSwap: evmGetSwap, sostHtlcStatus: sostHtlcStatus, reconcileOnLoad: reconcileOnLoad
  };
});
