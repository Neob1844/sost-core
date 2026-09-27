/* SOST DEX — sensitive-action gate: double-confirmation + optional local TOTP 2FA.
 *
 * For sensitive actions (connect wallet, execute a swap) the DEX asks for an explicit
 * double confirmation, and — if the viewer has enabled it — a 6-digit TOTP code from a
 * standard authenticator app (Google Authenticator / Aegis / 1Password, RFC 6238).
 *
 * HONEST SCOPE: this is a LOCAL, device-side confirmation gate that adds deliberate
 * friction before sensitive UI actions. The TOTP secret lives only in this browser's
 * localStorage; it is never sent anywhere and there is no server enforcing it. It is a
 * UX safeguard, NOT custody security — a non-custodial swap is ultimately authorised by
 * your wallet extension's own signature prompt, which this never replaces or weakens.
 */
(function (root) {
  "use strict";
  var LS = "sost_dex_2fa_secret_b32";
  var subtle = (root.crypto && root.crypto.subtle) || (typeof crypto !== "undefined" && crypto.subtle);

  // ---- base32 (RFC 4648, no padding) ----
  var B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  function b32encode(bytes) {
    var out = "", bits = 0, val = 0;
    for (var i = 0; i < bytes.length; i++) { val = (val << 8) | bytes[i]; bits += 8;
      while (bits >= 5) { out += B32[(val >>> (bits - 5)) & 31]; bits -= 5; } }
    if (bits > 0) out += B32[(val << (5 - bits)) & 31];
    return out;
  }
  function b32decode(s) {
    s = (s || "").replace(/=+$/, "").replace(/\s+/g, "").toUpperCase();
    var bits = 0, val = 0, out = [];
    for (var i = 0; i < s.length; i++) { var idx = B32.indexOf(s[i]); if (idx < 0) continue;
      val = (val << 5) | idx; bits += 5;
      if (bits >= 8) { out.push((val >>> (bits - 8)) & 0xff); bits -= 8; } }
    return new Uint8Array(out);
  }

  // ---- TOTP (HMAC-SHA1, 30s step, 6 digits) ----
  async function hotp(secretBytes, counter) {
    var buf = new ArrayBuffer(8), dv = new DataView(buf);
    dv.setUint32(0, Math.floor(counter / 0x100000000));
    dv.setUint32(4, counter >>> 0);
    var key = await subtle.importKey("raw", secretBytes, { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
    var sig = new Uint8Array(await subtle.sign("HMAC", key, buf));
    var off = sig[19] & 0xf;
    var bin = ((sig[off] & 0x7f) << 24) | ((sig[off + 1] & 0xff) << 16) | ((sig[off + 2] & 0xff) << 8) | (sig[off + 3] & 0xff);
    return ("00000" + (bin % 1000000)).slice(-6);
  }
  async function totp(secretB32, epochSec, step) {
    step = step || 30;
    return hotp(b32decode(secretB32), Math.floor(epochSec / step));
  }
  // verify with a ±1 step window (clock skew tolerance)
  async function verifyAt(secretB32, code, epochSec, step) {
    step = step || 30; code = String(code || "").replace(/\s+/g, "");
    if (!/^\d{6}$/.test(code)) return false;
    for (var w = -1; w <= 1; w++) {
      if ((await totp(secretB32, epochSec + w * step, step)) === code) return true;
    }
    return false;
  }

  // ---- local secret (browser only) ----
  function get2FASecret() { try { return root.localStorage.getItem(LS); } catch (e) { return null; } }
  function is2FAEnabled() { return !!get2FASecret(); }
  function randomSecretB32() {
    var b = new Uint8Array(20); (root.crypto || crypto).getRandomValues(b); return b32encode(b);
  }
  function enable2FA(label) {
    var secret = randomSecretB32();
    try { root.localStorage.setItem(LS, secret); } catch (e) {}
    var otpauth = "otpauth://totp/" + encodeURIComponent("SOST DEX:" + (label || "wallet")) +
      "?secret=" + secret + "&issuer=SOST%20DEX&algorithm=SHA1&digits=6&period=30";
    return { secret: secret, otpauth: otpauth };
  }
  function disable2FA() { try { root.localStorage.removeItem(LS); } catch (e) {} }
  async function verify(code) {
    var s = get2FASecret(); if (!s) return true; // no 2FA set -> pass
    return verifyAt(s, code, Math.floor(Date.now() / 1000));
  }

  // ---- confirmation modal (browser) ----
  function confirmModal(opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      if (typeof document === "undefined") return resolve(true);
      var need2FA = opts.require2FA && is2FAEnabled();
      var bg = document.createElement("div");
      bg.setAttribute("style", "position:fixed;inset:0;background:rgba(2,4,8,.74);backdrop-filter:blur(3px);display:grid;place-items:center;z-index:120;padding:20px;font-family:'Space Grotesk',system-ui,sans-serif");
      bg.innerHTML =
        '<div role="dialog" aria-modal="true" style="width:100%;max-width:420px;background:#0D1117;border:1px solid #232f3d;border-radius:16px;padding:22px;color:#eef2f6;box-shadow:0 18px 48px -24px #000">' +
        '<div style="font-size:17px;font-weight:700;margin-bottom:6px">' + esc(opts.title || "Confirm sensitive action") + "</div>" +
        '<div style="font-size:13px;color:#a9b6c4;line-height:1.6;margin-bottom:14px">' + (opts.bodyHtml || esc(opts.body || "")) + "</div>" +
        '<label style="display:flex;gap:9px;align-items:flex-start;font-size:12.5px;color:#a9b6c4;cursor:pointer;margin-bottom:14px">' +
        '<input type="checkbox" id="sgAck" style="margin-top:2px"> <span>' + esc(opts.ack || "I understand and want to proceed.") + "</span></label>" +
        (need2FA ? '<div style="margin-bottom:14px"><div style="font-size:10.5px;letter-spacing:1px;text-transform:uppercase;color:#6d7d8e;margin-bottom:5px">Authenticator code</div>' +
          '<input id="sg2fa" inputmode="numeric" maxlength="6" placeholder="000000" style="width:100%;background:#10161f;border:1px solid #232f3d;color:#eef2f6;border-radius:8px;padding:10px 12px;font-family:JetBrains Mono,monospace;font-size:18px;letter-spacing:4px;text-align:center"></div>' : "") +
        '<div id="sgErr" style="color:#ff8a8a;font-size:12px;min-height:16px;margin-bottom:8px"></div>' +
        '<div style="display:flex;gap:10px">' +
        '<button id="sgCancel" style="flex:1;background:#10161f;border:1px solid #232f3d;color:#eef2f6;border-radius:9px;padding:11px;font-weight:600;cursor:pointer">Cancel</button>' +
        '<button id="sgOk" disabled style="flex:1;background:#FB010D;border:0;color:#fff;border-radius:9px;padding:11px;font-weight:700;cursor:pointer;opacity:.5">' + esc(opts.confirmText || "Confirm") + "</button>" +
        "</div></div>";
      document.body.appendChild(bg);
      var ack = bg.querySelector("#sgAck"), ok = bg.querySelector("#sgOk"), err = bg.querySelector("#sgErr"), f2 = bg.querySelector("#sg2fa");
      function refresh() { var good = ack.checked && (!need2FA || (f2 && /^\d{6}$/.test(f2.value))); ok.disabled = !good; ok.style.opacity = good ? "1" : ".5"; }
      ack.addEventListener("change", refresh); if (f2) f2.addEventListener("input", refresh);
      function close(v) { bg.remove(); resolve(v); }
      bg.querySelector("#sgCancel").addEventListener("click", function () { close(false); });
      bg.addEventListener("click", function (e) { if (e.target === bg) close(false); });
      ok.addEventListener("click", async function () {
        if (need2FA) { var okc = await verify(f2.value); if (!okc) { err.textContent = "Invalid authenticator code."; return; } }
        close(true);
      });
    });
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  // guard: run `fn` only after a confirmed (and, if enabled, 2FA-verified) sensitive action.
  async function guard(fn, opts) { var okc = await confirmModal(opts || {}); if (okc && typeof fn === "function") return fn(); return false; }

  var API = {
    // TOTP core (also unit-testable in node)
    b32encode: b32encode, b32decode: b32decode, totp: totp, verifyAt: verifyAt,
    // local 2FA
    is2FAEnabled: is2FAEnabled, enable2FA: enable2FA, disable2FA: disable2FA, verify: verify,
    // UI
    confirm: confirmModal, guard: guard
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (root) root.SOSTDexGate = API;
})(typeof self !== "undefined" ? self : this);
