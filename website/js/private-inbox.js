/**
 * SOST DEX — Private Inbox
 *
 * Manages encrypted message reception, decryption, and display.
 * Messages are fetched from the relay, decrypted locally with the user's
 * channel keys, and rendered in the private inbox UI.
 *
 * Depends on: browser-crypto.js, keystore.js, relay-client.js
 */

const SOSTInbox = (function () {
  'use strict';

  var _messages = [];       // Decrypted messages cache
  var _channels = {};       // channel keys per deal_id
  var _pollInterval = null;
  var _onMessage = null;    // Callback when new message arrives

  /**
   * Set callback for new messages.
   */
  function onMessage(callback) {
    _onMessage = callback;
  }

  /**
   * Store channel keys for a deal (needed to decrypt messages).
   */
  function registerChannel(dealId, channelKeys) {
    _channels[dealId] = channelKeys;
  }

  /**
   * Get channel keys for a deal.
   */
  function getChannel(dealId) {
    return _channels[dealId] || null;
  }

  /**
   * Fetch and decrypt pending messages from the relay.
   * Returns array of decrypted messages.
   */
  async function fetchAndDecrypt() {
    if (!SOSTKeystore.isUnlocked()) return [];

    var identity = SOSTKeystore.getIdentity();
    var result = await SOSTRelay.fetchPending(identity.signingPublic);
    if (!result.ok || !result.messages || result.messages.length === 0) return [];

    var newMessages = [];
    for (var i = 0; i < result.messages.length; i++) {
      var queuedMsg = result.messages[i];
      var envelope = null;
      try {
        envelope = typeof queuedMsg.envelope_json === 'string'
          ? JSON.parse(queuedMsg.envelope_json)
          : queuedMsg.envelope_json || queuedMsg;
      } catch (e) {
        newMessages.push({
          id: queuedMsg.id || ('msg-' + i),
          deal_id: 'unknown',
          type: 'error',
          error: 'invalid envelope format',
          raw: queuedMsg,
          timestamp: Date.now()
        });
        continue;
      }

      var dealId = envelope.deal_id;
      var chKeys = _channels[dealId];

      if (!chKeys) {
        // Try to derive channel keys from encryption key + sender pub
        // This requires knowing the shared secret — may need prekey handshake
        newMessages.push({
          id: queuedMsg.id || ('msg-' + i),
          deal_id: dealId,
          type: 'pending_handshake',
          sender_id: envelope.sender_id,
          msg_type: envelope.msg_type,
          timestamp: envelope.timestamp,
          error: 'no channel keys for this deal — handshake needed',
          raw: queuedMsg
        });
        continue;
      }

      // Decrypt
      var decrypted = SOSTCrypto.decryptMessage(envelope, chKeys, envelope.sender_id);

      if (decrypted.plaintext === null) {
        newMessages.push({
          id: queuedMsg.id || ('msg-' + i),
          deal_id: dealId,
          type: 'decrypt_failed',
          sender_id: envelope.sender_id,
          msg_type: envelope.msg_type,
          timestamp: envelope.timestamp,
          verified: decrypted.verified,
          error: decrypted.error || 'decryption failed',
          raw: queuedMsg
        });
        continue;
      }

      var parsed = null;
      try { parsed = JSON.parse(decrypted.plaintext); } catch (e) { parsed = decrypted.plaintext; }

      var msg = {
        id: queuedMsg.id || ('msg-' + i),
        deal_id: dealId,
        type: envelope.msg_type,
        sender_id: envelope.sender_id,
        seq_no: envelope.seq_no,
        timestamp: envelope.timestamp,
        verified: decrypted.verified,
        content: parsed,
        status: 'decrypted'
      };

      newMessages.push(msg);
      _messages.push(msg);

      // Acknowledge receipt
      if (queuedMsg.id) {
        SOSTRelay.ack(queuedMsg.id).catch(function () {});
      }
    }

    if (newMessages.length > 0 && _onMessage) {
      _onMessage(newMessages);
    }

    return newMessages;
  }

  /**
   * Get all decrypted messages, optionally filtered by deal_id.
   */
  function getMessages(dealId) {
    if (dealId) return _messages.filter(function (m) { return m.deal_id === dealId; });
    return _messages.slice();
  }

  /**
   * Get messages grouped by deal_id.
   */
  function getByDeal() {
    var deals = {};
    _messages.forEach(function (m) {
      if (!deals[m.deal_id]) deals[m.deal_id] = [];
      deals[m.deal_id].push(m);
    });
    return deals;
  }

  /**
   * Get message counts by type.
   */
  function getCounts() {
    var counts = { total: _messages.length, offers: 0, accepts: 0, cancels: 0, notices: 0, errors: 0 };
    _messages.forEach(function (m) {
      if (m.type === 'trade_offer') counts.offers++;
      else if (m.type === 'trade_accept') counts.accepts++;
      else if (m.type === 'trade_cancel') counts.cancels++;
      else if (m.type === 'settlement_notice') counts.notices++;
      else if (m.type === 'error' || m.type === 'decrypt_failed') counts.errors++;
    });
    return counts;
  }

  /**
   * Start polling for new messages.
   */
  function startPolling(intervalMs) {
    if (_pollInterval) return;
    _pollInterval = setInterval(function () {
      if (SOSTKeystore.isUnlocked()) {
        fetchAndDecrypt().catch(function () {});
      }
    }, intervalMs || 15000);
  }

  /**
   * Stop polling.
   */
  function stopPolling() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  /**
   * Clear all cached messages (on lock/logout).
   */
  function clear() {
    _messages = [];
    _channels = {};
    stopPolling();
  }

  return {
    onMessage: onMessage,
    registerChannel: registerChannel,
    getChannel: getChannel,
    fetchAndDecrypt: fetchAndDecrypt,
    getMessages: getMessages,
    getByDeal: getByDeal,
    getCounts: getCounts,
    startPolling: startPolling,
    stopPolling: stopPolling,
    clear: clear
  };
})();
