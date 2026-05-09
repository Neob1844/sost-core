#!/usr/bin/env node
//
// sealed_envelope_vectors.mjs — cross-language sealed-envelope test
// (Fase Sealed-1.C-2). Runs the C++ fixture
// (build-phase2/sealed-envelope-fixture), parses its key=value dump, and
// reproduces every envelope using only Node's built-in `crypto` module.
//
// PASS criterion: for every vector,
//
//     hex(JS-built envelope) === envelope_hex from C++
//
// byte-for-byte. Anything else means the JS implementation cannot
// produce envelopes the C++ side will accept; sealed broadcast must
// stay disabled in the wallet UI.
//
// Why Node's built-in crypto and not noble-secp256k1:
//   * crypto.createECDH('secp256k1').computeSecret() returns the raw
//     x-coordinate of the shared point (32 bytes), with no parity-byte
//     prefix and no hash. That gives us full control over the
//     "SHA256(0x02 || x)" formula libsecp256k1 hard-codes.
//   * noble-secp256k1.getSharedSecret returns the compressed point with
//     the REAL parity byte (0x02 or 0x03 depending on y), not always
//     0x02. Hashing that directly diverges from libsecp256k1 ~50% of
//     the time. To make noble compatible, the wallet code must extract
//     bytes 1..33 (x-coord only) and prepend 0x02 manually — exactly
//     the path mirrored here. The wallet wiring lands in the SAME PR
//     once these vectors pass.

import { createECDH, createHash, createHmac, createCipheriv,
         createDecipheriv, randomBytes } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_BIN = resolve(__dirname,
    '../build-phase2/sealed-envelope-fixture');

const DOMAIN_SEP_V1 = Buffer.from('SOST_CAPSULE_SEALED_V1', 'utf8');

// ---------------- helpers ----------------

function fromHex(s)  { return Buffer.from(s, 'hex'); }
function toHex(buf)  { return Buffer.from(buf).toString('hex'); }

function sha256(buf) {
  return createHash('sha256').update(buf).digest();
}

// HKDF-SHA256 (RFC 5869), L <= 32 bytes (one expand round suffices).
function hkdfSha256(ikm, salt, info, length) {
  if (length > 32) throw new Error('this helper assumes L <= 32');
  const prk = createHmac('sha256', salt).update(ikm).digest();
  const t1  = createHmac('sha256', prk)
                .update(Buffer.concat([info, Buffer.from([0x01])]))
                .digest();
  return t1.subarray(0, length);
}

// libsecp256k1-compatible ECDH: shared_secret = SHA256(0x02 || x_shared).
// Node gives us the raw x bytes; we only have to prepend 0x02.
function libsecpEcdh(privBuf32, pubBuf33) {
  const ecdh = createECDH('secp256k1');
  ecdh.setPrivateKey(privBuf32);
  const xRaw = ecdh.computeSecret(pubBuf33);  // 32 bytes
  if (xRaw.length !== 32) throw new Error('unexpected ECDH x length');
  const hashInput = Buffer.concat([Buffer.from([0x02]), xRaw]);
  return sha256(hashInput);
}

function compressedPubFromPriv(priv32) {
  const ecdh = createECDH('secp256k1');
  ecdh.setPrivateKey(priv32);
  // getPublicKey('binary', 'compressed') returns 33 bytes.
  return ecdh.getPublicKey(null, 'compressed');
}

function aesGcmSeal(key, nonce, aad, plaintext) {
  const c = createCipheriv('aes-256-gcm', key, nonce);
  c.setAAD(aad, { plaintextLength: plaintext.length });
  const ct = Buffer.concat([c.update(plaintext), c.final()]);
  const tag = c.getAuthTag();
  return { ct, tag };
}

function aesGcmOpen(key, nonce, aad, ct, tag) {
  const d = createDecipheriv('aes-256-gcm', key, nonce);
  d.setAAD(aad, { plaintextLength: ct.length });
  d.setAuthTag(tag);
  const pt = Buffer.concat([d.update(ct), d.final()]);
  return pt;
}

// Build an envelope deterministically from fixed seeds. Mirrors the
// C++ SealSingleRecipientWithSeeds layout byte-for-byte.
function sealWithSeeds({ plaintext, ephPriv, recipientPub, recipientPkh, nonce }) {
  if (recipientPub.length !== 33) throw new Error('recipient pub must be 33 B');
  if (ephPriv.length      !== 32) throw new Error('eph priv must be 32 B');
  if (recipientPkh.length !== 20) throw new Error('recipient pkh must be 20 B');
  if (nonce.length        !== 12) throw new Error('nonce must be 12 B');

  const ephPub = compressedPubFromPriv(ephPriv);                // 33 B
  const shared = libsecpEcdh(ephPriv, recipientPub);            // 32 B
  const aesKey = hkdfSha256(shared, ephPub, DOMAIN_SEP_V1, 32); // 32 B

  const ctLen = plaintext.length;
  const aad = Buffer.concat([
    Buffer.from([0x01, 0x01]),    // version, recipient_count
    recipientPkh,                  // 20 B
    ephPub,                        // 33 B
    nonce,                         // 12 B
    Buffer.from([ctLen & 0xff, (ctLen >> 8) & 0xff]),  // u16 LE
  ]);
  if (aad.length !== 69) throw new Error('AAD length should be 69');

  const { ct, tag } = aesGcmSeal(aesKey, nonce, aad, plaintext);
  return Buffer.concat([aad, ct, tag]);
}

