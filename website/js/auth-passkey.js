/**
 * SOST DEX — Passkey / WebAuthn Authentication
 *
 * Modern device authentication using WebAuthn passkeys.
 * Supports fingerprint, Face ID, secure PIN, and other platform authenticators.
 * The passkey controls access to the DEX private mode and can gate sensitive actions.
 *
 * Architecture:
 *   passkey → unlocks session → session unlocks keystore → keystore holds crypto keys
 *   sensitive actions → require re-authentication via passkey
 */

const SOSTPasskey = (function () {
  'use strict';

  var RP_NAME = 'SOST DEX';
  var RP_ID = null; // Set from current hostname
  var _credential = null;
  var _registered = false;
  var _authenticated = false;
  var _lastAuthTime = 0;
  var _onAuth = null;

  // ── Availability ──────────────────────────────────────────────

  /**
   * Check if WebAuthn is available in this browser.
   */
  function isAvailable() {
    return !!(window.PublicKeyCredential && navigator.credentials && navigator.credentials.create);
  }

  /**
   * Check if platform authenticator (fingerprint/Face ID) is available.
   */
  async function isPlatformAvailable() {
    if (!isAvailable()) return false;
    try {
      return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
    } catch (e) {
      return false;
    }
  }

  // ── Registration ──────────────────────────────────────────────

  /**
   * Register a new passkey for this user.
   * @param {string} userId - Unique user ID (e.g. keystore identity ID)
   * @param {string} userName - Display name
   * @returns {object} { ok, credentialId } or { ok: false, error }
   */
  async function register(userId, userName) {
    if (!isAvailable()) return { ok: false, error: 'WebAuthn not available' };

    RP_ID = window.location.hostname;
    var challenge = crypto.getRandomValues(new Uint8Array(32));
    var userIdBytes = new TextEncoder().encode(userId);

    var options = {
      publicKey: {
        rp: { name: RP_NAME, id: RP_ID },
        user: {
          id: userIdBytes,
          name: userName || 'SOST User',
          displayName: userName || 'SOST User'
        },
        challenge: challenge,
        pubKeyCredParams: [
          { type: 'public-key', alg: -7 },   // ES256
          { type: 'public-key', alg: -257 }  // RS256
        ],
        timeout: 60000,
        authenticatorSelection: {
          authenticatorAttachment: 'platform',
          userVerification: 'required',
          residentKey: 'preferred',
          requireResidentKey: false
        },
        attestation: 'none'
      }
    };

    try {
      var cred = await navigator.credentials.create(options);
      _credential = {
        id: cred.id,
        rawId: new Uint8Array(cred.rawId),
        type: cred.type
      };
      _registered = true;

      // Store credential ID in localStorage for login
      var stored = JSON.parse(localStorage.getItem('sost_passkey_creds') || '[]');
      stored.push({ id: cred.id, userId: userId, userName: userName, createdAt: Date.now() });
      localStorage.setItem('sost_passkey_creds', JSON.stringify(stored));

      return { ok: true, credentialId: cred.id };
    } catch (e) {
      return { ok: false, error: e.message || 'registration failed' };
    }
  }

  // ── Authentication ────────────────────────────────────────────

  /**
   * Authenticate with an existing passkey.
   * @returns {object} { ok, credentialId } or { ok: false, error }
   */
  async function authenticate() {
    if (!isAvailable()) return { ok: false, error: 'WebAuthn not available' };

    RP_ID = window.location.hostname;
    var challenge = crypto.getRandomValues(new Uint8Array(32));

    // Get stored credential IDs
    var stored = JSON.parse(localStorage.getItem('sost_passkey_creds') || '[]');
    var allowCredentials = stored.map(function (c) {
      // Convert base64url credential ID to ArrayBuffer
      var idBytes = _base64urlToBytes(c.id);
      return { type: 'public-key', id: idBytes };
    });

    var options = {
      publicKey: {
        challenge: challenge,
        rpId: RP_ID,
        timeout: 60000,
        userVerification: 'required',
        allowCredentials: allowCredentials.length > 0 ? allowCredentials : undefined
      }
    };

    try {
      var assertion = await navigator.credentials.get(options);
      _credential = {
        id: assertion.id,
        rawId: new Uint8Array(assertion.rawId),
        type: assertion.type
      };
      _authenticated = true;
      _lastAuthTime = Date.now();

      if (_onAuth) _onAuth({ type: 'login', credentialId: assertion.id });

      return { ok: true, credentialId: assertion.id };
    } catch (e) {
      return { ok: false, error: e.message || 'authentication failed' };
    }
  }

  /**
   * Re-authenticate for a sensitive action.
   * Same as authenticate() but tracked separately for strong-auth gating.
   */
  async function reAuthenticate() {
    var result = await authenticate();
    if (result.ok) {
      _lastAuthTime = Date.now();
      if (_onAuth) _onAuth({ type: 'reauth', credentialId: result.credentialId });
    }
    return result;
  }

  // ── Strong Auth Gating ────────────────────────────────────────

  /**
   * Check if the user has authenticated recently enough for a sensitive action.
   * @param {number} maxAgeMs - Maximum time since last auth (default 2 min)
   */
  function isRecentlyAuthenticated(maxAgeMs) {
    var max = maxAgeMs || 120000; // 2 min default
    return _authenticated && (Date.now() - _lastAuthTime) < max;
  }

  /**
   * Check if a specific action type requires strong auth.
   */
  function requiresStrongAuth(actionType) {
    var sensitive = [
      'sign_offer', 'sign_accept', 'sign_cancel',
      'send_offer', 'send_accept', 'send_otc',
      'export_keystore', 'delete_identity',
      'change_beneficiary', 'execute_settlement'
    ];
    return sensitive.indexOf(actionType) >= 0;
  }

  /**
   * Ensure strong auth before proceeding.
   * If recently authenticated, returns immediately.
   * Otherwise prompts for re-authentication.
   * @returns {object} { ok } or { ok: false, error }
   */
  async function ensureStrongAuth(actionType) {
    if (!requiresStrongAuth(actionType)) return { ok: true };
    if (isRecentlyAuthenticated()) return { ok: true };
    return await reAuthenticate();
  }

  // ── State ─────────────────────────────────────────────────────

  function isRegistered() {
    var stored = JSON.parse(localStorage.getItem('sost_passkey_creds') || '[]');
    return stored.length > 0;
  }

  function isAuthenticated() { return _authenticated; }

  function getCredential() { return _credential; }

  function getStoredCredentials() {
    return JSON.parse(localStorage.getItem('sost_passkey_creds') || '[]');
  }

  function logout() {
    _authenticated = false;
    _lastAuthTime = 0;
    _credential = null;
  }

  function onAuth(callback) { _onAuth = callback; }

  // ── Helpers ───────────────────────────────────────────────────

  function _base64urlToBytes(base64url) {
    var base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
    while (base64.length % 4) base64 += '=';
    var binary = atob(base64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  return {
    isAvailable: isAvailable,
    isPlatformAvailable: isPlatformAvailable,
    register: register,
    authenticate: authenticate,
    reAuthenticate: reAuthenticate,
    isRecentlyAuthenticated: isRecentlyAuthenticated,
    requiresStrongAuth: requiresStrongAuth,
    ensureStrongAuth: ensureStrongAuth,
    isRegistered: isRegistered,
    isAuthenticated: isAuthenticated,
    getCredential: getCredential,
    getStoredCredentials: getStoredCredentials,
    logout: logout,
    onAuth: onAuth
  };
})();
