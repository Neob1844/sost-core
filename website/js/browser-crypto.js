/**
 * SOST DEX — Browser Crypto Foundation
 *
 * Provides ED25519 signing, X25519 key agreement, HKDF-SHA256 key derivation,
 * and ChaCha20-Poly1305 AEAD encryption in the browser via libsodium-wrappers.
 *
 * Compatible with sost-comms-private Node.js envelopes:
 *   - Same key formats (32-byte raw keys as hex)
 *   - Same HKDF labels and derivation
 *   - Same ChaCha20-Poly1305 with 12-byte nonce
 *   - Same canonical header signing
 *
 * Usage: await SOSTCrypto.ready(); then call functions.
 */

// Loaded via <script src="libsodium-wrappers.min.js"> before this file.
// sodium global becomes available after sodium.ready resolves.

const SOSTCrypto = (function () {
  'use strict';

  let _sodium = null;
  let _ready = false;

  // ── Init ──────────────────────────────────────────────────────

  async function ready() {
    if (_ready) return;
    if (typeof sodium === 'undefined') {
      throw new Error('libsodium-wrappers not loaded. Add <script src="...libsodium-wrappers.min.js"> before browser-crypto.js');
    }
    await sodium.ready;
    _sodium = sodium;
    _ready = true;
  }

  function _ensure() {
    if (!_ready) throw new Error('SOSTCrypto not ready. Call await SOSTCrypto.ready() first.');
  }

  // ── Utilities ─────────────────────────────────────────────────

  function hexToBytes(hex) {
    return _sodium.from_hex(hex);
  }

  function bytesToHex(bytes) {
    return _sodium.to_hex(bytes);
  }

  function randomBytes(n) {
    _ensure();
    return _sodium.randombytes_buf(n);
  }

  async function sha256(data) {
    _ensure();
    // Use Web Crypto for SHA-256 (native, fast)
    var buf;
    if (typeof data === 'string') {
      buf = new TextEncoder().encode(data);
    } else {
      buf = data;
    }
    var hash = await crypto.subtle.digest('SHA-256', buf);
    return bytesToHex(new Uint8Array(hash));
  }

  // Synchronous SHA-256 via libsodium (for internal use where async is awkward)
  function sha256Sync(data) {
    _ensure();
    var buf;
    if (typeof data === 'string') {
      buf = new TextEncoder().encode(data);
    } else {
      buf = data;
    }
    return bytesToHex(_sodium.crypto_hash_sha256(buf));
  }

  // ── ED25519 Signing ───────────────────────────────────────────

  /**
   * Generate an ED25519 signing keypair.
   * Returns { publicKey: hex, privateKey: hex, _raw: { pk, sk } }
   * privateKey is the 64-byte secret key (seed+pub) as hex.
   */
  function generateSigningKeyPair() {
    _ensure();
    var kp = _sodium.crypto_sign_keypair();
    return {
      publicKey: bytesToHex(kp.publicKey),
      privateKey: bytesToHex(kp.privateKey),
      _raw: kp
    };
  }

  /**
   * Sign a message string with ED25519 private key.
   * Returns signature as hex (64 bytes = 128 hex chars).
   */
  function sign(message, privateKeyHex) {
    _ensure();
    var sk = hexToBytes(privateKeyHex);
    var msgBytes = new TextEncoder().encode(message);
    var sig = _sodium.crypto_sign_detached(msgBytes, sk);
    return bytesToHex(sig);
  }

  /**
   * Verify an ED25519 signature.
   * Returns true/false.
   */
  function verify(message, signatureHex, publicKeyHex) {
    _ensure();
    try {
      var sig = hexToBytes(signatureHex);
      var pk = hexToBytes(publicKeyHex);
      var msgBytes = new TextEncoder().encode(message);
      return _sodium.crypto_sign_verify_detached(sig, msgBytes, pk);
    } catch (e) {
      return false;
    }
  }

  /**
   * Sign a pre-computed SHA-256 hash (hex) with ED25519.
   * Compatible with sost-comms-private signCanonicalHash().
   */
  function signHash(hashHex, privateKeyHex) {
    _ensure();
    // signCanonicalHash in Node signs the hash string as UTF-8 bytes
    return sign(hashHex, privateKeyHex);
  }

  /**
   * Verify a signature over a pre-computed hash.
   */
  function verifyHash(hashHex, signatureHex, publicKeyHex) {
    return verify(hashHex, signatureHex, publicKeyHex);
  }

  // ── X25519 Key Agreement ──────────────────────────────────────

  /**
   * Generate an X25519 encryption keypair.
   * Returns { publicKey: hex, privateKey: hex }
   */
  function generateEncryptionKeyPair() {
    _ensure();
    // libsodium crypto_box keypair uses X25519
    var kp = _sodium.crypto_box_keypair();
    return {
      publicKey: bytesToHex(kp.publicKey),
      privateKey: bytesToHex(kp.privateKey)
    };
  }

  /**
   * Convert ED25519 signing key to X25519 encryption key.
   * Useful for key bundles (signing + encryption from same seed).
   */
  function signingToEncryptionPublic(edPublicKeyHex) {
    _ensure();
    var edPk = hexToBytes(edPublicKeyHex);
    var xPk = _sodium.crypto_sign_ed25519_pk_to_curve25519(edPk);
    return bytesToHex(xPk);
  }

  function signingToEncryptionPrivate(edPrivateKeyHex) {
    _ensure();
    var edSk = hexToBytes(edPrivateKeyHex);
    var xSk = _sodium.crypto_sign_ed25519_sk_to_curve25519(edSk);
    return bytesToHex(xSk);
  }

  /**
   * Derive a 32-byte shared secret from X25519 DH.
   * Compatible with sost-comms-private deriveSharedSecret().
   */
  function deriveSharedSecret(ourPrivateHex, theirPublicHex) {
    _ensure();
    var sk = hexToBytes(ourPrivateHex);
    var pk = hexToBytes(theirPublicHex);
    var shared = _sodium.crypto_scalarmult(sk, pk);
    return bytesToHex(shared);
  }

  // ── HKDF-SHA256 Key Derivation ────────────────────────────────

  /**
   * HKDF-SHA256 extract + expand.
   * Compatible with Node.js crypto.hkdfSync('sha256', ikm, salt, info, length).
   */
  function hkdfSha256(ikm, salt, info, length) {
    _ensure();
    // HKDF-Extract: PRK = HMAC-SHA256(salt, ikm)
    var ikmBytes = typeof ikm === 'string' ? new TextEncoder().encode(ikm) : (ikm instanceof Uint8Array ? ikm : hexToBytes(ikm));
    var saltBytes = typeof salt === 'string' ? new TextEncoder().encode(salt) : (salt instanceof Uint8Array ? salt : hexToBytes(salt));
    var infoBytes = typeof info === 'string' ? new TextEncoder().encode(info) : (info instanceof Uint8Array ? info : hexToBytes(info));

    // Extract
    var prk;
    if (saltBytes.length === 0) {
      saltBytes = new Uint8Array(32); // HKDF spec: if salt is empty, use zeros
    }
    var authKey = _sodium.crypto_auth_hmacsha256_keygen();
    // Manual HMAC-SHA256: use crypto_auth_hmacsha256 with salt as key
    // libsodium's HMAC key must be 32 bytes — pad/hash salt if needed
    if (saltBytes.length === 32) {
      prk = _sodium.crypto_auth_hmacsha256(ikmBytes, saltBytes);
    } else {
      // Hash salt to 32 bytes if not standard size
      var saltKey = _sodium.crypto_hash_sha256(saltBytes);
      prk = _sodium.crypto_auth_hmacsha256(ikmBytes, saltKey.subarray(0, 32));
    }

    // Expand
    var hashLen = 32; // SHA-256
    var n = Math.ceil(length / hashLen);
    var okm = new Uint8Array(n * hashLen);
    var prev = new Uint8Array(0);

    for (var i = 0; i < n; i++) {
      var input = new Uint8Array(prev.length + infoBytes.length + 1);
      input.set(prev, 0);
      input.set(infoBytes, prev.length);
      input[prev.length + infoBytes.length] = i + 1;

      // HMAC-SHA256(PRK, T(i-1) || info || i)
      prev = _sodium.crypto_auth_hmacsha256(input, prk);
      okm.set(prev, i * hashLen);
    }

    return okm.subarray(0, length);
  }

  // HKDF labels — must match sost-comms-private/src/e2e/channel_keys.ts
  var LABEL_A = 'sost-deal-key-a';
  var LABEL_B = 'sost-deal-key-b';

  /**
   * Derive directional channel keys from a DH shared secret.
   * Compatible with sost-comms-private deriveChannelKeys().
   */
  function deriveChannelKeys(sharedSecretHex, dealId, isInitiator) {
    _ensure();
    var shared = hexToBytes(sharedSecretHex);
    var saltBytes = new TextEncoder().encode(dealId);

    var keyA = hkdfSha256(shared, saltBytes, LABEL_A, 32);
    var keyB = hkdfSha256(shared, saltBytes, LABEL_B, 32);

    // Session ID = first 16 bytes of SHA-256(shared || dealId)
    var concat = new Uint8Array(shared.length + saltBytes.length);
    concat.set(shared, 0);
    concat.set(saltBytes, shared.length);
    var sessionHash = _sodium.crypto_hash_sha256(concat);
    var sessionId = bytesToHex(sessionHash.subarray(0, 16));

    return {
      sendKey: isInitiator ? bytesToHex(keyA) : bytesToHex(keyB),
      recvKey: isInitiator ? bytesToHex(keyB) : bytesToHex(keyA),
      dealId: dealId,
      sessionId: sessionId
    };
  }

  // ── ChaCha20-Poly1305 AEAD ────────────────────────────────────

  /**
   * Build canonical header string for signing.
   * Must match sost-comms-private/src/e2e/encrypt.ts canonicalHeader().
   */
  function canonicalHeader(fields) {
    return [
      fields.version,
      fields.deal_id,
      fields.session_id,
      fields.sender_id,
      fields.receiver_id,
      fields.msg_type,
      fields.seq_no,
      fields.timestamp,
      fields.nonce
    ].join('|');
  }

  /**
   * Build a 12-byte nonce from seq_no (first 4 bytes) + random (last 8 bytes).
   * Compatible with sost-comms-private buildNonce().
   */
  function buildNonce(seqNo) {
    _ensure();
    var nonce = new Uint8Array(12);
    // Write seqNo as big-endian uint32 in first 4 bytes
    nonce[0] = (seqNo >>> 24) & 0xff;
    nonce[1] = (seqNo >>> 16) & 0xff;
    nonce[2] = (seqNo >>> 8) & 0xff;
    nonce[3] = seqNo & 0xff;
    // Random last 8 bytes
    var rand = _sodium.randombytes_buf(8);
    nonce.set(rand, 4);
    return nonce;
  }

  /**
   * Encrypt a plaintext JSON payload into an EncryptedEnvelope.
   * Compatible with sost-comms-private encryptMessage().
   *
   * Uses ChaCha20-Poly1305 IETF (12-byte nonce, 16-byte tag).
   */
  function encryptMessage(plaintext, channelKeys, seqNo, signingPrivateKeyHex, metadata) {
    _ensure();
    var nonce = buildNonce(seqNo);
    var timestamp = Date.now();

    var headerFields = {
      version: 1,
      deal_id: metadata.deal_id,
      session_id: channelKeys.sessionId,
      sender_id: metadata.sender_id,
      receiver_id: metadata.receiver_id,
      msg_type: metadata.msg_type,
      seq_no: seqNo,
      timestamp: timestamp,
      nonce: bytesToHex(nonce)
    };

    // Sign the canonical header
    var headerStr = canonicalHeader(headerFields);
    var headerHash = sha256Sync(headerStr);
    var signature = signHash(headerHash, signingPrivateKeyHex);

    // Encrypt with ChaCha20-Poly1305 IETF
    var key = hexToBytes(channelKeys.sendKey);
    var plaintextBytes = new TextEncoder().encode(plaintext);
    var aad = new TextEncoder().encode(headerStr);

    // crypto_aead_chacha20poly1305_ietf_encrypt includes tag in output
    var ciphertextWithTag = _sodium.crypto_aead_chacha20poly1305_ietf_encrypt(
      plaintextBytes, aad, null, nonce, key
    );

    // Split: ciphertext is all but last 16 bytes, tag is last 16
    var ciphertext = ciphertextWithTag.subarray(0, ciphertextWithTag.length - 16);
    var tag = ciphertextWithTag.subarray(ciphertextWithTag.length - 16);

    return {
      version: 1,
      deal_id: headerFields.deal_id,
      session_id: headerFields.session_id,
      sender_id: headerFields.sender_id,
      receiver_id: headerFields.receiver_id,
      msg_type: headerFields.msg_type,
      seq_no: seqNo,
      timestamp: timestamp,
      nonce: headerFields.nonce,
      ciphertext: bytesToHex(ciphertext),
      tag: bytesToHex(tag),
      signature: signature
    };
  }

  /**
   * Decrypt an EncryptedEnvelope.
   * Compatible with sost-comms-private decryptMessage().
   */
  function decryptMessage(envelope, channelKeys, senderPublicKeyHex) {
    _ensure();
    // Verify header signature
    var headerFields = {
      version: envelope.version,
      deal_id: envelope.deal_id,
      session_id: envelope.session_id,
      sender_id: envelope.sender_id,
      receiver_id: envelope.receiver_id,
      msg_type: envelope.msg_type,
      seq_no: envelope.seq_no,
      timestamp: envelope.timestamp,
      nonce: envelope.nonce
    };
    var headerStr = canonicalHeader(headerFields);
    var headerHash = sha256Sync(headerStr);
    var verified = verifyHash(headerHash, envelope.signature, senderPublicKeyHex);

    // Decrypt
    var key = hexToBytes(channelKeys.recvKey);
    var nonce = hexToBytes(envelope.nonce);
    var ciphertext = hexToBytes(envelope.ciphertext);
    var tag = hexToBytes(envelope.tag);

    // Reconstruct ciphertext+tag for libsodium
    var combined = new Uint8Array(ciphertext.length + tag.length);
    combined.set(ciphertext, 0);
    combined.set(tag, ciphertext.length);

    var aad = new TextEncoder().encode(headerStr);

    try {
      var plaintext = _sodium.crypto_aead_chacha20poly1305_ietf_decrypt(
        null, combined, aad, nonce, key
      );
      return {
        plaintext: new TextDecoder().decode(plaintext),
        verified: verified
      };
    } catch (e) {
      return { plaintext: null, verified: verified, error: 'decryption failed' };
    }
  }

  // ── Key Bundle ────────────────────────────────────────────────

  /**
   * Generate a complete identity bundle (signing + encryption).
   * Compatible with sost-comms-private KeyBundle.
   */
  function generateKeyBundle() {
    _ensure();
    var signing = generateSigningKeyPair();
    var encryption = generateEncryptionKeyPair();
    return {
      signing: {
        publicKey: signing.publicKey,
        privateKey: signing.privateKey
      },
      encryption: {
        publicKey: encryption.publicKey,
        privateKey: encryption.privateKey
      }
    };
  }

  // ── Public API ────────────────────────────────────────────────

  return {
    ready: ready,

    // Utils
    hexToBytes: hexToBytes,
    bytesToHex: bytesToHex,
    randomBytes: randomBytes,
    sha256: sha256,
    sha256Sync: sha256Sync,

    // ED25519
    generateSigningKeyPair: generateSigningKeyPair,
    sign: sign,
    verify: verify,
    signHash: signHash,
    verifyHash: verifyHash,

    // X25519
    generateEncryptionKeyPair: generateEncryptionKeyPair,
    deriveSharedSecret: deriveSharedSecret,
    signingToEncryptionPublic: signingToEncryptionPublic,
    signingToEncryptionPrivate: signingToEncryptionPrivate,

    // Key derivation
    hkdfSha256: hkdfSha256,
    deriveChannelKeys: deriveChannelKeys,

    // AEAD
    canonicalHeader: canonicalHeader,
    encryptMessage: encryptMessage,
    decryptMessage: decryptMessage,

    // Bundle
    generateKeyBundle: generateKeyBundle
  };
})();
