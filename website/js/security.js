/* SOST Security Layer — XSS protection, auto-lock, injection detection */

// === XSS SANITIZATION ===
function sanitize(str){
  if(typeof str!=='string')return'';
  var d=document.createElement('div');d.textContent=str;return d.innerHTML;
}

// === WALLET AUTO-LOCK (5 min inactivity) ===
var _lastActivity=Date.now();
['mousemove','keypress','touchstart','click'].forEach(function(e){
  document.addEventListener(e,function(){_lastActivity=Date.now()},{passive:true});
});
setInterval(function(){
  if(Date.now()-_lastActivity>300000){
    // Clear sensitive data from global scope
    if(window.walletPrivKey){window.walletPrivKey=null;}
    if(window.decryptedKey){window.decryptedKey=null;}
    if(typeof lockWallet==='function')try{lockWallet();}catch(e){}
  }
},30000);

// === EXTENSION INJECTION DETECTION ===
try{
  var _secObs=new MutationObserver(function(muts){
    muts.forEach(function(m){
      m.addedNodes.forEach(function(node){
        if(node.tagName==='SCRIPT'&&node.src&&
           node.src.indexOf('sostcore.com')<0&&
           node.src.indexOf('jsdelivr')<0&&
           node.src.indexOf('unpkg')<0&&
           node.src.indexOf('cdnjs')<0&&
           node.src.indexOf('googleapis')<0){
          console.warn('SECURITY: Blocked external script:',node.src);
          node.remove();
        }
      });
    });
  });
  _secObs.observe(document.documentElement,{childList:true,subtree:true});
}catch(e){}