// Open an envelope using the recipient privkey. Mirrors C++ OpenSingleRecipient.
function openEnvelope(envelope, recipientPriv) {
  if (envelope.length < 85) throw new Error('envelope truncated');
  if (envelope[0] !== 0x01) throw new Error('bad envelope version');
  if (envelope[1] !== 0x01) throw new Error('multi-recipient not supported');
  const pkhHint = envelope.subarray(2, 22);
  const ephPub  = envelope.subarray(22, 55);
  const nonce   = envelope.subarray(55, 67);
  const ctLen   = envelope[67] | (envelope[68] << 8);
  if (85 + ctLen !== envelope.length)
    throw new Error('envelope length / ct_len mismatch');
  // Cheap pkh-hint short-circuit (no ECDH wasted on envelopes addressed
  // to someone else).
  const ourPub = compressedPubFromPriv(recipientPriv);
  const ourPkh = hash160(ourPub);
  if (!ourPkh.equals(pkhHint))
    throw new Error('not addressed to this key');
  const shared = libsecpEcdh(recipientPriv, ephPub);
  const aesKey = hkdfSha256(shared, ephPub, DOMAIN_SEP_V1, 32);
  const aad = envelope.subarray(0, 69);
  const ct  = envelope.subarray(69, 69 + ctLen);
  const tag = envelope.subarray(69 + ctLen);
  return aesGcmOpen(aesKey, nonce, aad, ct, tag);
}

// ripemd160(sha256(buf))
function hash160(buf) {
  const a = sha256(buf);
  // Node 18+ supports the 'ripemd160' digest name in createHash.
  return createHash('ripemd160').update(a).digest();
}

// ---------------- harness ----------------

function parseFixture(stdout) {
  const out = [];
  let cur = null;
  for (const line of stdout.split(/\r?\n/)) {
    const m = line.match(/^---- (.*) ----$/);
    if (m) { if (cur) out.push(cur); cur = { label: m[1] }; continue; }
    if (!cur) continue;
    const kv = line.match(/^([a-z_]+)=(.*)$/);
    if (kv) cur[kv[1]] = kv[2];
  }
  if (cur) out.push(cur);
  return out;
}

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { console.log(`  PASS: ${name}`); pass++; }
  else      { console.log(`  *** FAIL: ${name}${extra ? '  ' + extra : ''}`); fail++; }
}

function runVector(v) {
  console.log(`\n=== Vector ${v.label} ===`);
  const plaintext   = fromHex(v.plaintext_hex);
  const recPriv     = fromHex(v.recipient_priv_hex);
  const recPub      = fromHex(v.recipient_pub_hex);
  const recPkh      = fromHex(v.recipient_pkh_hex);
  const ephPriv     = fromHex(v.eph_priv_hex);
  const expEphPub   = fromHex(v.eph_pub_hex);
  const nonce       = fromHex(v.nonce_hex);
  const expEnv      = fromHex(v.envelope_hex);

  // 1. Pubkey derivation: ourPub(eph_priv) must match the C++ eph_pub.
  const jsEphPub = compressedPubFromPriv(ephPriv);
  check('JS eph_pub == C++ eph_pub',
        jsEphPub.equals(expEphPub),
        `\n        js  ${toHex(jsEphPub)}\n        cpp ${toHex(expEphPub)}`);

  // 2. hash160(recipient_pub) == recipient_pkh from C++ (consistency).
  check('JS hash160(recipient_pub) == C++ recipient_pkh',
        hash160(recPub).equals(recPkh));

  // 3. Build the envelope from the same seeds and compare hex.
  const jsEnv = sealWithSeeds({
    plaintext, ephPriv,
    recipientPub: recPub, recipientPkh: recPkh, nonce,
  });
  check('JS envelope hex == C++ envelope hex',
        jsEnv.equals(expEnv),
        `\n        js  ${toHex(jsEnv)}\n        cpp ${toHex(expEnv)}`);

  // 4. Open the C++ envelope with the recipient priv → recover plaintext.
  try {
    const recovered = openEnvelope(expEnv, recPriv);
    check('JS opens C++ envelope and recovers plaintext',
          recovered.equals(plaintext));
  } catch (e) {
    check('JS opens C++ envelope and recovers plaintext', false,
          `(threw: ${e.message})`);
  }

  // 5. Wrong key cannot open.
  const otherPriv = randomBytes(32);
  // make sure it's a valid privkey (probability ~1)
  let opened = false;
  try {
    openEnvelope(expEnv, otherPriv);
    opened = true;
  } catch { opened = false; }
  check('Random privkey CANNOT open the envelope', !opened);

  // 6. Tamper detection: flip one ciphertext byte.
  const tampered = Buffer.from(expEnv);
  tampered[70] ^= 0x01;     // ciphertext byte 1
  let tamperOpened = false;
  try {
    openEnvelope(tampered, recPriv);
    tamperOpened = true;
  } catch { tamperOpened = false; }
  check('Tampered ciphertext is rejected', !tamperOpened);
}

// ---------------- main ----------------

if (!existsSync(FIXTURE_BIN)) {
  console.error(`fixture binary not found: ${FIXTURE_BIN}`);
  console.error('build it first:  cmake --build build-phase2 --target sealed-envelope-fixture');
  process.exit(2);
}

const stdout = execFileSync(FIXTURE_BIN, [], { encoding: 'utf8' });
const vectors = parseFixture(stdout);
if (vectors.length === 0) { console.error('no vectors parsed'); process.exit(2); }

console.log(`Parsed ${vectors.length} vectors from C++ fixture.`);
for (const v of vectors) runVector(v);

console.log(`\n=== Summary: ${pass} passed, ${fail} failed ===`);
process.exit(fail === 0 ? 0 : 1);
