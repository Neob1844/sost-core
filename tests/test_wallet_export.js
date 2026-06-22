/* Tests for the web wallet "Export Private Key" feature.
 *
 *   node tests/test_wallet_export.js
 *
 * Two layers:
 *  1. Pure-logic tests of website/js/wallet-export.js (gate, schema, filename)
 *     using DUMMY keys only — no real secret is present anywhere in this file.
 *  2. Static-analysis tests of the export UI block in sost-wallet.html that lock
 *     in the security invariants: collapsed by default; password + phrase +
 *     checkbox gate enforced; the private key is never sent via
 *     fetch/XHR/WebSocket, never persisted to localStorage/sessionStorage, and
 *     never logged to the console.
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const X = require("../website/js/wallet-export.js");
const HTML = fs.readFileSync(path.join(__dirname, "..", "website", "sost-wallet.html"), "utf8");

// DUMMY key material — NOT a real key. 64/66 hex chars + a valid-shaped address.
const DUMMY = {
  privKey: "11111111111111111111111111111111111111111111111111111111111111ab",
  pubKey: "02" + "33".repeat(32),
  address: "sost1" + "ab".repeat(20),
  watchOnly: false
};

let pass = 0;
function t(name, fn) { fn(); pass++; console.log("  ok -", name); }

// ---------- 1. gate ----------
t("gate requires a password", () => {
  assert.deepStrictEqual(X.validateExportGate("", "EXPORT PRIVATE KEY", true),
    { ok: false, reason: "password-required" });
});
t("gate requires the exact confirmation phrase", () => {
  assert.strictEqual(X.validateExportGate("pw", "export private key", true).reason, "phrase-required");
  assert.strictEqual(X.validateExportGate("pw", "EXPORT  PRIVATE KEY", true).reason, "phrase-required");
});
t("gate requires the acknowledgement checkbox", () => {
  assert.strictEqual(X.validateExportGate("pw", "EXPORT PRIVATE KEY", false).reason, "ack-required");
});
t("gate passes only when all three hold", () => {
  assert.deepStrictEqual(X.validateExportGate("pw", "EXPORT PRIVATE KEY", true), { ok: true });
});

// ---------- 2. key-material validation ----------
t("watch-only wallets cannot be exported", () => {
  assert.strictEqual(X.validateKeyMaterial({ watchOnly: true }).reason, "watch-only");
});
t("malformed key material is rejected", () => {
  assert.strictEqual(X.validateKeyMaterial({ privKey: "xyz", pubKey: DUMMY.pubKey, address: DUMMY.address }).reason, "bad-privkey");
  assert.strictEqual(X.validateKeyMaterial({ privKey: DUMMY.privKey, pubKey: "02", address: DUMMY.address }).reason, "bad-pubkey");
  assert.strictEqual(X.validateKeyMaterial({ privKey: DUMMY.privKey, pubKey: DUMMY.pubKey, address: "btc1abc" }).reason, "bad-address");
});
t("valid dummy material passes", () => {
  assert.deepStrictEqual(X.validateKeyMaterial(DUMMY), { ok: true });
});

// ---------- 3. CLI wallet JSON schema (matches src/wallet.cpp v1) ----------
t("CLI wallet JSON has the exact v1 schema the miner expects", () => {
  const j = X.buildCliWalletJson(DUMMY, "SOST CEX LIQUIDITY RESERVE");
  assert.strictEqual(j.version, 1);
  assert.ok(typeof j.warning === "string" && j.warning.length > 0);
  assert.ok(Array.isArray(j.keys) && j.keys.length === 1);
  assert.deepStrictEqual(Object.keys(j.keys[0]).sort(), ["address", "label", "privkey", "pubkey"]);
  assert.strictEqual(j.keys[0].privkey, DUMMY.privKey);
  assert.strictEqual(j.keys[0].pubkey, DUMMY.pubKey);
  assert.strictEqual(j.keys[0].address, DUMMY.address);
  assert.strictEqual(j.keys[0].label, "SOST CEX LIQUIDITY RESERVE");
  assert.deepStrictEqual(j.utxos, []);
});
t("CLI wallet JSON falls back to the default label", () => {
  assert.strictEqual(X.buildCliWalletJson(DUMMY, "  ").keys[0].label, X.DEFAULT_LABEL);
  assert.strictEqual(X.buildCliWalletJson(DUMMY, null).keys[0].label, "SOST CEX LIQUIDITY RESERVE");
});

// ---------- 4. filename ----------
t("export filename is slugged + dated", () => {
  assert.strictEqual(X.exportFilename("SOST CEX LIQUIDITY RESERVE", "20260622"),
    "sost-cli-wallet-SOST-CEX-LIQUIDITY-RESERVE-20260622.json");
  assert.strictEqual(X.exportFilename("my wallet!", "20260101"),
    "sost-cli-wallet-MY-WALLET-20260101.json");
});

// ---------- 5. static security invariants in the UI block ----------
const startM = "==================== EXPORT PRIVATE KEY (Advanced) ====================";
const endM = "==================== /EXPORT PRIVATE KEY ====================";
const si = HTML.indexOf(startM), ei = HTML.indexOf(endM);
assert.ok(si > 0 && ei > si, "export block markers not found");
// Scan CODE, not comments: strip /* */ and // comments so the forbidden-token
// checks below don't trip on this feature's own explanatory prose.
const BLOCK = HTML.slice(si, ei)
  .replace(/\/\*[\s\S]*?\*\//g, " ")
  .replace(/(^|[^:])\/\/[^\n]*/g, "$1");

t("export panel is collapsed by default", () => {
  assert.ok(/id="exportKeyBody"[^>]*class="hidden"/.test(HTML), "exportKeyBody must start hidden");
});
t("UI wires the password, phrase and checkbox gate", () => {
  ["exportKeyPass", "exportKeyPhrase", "exportKeyAck"].forEach(id =>
    assert.ok(HTML.indexOf('id="' + id + '"') > 0, "missing " + id));
  assert.ok(BLOCK.indexOf("validateExportGate") > 0, "gate not called");
});
t("private key is never sent over the network from the export block", () => {
  assert.ok(!/\bfetch\s*\(/.test(BLOCK), "fetch() in export block");
  assert.ok(!/XMLHttpRequest/.test(BLOCK), "XHR in export block");
  assert.ok(!/WebSocket/.test(BLOCK), "WebSocket in export block");
  assert.ok(!/navigator\.sendBeacon/.test(BLOCK), "sendBeacon in export block");
});
t("private key is never persisted to storage from the export block", () => {
  assert.ok(!/localStorage\.setItem/.test(BLOCK), "localStorage.setItem in export block");
  assert.ok(!/sessionStorage/.test(BLOCK), "sessionStorage in export block");
});
t("private key is never logged from the export block", () => {
  assert.ok(!/console\.(log|error|warn|info|debug)\s*\([^)]*(privKey|privkey|data\.priv)/.test(BLOCK),
    "console call with key material in export block");
});
t("export forces an auto-lock", () => {
  assert.ok(BLOCK.indexOf("lockWallet") > 0, "export must force-lock the wallet");
});
t("reveal-once also locks the wallet (after the 60s auto-hide)", () => {
  const s = HTML.indexOf("window.exportRevealOnce");
  const e = HTML.indexOf("window.exportToggleRevealField");
  assert.ok(s > 0 && e > s, "exportRevealOnce body not found");
  const fn = HTML.slice(s, e);
  assert.ok(/setTimeout/.test(fn), "reveal-once must auto-hide on a timer");
  assert.ok(/lockWallet/.test(fn), "reveal-once must call lockWallet after the timer");
});

console.log("\n" + pass + " checks passed.");
