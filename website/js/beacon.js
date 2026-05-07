// website/js/beacon.js
//
// SOST Beacon Phase 1 — explorer banner.
//
// Fetches /api/notices.json, verifies ECDSA-SHA256 signatures using the
// vendored, hash-pinned noble-secp256k1, and renders an info banner only
// when at least one notice has a valid signature AND is currently active.
//
// HARD INVARIANTS (do not relax without re-review):
//   - Public key is hardcoded in BEACON_PUBKEY_HEX. Never read from a file.
//   - secp256k1 library is imported from website/vendor/. Never from a CDN.
//   - All errors are caught. Any failure mode → no banner.
//   - This file does NOT touch consensus, mining, node, or RPC paths.
//   - This file does NOT block page rendering, navigation, or interaction.
//
// The browser-side verification path is byte-for-byte identical to the
// shell `beacon-verify.sh` path:
//   canonical_payload = jq -cS over (notice minus the signature field)
//   signature         = base64( ECDSA-SHA256(canonical_payload, priv) ) DER
// In JS, `canonicalize()` reproduces `jq -cS` ordering, and the DER
// signature is parsed into the 64-byte compact form noble expects.

import { verify, etc } from '../vendor/noble-secp256k1-2.2.3.js';

// -----------------------------------------------------------------------------
// HARDCODED Beacon public key (uncompressed, 65 bytes hex).
// Replace with the real operator pubkey produced by `scripts/beacon-keygen.sh`
// before deploying to production. The placeholder below is a syntactically
// valid but obviously fake point — verification with this key will reject
// every signature, which is the safe default for a freshly cloned tree.
// -----------------------------------------------------------------------------
export const BEACON_PUBKEY_HEX =
    '04' +
    '0000000000000000000000000000000000000000000000000000000000000001' +
    'b7c52588d95c3b9aa25b0403f1eef75702e84bb7597aabe663b82f6f04ef2777';

// Operational caps — defensive against runaway downloads or oversized data.
const NOTICE_FETCH_TIMEOUT_MS = 5000;
const NOTICE_FETCH_MAX_BYTES  = 256 * 1024;       // 256 KB; real notices are <2 KB
const REQUIRED_FIELDS = [
    'notice_id', 'network', 'severity',
    'title_en', 'message_en',
    'activation_height', 'expires_height',
    'created_at', 'commands', 'signature',
];

// -----------------------------------------------------------------------------
// canonicalize — reproduce `jq -cS` byte-for-byte for the schemas we sign.
// Sorts object keys lexicographically (recursively), no whitespace, compact.
// Beacon notices contain only string / integer / array-of-string values, all
// well-defined under JSON.stringify on modern engines.
// -----------------------------------------------------------------------------
export function canonicalize(value) {
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return '[' + value.map(canonicalize).join(',') + ']';
    }
    const keys = Object.keys(value).sort();
    const parts = keys.map(k => JSON.stringify(k) + ':' + canonicalize(value[k]));
    return '{' + parts.join(',') + '}';
}

// -----------------------------------------------------------------------------
// derToCompact — parse the standard ECDSA DER encoding produced by
// `openssl dgst -sign` into the 64-byte (r||s) compact form noble expects.
// Throws on any malformed input; callers must catch.
// -----------------------------------------------------------------------------
export function derToCompact(der) {
    if (!(der instanceof Uint8Array)) throw new Error('der: expected Uint8Array');
    let i = 0;
    if (der[i++] !== 0x30) throw new Error('der: expected SEQUENCE');
    let seqLen = der[i++];
    if (seqLen & 0x80) {
        const lenBytes = seqLen & 0x7f;
        if (lenBytes < 1 || lenBytes > 2) throw new Error('der: bad length');
        seqLen = 0;
        for (let j = 0; j < lenBytes; j++) seqLen = (seqLen << 8) | der[i++];
    }
    if (i + seqLen !== der.length) throw new Error('der: length mismatch');
    const readInt = () => {
        if (der[i++] !== 0x02) throw new Error('der: expected INTEGER');
        const len = der[i++];
        if (len & 0x80) throw new Error('der: long-form integer not allowed');
        const start = i;
        i += len;
        let bytes = der.slice(start, start + len);
        // Strip the optional leading 0x00 used to mark positivity.
        if (bytes.length > 1 && bytes[0] === 0x00 && (bytes[1] & 0x80)) bytes = bytes.slice(1);
        if (bytes.length > 32) throw new Error('der: integer > 32 bytes');
        const padded = new Uint8Array(32);
        padded.set(bytes, 32 - bytes.length);
        return padded;
    };
    const r = readInt();
    const s = readInt();
    if (i !== der.length) throw new Error('der: trailing bytes');
    const out = new Uint8Array(64);
    out.set(r, 0);
    out.set(s, 32);
    return out;
}

// -----------------------------------------------------------------------------
// base64 → Uint8Array (browser-friendly, no Buffer dependency).
// -----------------------------------------------------------------------------
function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
}

// -----------------------------------------------------------------------------
// sha256 (WebCrypto). Returns Uint8Array(32).
// -----------------------------------------------------------------------------
async function sha256(bytes) {
    const buf = await crypto.subtle.digest('SHA-256', bytes);
    return new Uint8Array(buf);
}

