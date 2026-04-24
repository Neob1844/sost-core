/**
 * SOST Talk — Community Feed System
 *
 * Manages the community feed: messages, rooms, filtering, identity-gated posting.
 * Uses local storage for MVP; can be extended to server-backed storage.
 *
 * Depends on: sost-sentinel.js, keystore.js (optional for DEX identity)
 */

const SOSTTalk = (function () {
  'use strict';

  var STORAGE_KEY = 'sost_talk_messages';
  var MAX_MESSAGES = 500;
  var ROOMS = ['general', 'miners', 'dex', 'bugs'];
  var ROOM_LABELS = { general: 'General', miners: 'Miners', dex: 'DEX / PoPC', bugs: 'Bugs / Feedback' };

  var _messages = [];
  var _currentRoom = 'general';
  var _currentFilter = 'all';
  var _identity = null;
  var _onUpdate = null;

  // ── Init ──────────────────────────────────────────────────────

  function init() {
    _loadMessages();
    _fetchRemoteMessages();
  }

  function onUpdate(callback) { _onUpdate = callback; }

  // ── Identity ──────────────────────────────────────────────────

  function setIdentity(identity) {
    _identity = identity;
  }

  function getIdentity() { return _identity; }

  function isAuthenticated() { return _identity !== null; }

  // ── Rooms ─────────────────────────────────────────────────────

  function getRooms() { return ROOMS.slice(); }
  function getRoomLabel(room) { return ROOM_LABELS[room] || room; }
  function getCurrentRoom() { return _currentRoom; }

  function setRoom(room) {
    if (ROOMS.indexOf(room) >= 0) _currentRoom = room;
    if (_onUpdate) _onUpdate();
  }

  function setFilter(filter) {
    _currentFilter = filter;
    if (_onUpdate) _onUpdate();
  }

  // ── Messages ──────────────────────────────────────────────────

  /**
   * Post a message. Returns { ok, message, error }
   */
  function post(text, room) {
    if (!_identity) return { ok: false, error: 'Please unlock your identity to post.' };

    var targetRoom = room || _currentRoom;
    var userId = _identity.id || _identity.signingPublic || 'anon';
    var userName = _identity.label || _identity.id || 'User';

    // Sentinel check
    var check = SOSTSentinel.analyze(text, userId, userName);
    if (!check.allowed) return { ok: false, error: check.reason, flags: check.flags };

    // Auto-classify room suggestion
    var suggestedRoom = SOSTSentinel.classify(text);

    var msg = {
      id: _generateId(),
      text: SOSTSentinel.sanitize(text.trim()),
      room: targetRoom,
      suggestedRoom: suggestedRoom !== targetRoom ? suggestedRoom : null,
      userId: userId,
      userName: SOSTSentinel.sanitize(userName),
      badge: _identity.badge || 'community',
      timestamp: Date.now(),
      flags: check.flags,
      reported: false,
      hidden: false
    };

    _messages.unshift(msg);
    if (_messages.length > MAX_MESSAGES) _messages = _messages.slice(0, MAX_MESSAGES);
    _saveMessages();

    // Check for auto-response
    var autoReply = SOSTSentinel.autoRespond(text);
    if (autoReply) {
      var botMsg = {
        id: _generateId(),
        text: SOSTSentinel.sanitize(autoReply),
        room: targetRoom,
        userId: 'sentinel',
        userName: 'SOST Sentinel',
        badge: 'official',
        timestamp: Date.now() + 1,
        flags: [],
        reported: false,
        hidden: false,
        isBot: true
      };
      _messages.unshift(botMsg);
      _saveMessages();
    }

    if (_onUpdate) _onUpdate();
    return { ok: true, message: msg };
  }

  /**
   * Report a message for review.
   */
  function report(messageId) {
    var msg = _messages.find(function (m) { return m.id === messageId; });
    if (msg) {
      msg.reported = true;
      _saveMessages();
      if (_onUpdate) _onUpdate();
      return true;
    }
    return false;
  }

  /**
   * Get messages for current room and filter.
   */
  function getMessages() {
    var filtered = _messages.filter(function (m) {
      if (m.hidden) return false;
      if (_currentFilter === 'all') return m.room === _currentRoom;
      if (_currentFilter === 'mine') return m.userId === (_identity ? _identity.id : '');
      if (_currentFilter === 'flagged') return m.flags && m.flags.length > 0;
      if (_currentFilter === 'official') return m.badge === 'official' || m.badge === 'founder';
      return m.room === _currentRoom;
    });
    return filtered;
  }

  /**
   * Get all messages (for moderation).
   */
  function getAllMessages() { return _messages.slice(); }

  /**
   * Get message counts per room.
   */
  function getCounts() {
    var counts = {};
    ROOMS.forEach(function (r) {
      counts[r] = _messages.filter(function (m) { return m.room === r && !m.hidden; }).length;
    });
    counts.total = _messages.filter(function (m) { return !m.hidden; }).length;
    counts.flagged = _messages.filter(function (m) { return m.flags && m.flags.length > 0; }).length;
    counts.reported = _messages.filter(function (m) { return m.reported; }).length;
    return counts;
  }

  // ── Storage ───────────────────────────────────────────────────

  function _loadMessages() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) _messages = JSON.parse(stored);
    } catch (e) { _messages = []; }
  }

  function _saveMessages() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(_messages.slice(0, MAX_MESSAGES)));
    } catch (e) { /* storage full — ok */ }
  }

  function _fetchRemoteMessages() {
    // MVP: try to fetch from api/talk_messages.json
    fetch('api/talk_messages.json?t=' + Date.now()).then(function (r) {
      if (r.ok) return r.json();
      return [];
    }).then(function (remote) {
      if (Array.isArray(remote) && remote.length > 0) {
        // Merge remote messages (avoid duplicates)
        var existingIds = new Set(_messages.map(function (m) { return m.id; }));
        remote.forEach(function (m) {
          if (!existingIds.has(m.id)) _messages.push(m);
        });
        _messages.sort(function (a, b) { return b.timestamp - a.timestamp; });
        if (_onUpdate) _onUpdate();
      }
    }).catch(function () { /* no remote messages — ok */ });
  }

  function _generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substring(2, 8);
  }

  return {
    init: init,
    onUpdate: onUpdate,
    setIdentity: setIdentity,
    getIdentity: getIdentity,
    isAuthenticated: isAuthenticated,
    getRooms: getRooms,
    getRoomLabel: getRoomLabel,
    getCurrentRoom: getCurrentRoom,
    setRoom: setRoom,
    setFilter: setFilter,
    post: post,
    report: report,
    getMessages: getMessages,
    getAllMessages: getAllMessages,
    getCounts: getCounts
  };
})();
