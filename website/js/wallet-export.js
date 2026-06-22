/* SOST web wallet — "Export Private Key" pure helpers.
 *
 * This file holds ONLY pure, side-effect-free logic (validation, schema
 * building, filename derivation). It performs NO decryption, NO DOM access,
 * NO network calls, NO storage, and NO logging. Those happen in the UI layer
 * in sost-wallet.html, which decrypts the wallet in-memory and triggers a
 * client-side download.
 *
 * Dual export: attaches to window.SostExport in the browser and to
 * module.exports under Node (so tests/test_wallet_export.js can import it).
 */
(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.SostExport = api;
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  // The user must type this exactly before any key material is touched.
  var CONFIRM_PHRASE = "EXPORT PRIVATE KEY";
  var DEFAULT_LABEL = "SOST CEX LIQUIDITY RESERVE";

  function isHex(s, len) {
    return typeof s === "string" && new RegExp("^[0-9a-fA-F]{" + len + "}$").test(s);
  }

  // Gate: ALL three conditions must hold (password present, exact phrase,
  // acknowledgement checked) before the caller may decrypt/export anything.
  function validateExportGate(password, phrase, ack) {
    if (password == null || String(password).length === 0) return { ok: false, reason: "password-required" };
    if (String(phrase) !== CONFIRM_PHRASE) return { ok: false, reason: "phrase-required" };
    if (ack !== true) return { ok: false, reason: "ack-required" };
    return { ok: true };
  }

  // Defensive validation of the decrypted key triple. Watch-only wallets and
  // malformed material are rejected so we never export junk.
  function validateKeyMaterial(k) {
    if (!k || k.watchOnly === true) return { ok: false, reason: "watch-only" };
    if (!isHex(k.privKey, 64)) return { ok: false, reason: "bad-privkey" };
    if (!isHex(k.pubKey, 66)) return { ok: false, reason: "bad-pubkey" };
    if (typeof k.address !== "string" || !/^sost1[0-9a-fA-F]{40}$/.test(k.address)) {
      return { ok: false, reason: "bad-address" };
    }
    return { ok: true };
  }

  // Build the CLI/miner-compatible wallet JSON. Schema mirrors the v1 format
  // written/read by src/wallet.cpp (version, warning, keys[], utxos[]), so the
  // file loads directly with:  sost-miner --wallet <file> --mining-key-label <label>
  function buildCliWalletJson(k, label) {
    var lbl = (label != null && String(label).trim()) ? String(label).trim() : DEFAULT_LABEL;
    return {
      version: 1,
      warning: "PRIVATE KEYS ARE UNENCRYPTED — KEEP THIS FILE SECURE",
      keys: [{
        privkey: k.privKey,
        pubkey: k.pubKey,
        address: k.address,
        label: lbl
      }],
      utxos: []
    };
  }

  // e.g. sost-cli-wallet-SOST-CEX-LIQUIDITY-RESERVE-20260622.json
  // dateStr (YYYYMMDD) is passed by the caller; falls back to today in-browser.
  function exportFilename(label, dateStr) {
    var lbl = (label != null && String(label).trim()) ? String(label).trim() : DEFAULT_LABEL;
    var slug = lbl.toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    var d = dateStr || todayStamp();
    return "sost-cli-wallet-" + slug + "-" + d + ".json";
  }

  function todayStamp() {
    var dt = new Date();
    var m = ("0" + (dt.getMonth() + 1)).slice(-2);
    var day = ("0" + dt.getDate()).slice(-2);
    return "" + dt.getFullYear() + m + day;
  }

  return {
    CONFIRM_PHRASE: CONFIRM_PHRASE,
    DEFAULT_LABEL: DEFAULT_LABEL,
    isHex: isHex,
    validateExportGate: validateExportGate,
    validateKeyMaterial: validateKeyMaterial,
    buildCliWalletJson: buildCliWalletJson,
    exportFilename: exportFilename,
    todayStamp: todayStamp
  };
});
