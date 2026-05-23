// SOST DEX — Local-only anti-scam warning layer.
//
// Hard invariants:
//   - Runs ENTIRELY in the user's browser.
//   - Reads only the text the user themselves typed into the AI assistant
//     input box.
//   - Does NOT read, intercept, log, store, or transmit any private trade
//     content, any decrypted message, any signed payload, any wallet data,
//     or any other client-side data.
//   - Does NOT block actions by default. Shows a warning + requires the
//     user to confirm explicitly before proceeding.
//   - Does NOT make any network call.
//
// What it does:
//   - Hooks into the AI assistant input (single text field where the user
//     types intent in natural language).
//   - Before SOSTDEX.processAIInput() runs (which itself is local-only and
//     fills the structured trade composer form), the hook scans the user's
//     typed text for known scam patterns.
//   - If patterns are found, shows a local modal that the user must
//     acknowledge before processAIInput() continues.
//
// The patterns below are intentionally narrow — they target socially-
// engineered phrases a SCAMMER might pressure a victim to TYPE into the
// AI input ("I'll send you my seed phrase to verify", "release after I
// send screenshot", etc.). Normal trade-intent text does not trigger.

(function () {
  'use strict';

  if (typeof window === 'undefined') return;

  // Pattern set — kept small and high-precision. Each one targets a phrase
  // structure that should NEVER appear in a legitimate trade intent.
  var SCAM_PATTERNS = [
    {
      id: 'seed_phrase',
      label: 'seed phrase / private key reference',
      regex: /(seed\s*phrase|recovery\s*phrase|private\s*key|24\s*words?|12\s*words?|backup\s*phrase|mnemonic)/i,
      msg: 'Mentions a seed phrase, private key, or recovery phrase. ' +
           'NO legitimate trade ever requires sharing these. Anyone ' +
           'asking is a scammer.'
    },
    {
      id: 'screen_share',
      label: 'screen-share / remote-access request',
      regex: /(screen\s*share|share\s*(my|your)?\s*screen|teamviewer|anydesk|remote\s*desktop|remote\s*access)/i,
      msg: 'Mentions screen-sharing or remote-access tools. NO legitimate ' +
           'trade requires giving someone remote control of your device.'
    },
    {
      id: 'advance_fee',
      label: 'advance / activation / unlock fee',
      regex: /(activation|unlock|release|escrow|gas|processing|tax|withdrawal)\s*fee\s*(first|required)|pay\s*(a\s*)?(small\s*)?fee\s*first|small\s*fee\s*to\s*(release|unlock)/i,
      msg: 'Mentions an out-of-process fee that must be paid first to ' +
           'unlock something. SOST has no such fee. This is the classic ' +
           'advance-fee scam pattern.'
    },
    {
      id: 'release_first',
      label: 'release / send first',
      regex: /(release|send)\s*(it|the\s*coins?|the\s*sost|the\s*position)?\s*first|i'?ll\s*send\s*(it|mine|after)|pay\s*(first|now)\s*(and\s*)?i'?ll/i,
      msg: 'Mentions a counterparty asking you to release or send funds ' +
           'first before they fulfil their side. Use a small test ' +
           'transaction or a mutually-trusted on-chain escrow contract.'
    },
    {
      id: 'urgency',
      label: 'urgency / pressure',
      regex: /(hurry|urgent|asap|limited\s*time|deal\s*expires|listing\s*closes|last\s*chance|final\s*offer|right\s*now)/i,
      msg: 'Mentions time pressure or urgency. Legitimate trades do not ' +
           'require you to act before you can verify.'
    },
    {
      id: 'guaranteed',
      label: 'guaranteed profit / outcome',
      regex: /(guaranteed|risk[\-\s]*free|no\s*risk)\s*(profit|return|gain|trade|deal|swap|listing)/i,
      msg: 'Mentions guaranteed profit, risk-free trade, or similar. ' +
           'There are no guaranteed outcomes in trading. This is scam ' +
           'vocabulary.'
    },
    {
      id: 'screenshot_proof',
      label: 'screenshot as proof',
      regex: /screenshot\s*(is|as|of)?\s*(proof|enough)|here'?s?\s*(the|my|a)?\s*screenshot|i\s*sent\s*(you\s*)?(the\s*)?screenshot/i,
      msg: 'Mentions a screenshot as proof of payment. Screenshots are ' +
           'editable. ALWAYS verify the actual txid in the explorer / ' +
           'your wallet directly.'
    },
    {
      id: 'official_support_dm',
      label: 'official-support DM claim',
      regex: /(official|sost)\s*support\s*(dm|direct\s*message|will\s*help|will\s*contact)|admin\s*will\s*(dm|message|contact)/i,
      msg: 'Mentions SOST support / admins reaching out via DM. SOST ' +
           'admins NEVER initiate direct messages.'
    },
    {
      id: 'lookalike_domain',
      label: 'lookalike DEX domain',
      regex: /(sost[\-_.]?(dex|verify|support|admin|official|wallet|portal|gateway|trade|recover|claim))[\-_.](net|org|io|app|com|xyz|finance|exchange)|sostcore[\-_.](net|org|io|app|xyz)/i,
      msg: 'Mentions a domain that looks like SOST but is NOT ' +
           'sostcore.com or sostprotocol.com. Lookalike domains are ' +
           'phishing sites.'
    },
    {
      id: 'wallet_verification_phishing',
      label: 'wallet-verification phishing',
      regex: /verify\s*your\s*wallet|wallet\s*verification|connect\s*your\s*wallet\s*to\s*(verify|validate|sync)|wallet\s*will\s*be\s*(flagged|frozen|blocked)/i,
      msg: 'Mentions wallet verification or wallet-flagging threats. ' +
           'SOST has no such system. This is a phishing pattern designed ' +
           'to steal seed phrases.'
    }
  ];

  function findScamPatterns(text) {
    if (!text || typeof text !== 'string') return [];
    var hits = [];
    for (var i = 0; i < SCAM_PATTERNS.length; i++) {
      if (SCAM_PATTERNS[i].regex.test(text)) {
        hits.push(SCAM_PATTERNS[i]);
      }
    }
    return hits;
  }

  function buildWarningHtml(hits) {
    var rows = hits.map(function (h) {
      return '<li><b>' + h.label + '</b><br><span style="color:#94a3b8;font-size:12px">' +
             h.msg.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</span></li>';
    }).join('');
    return '' +
      '<div id="dexAntiScamOverlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.82);z-index:9500;display:flex;align-items:flex-start;justify-content:center;padding:40px 16px;overflow-y:auto">' +
      '  <div style="background:#0a0a0a;border:2px solid #fb010d;border-radius:6px;max-width:660px;width:100%;padding:24px 28px;font-size:13px;line-height:1.65;color:#e2e8f0">' +
      '    <div style="color:#fb010d;font-weight:900;letter-spacing:1.2px;font-size:13px;margin-bottom:12px">&#9888; LOCAL ANTI-SCAM WARNING</div>' +
      '    <p style="margin:0 0 12px">Your typed text matches <b>' + hits.length + '</b> known scam pattern(s):</p>' +
      '    <ul style="list-style:none;padding:0;margin:0 0 16px">' + rows + '</ul>' +
      '    <p style="margin:0 0 12px;color:#94a3b8;font-size:12px;line-height:1.7">' +
      '      <b style="color:#94a3b8">This warning is generated locally in your browser before encryption.</b> ' +
      '      SOST servers cannot read your private trade message; this check ran on the text you typed into the AI input box, in this tab, with no network call. ' +
      '      You may proceed if you understand the risk.' +
      '    </p>' +
      '    <div style="display:flex;gap:12px;flex-wrap:wrap">' +
      '      <button id="dexAntiScamCancel" type="button" style="background:#fb010d;color:#fff;border:none;padding:10px 18px;border-radius:4px;font-weight:700;font-size:13px;letter-spacing:0.5px;cursor:pointer">Cancel (recommended)</button>' +
      '      <button id="dexAntiScamProceed" type="button" style="background:transparent;color:#e2e8f0;padding:10px 18px;border:1px solid #2a2a2a;border-radius:4px;font-weight:600;font-size:13px;letter-spacing:0.5px;cursor:pointer">I understand the risk — proceed anyway</button>' +
      '    </div>' +
      '  </div>' +
      '</div>';
  }

  // Hook into SOSTDEX.processAIInput. Wait for it to be defined; if it
  // never appears, the hook silently no-ops.
  function installHook() {
    if (typeof window.SOSTDEX === 'undefined' || typeof window.SOSTDEX.processAIInput !== 'function') {
      return false;
    }
    if (window.SOSTDEX._antiScamHooked) return true;
    var original = window.SOSTDEX.processAIInput;
    window.SOSTDEX.processAIInput = function () {
      try {
        var input = document.getElementById('aiInput');
        var text = input ? (input.value || '') : '';
        var hits = findScamPatterns(text);
        if (hits.length > 0) {
          showWarning(hits, function (proceed) {
            if (proceed) return original.apply(window.SOSTDEX, arguments);
          });
          return;
        }
      } catch (e) { /* fail open — never block normal use */ }
      return original.apply(window.SOSTDEX, arguments);
    };
    window.SOSTDEX._antiScamHooked = true;
    return true;
  }

  function showWarning(hits, callback) {
    var existing = document.getElementById('dexAntiScamOverlay');
    if (existing) existing.parentNode.removeChild(existing);
    var wrapper = document.createElement('div');
    wrapper.innerHTML = buildWarningHtml(hits);
    document.body.appendChild(wrapper.firstChild);
    var prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    function cleanup() {
      var ov = document.getElementById('dexAntiScamOverlay');
      if (ov) ov.parentNode.removeChild(ov);
      document.body.style.overflow = prevOverflow;
    }
    document.getElementById('dexAntiScamCancel').addEventListener('click', function () {
      cleanup();
      if (typeof callback === 'function') callback(false);
    });
    document.getElementById('dexAntiScamProceed').addEventListener('click', function () {
      cleanup();
      if (typeof callback === 'function') callback(true);
    });
  }

  // Retry hook every 500ms for up to 10s in case SOSTDEX loads late.
  var attempts = 0;
  var iv = setInterval(function () {
    attempts++;
    if (installHook() || attempts >= 20) clearInterval(iv);
  }, 500);
  document.addEventListener('DOMContentLoaded', function () { installHook(); });

  // Expose a small public surface for testing / future reuse.
  window.DEXAntiScam = {
    findScamPatterns: findScamPatterns,
    showWarning: showWarning,
    patternCount: SCAM_PATTERNS.length
  };
})();
