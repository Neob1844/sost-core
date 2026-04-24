/**
 * SOST DEX — Trade Engine
 *
 * Connects the Trade Composer UI to real cryptographic operations:
 * - Create real offers from form data
 * - Sign with ED25519
 * - Encrypt with ChaCha20-Poly1305 via channel keys
 * - Submit to blind relay
 * - Track deal status
 *
 * Depends on: browser-crypto.js, keystore.js, relay-client.js,
 *             recipient-directory.js, private-inbox.js
 */

const SOSTTradeEngine = (function () {
  'use strict';

  var _seqCounters = {}; // per-deal sequence counters

  function _nextSeq(dealId) {
    if (!_seqCounters[dealId]) _seqCounters[dealId] = 0;
    return ++_seqCounters[dealId];
  }

  // ── Offer Creation ────────────────────────────────────────────

  /**
   * Create a structured trade offer from form parameters.
   * Does NOT sign or encrypt — just builds the payload.
   */
  function buildOffer(params) {
    var now = Date.now();
    var nonceBytes = SOSTCrypto.randomBytes(16);
    var nonce = SOSTCrypto.bytesToHex(nonceBytes);

    var idInput = params.position_id + ':' + params.maker_sost_addr + ':' + now;
    var offerId = SOSTCrypto.sha256Sync(idInput).substring(0, 16);

    return {
      version: 1,
      type: 'trade_offer',
      offer_id: offerId,
      pair: params.pair || 'SOST/XAUT',
      side: params.side || 'sell',
      amount_sost: params.amount_sost || '0',
      amount_gold: params.amount_gold || '0',
      price: params.price_sost || '0',
      price_sost: params.price_sost || '0',
      maker_sost_addr: params.maker_sost_addr || '',
      maker_eth_addr: params.maker_eth_addr || '',
      asset_type: params.asset_type || 'POSITION_FULL',
      position_id: params.position_id || '',
      expires_at: now + (parseInt(params.expiry_seconds) || 86400) * 1000,
      settlement_mode: 'operator_assisted',
      nonce: nonce,
      created_at: now
    };
  }

  /**
   * Create a structured trade accept.
   */
  function buildAccept(params) {
    var now = Date.now();
    var nonce = SOSTCrypto.bytesToHex(SOSTCrypto.randomBytes(16));
    var acceptId = SOSTCrypto.sha256Sync(params.offer_id + ':' + params.taker_sost_addr + ':' + now).substring(0, 16);
    var dealId = SOSTCrypto.sha256Sync(params.offer_id + ':' + acceptId).substring(0, 16);

    return {
      version: 1,
      type: 'trade_accept',
      accept_id: acceptId,
      offer_id: params.offer_id,
      deal_id: dealId,
      taker_sost_addr: params.taker_sost_addr || '',
      taker_eth_addr: params.taker_eth_addr || '',
      fill_amount_sost: params.fill_amount_sost || params.amount_sost || '0',
      fill_amount_gold: params.fill_amount_gold || params.amount_gold || '0',
      asset_type: params.asset_type || 'POSITION_FULL',
      position_id: params.position_id || '',
      accepted_at: now,
      nonce: nonce
    };
  }

  /**
   * Create a trade cancel.
   */
  function buildCancel(params) {
    var nonce = SOSTCrypto.bytesToHex(SOSTCrypto.randomBytes(16));
    var cancelId = SOSTCrypto.sha256Sync(params.target_id + ':cancel:' + Date.now()).substring(0, 16);

    return {
      version: 1,
      type: 'trade_cancel',
      cancel_id: cancelId,
      target_id: params.target_id,
      target_type: params.target_type || 'offer',
      cancelled_by: params.cancelled_by || '',
      reason: params.reason || 'user_cancelled',
      cancelled_at: Date.now(),
      nonce: nonce
    };
  }

  // ── Sign ──────────────────────────────────────────────────────

  /**
   * Sign a trade message (offer, accept, cancel).
   * Returns the message with signature field added.
   */
  function signMessage(message) {
    if (!SOSTKeystore.isUnlocked()) throw new Error('Wallet locked');
    var sk = SOSTKeystore.getSigningKey();

    // Canonical hash — sort keys deterministically
    var canonical = JSON.stringify(message, Object.keys(message).sort());
    var hash = SOSTCrypto.sha256Sync(canonical);
    var signature = SOSTCrypto.signHash(hash, sk);

    return Object.assign({}, message, { signature: signature, _hash: hash });
  }

  // ── Encrypt + Send ────────────────────────────────────────────

  /**
   * Full flow: sign message → establish channel → encrypt → send to relay.
   *
   * @param {object} message - The trade message (offer/accept/cancel)
   * @param {string} recipientSigningPub - Recipient's signing public key hex
   * @returns {object} { ok, envelope, dealId, error }
   */
  async function signEncryptAndSend(message, recipientSigningPub) {
    if (!SOSTKeystore.isUnlocked()) return { ok: false, error: 'wallet locked' };

    var identity = SOSTKeystore.getIdentity();
    var sk = SOSTKeystore.getSigningKey();
    var ek = SOSTKeystore.getEncryptionKey();

    // 1. Sign the message
    var signed = signMessage(message);
    var payload = JSON.stringify(signed);

    // 2. Resolve recipient encryption key
    var recipientKey = await SOSTDirectory.resolveEncryptionKey(recipientSigningPub);
    if (!recipientKey.ok) return { ok: false, error: 'cannot resolve recipient key: ' + recipientKey.error };

    // 3. Derive shared secret and channel keys
    var shared = SOSTCrypto.deriveSharedSecret(ek, recipientKey.encryptionPublic);
    var dealId = signed.deal_id || signed.offer_id || signed.cancel_id || SOSTCrypto.sha256Sync(payload).substring(0, 16);
    var channelKeys = SOSTCrypto.deriveChannelKeys(shared, dealId, true);

    // Register channel for inbox decryption
    SOSTInbox.registerChannel(dealId, channelKeys);

    // 4. Encrypt
    var seqNo = _nextSeq(dealId);
    var envelope = SOSTCrypto.encryptMessage(payload, channelKeys, seqNo, sk, {
      deal_id: dealId,
      sender_id: identity.signingPublic,
      receiver_id: recipientSigningPub,
      msg_type: signed.type
    });

    // 5. Send to relay
    var result = await SOSTRelay.submitEncrypted(envelope, recipientSigningPub);
    if (!result.ok) return { ok: false, error: 'relay submit failed: ' + (result.reason || 'unknown'), envelope: envelope };

    return {
      ok: true,
      envelope: envelope,
      dealId: dealId,
      signed: signed,
      delivered: result.accepted !== false,
      queued: result.queued || false
    };
  }

  // ── Outcome Preview ───────────────────────────────────────────

  /**
   * Generate a human-readable preview of what changes if this trade executes.
   */
  function previewOutcome(offer, position) {
    var changes = [];
    var unchanged = [];

    if (!position) {
      return { changes: ['Position details not available'], unchanged: [], warnings: ['Cannot preview without position data'] };
    }

    var isFull = offer.asset_type === 'POSITION_FULL';
    var isReward = offer.asset_type === 'POSITION_REWARD_RIGHT';

    if (isFull) {
      changes.push('principal_owner → transfers to buyer');
      changes.push('reward_owner → transfers to buyer');
      changes.push('eth_beneficiary → updates to buyer ETH address');
      unchanged.push('Escrow remains locked until maturity');
      unchanged.push('Gold amount unchanged: ' + (position.amount_oz || position.reference_amount || '?') + ' oz');
    } else if (isReward) {
      changes.push('reward_owner → transfers to buyer');
      unchanged.push('principal_owner remains: ' + (position.principal_owner || position.owner || '?'));
      unchanged.push('eth_beneficiary remains unchanged');
      unchanged.push('Escrow remains locked until maturity');
    }

    changes.push('Price: ' + (offer.price_sost || offer.price || '?') + ' SOST');
    changes.push('Offer expires: ' + new Date(offer.expires_at).toLocaleString());

    var warnings = [];
    var price = parseFloat(offer.price_sost || offer.price || 0);
    if (price <= 0) warnings.push('Price is zero or negative');
    if (offer.expires_at < Date.now()) warnings.push('Offer has already expired');
    if (!offer.maker_sost_addr) warnings.push('Maker SOST address not set');

    return { changes: changes, unchanged: unchanged, warnings: warnings };
  }

  // ── Status helpers ────────────────────────────────────────────

  /**
   * Get the signing/encryption status for display in Pro mode.
   */
  function getStatus() {
    return {
      walletUnlocked: SOSTKeystore.isUnlocked(),
      identity: SOSTKeystore.getIdentity(),
      channelCount: Object.keys(_seqCounters).length,
      inboxCount: SOSTInbox.getCounts().total
    };
  }

  return {
    buildOffer: buildOffer,
    buildAccept: buildAccept,
    buildCancel: buildCancel,
    signMessage: signMessage,
    signEncryptAndSend: signEncryptAndSend,
    previewOutcome: previewOutcome,
    getStatus: getStatus
  };
})();
