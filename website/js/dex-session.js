/**
 * SOST DEX — Session Manager
 *
 * Manages the DEX session lifecycle: unlock, lock, timeout, state tracking.
 * Bridges the keystore with the DEX UI and relay.
 *
 * Depends on: keystore.js, relay-client.js, private-inbox.js, recipient-directory.js
 */

const SOSTSession = (function () {
  'use strict';

  var _state = 'locked'; // 'locked' | 'unlocked'
  var _timeoutId = null;
  var _timeoutMs = 5 * 60 * 1000; // 5 min default
  var _onStateChange = null;

  /**
   * Set callback for state changes.
   */
  function onStateChange(callback) {
    _onStateChange = callback;
  }

  function _setState(newState) {
    if (_state === newState) return;
    _state = newState;
    if (_onStateChange) _onStateChange(newState);
  }

  /**
   * Reset the inactivity timer.
   */
  function _resetTimeout() {
    if (_timeoutId) clearTimeout(_timeoutId);
    if (_state === 'unlocked') {
      _timeoutId = setTimeout(function () {
        lock();
      }, _timeoutMs);
    }
  }

  /**
   * Unlock the DEX session with a keystore identity.
   */
  async function unlock(identityId, passphrase) {
    var result = await SOSTKeystore.unlock(identityId, passphrase);
    if (!result) return { ok: false, error: 'wrong passphrase' };

    _setState('unlocked');
    _resetTimeout();

    // Load directory
    await SOSTDirectory.load();

    // Start inbox polling
    SOSTInbox.startPolling(15000);

    // Track user activity for timeout
    ['click', 'keydown', 'mousemove', 'touchstart'].forEach(function (evt) {
      document.addEventListener(evt, _resetTimeout, { passive: true });
    });

    return { ok: true, identity: result };
  }

  /**
   * Lock the session (clear keys, stop polling).
   */
  function lock() {
    SOSTKeystore.lock();
    SOSTInbox.clear();
    _setState('locked');

    if (_timeoutId) {
      clearTimeout(_timeoutId);
      _timeoutId = null;
    }

    ['click', 'keydown', 'mousemove', 'touchstart'].forEach(function (evt) {
      document.removeEventListener(evt, _resetTimeout);
    });
  }

  /**
   * Get current session state.
   */
  function getState() {
    return _state;
  }

  /**
   * Check if session is unlocked.
   */
  function isUnlocked() {
    return _state === 'unlocked';
  }

  /**
   * Set session timeout duration.
   */
  function setTimeoutDuration(ms) {
    _timeoutMs = ms;
  }

  /**
   * Get session info (for UI display).
   */
  function getInfo() {
    var identity = SOSTKeystore.getIdentity();
    return {
      state: _state,
      identity: identity,
      relayConfigured: !!SOSTRelay,
      inboxCount: SOSTInbox.getCounts().total
    };
  }

  return {
    onStateChange: onStateChange,
    unlock: unlock,
    lock: lock,
    getState: getState,
    isUnlocked: isUnlocked,
    setTimeoutDuration: setTimeoutDuration,
    getInfo: getInfo
  };
})();
