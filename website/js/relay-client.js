/**
 * SOST DEX — Relay Client for Browser
 *
 * HTTP client for the sost-comms-private blind relay.
 * Talks to the relay HTTP API to submit encrypted envelopes,
 * fetch pending messages, manage prekeys, and track delivery.
 *
 * Depends on: browser-crypto.js (SOSTCrypto)
 */

const SOSTRelay = (function () {
  'use strict';

  // Default relay URL — can be overridden via configure()
  var _relayUrl = '';
  var _timeout = 15000; // 15s default timeout

  /**
   * Configure the relay client.
   * @param {string} relayUrl - Base URL of the relay (e.g. "https://relay.sostcore.com:8400")
   * @param {object} opts - Optional: { timeout: ms }
   */
  function configure(relayUrl, opts) {
    _relayUrl = relayUrl.replace(/\/$/, ''); // strip trailing slash
    if (opts && opts.timeout) _timeout = opts.timeout;
  }

  function _url(path) {
    if (!_relayUrl) throw new Error('Relay not configured. Call SOSTRelay.configure(url) first.');
    return _relayUrl + path;
  }

  async function _fetch(path, opts) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, _timeout);
    try {
      var resp = await fetch(_url(path), Object.assign({ signal: controller.signal }, opts));
      clearTimeout(timer);
      if (!resp.ok) {
        var body = await resp.text().catch(function () { return ''; });
        return { ok: false, status: resp.status, error: body || resp.statusText };
      }
      var json = await resp.json().catch(function () { return null; });
      return { ok: true, status: resp.status, data: json };
    } catch (e) {
      clearTimeout(timer);
      return { ok: false, status: 0, error: e.message || 'network error' };
    }
  }

  // ── Submit encrypted envelope ─────────────────────────────────

  /**
   * Submit an encrypted envelope to the relay for blind transport.
   * The relay validates the header signature but cannot read the content.
   *
   * @param {object} envelope - EncryptedEnvelope from SOSTCrypto.encryptMessage()
   * @param {string} recipientId - Recipient's public signing key hex (for offline queue)
   * @returns {object} { ok, accepted, deal_id, queued, reason }
   */
  async function submitEncrypted(envelope, recipientId) {
    var result = await _fetch('/submit/encrypted', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        envelope: envelope,
        recipient_id: recipientId
      })
    });
    if (!result.ok) return { ok: false, accepted: false, reason: result.error };
    return Object.assign({ ok: true }, result.data);
  }

  // ── Fetch pending messages (offline queue) ────────────────────

  /**
   * Fetch pending encrypted messages for a recipient.
   * Used when the user comes online and checks their inbox.
   *
   * @param {string} recipientId - Your public signing key hex
   * @returns {object} { ok, messages: [...] }
   */
  async function fetchPending(recipientId) {
    var result = await _fetch('/pending/' + encodeURIComponent(recipientId));
    if (!result.ok) return { ok: false, messages: [], error: result.error };
    return { ok: true, messages: result.data || [] };
  }

  // ── Acknowledge message delivery ──────────────────────────────

  /**
   * Acknowledge that a message has been received and decrypted.
   *
   * @param {string} messageId - Message ID to acknowledge
   * @returns {object} { ok }
   */
  async function ack(messageId) {
    var result = await _fetch('/ack/' + encodeURIComponent(messageId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    });
    return { ok: result.ok };
  }

  // ── Prekey management ─────────────────────────────────────────

  /**
   * Publish a prekey bundle for offline session establishment.
   *
   * @param {string} identity - Your public signing key hex
   * @param {object} bundle - PrekeyBundle { identityKey, signedPrekey, oneTimePrekeys }
   * @returns {object} { ok }
   */
  async function publishPrekeys(identity, bundle) {
    var result = await _fetch('/prekeys/' + encodeURIComponent(identity), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bundle)
    });
    return { ok: result.ok };
  }

  /**
   * Fetch someone's prekey bundle for establishing an encrypted session.
   *
   * @param {string} identity - Their public signing key hex
   * @returns {object} { ok, bundle } or { ok: false }
   */
  async function fetchPrekeys(identity) {
    var result = await _fetch('/prekeys/' + encodeURIComponent(identity));
    if (!result.ok) return { ok: false, bundle: null, error: result.error };
    return { ok: true, bundle: result.data };
  }

  // ── Deal queries ──────────────────────────────────────────────

  /**
   * List all active deals on the relay.
   */
  async function listDeals() {
    var result = await _fetch('/deals');
    if (!result.ok) return { ok: false, deals: [], error: result.error };
    return { ok: true, deals: result.data || [] };
  }

  /**
   * Get encrypted messages for a specific deal.
   */
  async function getDealMessages(dealId) {
    var result = await _fetch('/deals/' + encodeURIComponent(dealId) + '/encrypted');
    if (!result.ok) return { ok: false, messages: [], error: result.error };
    return { ok: true, messages: result.data || [] };
  }

  /**
   * Get delivery status for a deal.
   */
  async function getDeliveryStatus(dealId) {
    var result = await _fetch('/delivery/' + encodeURIComponent(dealId));
    if (!result.ok) return { ok: false, status: [], error: result.error };
    return { ok: true, status: result.data || [] };
  }

  // ── Health check ──────────────────────────────────────────────

  /**
   * Check relay health.
   */
  async function health() {
    var result = await _fetch('/health');
    return { ok: result.ok, data: result.data };
  }

  // ── Offers ────────────────────────────────────────────────────

  /**
   * Get open offers from the relay.
   */
  async function getOffers() {
    var result = await _fetch('/offers');
    if (!result.ok) return { ok: false, offers: [], error: result.error };
    return { ok: true, offers: result.data || [] };
  }

  return {
    configure: configure,
    submitEncrypted: submitEncrypted,
    fetchPending: fetchPending,
    ack: ack,
    publishPrekeys: publishPrekeys,
    fetchPrekeys: fetchPrekeys,
    listDeals: listDeals,
    getDealMessages: getDealMessages,
    getDeliveryStatus: getDeliveryStatus,
    getOffers: getOffers,
    health: health
  };
})();