// === WALLET CAPSULE HOTFIXES (web/UI only, no consensus) ===
(function(){
  'use strict';
  if(!/sost-wallet\.html(?:$|[?#])/.test(location.pathname + location.search + location.hash)) return;
  if(window.__sostCapsuleHotfixV172) return;
  window.__sostCapsuleHotfixV172 = true;

  var STANDARD_TX_MAX_BYTES = 16000;
  var CAPSULE_ACTIVATION_HEIGHT_WEB = 7350;
  var CAP_DOC_REF_MAX_LOCATOR = 96;
  var CAP_OPEN_MAX = 80;
  var CAP_STRUCTURED_MAX = 128;
  var CAP_CERT_MAX = 64;
  var textEncoder = new TextEncoder();
  var docRefState = { fileName:'', size:0, hash:null, ready:false, error:'' };

  function hotfixReady(){
    return typeof window.buildAndSignTx === 'function' &&
           typeof window.buildAndSignManyTx === 'function' &&
           typeof window.sendTransaction === 'function' &&
           typeof window.concatBytes === 'function' &&
           typeof window.writeU64LE === 'function' &&
           typeof window.writeU32LE === 'function' &&
           typeof window.doubleSha256 === 'function' &&
           typeof window.addressToPKH === 'function' &&
           typeof window.bytesToHex === 'function' &&
           typeof window.encodeVarInt === 'function' &&
           typeof window.hexToBytes === 'function' &&
           typeof window.validateAddress === 'function' &&
           typeof window.parseSost === 'function' &&
           typeof window.formatSost === 'function' &&
           typeof window.rpcCall === 'function';
  }

  function modeMax(type){
    if(type === 'open_note' || type === 'sealed_note') return CAP_OPEN_MAX;
    if(type === 'doc_ref' || type === 'doc_ref_sealed') return CAP_DOC_REF_MAX_LOCATOR;
    if(type === 'template' || type === 'template_sealed') return CAP_STRUCTURED_MAX;
    if(type === 'cert') return CAP_CERT_MAX;
    return 0;
  }

  function byteLen(s){ return textEncoder.encode(s || '').length; }

  function locatorType(locator){
    var s = (locator || '').trim().toLowerCase();
    if(!s) return 0;
    if(s.indexOf('ipfs://') === 0 || s.indexOf('bafy') === 0 || s.indexOf('qm') === 0) return 3;
    if(s.indexOf('https://') === 0) return 2;
    if(s.charAt(0) === '/') return 1;
    return 4;
  }

  function u64le(n){
    var out = new Uint8Array(8), v = BigInt(n || 0);
    for(var i=0;i<8;i++) out[i] = Number((v >> BigInt(i*8)) & 0xffn);
    return out;
  }
  function u32le(n){
    var v = Number(n || 0) >>> 0;
    return new Uint8Array([v & 255, (v>>>8)&255, (v>>>16)&255, (v>>>24)&255]);
  }
  function zeros32(){ return new Uint8Array(32); }

  function encodeCapsuleHeader(type, flags, templateId, locType, hashAlg, encAlg, bodyLen){
    return new Uint8Array([0x53,0x43,0x01,type&255,flags&255,templateId&255,locType&255,hashAlg&255,encAlg&255,bodyLen&255,0,0]);
  }

  function buildDocRefPayload(locator){
    if(!docRefState.ready || !docRefState.hash) throw new Error('Document Reference needs a selected file. Pick a file and wait until SHA-256 says ready.');
    if(docRefState.size > 0xffffffff) throw new Error('Document Reference file is too large for v1 metadata (max 4GB file_size field).');
    var loc = textEncoder.encode((locator || '').trim());
    if(loc.length === 0) throw new Error('Document Reference needs a URL, IPFS CID, or opaque locator.');
    if(loc.length > CAP_DOC_REF_MAX_LOCATOR) throw new Error('Document locator is ' + loc.length + ' bytes (max ' + CAP_DOC_REF_MAX_LOCATOR + '). Shorten it.');
    var body = window.concatBytes(u64le(0), u32le(docRefState.size), docRefState.hash, zeros32(), new Uint8Array([loc.length]), loc);
    if(body.length > 243) throw new Error('Document Reference body is ' + body.length + ' bytes (max 243). Shorten the locator.');
    var header = encodeCapsuleHeader(0x03, 0, 0, locatorType(locator), 0x01, 0, body.length);
    return window.concatBytes(header, body);
  }

  function ensureDocRefUI(){
    var textWrap = document.getElementById('capsuleTextWrap');
    if(!textWrap || document.getElementById('capsuleDocRefWrap')) return;
    var wrap = document.createElement('div');
    wrap.id = 'capsuleDocRefWrap';
    wrap.style.cssText = 'display:none;margin-top:8px;border:1px solid rgba(251,191,36,.25);background:rgba(251,191,36,.04);padding:8px;border-radius:4px';
    wrap.innerHTML = [
      '<div style="font-size:11px;color:#fbbf24;margin-bottom:6px;font-weight:600">Document Reference</div>',
      '<input id="capsuleDocFile" type="file" class="form-input" style="font-size:12px;margin-bottom:6px">',
      '<div id="capsuleDocStatus" style="font-size:10px;color:var(--text-dim);line-height:1.5">Pick a file. The wallet stores only SHA-256 + size + locator on-chain; it does not upload the file.</div>'
    ].join('');
    textWrap.parentNode.insertBefore(wrap, textWrap);
    var input = document.getElementById('capsuleDocFile');
    input.addEventListener('change', async function(){
      var status = document.getElementById('capsuleDocStatus');
      docRefState = { fileName:'', size:0, hash:null, ready:false, error:'' };
      var file = input.files && input.files[0];
      if(!file){ if(status) status.textContent = 'No file selected.'; return; }
      if(file.size > 50 * 1024 * 1024){
        docRefState.error = 'File is above 50 MB. Use CLI for very large document hashing.';
        if(status) status.textContent = docRefState.error;
        return;
      }
      if(status) status.textContent = 'Hashing ' + file.name + '...';
      try{
        var buf = await file.arrayBuffer();
        var digest = await crypto.subtle.digest('SHA-256', buf);
        docRefState = { fileName:file.name, size:file.size, hash:new Uint8Array(digest), ready:true, error:'' };
        if(status) status.textContent = 'Ready: ' + file.name + ' · ' + file.size + ' bytes · SHA-256 locked. Put URL/IPFS/locator in the text field below.';
      }catch(e){
        docRefState.error = e && e.message ? e.message : String(e);
        if(status) status.textContent = 'Hash failed: ' + docRefState.error;
      }
    });
  }

  function refreshCounterHotfix(){
    var ta = document.getElementById('capsuleText');
    var counter = document.getElementById('capsuleCharCount');
    var sel = document.getElementById('capsuleType');
    if(!ta || !counter || !sel) return;
    var max = modeMax(sel.value);
    if(!max){ counter.textContent = ''; return; }
    var n = byteLen(ta.value || '');
    counter.textContent = n + ' / ' + max + ' bytes';
    counter.style.color = n > max ? '#fb010d' : (n > max * 0.9 ? '#fbbf24' : 'var(--text-dim)');
    counter.style.fontWeight = n > max ? '700' : 'normal';
  }

  function patchCapsuleUI(){
    ensureDocRefUI();
    var oldUpdate = window.updateCapsuleUI;
    if(typeof oldUpdate === 'function' && !oldUpdate.__sostHotfixWrapped){
      window.updateCapsuleUI = function(){
        oldUpdate.apply(this, arguments);
        var sel = document.getElementById('capsuleType');
        var ta = document.getElementById('capsuleText');
        var docWrap = document.getElementById('capsuleDocRefWrap');
        if(sel && docWrap) docWrap.style.display = sel.value === 'doc_ref' ? 'block' : 'none';
        if(sel && ta && sel.value === 'doc_ref'){
          ta.placeholder = 'Document locator: https://..., ipfs://..., CID, or internal reference';
          ta.maxLength = CAP_DOC_REF_MAX_LOCATOR;
        }
        refreshCounterHotfix();
      };
      window.updateCapsuleUI.__sostHotfixWrapped = true;
    }
    var ta = document.getElementById('capsuleText');
    if(ta && !ta.__sostHotfixCounter){
      ta.__sostHotfixCounter = true;
      ta.addEventListener('input', refreshCounterHotfix);
      ta.addEventListener('paste', function(){ setTimeout(refreshCounterHotfix, 0); });
    }
    var sel = document.getElementById('capsuleType');
    if(sel && !sel.__sostHotfixCounter){
      sel.__sostHotfixCounter = true;
      sel.addEventListener('change', function(){ setTimeout(refreshCounterHotfix, 0); });
    }
    if(typeof window.updateCapsuleUI === 'function') window.updateCapsuleUI();
  }

  function patchBuildCapsule(){
    var original = window.buildCapsulePayloadFromForm;
    window.__sostOriginalBuildCapsulePayloadFromForm = original;
    window.__sostBuildCapsulePayloadFromFormV172 = function(){
      var sel = document.getElementById('capsuleType');
      var ta = document.getElementById('capsuleText');
      var mode = (sel && sel.value) || 'none';
      var text = (ta && ta.value) || '';
      if(mode === 'doc_ref') return buildDocRefPayload(text);
      if(mode === 'sealed_note' || mode === 'doc_ref_sealed' || mode === 'template_sealed'){
        throw new Error('Encrypted Capsule modes are planned, not enabled in the web wallet yet. They need a recipient public key and one ECIES envelope per recipient. Use a public mode for now.');
      }
      return original.apply(this, arguments);
    };
    window.buildCapsulePayloadFromForm = window.__sostBuildCapsulePayloadFromFormV172;
    try{ window.eval('buildCapsulePayloadFromForm = window.__sostBuildCapsulePayloadFromFormV172'); }catch(e){}
  }

  function assertStandardTx(rawTx, context){
    var bytes = rawTx ? rawTx.length / 2 : 0;
    if(bytes > STANDARD_TX_MAX_BYTES){
      throw new Error((context || 'Transaction') + ' is ' + bytes + ' bytes, above the 16,000-byte standard relay limit. Split it into smaller sends, consolidate UTXOs first, or reduce recipients/capsule data. No funds were spent.');
    }
  }

  function patchSingleBuilder(){
    var original = window.buildAndSignTx;
    window.__sostOriginalBuildAndSignTx = original;
    window.__sostPatchedBuildAndSignTx = async function(){
      var built = await original.apply(this, arguments);
      assertStandardTx(built && built.rawTx, 'Transaction');
      return built;
    };
    window.buildAndSignTx = window.__sostPatchedBuildAndSignTx;
    try{ window.eval('buildAndSignTx = window.__sostPatchedBuildAndSignTx'); }catch(e){}
  }

  function patchManyBuilder(){
    window.__sostPatchedBuildAndSignManyTx = async function(utxos, recipients, feeStocks, changeAddr, capsulePayload){
      var cap = capsulePayload instanceof Uint8Array ? capsulePayload : new Uint8Array(0);
      if(cap.length > 255) throw new Error('Capsule payload exceeds 255 bytes (sighash limit); refusing to sign.');
      if(!Array.isArray(recipients) || recipients.length === 0) throw new Error('No recipients');
      var totalOut = 0;
      for(var ri=0; ri<recipients.length; ri++){
        var r = recipients[ri];
        if(!r.address || !window.validateAddress(r.address)) throw new Error('Invalid recipient address: ' + (r.address || ''));
        if(!Number.isFinite(r.amount) || r.amount <= 0) throw new Error('Recipient amount must be positive: ' + r.address);
        totalOut += r.amount;
      }
      var sorted = utxos.slice().sort(function(a,b){ return a.amount - b.amount; });
      var selected = [], total = 0;
      for(var ui=0; ui<sorted.length; ui++){
        selected.push(sorted[ui]); total += sorted[ui].amount;
        if(total >= totalOut + feeStocks) break;
      }
      if(total < totalOut + feeStocks) throw new Error('Insufficient funds');
      var change = total - totalOut - feeStocks;
      var txOutputs = recipients.map(function(r){ return { address:r.address, amount:r.amount, type:0x00, payload:cap }; });
      if(change > 0) txOutputs.push({ address:changeAddr, amount:change, type:0x00, payload:new Uint8Array(0) });

      var pubKeyBytes = window.hexToBytes(wallet.pubKey);
      var genesisBytes = window.hexToBytes('6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37');
      var hpParts = [];
      for(var i=0; i<selected.length; i++){ hpParts.push(window.hexToBytes(selected[i].txid)); hpParts.push(window.writeU32LE(selected[i].vout)); }
      var hashPrevouts = window.doubleSha256(window.concatBytes.apply(null, hpParts));

      var hoParts = [];
      for(var oi=0; oi<txOutputs.length; oi++){
        var out = txOutputs[oi];
        var pl = out.payload || new Uint8Array(0);
        if(pl.length > 255) throw new Error('output payload exceeds 255 bytes (sighash limit)');
        hoParts.push(window.writeU64LE(out.amount));
        hoParts.push(new Uint8Array([out.type]));
        hoParts.push(window.addressToPKH(out.address));
        hoParts.push(new Uint8Array([pl.length & 0xff])); // sighash u8, wire below uses u16 LE
        if(pl.length > 0) hoParts.push(pl);
      }
      var hashOutputs = window.doubleSha256(window.concatBytes.apply(null, hoParts));

      var signatures = [];
      for(var si=0; si<selected.length; si++){
        var u = selected[si];
        var spentType = u.output_type || u.type || 0x00;
        var preimage = window.concatBytes(
          window.writeU32LE(1), new Uint8Array([0x00]), hashPrevouts,
          window.hexToBytes(u.txid), window.writeU32LE(u.vout), window.writeU64LE(u.amount),
          new Uint8Array([spentType]), hashOutputs, genesisBytes
        );
        var hash = window.doubleSha256(preimage);
        var sig = secp.sign(hash, wallet.privKey, { lowS:true });
        signatures.push(sig.toCompactRawBytes());
      }

      var parts = [];
      parts.push(window.writeU32LE(1));
      parts.push(new Uint8Array([0x00]));
      parts.push(window.encodeVarInt(selected.length));
      for(var ii=0; ii<selected.length; ii++){
        var su = selected[ii];
        parts.push(window.hexToBytes(su.txid));
        parts.push(window.writeU32LE(su.vout));
        parts.push(signatures[ii]);
        parts.push(pubKeyBytes);
      }
      parts.push(window.encodeVarInt(txOutputs.length));
      for(var po=0; po<txOutputs.length; po++){
        var tout = txOutputs[po];
        var payload = tout.payload || new Uint8Array(0);
        parts.push(window.writeU64LE(tout.amount));
        parts.push(new Uint8Array([tout.type]));
        parts.push(window.addressToPKH(tout.address));
        parts.push(new Uint8Array([payload.length & 0xff, (payload.length >>> 8) & 0xff])); // wire u16 LE
        if(payload.length > 0) parts.push(payload);
      }
      var rawTx = window.bytesToHex(window.concatBytes.apply(null, parts));
      assertStandardTx(rawTx, 'Multi-recipient transaction');
      return { rawTx:rawTx, selected:selected, totalOut:totalOut, change:change };
    };
    window.buildAndSignManyTx = window.__sostPatchedBuildAndSignManyTx;
    try{ window.eval('buildAndSignManyTx = window.__sostPatchedBuildAndSignManyTx'); }catch(e){}
  }

  function patchSendMany(){
    window.__sostPatchedSendTransactionMany = async function(recipients, capsulePayload){
      var feePerByte = parseInt(document.getElementById('sendFee').value) || 1000;
      var cap = capsulePayload instanceof Uint8Array ? capsulePayload : new Uint8Array(0);
      if(typeof isTotpEnabled === 'function' && isTotpEnabled()){
        var code = document.getElementById('sendTotp').value.trim();
        if(!(await verifyTotpCode(code))) return showError('sendResult', '2FA code is invalid');
      }
      document.getElementById('sendBtn').disabled = true;
      try{
        var both = await Promise.all([window.rpcCall('getinfo'), window.rpcCall('getaddressinfo', [wallet.address])]);
        var nodeInfo = both[0], balResult = both[1];
        var chainHeight = nodeInfo.blocks || 0;
        if(cap.length > 0 && chainHeight < CAPSULE_ACTIVATION_HEIGHT_WEB) throw new Error('Capsule attach requires block ' + CAPSULE_ACTIVATION_HEIGHT_WEB + ' or later.');
        var rawUtxos = balResult.utxos || [];
        if(rawUtxos.length === 0) throw new Error('No UTXOs available');
        var utxos = rawUtxos.map(function(u){
          var x = {}; for(var k in u) x[k] = u[k];
          x.amount = Math.round((u.amount || 0) * SAT);
          x.confs = chainHeight - (u.height || 0);
          return x;
        }).filter(function(u){ return !u.coinbase || u.confs >= 1000; });
        if(utxos.length === 0) throw new Error('No spendable UTXOs (coinbase needs 1000 confs)');

        var totalOut = recipients.reduce(function(s,r){ return s + r.amount; }, 0);
        var outputCount = recipients.length + 1;
        var seedInputCount = Math.min(utxos.length, 10);
        var seedPayloadBytes = cap.length > 0 ? cap.length * recipients.length : 0;
        var seedSize = 148 * seedInputCount + 34 * outputCount + 10 + seedPayloadBytes;
        var feeStocks = feePerByte * seedSize;
        var built = await window.__sostPatchedBuildAndSignManyTx(utxos, recipients, feeStocks, wallet.address, cap);
        var rawTx = built.rawTx;
        var txSize = rawTx.length / 2;
        var realFee = feePerByte * txSize;
        if(realFee !== feeStocks){
          feeStocks = realFee;
          built = await window.__sostPatchedBuildAndSignManyTx(utxos, recipients, feeStocks, wallet.address, cap);
          rawTx = built.rawTx;
          txSize = rawTx.length / 2;
          var finalFee = feePerByte * txSize;
          if(finalFee > feeStocks){
            feeStocks = finalFee;
            built = await window.__sostPatchedBuildAndSignManyTx(utxos, recipients, feeStocks, wallet.address, cap);
            rawTx = built.rawTx;
            txSize = rawTx.length / 2;
          }
        }
        assertStandardTx(rawTx, 'Multi-recipient transaction');
        var inputCount = built.selected.length;
        var changeAmt = built.change || 0;
        var capLine = cap.length > 0 ? ('Capsule:   same public payload attached to ' + recipients.length + ' payment outputs (' + cap.length + ' bytes each)\n') : '';
        var lines = recipients.map(function(r,i){ return '  ' + (i+1) + '. ' + r.address.substring(0,12) + '...  ' + window.formatSost(r.amount) + ' SOST'; }).join('\n');
        var confirmMsg = 'SENDMANY CONFIRMATION\n\n' +
          'Recipients: ' + recipients.length + '\n' + lines + '\n\n' +
          capLine +
          'Total out: ' + window.formatSost(totalOut) + ' SOST\n' +
          'Fee rate:  ' + feePerByte + ' st/B\n' +
          'TX size:   ' + txSize + ' bytes (standard limit 16,000)\n' +
          'Total fee: ' + window.formatSost(feeStocks) + ' SOST\n' +
          'Inputs:    ' + inputCount + ' UTXOs\n' +
          'Change:    ' + window.formatSost(Math.max(0, changeAmt)) + ' SOST\n\n' +
          'Confirm and broadcast?';
        if(!confirm(confirmMsg)){ showError('sendResult', 'Transaction cancelled by user.'); return; }
        var result = await window.rpcCall('sendrawtransaction', [rawTx]);
        var txid = result.txid || result || 'unknown';
        showSuccess('sendResult', '<div style="border:1px solid var(--green-primary,#4ade80);border-radius:6px;padding:12px;margin-top:8px;background:rgba(74,222,128,0.03)"><div style="color:var(--green-primary);font-weight:600;margin-bottom:8px">Transaction Broadcast</div><div style="font-size:12px;line-height:1.8"><div><span style="color:var(--text-dim)">TXID</span> <a href="https://sostcore.com/sost-explorer.html" target="_blank" style="color:var(--cyan-primary,#67e8f9);word-break:break-all;text-decoration:none">' + txid + '</a></div><div><span style="color:var(--text-dim)">RECIPIENTS</span> ' + recipients.length + '</div><div><span style="color:var(--text-dim)">TOTAL OUT</span> ' + window.formatSost(totalOut) + ' SOST</div><div><span style="color:var(--text-dim)">FEE</span> ' + window.formatSost(feeStocks) + ' SOST</div><div><span style="color:var(--text-dim)">CAPSULE</span> ' + (cap.length > 0 ? 'attached to every payment output' : 'none') + '</div><div><span style="color:var(--text-dim)">STATUS</span> Broadcast — waiting for confirmation</div></div></div>');
        if(typeof saveTxToHistory === 'function') saveTxToHistory({ txid:txid, type:'sendmany', recipients:recipients.map(function(r){ return {address:r.address, amount:r.amount}; }), amount:totalOut, fee:feeStocks, time:Date.now(), inputs:built.selected.map(function(u){ return {txid:u.txid, vout:u.vout, amount:u.amount, type:u.output_type || 0}; }) });
        document.querySelectorAll('#recipientRows .recipient-row').forEach(function(row,i){ if(i===0){ document.getElementById('sendTo').value=''; document.getElementById('sendAmount').value=''; } else row.remove(); });
      }catch(e){
        console.error('[sendmany capsule hotfix] error:', e);
        showError('sendResult', 'Send failed: ' + (e.message || e));
      }finally{
        document.getElementById('sendBtn').disabled = false;
      }
    };
    window.sendTransactionMany = window.__sostPatchedSendTransactionMany;
    try{ window.eval('sendTransactionMany = window.__sostPatchedSendTransactionMany'); }catch(e){}
  }

  function patchSendTransaction(){
    var original = window.sendTransaction;
    window.__sostOriginalSendTransaction = original;
    window.__sostPatchedSendTransaction = async function(){
      var recipients;
      try{ recipients = collectRecipients(); }
      catch(e){ return showError('sendResult', e.message || String(e)); }
      if(recipients.length <= 1) return original.apply(this, arguments);
      var payload = new Uint8Array(0);
      try{ payload = window.__sostBuildCapsulePayloadFromFormV172 ? window.__sostBuildCapsulePayloadFromFormV172() : buildCapsulePayloadFromForm(); }
      catch(e){ return showError('sendResult', 'Capsule: ' + (e.message || e)); }
      return window.__sostPatchedSendTransactionMany(recipients, payload);
    };
    window.sendTransaction = window.__sostPatchedSendTransaction;
    try{ window.eval('sendTransaction = window.__sostPatchedSendTransaction'); }catch(e){}
  }

  function install(){
    if(!hotfixReady()) return setTimeout(install, 80);
    if(window.__sostCapsuleHotfixInstalled) return;
    window.__sostCapsuleHotfixInstalled = true;
    patchCapsuleUI();
    patchBuildCapsule();
    patchSingleBuilder();
    patchManyBuilder();
    patchSendMany();
    patchSendTransaction();
    console.info('[SOST] wallet capsule hotfix v172 active: byte counter, doc-ref UI, public capsule sendmany, 16KB preflight.');
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
