// SOST CLI / miner wallet tools — crypto core (browser + Node).
//
// Reproduces EXACTLY the CLI wallet formats of src/wallet.cpp:
//   v1  Wallet::save()            plaintext keys
//   v2  Wallet::save_encrypted()  scrypt(N=32768,r=8,p=1, salt 32B) -> 32B key,
//                                 AES-256-GCM (IV 12B, tag 16B, no AAD) over
//                                 "privkey_hex:label\n" per key.
// Everything runs locally. This module never touches the network.
import { scryptAsync } from '@noble/hashes/scrypt';
import { sha256 } from '@noble/hashes/sha256';
import { ripemd160 } from '@noble/hashes/ripemd160';
import { getPublicKey } from '@noble/secp256k1';

export const V2_PARAMS = Object.freeze({ N: 32768, r: 8, p: 1, dkLen: 32, saltLen: 32, ivLen: 12, tagLen: 16 });
export const MIN_PASSPHRASE_BYTES = 8;                 // sost-cli wallet-export rule
const MAX_FILE_BYTES = 4 * 1024 * 1024;
const MAX_KEYS = 10000;
const HEX = /^[0-9a-f]*$/;
const enc = new TextEncoder();

export class WalletError extends Error {}
const fail = (m) => { throw new WalletError(m); };

export const toHex = (b) => Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
export function fromHex(h, len) {
  if (typeof h !== 'string' || !HEX.test(h) || h.length % 2) fail('invalid hex');
  if (len !== undefined && h.length !== len * 2) fail('invalid length');
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
}
function wipe(...bufs) { for (const b of bufs) if (b && b.fill) b.fill(0); }

export function addressFromPriv(priv) {
  const pub = getPublicKey(priv, true);
  return { pubkey: toHex(pub), address: 'sost1' + toHex(ripemd160(sha256(pub))) };
}

// Labels are written raw (unescaped) into the CLI JSON and the encrypted
// "priv:label\n" lines, so anything that would break either is refused.
export function passphraseProblem(p) {
  if (/[\r\n]/.test(p)) return 'passphrase must not contain line breaks';
  if (/^[ \t]|[ \t]$/.test(p)) return 'passphrase must not start or end with a space or tab (the miner passphrase file trims them)';
  return null;
}

