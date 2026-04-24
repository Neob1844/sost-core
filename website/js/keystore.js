/**
 * SOST DEX — Browser Keystore
 *
 * Manages cryptographic identity in the browser using IndexedDB for persistence
 * and XChaCha20-Poly1305 (via libsodium) for encrypting stored keys.
 *
 * Identity = ED25519 signing keypair + X25519 encryption keypair.
 * The private keys are encrypted with a passphrase-derived key before storage.
 *
 * Depends on: browser-crypto.js (SOSTCrypto)
 */

const SOSTKeystore = (function () {
  'use strict';

  var DB_NAME = 'sost-dex-keystore';
  var DB_VERSION = 1;
  var STORE_NAME = 'identities';
  var _db = null;
  var _unlocked = null; // { signing, encryption } with private keys in memory

  // ── IndexedDB ─────────────────────────────────────────────────

  function _openDB() {
    return new Promise(function (resolve, reject) {
      if (_db) { resolve(_db); return; }
      var req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        }
      };
      req.onsuccess = function (e) { _db = e.target.result; resolve(_db); };
      req.onerror = function (e) { reject(e.target.error); };
    });
  }

  function _put(record) {
    return new Promise(function (resolve, reject) {
      _openDB().then(function (db) {
        var tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(record);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function (e) { reject(e.target.error); };
      });
    });
  }

  function _get(id) {
    return new Promise(function (resolve, reject) {
      _openDB().then(function (db) {
        var tx = db.transaction(STORE_NAME, 'readonly');
        var req = tx.objectStore(STORE_NAME).get(id);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  }

  function _getAll() {
    return new Promise(function (resolve, reject) {
      _openDB().then(function (db) {
        var tx = db.transaction(STORE_NAME, 'readonly');
        var req = tx.objectStore(STORE_NAME).getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  }

  function _delete(id) {
    return new Promise(function (resolve, reject) {
      _openDB().then(function (db) {
        var tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).delete(id);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function (e) { reject(e.target.error); };
      });
    });
  }

  // ── Passphrase-based encryption ───────────────────────────────

  /**
   * Derive a 32-byte key from a passphrase using Argon2id (via libsodium).
   * Returns { key, salt } where salt is 16 bytes hex (stored with ciphertext).
   */
  function _deriveKeyFromPassphrase(passphrase, saltHex) {
    var salt;
    if (saltHex) {
      salt = SOSTCrypto.hexToBytes(saltHex);
    } else {
      salt = SOSTCrypto.randomBytes(sodium.crypto_pwhash_SALTBYTES);
    }
    var key = sodium.crypto_pwhash(
      32,
      passphrase,
      salt,
      sodium.crypto_pwhash_OPSLIMIT_INTERACTIVE,
      sodium.crypto_pwhash_MEMLIMIT_INTERACTIVE,
      sodium.crypto_pwhash_ALG_ARGON2ID13
    );
    return { key: key, salt: SOSTCrypto.bytesToHex(salt) };
  }

  /**
   * Encrypt private key material with passphrase-derived key.
   */
  function _encryptPrivateKeys(bundle, passphrase) {
    var plaintext = JSON.stringify({
      signingPrivate: bundle.signing.privateKey,
      encryptionPrivate: bundle.encryption.privateKey
    });
    var derived = _deriveKeyFromPassphrase(passphrase);
    var nonce = SOSTCrypto.randomBytes(sodium.crypto_secretbox_NONCEBYTES);
    var ciphertext = sodium.crypto_secretbox_easy(
      new TextEncoder().encode(plaintext),
      nonce,
      derived.key
    );
    return {
      salt: derived.salt,
      nonce: SOSTCrypto.bytesToHex(nonce),
      ciphertext: SOSTCrypto.bytesToHex(ciphertext)
    };
  }

  /**
   * Decrypt private key material with passphrase.
   */
  function _decryptPrivateKeys(encrypted, passphrase) {
    var derived = _deriveKeyFromPassphrase(passphrase, encrypted.salt);
    var nonce = SOSTCrypto.hexToBytes(encrypted.nonce);
    var ciphertext = SOSTCrypto.hexToBytes(encrypted.ciphertext);
    try {
      var plaintext = sodium.crypto_secretbox_open_easy(ciphertext, nonce, derived.key);
      return JSON.parse(new TextDecoder().decode(plaintext));
    } catch (e) {
      return null; // Wrong passphrase
    }
  }

  // ── Public API ────────────────────────────────────────────────

  /**
   * Create a new identity and store it encrypted with passphrase.
   * Returns { id, signingPublic, encryptionPublic }.
   */
  async function createIdentity(passphrase, label) {
    await SOSTCrypto.ready();
    var bundle = SOSTCrypto.generateKeyBundle();
    var encrypted = _encryptPrivateKeys(bundle, passphrase);
    var id = bundle.signing.publicKey.substring(0, 16); // Short ID from pub key

    var record = {
      id: id,
      label: label || 'default',
      signingPublic: bundle.signing.publicKey,
      encryptionPublic: bundle.encryption.publicKey,
      encrypted: encrypted,
      createdAt: Date.now()
    };

    await _put(record);

    // Auto-unlock after creation
    _unlocked = {
      id: id,
      signing: bundle.signing,
      encryption: bundle.encryption
    };

    return {
      id: id,
      signingPublic: bundle.signing.publicKey,
      encryptionPublic: bundle.encryption.publicKey
    };
  }

  /**
   * List all stored identities (public info only).
   */
  async function listIdentities() {
    var records = await _getAll();
    return records.map(function (r) {
      return {
        id: r.id,
        label: r.label,
        signingPublic: r.signingPublic,
        encryptionPublic: r.encryptionPublic,
        createdAt: r.createdAt
      };
    });
  }

  /**
   * Unlock an identity with passphrase.
   * Returns { id, signingPublic, encryptionPublic } or null if wrong passphrase.
   */
  async function unlock(id, passphrase) {
    await SOSTCrypto.ready();
    var record = await _get(id);
    if (!record) return null;

    var keys = _decryptPrivateKeys(record.encrypted, passphrase);
    if (!keys) return null;

    _unlocked = {
      id: id,
      signing: {
        publicKey: record.signingPublic,
        privateKey: keys.signingPrivate
      },
      encryption: {
        publicKey: record.encryptionPublic,
        privateKey: keys.encryptionPrivate
      }
    };

    return {
      id: id,
      signingPublic: record.signingPublic,
      encryptionPublic: record.encryptionPublic
    };
  }

  /**
   * Lock the current session (clear private keys from memory).
   */
  function lock() {
    _unlocked = null;
  }

  /**
   * Check if an identity is currently unlocked.
   */
  function isUnlocked() {
    return _unlocked !== null;
  }

  /**
   * Get the current unlocked identity (null if locked).
   */
  function getIdentity() {
    return _unlocked ? {
      id: _unlocked.id,
      signingPublic: _unlocked.signing.publicKey,
      encryptionPublic: _unlocked.encryption.publicKey
    } : null;
  }

  /**
   * Get signing private key (only available when unlocked).
   */
  function getSigningKey() {
    if (!_unlocked) throw new Error('Keystore locked. Call unlock() first.');
    return _unlocked.signing.privateKey;
  }

  /**
   * Get encryption private key (only available when unlocked).
   */
  function getEncryptionKey() {
    if (!_unlocked) throw new Error('Keystore locked. Call unlock() first.');
    return _unlocked.encryption.privateKey;
  }

  /**
   * Export the identity as an encrypted JSON blob (for backup/transfer).
   */
  async function exportEncrypted(id) {
    var record = await _get(id);
    if (!record) return null;
    return JSON.stringify({
      version: 1,
      id: record.id,
      label: record.label,
      signingPublic: record.signingPublic,
      encryptionPublic: record.encryptionPublic,
      encrypted: record.encrypted,
      createdAt: record.createdAt,
      exportedAt: Date.now()
    });
  }

  /**
   * Import an encrypted identity from a JSON blob.
   */
  async function importEncrypted(jsonBlob) {
    var data = JSON.parse(jsonBlob);
    if (data.version !== 1) throw new Error('Unsupported keystore version');
    await _put({
      id: data.id,
      label: data.label,
      signingPublic: data.signingPublic,
      encryptionPublic: data.encryptionPublic,
      encrypted: data.encrypted,
      createdAt: data.createdAt
    });
    return {
      id: data.id,
      signingPublic: data.signingPublic,
      encryptionPublic: data.encryptionPublic
    };
  }

  /**
   * Delete an identity from the keystore.
   */
  async function deleteIdentity(id) {
    if (_unlocked && _unlocked.id === id) lock();
    await _delete(id);
  }

  return {
    createIdentity: createIdentity,
    listIdentities: listIdentities,
    unlock: unlock,
    lock: lock,
    isUnlocked: isUnlocked,
    getIdentity: getIdentity,
    getSigningKey: getSigningKey,
    getEncryptionKey: getEncryptionKey,
    exportEncrypted: exportEncrypted,
    importEncrypted: importEncrypted,
    deleteIdentity: deleteIdentity
  };
})();
