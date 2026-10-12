(function () {
  'use strict';
  var W = globalThis.SOSTCliWallet;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); };
  var state = { name: null, text: null, meta: null };

  function msg(id, html, kind) { var e = $(id); e.innerHTML = html; e.className = 'msg ' + (kind || ''); }
  function show(id, on) { $(id).hidden = !on; }
  function clearPw() { ['pw1', 'pw2', 'vpw'].forEach(function (i) { $(i).value = ''; }); }

  function strength(p) {
    var bytes = new TextEncoder().encode(p).length, classes = 0;
    [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].forEach(function (r) { if (r.test(p)) classes++; });
    if (bytes < 8) return ['too short (minimum 8)', 'bad'];
    if (bytes < 12 || classes < 2) return ['weak', 'warn'];
    if (bytes < 16) return ['fair', 'warn'];
    return ['strong', 'ok'];
  }

  // ------------------------------------------------------------------ 1. import
  $('file').addEventListener('change', function () {
    var f = this.files && this.files[0];
    state = { name: null, text: null, meta: null };
    show('encBox', false); show('verBox', false);
    msg('detect', '', '');
    if (!f) return;
    if (f.size > 4 * 1024 * 1024) { msg('detect', 'File too large for a wallet.', 'bad'); return; }
    var rd = new FileReader();
    rd.onload = function () {
      try {
        var m = W.inspectWallet(rd.result);
        state = { name: f.name, text: rd.result, meta: m };
        if (m.format === 'v1') {
          msg('detect', '<b>CLI v1 · UNENCRYPTED</b> <span class="tag bad">PRIVATE KEYS IN PLAIN TEXT</span><br>' +
            m.keys + ' key(s): ' + m.addresses.map(function (a, i) { return '<code>' + esc(a) + '</code> <span class="lbl">' + esc(m.labels[i] || '(no label)') + '</span>'; }).join('<br>'), 'warn');
          show('encBox', true);
        } else {
          msg('detect', '<b>CLI v2 · ENCRYPTED</b> <span class="tag ok">AES-256-GCM · scrypt</span><br>' + m.keys +
            ' key(s). Addresses listed in the file (not yet verified): ' +
            m.addresses_unverified.map(function (a) { return '<code>' + esc(a) + '</code>'; }).join(', '), 'ok');
          show('verBox', true);
        }
      } catch (e) {
        msg('detect', 'Not a supported SOST CLI wallet: ' + esc(e.message), 'bad');
      }
    };
    rd.onerror = function () { msg('detect', 'Could not read the file.', 'bad'); };
    rd.readAsText(f);
  });

  $('pw1').addEventListener('input', function () {
    var s = strength(this.value); msg('pwStrength', this.value ? 'Strength: ' + s[0] : '', s[1]);
  });

  // ------------------------------------------------------------------ 2. encrypt
  $('encBtn').addEventListener('click', async function () {
    var p1 = $('pw1').value, p2 = $('pw2').value;
    if (!state.text || !state.meta || state.meta.format !== 'v1') return;
    if (p1 !== p2) { msg('encOut', 'Passphrases do not match.', 'bad'); return; }
    var prob = W.passphraseProblem(p1);
    if (prob) { msg('encOut', esc(prob), 'bad'); return; }
    this.disabled = true;
    msg('encOut', 'Deriving the key (scrypt, ~1–3 s)…', '');
    try {
      var out = await W.encryptV1(state.text, p1);
      var ver = await W.verifyV2(out, p1);                 // re-open what we just wrote before offering it
      var same = ver.addressListMatches && JSON.stringify(ver.keys.map(function (k) { return k.address; })) === JSON.stringify(state.meta.addresses);
      if (!same) throw new Error('self-check failed — nothing was saved');
      var base = (state.name || 'wallet.json').replace(/\.json$/i, '');
      var url = URL.createObjectURL(new Blob([out], { type: 'application/json' }));
      var a = $('dl'); a.href = url; a.download = base + '.v2.json'; a.textContent = 'Download ' + base + '.v2.json';
      show('dl', true);
      setTimeout(function () { URL.revokeObjectURL(url); }, 120000);
      msg('encOut', '<b>Encrypted ✓</b> Re-opened and checked locally: ' + ver.keys.map(function (k) { return '<code>' + esc(k.address) + '</code> <span class="lbl">' + esc(k.label) + '</span>'; }).join('<br>') +
        '<br>Your original file was not modified. Save the v2 file, then verify it below with its passphrase before using it.', 'ok');
      fillWalletName(base + '.v2.json');
      out = null;
    } catch (e) {
      msg('encOut', esc(e.message), 'bad');
    } finally {
      clearPw(); $('pwStrength').textContent = ''; this.disabled = false;
      state.text = null;                                    // drop the plaintext wallet from memory as soon as practical
    }
  });

  // ------------------------------------------------------------------ 3. verify
  $('verBtn').addEventListener('click', async function () {
    var p = $('vpw').value, expected = $('expect').value;
    if (!state.text || state.meta.format !== 'v2') return;
    this.disabled = true;
    msg('verOut', 'Deriving the key (scrypt, ~1–3 s)…', '');
    try {
      var r = await W.verifyV2(state.text, p);
      var m = W.checkExpected(r.keys, expected);
      var rows = r.keys.map(function (k) { return '<tr><td><code>' + esc(k.address) + '</code></td><td>' + esc(k.label || '(no label)') + '</td></tr>'; }).join('');
      var exp = m === null ? '' : (m
        ? '<div class="match ok">EXPECTED <code>' + esc(expected.trim()) + '</code><br>FOUND in this wallet · <b>MATCH ✓</b></div>'
        : '<div class="match bad">EXPECTED <code>' + esc(expected.trim()) + '</code><br><b>NOT FOUND ⚠</b> — do not switch your miner to this file.</div>');
      msg('verOut', '<b>CLI WALLET V2 · unlocked ✓</b><br>Encryption: ' + r.cipher + ' · KDF: ' + esc(r.kdf) + ' · Keys: ' + r.keys.length +
        (r.addressListMatches ? '' : '<br><span class="tag bad">The public address list in the file does not match the encrypted keys</span>') +
        '<table class="kt"><tr><th>Address (derived from the decrypted key)</th><th>Label</th></tr>' + rows + '</table>' + exp +
        '<div class="small">Private keys are never displayed. Labels are what <code>--mining-key-label</code> must match.</div>', 'ok');
      if (r.keys.length) { $('mLabel').value = r.keys[r.keys.length - 1].label || 'default'; }
      fillWalletName(state.name);
      renderCmd();
    } catch (e) {
      msg('verOut', esc(e.message), 'bad');
    } finally { clearPw(); this.disabled = false; }
  });

  // ------------------------------------------------------------------ 4. helpers (no secrets ever)
  function q(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }
  function fillWalletName(n) { if (n && !$('mWallet').dataset.touched) $('mWallet').value = '$HOME/sost-keys/' + n; renderCmd(); }
  $('mWallet').addEventListener('input', function () { this.dataset.touched = '1'; });

  function wslText() {
    var pf = $('mPassFile').value.trim() || '$HOME/.sost/wallet.pass';
    var dir = pf.replace(/\/[^/]*$/, '') || '$HOME/.sost';
    return [
      'umask 077',
      'mkdir -p ' + dir,
      'IFS= read -r -s -p "Wallet passphrase: " WP',
      'echo',
      "printf '%s\\n' \"$WP\" > " + pf,
      'unset WP',
      'chmod 600 ' + pf,
      'ls -l ' + pf
    ].join('\n');
  }

  function renderCmd() {
    var v = function (id) { return $(id).value.trim(); };
    var lines = [v('mBin') || '$HOME/sost/sost-miner'];
    lines.push('--wallet ' + (v('mWallet') || '$HOME/sost-keys/wallet.v2.json'));
    lines.push('--wallet-passphrase-file ' + (v('mPassFile') || '$HOME/.sost/wallet.pass'));
    lines.push('--mining-key-label ' + q(v('mLabel') || 'default'));
    lines.push('--genesis ' + (v('mGenesis') || '$HOME/sost/genesis_block.json'));
    lines.push('--rpc ' + (v('mRpc') || '127.0.0.1:18232'));
    if (v('mUser')) lines.push('--rpc-user ' + q(v('mUser')));
    if (v('mRpcPassFile')) lines.push('--rpc-pass-file ' + v('mRpcPassFile'));
    lines.push('--profile ' + ($('mProfile').value || 'mainnet'));
    lines.push('--threads ' + (parseInt(v('mThreads'), 10) > 0 ? parseInt(v('mThreads'), 10) : 4));
    lines.push('--blocks 999999 --realtime');
    $('cmd').textContent = lines.join(' \\\n  ');
    $('wsl').textContent = wslText();
  }
  ['mBin', 'mWallet', 'mPassFile', 'mLabel', 'mGenesis', 'mRpc', 'mUser', 'mRpcPassFile', 'mThreads', 'mProfile'].forEach(function (id) {
    $(id).addEventListener('input', renderCmd); $(id).addEventListener('change', renderCmd);
  });

  function copy(id, btn) {
    var t = $(id).textContent;
    var done = function () { var o = btn.textContent; btn.textContent = 'Copied ✓'; setTimeout(function () { btn.textContent = o; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(done, function () { selectText(id); });
    else selectText(id);
  }
  function selectText(id) { var r = document.createRange(); r.selectNodeContents($(id)); var s = getSelection(); s.removeAllRanges(); s.addRange(r); }
  $('copyWsl').addEventListener('click', function () { copy('wsl', this); });
  $('copyCmd').addEventListener('click', function () { copy('cmd', this); });

  renderCmd();
  $('ready').textContent = 'Ready · crypto loaded locally · this page cannot make network connections';
})();