// -----------------------------------------------------------------------------
// validateSchema — reject any object missing fields, with wrong types, or
// with a signature mismatch is left to verifyNotice (this only checks shape).
// -----------------------------------------------------------------------------
function validateSchema(obj) {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return false;
    for (const k of REQUIRED_FIELDS) {
        if (!Object.prototype.hasOwnProperty.call(obj, k)) return false;
    }
    if (typeof obj.notice_id !== 'string' || obj.notice_id.length === 0) return false;
    if (typeof obj.network   !== 'string') return false;
    if (typeof obj.severity  !== 'string') return false;
    if (typeof obj.title_en  !== 'string') return false;
    if (typeof obj.message_en !== 'string') return false;
    if (!Number.isInteger(obj.activation_height)) return false;
    if (!Number.isInteger(obj.expires_height))    return false;
    if (typeof obj.created_at !== 'string')       return false;
    if (!Array.isArray(obj.commands))             return false;
    if (typeof obj.signature !== 'string' || obj.signature.length === 0) return false;
    return true;
}

// -----------------------------------------------------------------------------
// verifyNotice — single-notice verification. Returns true only when the
// signature is well-formed AND matches the canonical payload under the
// configured public key. ANY failure path returns false silently.
// -----------------------------------------------------------------------------
export async function verifyNotice(notice, pubkeyHex = BEACON_PUBKEY_HEX) {
    try {
        if (!validateSchema(notice)) return false;
        const sigDer = b64ToBytes(notice.signature);
        const sigCompact = derToCompact(sigDer);
        const { signature: _drop, ...payload } = notice;
        const canon = canonicalize(payload);
        const msgBytes = new TextEncoder().encode(canon);
        const msgHash = await sha256(msgBytes);
        const pubBytes = etc.hexToBytes(pubkeyHex);
        // lowS: false — openssl produces both low- and high-S signatures and
        // does not normalise. Beacon uses a single pinned pubkey, so signature
        // malleability is irrelevant; what matters is authenticity, which both
        // forms preserve. Setting lowS strict here would reject ~half of the
        // valid signatures emitted by `beacon-sign.sh`.
        return verify(sigCompact, msgHash, pubBytes, { lowS: false });
    } catch (_e) {
        return false;
    }
}

// -----------------------------------------------------------------------------
// fetchNotices — bounded fetch with timeout + size cap. Returns [] on any
// failure. Never throws.
// -----------------------------------------------------------------------------
async function fetchNotices(url) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), NOTICE_FETCH_TIMEOUT_MS);
    try {
        const resp = await fetch(url, { signal: ctl.signal, cache: 'no-store' });
        if (!resp.ok) return [];
        const cl = parseInt(resp.headers.get('content-length') || '0', 10);
        if (cl && cl > NOTICE_FETCH_MAX_BYTES) return [];
        const text = await resp.text();
        if (text.length > NOTICE_FETCH_MAX_BYTES) return [];
        const parsed = JSON.parse(text);
        if (!Array.isArray(parsed)) return [];
        return parsed;
    } catch (_e) {
        return [];
    } finally {
        clearTimeout(timer);
    }
}

// -----------------------------------------------------------------------------
// renderBanner — minimal DOM injection. Idempotent. Safe to call repeatedly.
// -----------------------------------------------------------------------------
function renderBanner(notices) {
    if (!notices.length) return;
    const id = 'sost-beacon-banner';
    let host = document.getElementById(id);
    if (!host) {
        host = document.createElement('div');
        host.id = id;
        host.style.cssText = [
            'position:relative',
            'margin:0',
            'padding:10px 16px',
            'background:#1a0d00',
            'border-bottom:1px solid #ff8800',
            'color:#ffb86b',
            'font-family:monospace',
            'font-size:13px',
            'z-index:10',
        ].join(';');
        document.body.insertBefore(host, document.body.firstChild);
    }
    host.replaceChildren();
    for (const n of notices) {
        const row = document.createElement('div');
        row.style.cssText = 'padding:4px 0';
        const sev = (n.severity || 'info').toUpperCase();
        const title = document.createElement('span');
        title.textContent = `[BEACON ${sev}] ${n.title_en}`;
        title.style.cssText = 'font-weight:600;color:#ff8800';
        const msg = document.createElement('span');
        msg.textContent = ' — ' + n.message_en;
        msg.style.cssText = 'color:#ffb86b';
        row.appendChild(title);
        row.appendChild(msg);
        host.appendChild(row);
    }
}

// -----------------------------------------------------------------------------
// currentChainHeight — best-effort read from the explorer's existing global
// state. Returns null when unavailable, which means "skip height filter".
// We deliberately do NOT make a fresh RPC call; the explorer already has
// recent height data, and a missing value should never disable banners.
// -----------------------------------------------------------------------------
function currentChainHeight() {
    try {
        const h = window.__SOST_TIP_HEIGHT__;
        if (typeof h === 'number' && Number.isFinite(h) && h >= 0) return h;
    } catch (_e) { /* ignore */ }
    return null;
}

// -----------------------------------------------------------------------------
// run — public entry point. Always async, always silent on failure.
// -----------------------------------------------------------------------------
export async function run({
    url = '/api/notices.json',
    pubkeyHex = BEACON_PUBKEY_HEX,
} = {}) {
    try {
        const notices = await fetchNotices(url);
        if (!notices.length) return;
        const tip = currentChainHeight();
        const verified = [];
        for (const n of notices) {
            const ok = await verifyNotice(n, pubkeyHex);
            if (!ok) continue;
            if (tip !== null) {
                if (n.activation_height > tip) continue;
                if (n.expires_height <= tip)   continue;
            }
            verified.push(n);
        }
        if (verified.length) renderBanner(verified);
    } catch (_e) {
        // Fail silent. Beacon must never break the page.
    }
}

// Auto-run on import in browser context. Tests / Node consumers can import
// `run`, `verifyNotice`, etc. directly without triggering the auto-run.
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => { run(); });
    } else {
        run();
    }
}
