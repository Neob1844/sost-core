/**
 * SOST DEX — Onboarding & UI Integration
 *
 * Connects all Phase A+B+C modules to the DEX page UI.
 * Manages public/private mode, wallet panel, AI assistant box,
 * inbox rendering, and error/empty states.
 *
 * This is the "glue" that turns individual modules into a cohesive product.
 *
 * Depends on: All Phase A+B+C modules
 */

const SOSTDEX = (function () {
  'use strict';

  var _mode = 'public'; // 'public' | 'private'
  var _initialized = false;

  // ── Initialization ────────────────────────────────────────────

  async function init() {
    if (_initialized) return;

    // Initialize crypto
    try {
      await SOSTCrypto.ready();
    } catch (e) {
      _showError('crypto-init', 'Cryptography library failed to load. Some features may be unavailable.');
    }

    // Check passkey availability
    _updatePasskeyUI();

    // Set up session callbacks
    SOSTSession.onStateChange(function (state) {
      if (state === 'unlocked') {
        _enterPrivateMode();
      } else {
        _enterPublicMode();
      }
    });

    // Check for existing identity
    var identities = await SOSTKeystore.listIdentities();
    if (identities.length > 0) {
      _showWalletPanel('unlock');
    } else {
      _showWalletPanel('create');
    }

    // Set up inbox message handler
    SOSTInbox.onMessage(function (messages) {
      _renderInboxBadge(messages.length);
      _renderInboxMessages(messages);
    });

    _initialized = true;
    _enterPublicMode();
  }

  // ── Public / Private Mode ─────────────────────────────────────

  function _enterPublicMode() {
    _mode = 'public';
    // Show public elements
    _showAll('.dex-public');
    _hideAll('.dex-private');
    // Update wallet panel
    var wp = document.getElementById('walletPanel');
    if (wp) wp.style.display = '';
    // Update status
    _updateStatusBar();
  }

  function _enterPrivateMode() {
    _mode = 'private';
    // Show private elements
    _showAll('.dex-private');
    _hideAll('.dex-public-only');
    // Hide wallet login panel
    var wp = document.getElementById('walletPanel');
    if (wp) wp.style.display = 'none';
    // Show identity info
    _updateIdentityBar();
    _updateStatusBar();
    // Fetch inbox
    SOSTInbox.fetchAndDecrypt().catch(function () {});
    // Load positions
    _refreshPositions();
  }

  // ── Wallet Panel ──────────────────────────────────────────────

  function _showWalletPanel(mode) {
    var panel = document.getElementById('walletPanel');
    if (!panel) return;

    if (mode === 'create') {
      panel.innerHTML = _walletCreateHTML();
    } else {
      panel.innerHTML = _walletUnlockHTML();
    }
  }

  function _walletCreateHTML() {
    return '<div class="dex-wallet-box">' +
      '<div style="font-size:10px;color:var(--text-muted);letter-spacing:1px;margin-bottom:8px">WALLET</div>' +
      '<p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px">Create or import a cryptographic identity to access the private DEX.</p>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<button class="btn-wallet" onclick="SOSTDEX.createIdentity()">Create Identity</button>' +
        '<button class="btn-wallet btn-wallet-secondary" onclick="SOSTDEX.showImport()">Import Backup</button>' +
      '</div>' +
      '<div id="walletForm" style="display:none;margin-top:12px"></div>' +
      '<div id="walletError" style="display:none;margin-top:8px;color:var(--red-primary);font-size:11px"></div>' +
      '<p style="font-size:9px;color:var(--text-dim);margin-top:12px">Your keys stay in your browser. The relay cannot read your encrypted deals.</p>' +
    '</div>';
  }

  function _walletUnlockHTML() {
    return '<div class="dex-wallet-box">' +
      '<div style="font-size:10px;color:var(--text-muted);letter-spacing:1px;margin-bottom:8px">WALLET</div>' +
      '<p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px">Unlock your identity to access private deal flow.</p>' +
      '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
        '<input type="password" id="walletPassphrase" placeholder="Passphrase" class="form-control" style="max-width:200px;font-size:12px" onkeydown="if(event.key===\'Enter\')SOSTDEX.unlock()">' +
        '<button class="btn-wallet" onclick="SOSTDEX.unlock()">Unlock</button>' +
        (SOSTPasskey.isAvailable() ? '<button class="btn-wallet btn-wallet-secondary" onclick="SOSTDEX.passkeyLogin()">Passkey</button>' : '') +
      '</div>' +
      '<div id="walletError" style="display:none;margin-top:8px;color:var(--red-primary);font-size:11px"></div>' +
      '<p style="font-size:9px;color:var(--text-dim);margin-top:8px"><a href="#" onclick="SOSTDEX.showImport();return false" style="color:var(--gold);text-decoration:none">Import backup</a> · <a href="#" onclick="SOSTDEX.createIdentity();return false" style="color:var(--gold);text-decoration:none">New identity</a></p>' +
    '</div>';
  }

  // ── Wallet Actions ────────────────────────────────────────────

  async function createIdentity() {
    var form = document.getElementById('walletForm');
    if (!form) return;
    form.style.display = '';
    form.innerHTML = '<div style="margin-bottom:8px">' +
      '<input type="text" id="newLabel" placeholder="Name (e.g. Alice)" class="form-control" style="max-width:200px;font-size:12px;margin-bottom:6px">' +
      '<input type="password" id="newPassphrase" placeholder="Choose a passphrase" class="form-control" style="max-width:200px;font-size:12px;margin-bottom:6px">' +
      '<input type="password" id="newPassphrase2" placeholder="Confirm passphrase" class="form-control" style="max-width:200px;font-size:12px;margin-bottom:6px">' +
      '<button class="btn-wallet" onclick="SOSTDEX._doCreate()">Create</button>' +
      '<button class="btn-wallet btn-wallet-secondary" onclick="document.getElementById(\'walletForm\').style.display=\'none\'">Cancel</button>' +
    '</div>';
  }

  async function _doCreate() {
    var label = document.getElementById('newLabel').value.trim() || 'default';
    var pass1 = document.getElementById('newPassphrase').value;
    var pass2 = document.getElementById('newPassphrase2').value;
    if (!pass1 || pass1.length < 4) return _walletError('Passphrase must be at least 4 characters.');
    if (pass1 !== pass2) return _walletError('Passphrases do not match.');

    try {
      var id = await SOSTKeystore.createIdentity(pass1, label);
      _walletError('');
      // Auto-unlock session
      await SOSTSession.unlock(id.id, pass1);
    } catch (e) {
      _walletError('Failed to create identity: ' + e.message);
    }
  }

  async function unlock() {
    var pass = document.getElementById('walletPassphrase');
    if (!pass || !pass.value) return _walletError('Enter your passphrase.');

    var identities = await SOSTKeystore.listIdentities();
    if (identities.length === 0) return _walletError('No identity found. Create one first.');

    var result = await SOSTSession.unlock(identities[0].id, pass.value);
    if (!result.ok) return _walletError('Wrong passphrase.');
    _walletError('');
    pass.value = '';
  }

  async function passkeyLogin() {
    var result = await SOSTPasskey.authenticate();
    if (!result.ok) return _walletError('Passkey authentication failed: ' + result.error);
    // After passkey auth, still need to unlock keystore
    // Show passphrase prompt with passkey-verified badge
    _walletError('');
    var form = document.getElementById('walletForm');
    if (form) {
      form.style.display = '';
      form.innerHTML = '<div style="margin-bottom:4px;font-size:10px;color:var(--green-primary)">✓ Device authenticated</div>' +
        '<input type="password" id="walletPassphrase2" placeholder="Keystore passphrase" class="form-control" style="max-width:200px;font-size:12px;margin-bottom:6px" onkeydown="if(event.key===\'Enter\')SOSTDEX.unlock2()">' +
        '<button class="btn-wallet" onclick="SOSTDEX.unlock2()">Unlock Keystore</button>';
    }
  }

  async function unlock2() {
    var pass = document.getElementById('walletPassphrase2');
    if (!pass || !pass.value) return _walletError('Enter keystore passphrase.');
    var identities = await SOSTKeystore.listIdentities();
    if (identities.length === 0) return _walletError('No identity found.');
    var result = await SOSTSession.unlock(identities[0].id, pass.value);
    if (!result.ok) return _walletError('Wrong passphrase.');
    pass.value = '';
  }

  function lockWallet() {
    SOSTSession.lock();
    SOSTPasskey.logout();
    _enterPublicMode();
    _showWalletPanel('unlock');
  }

  async function showImport() {
    var form = document.getElementById('walletForm');
    if (!form) return;
    form.style.display = '';
    form.innerHTML = '<div style="margin-bottom:8px">' +
      '<textarea id="importBlob" placeholder="Paste encrypted identity backup JSON" class="form-control" style="width:100%;max-width:400px;height:80px;font-size:11px;margin-bottom:6px"></textarea>' +
      '<button class="btn-wallet" onclick="SOSTDEX._doImport()">Import</button>' +
      '<button class="btn-wallet btn-wallet-secondary" onclick="document.getElementById(\'walletForm\').style.display=\'none\'">Cancel</button>' +
    '</div>';
  }

  async function _doImport() {
    var blob = document.getElementById('importBlob').value.trim();
    if (!blob) return _walletError('Paste the backup JSON.');
    try {
      var result = await SOSTKeystore.importEncrypted(blob);
      _walletError('');
      _showWalletPanel('unlock');
    } catch (e) {
      _walletError('Import failed: ' + e.message);
    }
  }

  async function exportIdentity() {
    // Require strong auth
    if (SOSTPasskey.isAvailable()) {
      var auth = await SOSTPasskey.ensureStrongAuth('export_keystore');
      if (!auth.ok) return alert('Authentication required to export.');
    }
    var identities = await SOSTKeystore.listIdentities();
    if (identities.length === 0) return alert('No identity to export.');
    var json = await SOSTKeystore.exportEncrypted(identities[0].id);
    if (!json) return alert('Export failed.');
    // Copy to clipboard
    navigator.clipboard.writeText(json).then(function () {
      alert('Encrypted backup copied to clipboard. Save it somewhere safe.');
    }).catch(function () {
      prompt('Copy this backup JSON:', json);
    });
  }

  // ── AI Assistant Integration ──────────────────────────────────

  function processAIInput() {
    var input = document.getElementById('aiInput');
    if (!input || !input.value.trim()) return;

    var text = input.value.trim();
    var context = { positions: _getPositionsData(), identity: SOSTKeystore.getIdentity() };
    var result = SOSTAIAssistant.process(text, context);

    _renderAIReview(result);
  }

  function _renderAIReview(result) {
    var panel = document.getElementById('aiReviewPanel');
    if (!panel) return;

    var html = '<div class="ai-review">';
    html += '<div style="font-size:10px;color:var(--text-muted);letter-spacing:1px;margin-bottom:8px">WHAT THE ASSISTANT UNDERSTOOD</div>';

    // Intent summary
    html += '<div style="margin-bottom:12px">';
    html += '<div class="ai-review-row"><span class="ai-label">Action</span><span class="ai-value">' + result.review.action + '</span></div>';
    html += '<div class="ai-review-row"><span class="ai-label">Position</span><span class="ai-value">' + result.review.position + '</span></div>';
    html += '<div class="ai-review-row"><span class="ai-label">Price</span><span class="ai-value">' + result.review.price + '</span></div>';
    html += '<div class="ai-review-row"><span class="ai-label">Expiry</span><span class="ai-value">' + result.review.expiry + '</span></div>';
    html += '<div class="ai-review-row"><span class="ai-label">Confidence</span><span class="ai-value" style="color:' + (result.confidence >= 70 ? 'var(--green-primary)' : result.confidence >= 40 ? 'var(--gold)' : 'var(--red-primary)') + '">' + result.confidence + '%</span></div>';
    html += '</div>';

    // Changes
    if (result.review.changes_sost.length > 0) {
      html += '<div style="margin-bottom:8px"><b style="color:var(--text-primary);font-size:10px">Changes in SOST:</b>';
      result.review.changes_sost.forEach(function (c) { html += '<div style="font-size:11px;color:var(--gold);padding-left:8px">→ ' + c + '</div>'; });
      html += '</div>';
    }
    if (result.review.changes_eth.length > 0) {
      html += '<div style="margin-bottom:8px"><b style="color:var(--text-primary);font-size:10px">Changes in Ethereum:</b>';
      result.review.changes_eth.forEach(function (c) { html += '<div style="font-size:11px;color:var(--cyan-primary);padding-left:8px">→ ' + c + '</div>'; });
      html += '</div>';
    }
    if (result.review.unchanged.length > 0) {
      html += '<div style="margin-bottom:8px"><b style="color:var(--text-primary);font-size:10px">Unchanged:</b>';
      result.review.unchanged.forEach(function (c) { html += '<div style="font-size:11px;color:var(--text-dim);padding-left:8px">· ' + c + '</div>'; });
      html += '</div>';
    }

    // Risks
    if (result.risks.blocking.length > 0) {
      result.risks.blocking.forEach(function (r) { html += '<div style="color:var(--red-primary);font-size:11px;margin:4px 0">✖ BLOCKING: ' + r + '</div>'; });
    }
    if (result.risks.warnings.length > 0) {
      result.risks.warnings.forEach(function (r) { html += '<div style="color:var(--gold);font-size:11px;margin:4px 0">⚠ ' + r + '</div>'; });
    }
    if (result.risks.info.length > 0) {
      result.risks.info.forEach(function (r) { html += '<div style="color:var(--text-dim);font-size:11px;margin:4px 0">ℹ ' + r + '</div>'; });
    }

    // Note
    html += '<div style="font-size:11px;color:var(--text-secondary);margin-top:8px;padding:6px 0;border-top:1px solid var(--border-dim)">' + result.assistantNote + '</div>';

    // Buttons
    html += '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">';
    if (result.canProceed) {
      html += '<button class="btn-wallet" onclick="SOSTDEX.applyAIResult()">Accept & Fill Form</button>';
    }
    html += '<button class="btn-wallet btn-wallet-secondary" onclick="document.getElementById(\'aiReviewPanel\').innerHTML=\'\'">Discard</button>';
    html += '</div>';

    html += '<div style="font-size:9px;color:var(--text-dim);margin-top:8px">The assistant fills forms only. You review and authorize every action.</div>';
    html += '</div>';

    panel.innerHTML = html;
    // Store result for apply
    panel.dataset.result = JSON.stringify(result);
  }

  function applyAIResult() {
    var panel = document.getElementById('aiReviewPanel');
    if (!panel || !panel.dataset.result) return;
    var result = JSON.parse(panel.dataset.result);
    var fields = SOSTAIAssistant.fillForm(result.intent);

    // Apply fields to form
    Object.keys(fields).forEach(function (id) {
      if (id === '_action') {
        // Trigger action selection
        var cards = document.querySelectorAll('.option-card');
        cards.forEach(function (card) {
          if (card.dataset.action === fields[id]) card.click();
        });
        return;
      }
      var el = document.getElementById(id);
      if (el) {
        el.value = fields[id];
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });

    panel.innerHTML = '<div style="color:var(--green-primary);font-size:11px;padding:8px 0">✓ Form filled. Review the fields and confirm when ready.</div>';
  }

  // ── Identity Bar ──────────────────────────────────────────────

  function _updateIdentityBar() {
    var bar = document.getElementById('identityBar');
    if (!bar) return;
    var identity = SOSTKeystore.getIdentity();
    if (!identity) {
      bar.innerHTML = '';
      return;
    }
    bar.innerHTML = '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 0">' +
      '<span style="font-size:10px;color:var(--green-primary)">● UNLOCKED</span>' +
      '<span style="font-size:10px;color:var(--text-dim)">ID: ' + identity.id + '</span>' +
      '<span style="font-size:10px;color:var(--text-dim)">Pub: ' + identity.signingPublic.substring(0, 12) + '...</span>' +
      '<button style="font-size:9px;padding:2px 8px;background:none;border:1px solid var(--border-dim);color:var(--text-dim);cursor:pointer;border-radius:4px" onclick="SOSTDEX.exportIdentity()">Export</button>' +
      '<button style="font-size:9px;padding:2px 8px;background:none;border:1px solid rgba(251,1,13,0.3);color:var(--red-primary);cursor:pointer;border-radius:4px" onclick="SOSTDEX.lockWallet()">Lock</button>' +
    '</div>';
  }

  function _updateStatusBar() {
    var bar = document.getElementById('dexStatusBar');
    if (!bar) return;
    var items = [];

    if (_mode === 'private') {
      items.push('<span style="color:var(--green-primary)">● Private Mode</span>');
      if (SOSTPasskey.isAuthenticated()) items.push('<span style="color:var(--cyan-primary)">Passkey ✓</span>');
      var counts = SOSTInbox.getCounts();
      if (counts.total > 0) items.push('<span style="color:var(--gold)">' + counts.total + ' messages</span>');
    } else {
      items.push('<span style="color:var(--text-dim)">○ Public Mode</span>');
      items.push('<span style="color:var(--text-dim)">Unlock wallet for private deal flow</span>');
    }

    bar.innerHTML = '<div style="display:flex;gap:12px;font-size:10px;letter-spacing:0.5px;flex-wrap:wrap">' + items.join('') + '</div>';
  }

  // ── Inbox Rendering ───────────────────────────────────────────

  function _renderInboxBadge(count) {
    var badge = document.getElementById('inboxBadge');
    if (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? '' : 'none';
    }
  }

  function _renderInboxMessages(messages) {
    var container = document.getElementById('inboxMessages');
    if (!container) return;
    if (messages.length === 0) {
      container.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:12px">No pending messages.</div>';
      return;
    }
    var html = '';
    messages.forEach(function (m) {
      var typeColor = m.type === 'trade_offer' ? 'var(--green-primary)' :
                      m.type === 'trade_accept' ? 'var(--cyan-primary)' :
                      m.type === 'trade_cancel' ? 'var(--red-primary)' :
                      m.type === 'settlement_notice' ? 'var(--gold)' : 'var(--text-dim)';
      html += '<div style="border-bottom:1px solid var(--border-dim);padding:8px 0;font-size:11px">';
      html += '<span style="color:' + typeColor + ';font-weight:600">' + (m.type || 'unknown').toUpperCase() + '</span>';
      html += ' <span style="color:var(--text-dim)">deal:' + (m.deal_id || '?').substring(0, 8) + '</span>';
      if (m.verified) html += ' <span style="color:var(--green-primary);font-size:9px">✓ signed</span>';
      if (m.error) html += ' <span style="color:var(--red-primary);font-size:9px">' + m.error + '</span>';
      html += '</div>';
    });
    container.innerHTML = html;
  }

  // ── Passkey UI ────────────────────────────────────────────────

  async function _updatePasskeyUI() {
    var available = await SOSTPasskey.isPlatformAvailable();
    // Store availability for UI conditionals
    window._passkeyAvailable = available;
  }

  // ── Helpers ───────────────────────────────────────────────────

  function _showError(id, msg) {
    console.warn('[SOST DEX] ' + id + ': ' + msg);
  }

  function _walletError(msg) {
    var el = document.getElementById('walletError');
    if (el) {
      el.textContent = msg;
      el.style.display = msg ? '' : 'none';
    }
  }

  function _showAll(selector) {
    document.querySelectorAll(selector).forEach(function (el) { el.style.display = ''; });
  }

  function _hideAll(selector) {
    document.querySelectorAll(selector).forEach(function (el) { el.style.display = 'none'; });
  }

  function _getPositionsData() {
    // Get cached positions from the existing DEX data fetch
    return window._dexPositions || [];
  }

  function _refreshPositions() {
    // Trigger existing position fetch
    if (typeof fetchAll === 'function') fetchAll();
  }

  return {
    init: init,
    createIdentity: createIdentity,
    _doCreate: _doCreate,
    unlock: unlock,
    unlock2: unlock2,
    passkeyLogin: passkeyLogin,
    lockWallet: lockWallet,
    showImport: showImport,
    _doImport: _doImport,
    exportIdentity: exportIdentity,
    processAIInput: processAIInput,
    applyAIResult: applyAIResult,
    getMode: function () { return _mode; }
  };
})();

// Auto-init when DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () { SOSTDEX.init(); });
} else {
  SOSTDEX.init();
}
