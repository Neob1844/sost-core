/**
 * SOST Sentinel — Community Moderation Bot
 *
 * "Protects the channel from spam, scams and noise — not from criticism."
 *
 * Runs client-side to filter, classify, and flag messages before display.
 * Server-side moderation can extend this with persistent bans and review queues.
 */

const SOSTSentinel = (function () {
  'use strict';

  // ── Configuration ─────────────────────────────────────────────

  var RATE_LIMIT_MS = 5000;          // Min 5s between messages per user
  var FLOOD_LIMIT = 5;               // Max 5 messages per minute
  var MAX_MSG_LENGTH = 1000;         // Characters
  var MIN_MSG_LENGTH = 2;
  var DUPLICATE_WINDOW = 60000;      // 1 min window for duplicate detection
  var OFFICIAL_DOMAINS = ['sostcore.com', 'sostprotocol.com', 'github.com/neob1844'];

  // ── Scam patterns ─────────────────────────────────────────────

  var SCAM_PATTERNS = [
    /send\s*(me\s*)?(your\s*)?(sost|btc|eth|coin|token|fund)/i,
    /free\s*(sost|btc|eth|coin|airdrop|giveaway)/i,
    /double\s*your\s*(sost|btc|coin|investment)/i,
    /guaranteed\s*(return|profit|yield|roi)/i,
    /invest\s*now.*\d+%/i,
    /admin.*DM|DM.*admin|support.*DM/i,
    /verify\s*your\s*wallet/i,
    /connect\s*your\s*wallet\s*to/i,
    /claim\s*your\s*(reward|airdrop|bonus)/i,
    /t\.me\/|telegram\.me\//i,
    /whatsapp\.com\/|wa\.me\//i
  ];

  var IMPERSONATION_NAMES = [
    /^neob$/i, /^neo\s*b$/i, /^sost\s*admin/i, /^sost\s*support/i,
    /^sost\s*team/i, /^sost\s*official/i, /^moderator$/i, /^mod$/i
  ];

  // ── State ─────────────────────────────────────────────────────

  var _userHistory = {};  // userId → { lastMsg, count, lastMinute, recentTexts }
  var _mutedUsers = {};   // userId → unmuteTime

  // ── Analysis ──────────────────────────────────────────────────

  /**
   * Analyze a message before publishing.
   * Returns { allowed, flags[], action, reason }
   */
  function analyze(message, userId, userName) {
    var flags = [];
    var text = (message || '').trim();

    // Basic validation
    if (text.length < MIN_MSG_LENGTH) return _block('message_too_short', 'Message too short.');
    if (text.length > MAX_MSG_LENGTH) return _block('message_too_long', 'Message exceeds ' + MAX_MSG_LENGTH + ' characters.');

    // Muted check
    if (_mutedUsers[userId] && Date.now() < _mutedUsers[userId]) {
      return _block('user_muted', 'You are temporarily muted. Please wait.');
    }

    // Rate limit
    var history = _getHistory(userId);
    var now = Date.now();
    if (history.lastMsg && (now - history.lastMsg) < RATE_LIMIT_MS) {
      flags.push({ type: 'RATE_LIMIT', severity: 'WARNING' });
      return _block('rate_limited', 'Please wait a few seconds between messages.');
    }

    // Flood detection
    if (history.lastMinute >= FLOOD_LIMIT) {
      flags.push({ type: 'FLOOD', severity: 'BLOCKING' });
      _muteUser(userId, 60000); // 1 min mute
      return _block('flood_detected', 'Too many messages. Temporarily muted for 1 minute.');
    }

    // Duplicate detection
    if (history.recentTexts.indexOf(text.toLowerCase()) >= 0) {
      flags.push({ type: 'DUPLICATE', severity: 'WARNING' });
      return _block('duplicate_message', 'Duplicate message detected.');
    }

    // Scam detection
    for (var i = 0; i < SCAM_PATTERNS.length; i++) {
      if (SCAM_PATTERNS[i].test(text)) {
        flags.push({ type: 'SCAM', severity: 'BLOCKING', pattern: SCAM_PATTERNS[i].source });
        return _flag('scam_detected', 'This message has been flagged as a potential scam.', flags);
      }
    }

    // Impersonation detection
    if (userName) {
      for (var j = 0; j < IMPERSONATION_NAMES.length; j++) {
        if (IMPERSONATION_NAMES[j].test(userName)) {
          flags.push({ type: 'IMPERSONATION', severity: 'BLOCKING' });
          return _flag('impersonation', 'This username appears to impersonate an official account.', flags);
        }
      }
    }

    // Link analysis
    var links = text.match(/https?:\/\/[^\s]+/gi) || [];
    if (links.length > 0) {
      for (var k = 0; k < links.length; k++) {
        var isSafe = false;
        for (var d = 0; d < OFFICIAL_DOMAINS.length; d++) {
          if (links[k].toLowerCase().indexOf(OFFICIAL_DOMAINS[d]) >= 0) { isSafe = true; break; }
        }
        if (!isSafe) {
          flags.push({ type: 'EXTERNAL_LINK', severity: 'INFO', url: links[k] });
        }
      }
    }

    // Update history
    _recordMessage(userId, text);

    return {
      allowed: true,
      flags: flags,
      action: flags.length > 0 ? 'publish_with_flags' : 'publish',
      reason: null
    };
  }

  /**
   * Classify a message into a suggested room.
   */
  function classify(text) {
    var lower = text.toLowerCase();

    // Bug/feedback
    if (/bug|error|crash|fail|broken|issue|problem|fix|report/i.test(lower)) return 'bugs';

    // Mining/sync
    if (/mine|miner|mining|sync|node|hash|block|peer|seed|wallet|bootstrap/i.test(lower)) return 'miners';

    // DEX/PoPC
    if (/dex|position|trade|offer|deal|popc|escrow|model\s*[ab]|reward|custody|bond/i.test(lower)) return 'dex';

    return 'general';
  }

  /**
   * Generate a helpful auto-response for common issues.
   */
  function autoRespond(text) {
    var lower = text.toLowerCase();

    if (/no\s*sinc|not\s*sync|sync.*fail|can.*sync/i.test(lower)) {
      return '🔧 Sync issues? Try: 1) git pull && rebuild, 2) rm -rf blocks utxo && restart node, 3) Use --p2p-enc off for faster historical sync. Check explorer for current height: https://sostcore.com/sost-explorer.html';
    }
    if (/wallet.*not|can.*wallet|lost.*wallet/i.test(lower)) {
      return '🔧 Wallet help: Your wallet is in wallet.json. Back it up! Generate a new one at https://sostcore.com/sost-wallet.html or use ./sost-cli newwallet';
    }
    if (/dex.*not|can.*dex|dex.*work/i.test(lower)) {
      return '🔧 DEX help: 1) Open https://sostcore.com/sost-dex.html, 2) Create Identity with a passphrase, 3) Unlock wallet, 4) Try the AI assistant. Check browser console (F12) for errors.';
    }
    if (/bad_alloc|memory|ram|crash.*mine/i.test(lower)) {
      return '🔧 Memory issue: Mining needs 8GB+ RAM. Add swap: sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile';
    }
    return null;
  }

  // ── Helpers ───────────────────────────────────────────────────

  function _getHistory(userId) {
    if (!_userHistory[userId]) {
      _userHistory[userId] = { lastMsg: 0, count: 0, lastMinute: 0, lastMinuteStart: 0, recentTexts: [] };
    }
    var h = _userHistory[userId];
    var now = Date.now();
    if (now - h.lastMinuteStart > 60000) { h.lastMinute = 0; h.lastMinuteStart = now; }
    // Clean old texts
    h.recentTexts = h.recentTexts.slice(-10);
    return h;
  }

  function _recordMessage(userId, text) {
    var h = _getHistory(userId);
    h.lastMsg = Date.now();
    h.count++;
    h.lastMinute++;
    h.recentTexts.push(text.toLowerCase());
  }

  function _muteUser(userId, durationMs) {
    _mutedUsers[userId] = Date.now() + durationMs;
  }

  function _block(code, reason) {
    return { allowed: false, flags: [{ type: code, severity: 'BLOCKING' }], action: 'blocked', reason: reason };
  }

  function _flag(code, reason, flags) {
    return { allowed: false, flags: flags, action: 'flagged', reason: reason };
  }

  /**
   * Sanitize text for safe display (anti-XSS).
   */
  function sanitize(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function getMutedUsers() { return Object.keys(_mutedUsers); }
  function unmuteUser(userId) { delete _mutedUsers[userId]; }

  return {
    analyze: analyze,
    classify: classify,
    autoRespond: autoRespond,
    sanitize: sanitize,
    getMutedUsers: getMutedUsers,
    unmuteUser: unmuteUser
  };
})();
