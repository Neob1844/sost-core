/*
 * SOST DEX — wallet connectors (EVM EIP-6963/1193, BTC PSBT, SOST bridge).
 * ---------------------------------------------------------------------------
 * Non-custodial: every connector talks to an INJECTED provider (the browser
 * wallet) and never sees a seed or private key — it only requests accounts,
 * balances and signatures. Provider injection makes the whole layer unit-
 * testable with mock providers; REAL-WALLET-VERIFIED is an owner step in a
 * real browser, but the connector code + logic is complete and tested here.
 * No consensus/node/STRATO change.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexConnectors = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var STATUS = { NOT_DETECTED: 'NOT_DETECTED', DETECTED: 'DETECTED', SUPPORTED: 'SUPPORTED', INCOMPATIBLE: 'INCOMPATIBLE', CONNECTED: 'CONNECTED' };

  // ---- EVM (EIP-1193 provider; EIP-6963 discovery) -------------------------
  // EIP-6963: pages listen for 'eip6963:announceProvider'. discoverEip6963 takes
  // an event source (window) or, for tests, an array of announced {info,provider}.
  function discoverEip6963(source) {
    var found = [];
    if (Array.isArray(source)) return source.slice();
    if (source && source.addEventListener) {
      source.addEventListener('eip6963:announceProvider', function (ev) {
        if (ev && ev.detail && ev.detail.provider) found.push(ev.detail);
      });
      try { source.dispatchEvent(new Event('eip6963:requestProvider')); } catch (e) {}
    }
    return found;
  }

  function evm(provider) {
    if (!provider || typeof provider.request !== 'function') return { status: STATUS.NOT_DETECTED, provider: null };
    var self = {
      status: STATUS.DETECTED, provider: provider, account: null, chainId: null,
      async connect() { var accs = await provider.request({ method: 'eth_requestAccounts' }); self.account = accs && accs[0] || null; self.chainId = await provider.request({ method: 'eth_chainId' }); self.status = self.account ? STATUS.CONNECTED : STATUS.DETECTED; return self.account; },
      disconnect() { self.account = null; self.status = STATUS.DETECTED; },
      on(ev, cb) { if (provider.on) provider.on(ev, cb); },
      async switchNetwork(chainIdHex) { return provider.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: chainIdHex }] }); },
      async balance(addr) { return provider.request({ method: 'eth_getBalance', params: [addr || self.account, 'latest'] }); },
      async allowance(token, owner, spender) { var data = '0xdd62ed3e' + pad(owner) + pad(spender); return provider.request({ method: 'eth_call', params: [{ to: token, data: data }, 'latest'] }); },
      async approve(token, spender, amountHex) { var data = '0x095ea7b3' + pad(spender) + pad32(amountHex); return provider.request({ method: 'eth_sendTransaction', params: [{ from: self.account, to: token, data: data }] }); },
      async send(tx) { return provider.request({ method: 'eth_sendTransaction', params: [Object.assign({ from: self.account }, tx)] }); },
      async receipt(txHash) { return provider.request({ method: 'eth_getTransactionReceipt', params: [txHash] }); }
    };
    return self;
  }
  function pad(addr) { return (addr || '').replace(/^0x/, '').toLowerCase().padStart(64, '0'); }
  function pad32(hex) { return (hex || '').replace(/^0x/, '').padStart(64, '0'); }

  // ---- BTC (PSBT capability detection: Xverse / UniSat) --------------------
  // A wallet that can only "send BTC" is NOT atomic-swap compatible; it must be
  // able to sign a PSBT for the P2WSH HTLC claim/refund path.
  function btc(provider) {
    if (!provider) return { status: STATUS.NOT_DETECTED, provider: null };
    var canPsbt = typeof provider.signPsbt === 'function' || typeof provider.signPsbts === 'function' ||
      (provider.request && (provider.capabilities || []).indexOf('signPsbt') >= 0);
    var self = {
      status: canPsbt ? STATUS.SUPPORTED : STATUS.INCOMPATIBLE, provider: provider,
      async getAddress() { if (provider.getAddresses) return provider.getAddresses(); if (provider.requestAccounts) return provider.requestAccounts(); return null; },
      async signPsbt(psbtBase64, opts) {
        if (!canPsbt) throw new Error('WALLET_UNSUPPORTED_FOR_ATOMIC_SWAPS: no PSBT signing');
        if (provider.signPsbt) return provider.signPsbt(psbtBase64, opts);
        if (provider.signPsbts) return provider.signPsbts([psbtBase64], opts);
        return provider.request({ method: 'signPsbt', params: [psbtBase64, opts] });
      }
    };
    return self;
  }

  // ---- SOST bridge (wallet builds/signs/broadcasts; DEX never sees the key) --
  function sost(bridge) {
    if (!bridge) return { status: STATUS.NOT_DETECTED, bridge: null };
    var self = {
      status: STATUS.SUPPORTED, bridge: bridge,
      async address() { return bridge.getAddress(); },
      async balance() { return bridge.getBalance(); },
      // build* return an UNSIGNED tx template; sign() is the wallet's job, then broadcast().
      async buildLock(o) { return bridge.buildTx(Object.assign({ kind: 'htlc_lock' }, o)); },
      async buildClaim(o) { return bridge.buildTx(Object.assign({ kind: 'htlc_claim' }, o)); },
      async buildRefund(o) { return bridge.buildTx(Object.assign({ kind: 'htlc_refund' }, o)); },
      async sign(unsignedTx) { return bridge.sign(unsignedTx); },        // wallet-side
      async broadcast(signedTx) { return bridge.broadcast(signedTx); }
    };
    return self;
  }

  return { STATUS: STATUS, discoverEip6963: discoverEip6963, evm: evm, btc: btc, sost: sost };
});
