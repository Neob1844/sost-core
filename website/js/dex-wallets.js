/* SOST DEX — real wallet adapters (lab). Replaces the connectDemo() placeholder.
 *
 * Three networks, each via its STANDARD interface (no seed/private key ever reaches this code):
 *   - EVM  : EIP-6963 provider discovery + EIP-1193 (MetaMask / Rabby / Coinbase; WalletConnect via
 *            an injected connector). request accounts, chainId, balance, account/chain change events.
 *   - BTC  : injected providers (UniSat window.unisat; Xverse window.XverseProviders.BitcoinProvider).
 *            A wallet is only marked HTLC-CAPABLE if it exposes PSBT signing (signPsbt/signPsbts) —
 *            being able to SEND btc is NOT enough for our P2WSH claim/refund.
 *   - SOST : a postMessage sign-request BRIDGE to the SOST web wallet — the DEX never sees the seed;
 *            it requests an address / a signature and receives only the signed result.
 *
 * Two wallets can be connected at once (a SOST slot + a counterparty EVM|BTC slot). swapReady()
 * gates a swap on: both slots connected, correct network, and the counterparty signer HTLC-capable.
 */
(function (root, factory){ var m=factory(); if(typeof module!=='undefined'&&module.exports){module.exports=m;} if(root){root.SOSTWallets=m;} })(typeof self!=='undefined'?self:this, function(){
  'use strict';

  // ---- EVM: EIP-6963 discovery (falls back to EIP-1193 window.ethereum) ----
  function discoverEvm(win, timeoutMs){
    win = win || (typeof window!=='undefined'?window:{});
    return new Promise(function(resolve){
      var found = {}; // rdns -> {info, provider}
      function onAnnounce(ev){
        var d = ev && ev.detail; if(!d || !d.info || !d.provider) return;
        found[d.info.rdns || d.info.name] = {info:d.info, provider:d.provider};
      }
      if(win.addEventListener) win.addEventListener('eip6963:announceProvider', onAnnounce);
      if(win.dispatchEvent && win.CustomEvent) win.dispatchEvent(new win.CustomEvent('eip6963:requestProvider'));
      setTimeout(function(){
        if(win.removeEventListener) win.removeEventListener('eip6963:announceProvider', onAnnounce);
        var list = Object.keys(found).map(function(k){return found[k];});
        // EIP-1193 fallback: a bare injected provider with no 6963 announcement
        if(list.length===0 && win.ethereum){
          list.push({info:{name:(win.ethereum.isMetaMask?'MetaMask':'Injected'), rdns:'injected'}, provider:win.ethereum});
        }
        resolve(list);
      }, timeoutMs||300);
    });
  }
  async function connectEvm(provider, onChange){
    if(!provider || !provider.request) throw new Error('not an EIP-1193 provider');
    var accts = await provider.request({method:'eth_requestAccounts'});
    if(!accts || !accts.length) throw new Error('no account authorized');
    var chainId = await provider.request({method:'eth_chainId'});
    var address = accts[0];
    var balHex = await provider.request({method:'eth_getBalance', params:[address,'latest']});
    if(provider.on && onChange){
      provider.on('accountsChanged', function(a){ onChange({type:'accountsChanged', accounts:a}); });
      provider.on('chainChanged', function(c){ onChange({type:'chainChanged', chainId:c}); });
    }
    return {network:'evm', address:address, chainId:chainId, balanceWei:BigInt(balHex||'0x0').toString(),
            capable:true /* EVM HTLC = AtomicSwapHTLC contract calls; any EIP-1193 signer can call it */};
  }

  // ---- BTC: injected UniSat / Xverse; HTLC-capable only if PSBT signing exists ----
  function discoverBtc(win){
    win = win || (typeof window!=='undefined'?window:{});
    var out = [];
    if(win.unisat) out.push({info:{name:'UniSat', rdns:'unisat'}, provider:win.unisat});
    var xv = win.XverseProviders && win.XverseProviders.BitcoinProvider;
    if(xv) out.push({info:{name:'Xverse', rdns:'xverse'}, provider:xv});
    return out;
  }
  function btcCapable(provider){
    // must expose PSBT signing to complete P2WSH claim/refund — not just sendBitcoin
    return !!(provider && (provider.signPsbt || provider.signPsbts || provider.request));
  }
  async function connectBtc(entry){
    var p = entry.provider, name = entry.info && entry.info.name;
    var address=null, balanceSats=null;
    if(name==='UniSat' && p.requestAccounts){
      var a = await p.requestAccounts(); address = a && a[0];
      if(p.getBalance){ var b = await p.getBalance(); balanceSats = (b && (b.confirmed!=null?b.confirmed:b.total)) || null; }
    } else if(p.request){ // Xverse (sats-connect style) / generic
      var res = await p.request('getAddresses', {purposes:['payment']}).catch(function(){return null;});
      address = res && res.result && res.result.addresses && res.result.addresses[0] && res.result.addresses[0].address;
    }
    var capable = btcCapable(p);
    return {network:'btc', address:address, balanceSats:balanceSats, capable:capable,
            warn: capable?null:'wallet exposes no PSBT signing — cannot claim/refund the P2WSH HTLC'};
  }

  // ---- SOST: postMessage sign-request bridge to the SOST web wallet (NO seed in the DEX) ----
  function connectSost(win, opts){
    win = win || (typeof window!=='undefined'?window:{});
    opts = opts || {};
    var walletUrl = opts.walletUrl || 'sost-wallet.html';
    return new Promise(function(resolve, reject){
      var reqId = 'req-'+(opts.nonce||String(Date.now()));
      var popup = win.open ? win.open(walletUrl+'#connect='+reqId, 'sostwallet', 'width=420,height=640') : null;
      var done=false;
      function onMsg(ev){
        // only accept the wallet origin + our request id; the payload is an ADDRESS, never a key
        var d = ev && ev.data;
        if(!d || d.reqId!==reqId || d.type!=='sost:connect') return;
        done=true; if(win.removeEventListener) win.removeEventListener('message', onMsg);
        if(d.error) return reject(new Error(d.error));
        resolve({network:'sost', address:d.address, balanceStocks:d.balanceStocks||null, capable:true, via:'bridge'});
      }
      if(win.addEventListener) win.addEventListener('message', onMsg);
      setTimeout(function(){ if(!done){ if(win.removeEventListener) win.removeEventListener('message', onMsg); reject(new Error('SOST wallet connect timed out (open '+walletUrl+' and approve)')); } }, opts.timeoutMs||60000);
      if(!popup && !opts.nonce) reject(new Error('popup blocked — allow popups for the SOST wallet'));
    });
  }

  // ---- dual-connection state + swap gating ----
  function makeManager(){
    var state = { sost:null, cp:null };  // cp = the EVM or BTC counterparty slot
    return {
      state: function(){ return {sost:state.sost, cp:state.cp}; },
      setSost: function(c){ state.sost=c; },
      setCp:   function(c){ state.cp=c; },
      clear:   function(slot){ if(slot==='sost') state.sost=null; else if(slot==='cp') state.cp=null; else {state.sost=null;state.cp=null;} },
      // pair e.g. 'SOST/BTC' or 'SOST/ETH' or 'SOST/ERC20'
      swapReady: function(pair){
        if(!state.sost) return {ready:false, why:'connect a SOST wallet'};
        var want = /BTC/.test(pair) ? 'btc' : 'evm';
        if(!state.cp) return {ready:false, why:'connect a '+(want==='btc'?'Bitcoin':'EVM')+' wallet'};
        if(state.cp.network!==want) return {ready:false, why:'wrong counterparty network ('+state.cp.network+', need '+want+')'};
        if(!state.cp.capable) return {ready:false, why: state.cp.warn||'counterparty wallet cannot sign the HTLC'};
        if(!state.sost.capable) return {ready:false, why:'SOST wallet cannot sign'};
        return {ready:true};
      }
    };
  }

  return { discoverEvm:discoverEvm, connectEvm:connectEvm, discoverBtc:discoverBtc, btcCapable:btcCapable,
           connectBtc:connectBtc, connectSost:connectSost, makeManager:makeManager };
});