export function labelOk(l) { return typeof l === 'string' && l.length <= 200 && !/["\\\n\r\u0000-\u001f\u007f]/.test(l); }

const isInt = (v) => Number.isSafeInteger(v);

function checkUtxos(u) {
  if (!Array.isArray(u)) fail('utxos must be an array');
  for (const x of u) {
    if (!x || typeof x !== 'object') fail('bad utxo');
    fromHex(x.txid, 32); fromHex(x.pkh, 20);
    if (!isInt(x.vout) || x.vout < 0 || !isInt(x.amount) || !isInt(x.output_type) || x.output_type < 0 || x.output_type > 255
        || !isInt(x.height) || typeof x.spent !== 'boolean') fail('bad utxo fields');
    if ('lock_until' in x && (!isInt(x.lock_until) || x.lock_until < 0)) fail('bad lock_until');
    if ('beneficiary' in x) fromHex(x.beneficiary, 20);
  }
}

/** Strict detection. Returns {format:'v1'|'v2', ...safe metadata}. Never returns private keys. */
export function inspectWallet(text) {
  if (typeof text !== 'string' || text.length === 0) fail('empty file');
  if (text.length > MAX_FILE_BYTES) fail('file too large');
  let j;
  try { j = JSON.parse(text); } catch { fail('not valid JSON'); }
  if (!j || typeof j !== 'object' || Array.isArray(j)) fail('not a wallet object');
  if (j.version === 1) {
    if (!Array.isArray(j.keys) || j.keys.length === 0 || j.keys.length > MAX_KEYS) fail('v1: missing keys');
    j.keys.forEach((k) => {
      if (!k || typeof k !== 'object') fail('v1: bad key');
      fromHex(k.privkey, 32); fromHex(k.pubkey, 33);
      if (typeof k.address !== 'string' || !/^sost1[0-9a-f]{40}$/.test(k.address)) fail('v1: bad address');
      if (!labelOk(k.label)) fail('v1: unsupported label characters');
    });
    checkUtxos(j.utxos ?? []);
    return { format: 'v1', encrypted: false, keys: j.keys.length, addresses: j.keys.map((k) => k.address), labels: j.keys.map((k) => k.label) };
  }
  if (j.version === 2) {
    if (j.encrypted !== true) fail('v2: encrypted flag missing');
    if (j.scrypt_N !== V2_PARAMS.N || j.scrypt_r !== V2_PARAMS.r || j.scrypt_p !== V2_PARAMS.p) fail('v2: unexpected KDF parameters');
    fromHex(j.salt, V2_PARAMS.saltLen); fromHex(j.iv, V2_PARAMS.ivLen); fromHex(j.tag, V2_PARAMS.tagLen);
    if (typeof j.keys_ct !== 'string' || j.keys_ct.length === 0) fail('v2: missing ciphertext');
    fromHex(j.keys_ct);
    if (!Array.isArray(j.addresses) || !j.addresses.every((a) => typeof a === 'string' && /^sost1[0-9a-f]{40}$/.test(a))) fail('v2: bad addresses');
    if (!isInt(j.num_addresses) || j.num_addresses !== j.addresses.length) fail('v2: address count mismatch');
    checkUtxos(j.utxos ?? []);
    return { format: 'v2', encrypted: true, keys: j.num_addresses, addresses_unverified: j.addresses };
  }
  fail('unsupported wallet version');
}

async function deriveKey(passphrase, salt) {
  const pw = enc.encode(passphrase);
  try {
    return await scryptAsync(pw, salt, { N: V2_PARAMS.N, r: V2_PARAMS.r, p: V2_PARAMS.p, dkLen: V2_PARAMS.dkLen });
  } finally { wipe(pw); }
}

function utxoText(u) {
  let s = '    {\n';
  s += `      "txid": "${u.txid}",\n      "vout": ${u.vout},\n      "amount": ${u.amount},\n`;
  s += `      "output_type": ${u.output_type},\n      "pkh": "${u.pkh}",\n      "height": ${u.height},\n`;
  s += `      "spent": ${u.spent ? 'true' : 'false'}`;
  if (u.lock_until > 0) {
    s += `,\n      "lock_until": ${u.lock_until}`;
    if (u.output_type === 0x11 && u.beneficiary) s += `,\n      "beneficiary": "${u.beneficiary}"`;   // OUT_ESCROW_LOCK
  }
  return s + '\n    }';
}

/** v1 text -> v2 text, byte-format identical to Wallet::save_encrypted(). */
export async function encryptV1(text, passphrase, rng = (n) => crypto.getRandomValues(new Uint8Array(n))) {
  const meta = inspectWallet(text);
  if (meta.format !== 'v1') fail('input is not a plaintext CLI v1 wallet');
  if (typeof passphrase !== 'string' || enc.encode(passphrase).length < MIN_PASSPHRASE_BYTES) fail('passphrase must be at least 8 characters');
  // sost-miner --wallet-passphrase-file trims trailing spaces/tabs/newlines and refuses
  // embedded newlines (src/secret_input.cpp); such a passphrase could never unlock the miner.
  if (passphraseProblem(passphrase)) fail(passphraseProblem(passphrase));
  const j = JSON.parse(text);
  // every key must be internally consistent before we encrypt it
  for (const k of j.keys) {
    const pk = fromHex(k.privkey, 32);
    const d = addressFromPriv(pk); wipe(pk);
    if (d.address !== k.address || d.pubkey !== k.pubkey) fail('v1: key/address mismatch — file is inconsistent, refusing to encrypt');
  }
  let plain = enc.encode(j.keys.map((k) => `${k.privkey}:${k.label}\n`).join(''));
  const salt = rng(V2_PARAMS.saltLen), iv = rng(V2_PARAMS.ivLen);
  const key = await deriveKey(passphrase, salt);
  let sealed;
  try {
    const ck = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['encrypt']);
    sealed = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv, tagLength: 128 }, ck, plain));
  } finally { wipe(key, plain); }
  const ct = sealed.slice(0, sealed.length - V2_PARAMS.tagLen), tag = sealed.slice(sealed.length - V2_PARAMS.tagLen);
  const utxos = j.utxos ?? [];
  let s = '{\n  "version": 2,\n  "encrypted": true,\n';
  s += `  "scrypt_N": ${V2_PARAMS.N},\n  "scrypt_r": ${V2_PARAMS.r},\n  "scrypt_p": ${V2_PARAMS.p},\n`;
  s += `  "salt": "${toHex(salt)}",\n  "iv": "${toHex(iv)}",\n  "tag": "${toHex(tag)}",\n  "keys_ct": "${toHex(ct)}",\n`;
  s += `  "num_addresses": ${j.keys.length},\n  "addresses": [\n`;
  s += j.keys.map((k, i) => `    "${k.address}"${i + 1 < j.keys.length ? ',' : ''}\n`).join('');
  s += '  ],\n  "utxos": [\n';
  s += utxos.map(utxoText).join(',\n') + (utxos.length ? '\n' : '');
  s += '  ]\n}\n';
  wipe(sealed);
  return s;
}

/** Decrypt a v2 wallet locally and return ONLY public data (addresses derived from the decrypted keys). */
export async function verifyV2(text, passphrase) {
  const meta = inspectWallet(text);
  if (meta.format !== 'v2') fail('input is not an encrypted CLI v2 wallet');
  if (typeof passphrase !== 'string' || passphrase.length === 0) fail('passphrase required');
  const j = JSON.parse(text);
  const salt = fromHex(j.salt), iv = fromHex(j.iv), tag = fromHex(j.tag), ct = fromHex(j.keys_ct);
  const sealed = new Uint8Array(ct.length + tag.length); sealed.set(ct); sealed.set(tag, ct.length);
  const key = await deriveKey(passphrase, salt);
  let plain;
  try {
    const ck = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['decrypt']);
    plain = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv, tagLength: 128 }, ck, sealed));
  } catch { fail('decryption failed — wrong passphrase or corrupted file'); }
  finally { wipe(key, sealed); }
  const out = [];
  try {
    for (const line of new TextDecoder().decode(plain).split('\n')) {
      if (!line) continue;
      const c = line.indexOf(':');
      const ph = c >= 0 ? line.slice(0, c) : line, label = c >= 0 ? line.slice(c + 1) : '';
      const pk = fromHex(ph, 32);
      out.push({ address: addressFromPriv(pk).address, label }); wipe(pk);
    }
  } finally { wipe(plain); }
  const listed = j.addresses;
  return {
    format: 'v2', cipher: 'AES-256-GCM', kdf: `scrypt N=${j.scrypt_N} r=${j.scrypt_r} p=${j.scrypt_p}`,
    keys: out,
    // the public address list is not authenticated by the file; flag any disagreement
    addressListMatches: listed.length === out.length && listed.every((a, i) => a === out[i].address),
  };
}

export function checkExpected(found, expected) {
  const e = (expected || '').trim().toLowerCase();
  return e ? found.some((k) => k.address === e) : null;
}
