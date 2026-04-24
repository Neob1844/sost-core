/**
 * SOST DEX — Recipient Directory
 *
 * Manages alpha participant discovery and prekey bundle lookup.
 * Used to find the encryption public key of a counterpart before
 * creating an encrypted deal envelope.
 *
 * Depends on: relay-client.js (SOSTRelay), browser-crypto.js (SOSTCrypto)
 */

const SOSTDirectory = (function () {
  'use strict';

  var _participants = [];
  var _loaded = false;

  /**
   * Load the participant directory from the API.
   */
  async function load() {
    try {
      var resp = await fetch('api/participant_directory.json?t=' + Date.now());
      if (resp.ok) {
        _participants = await resp.json();
        _loaded = true;
      }
    } catch (e) {
      // Directory may not exist yet — use empty list
      _participants = [];
      _loaded = true;
    }
  }

  /**
   * Get all known participants.
   */
  function list() {
    return _participants.slice();
  }

  /**
   * Find a participant by signing public key (identity).
   */
  function findByIdentity(signingPubHex) {
    return _participants.find(function (p) {
      return p.signingPublic === signingPubHex;
    }) || null;
  }

  /**
   * Find a participant by label/name.
   */
  function findByLabel(label) {
    var lower = label.toLowerCase();
    return _participants.filter(function (p) {
      return p.label && p.label.toLowerCase().indexOf(lower) >= 0;
    });
  }

  /**
   * Find a participant by SOST address.
   */
  function findBySostAddress(addr) {
    return _participants.find(function (p) {
      return p.sostAddress === addr;
    }) || null;
  }

  /**
   * Fetch the prekey bundle for a participant from the relay.
   * Returns { ok, bundle } or { ok: false }.
   */
  async function fetchPrekeyBundle(signingPubHex) {
    return await SOSTRelay.fetchPrekeys(signingPubHex);
  }

  /**
   * Verify a signed prekey using the participant's identity key.
   */
  function verifySignedPrekey(signedPrekey, identityPubHex) {
    if (!signedPrekey || !signedPrekey.publicKey || !signedPrekey.signature) return false;
    // The signature covers "prekey:" + publicKey + ":" + createdAt
    var msg = 'prekey:' + signedPrekey.publicKey + ':' + signedPrekey.createdAt;
    return SOSTCrypto.verify(msg, signedPrekey.signature, identityPubHex);
  }

  /**
   * Get encryption public key for a recipient.
   * First checks local directory, then falls back to relay prekeys.
   */
  async function resolveEncryptionKey(signingPubHex) {
    // Check local directory first
    var participant = findByIdentity(signingPubHex);
    if (participant && participant.encryptionPublic) {
      return { ok: true, encryptionPublic: participant.encryptionPublic, source: 'directory' };
    }
    // Try relay prekeys
    var prekeys = await fetchPrekeyBundle(signingPubHex);
    if (prekeys.ok && prekeys.bundle && prekeys.bundle.signedPrekey) {
      return {
        ok: true,
        encryptionPublic: prekeys.bundle.signedPrekey.publicKey,
        source: 'relay-prekey',
        bundle: prekeys.bundle
      };
    }
    return { ok: false, error: 'recipient key not found' };
  }

  /**
   * Register self in the directory (publish identity for others to find).
   * In alpha, this writes to the relay prekey store.
   */
  async function publishSelf(identity, encryptionPub, label, sostAddress) {
    // Publish prekey bundle to relay for others to discover
    var bundle = {
      identityKey: identity.signingPublic,
      encryptionPublic: encryptionPub,
      label: label || '',
      sostAddress: sostAddress || '',
      publishedAt: Date.now()
    };
    return await SOSTRelay.publishPrekeys(identity.signingPublic, bundle);
  }

  return {
    load: load,
    list: list,
    findByIdentity: findByIdentity,
    findByLabel: findByLabel,
    findBySostAddress: findBySostAddress,
    fetchPrekeyBundle: fetchPrekeyBundle,
    verifySignedPrekey: verifySignedPrekey,
    resolveEncryptionKey: resolveEncryptionKey,
    publishSelf: publishSelf
  };
})();
