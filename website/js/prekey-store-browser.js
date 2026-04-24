/**
 * SOST DEX — Browser Prekey Store
 *
 * Manages prekey bundles and private keys in IndexedDB.
 * Browser equivalent of sost-comms-private/src/e2e/prekey_store.ts
 * (which uses fs/JSON files on Node.js).
 *
 * Depends on: browser-crypto.js (SOSTCrypto)
 */

const SOSTPrekeyStore = (function () {
  'use strict';

  var DB_NAME = 'sost-dex-prekeys';
  var DB_VERSION = 1;
  var BUNDLE_STORE = 'bundles';
  var PRIVKEY_STORE = 'private_keys';
  var _db = null;

  // ── IndexedDB ─────────────────────────────────────────────────

  function _openDB() {
    return new Promise(function (resolve, reject) {
      if (_db) { resolve(_db); return; }
      var req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(BUNDLE_STORE)) {
          db.createObjectStore(BUNDLE_STORE, { keyPath: 'identity' });
        }
        if (!db.objectStoreNames.contains(PRIVKEY_STORE)) {
          db.createObjectStore(PRIVKEY_STORE, { keyPath: 'identity' });
        }
      };
      req.onsuccess = function (e) { _db = e.target.result; resolve(_db); };
      req.onerror = function (e) { reject(e.target.error); };
    });
  }

  function _put(storeName, record) {
    return new Promise(function (resolve, reject) {
      _openDB().then(function (db) {
        var tx = db.transaction(storeName, 'readwrite');
        tx.objectStore(storeName).put(record);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function (e) { reject(e.target.error); };
      });
    });
  }

  function _get(storeName, key) {
    return new Promise(function (resolve, reject) {
      _openDB().then(function (db) {
        var tx = db.transaction(storeName, 'readonly');
        var req = tx.objectStore(storeName).get(key);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  }

  // ── Bundle Management ─────────────────────────────────────────

  /**
   * Save a prekey bundle for an identity.
   * @param {string} identity - Public signing key hex
   * @param {object} bundle - { identityKey, signedPrekey, oneTimePrekeys }
   */
  async function saveBundle(identity, bundle) {
    await _put(BUNDLE_STORE, {
      identity: identity,
      bundle: bundle,
      updatedAt: Date.now()
    });
  }

  /**
   * Get a prekey bundle for an identity.
   * @returns {object|null} bundle or null
   */
  async function getBundle(identity) {
    var record = await _get(BUNDLE_STORE, identity);
    return record ? record.bundle : null;
  }

  /**
   * Consume (mark as used) a one-time prekey.
   * @returns {object|null} The consumed prekey or null
   */
  async function consumeOneTimePrekey(identity, prekeyId) {
    var record = await _get(BUNDLE_STORE, identity);
    if (!record || !record.bundle || !record.bundle.oneTimePrekeys) return null;

    var prekeys = record.bundle.oneTimePrekeys;
    var found = null;
    for (var i = 0; i < prekeys.length; i++) {
      if (prekeys[i].id === prekeyId && !prekeys[i].used) {
        prekeys[i].used = true;
        found = prekeys[i];
        break;
      }
    }

    if (found) {
      await _put(BUNDLE_STORE, record);
    }
    return found;
  }

  /**
   * Get count of remaining (unused) one-time prekeys.
   */
  async function getRemainingCount(identity) {
    var record = await _get(BUNDLE_STORE, identity);
    if (!record || !record.bundle || !record.bundle.oneTimePrekeys) return 0;
    return record.bundle.oneTimePrekeys.filter(function (p) { return !p.used; }).length;
  }

  // ── Private Key Management ────────────────────────────────────

  /**
   * Save prekey private keys for an identity.
   * These are needed to decrypt messages from senders who used our prekeys.
   */
  async function savePrivateKeys(identity, keys) {
    await _put(PRIVKEY_STORE, {
      identity: identity,
      keys: keys,
      updatedAt: Date.now()
    });
  }

  /**
   * Load prekey private keys for an identity.
   */
  async function loadPrivateKeys(identity) {
    var record = await _get(PRIVKEY_STORE, identity);
    return record ? record.keys : null;
  }

  return {
    saveBundle: saveBundle,
    getBundle: getBundle,
    consumeOneTimePrekey: consumeOneTimePrekey,
    getRemainingCount: getRemainingCount,
    savePrivateKeys: savePrivateKeys,
    loadPrivateKeys: loadPrivateKeys
  };
})();
