// tests/beacon_cross_verify.mjs
//
// Node harness: load the SAME beacon.js the browser loads, drive its
// verifyNotice() and canonicalize() exports against fixtures produced by
// the shell scripts. Reports PASS/FAIL line by line; exits non-zero on any
// failure. Designed to be invoked by tests/beacon_cross_verify_test.sh
// after generating keys and signing notices on disk.
//
// Args:
//   process.argv[2] = pubkey hex (uncompressed, 65 bytes)
//   process.argv[3] = path to a valid signed notice JSON
//   process.argv[4] = path to the canonical payload that produced the signature
//                     (signed.json with the signature field stripped, in
//                      compact-sorted form — typically built by
//                      `jq -cS 'del(.signature)' signed.json`).

import { readFileSync } from 'node:fs';
import { argv, exit } from 'node:process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const beaconUrl = 'file://' + resolve(here, '../website/js/beacon.js');
const { verifyNotice, canonicalize } = await import(beaconUrl);

const [, , PUBKEY_HEX, SIGNED_PATH, CANON_REF_PATH] = argv;
if (!PUBKEY_HEX || !SIGNED_PATH || !CANON_REF_PATH) {
    console.error('usage: beacon_cross_verify.mjs <pubkey_hex> <signed.json> <canonical_ref>');
    exit(64);
}

let pass = 0, fail = 0;
const ok   = msg => { console.log('  PASS — ' + msg); pass++; };
const bad  = msg => { console.log('  FAIL — ' + msg); fail++; };

const signed = JSON.parse(readFileSync(SIGNED_PATH, 'utf8'));

// Test A — canonicalize() matches `jq -cS` byte-for-byte.
{
    const ref = readFileSync(CANON_REF_PATH, 'utf8').replace(/\n$/, '');
    const { signature: _drop, ...payload } = signed;
    const canon = canonicalize(payload);
    if (canon === ref) ok('canonicalize() matches jq -cS exactly');
    else {
        bad('canonicalize() mismatch with jq -cS');
        console.error('    expected: ' + ref);
        console.error('    actual:   ' + canon);
    }
}

// Test B — valid signature accepted by JS path.
{
    const verdict = await verifyNotice(signed, PUBKEY_HEX);
    if (verdict) ok('shell-signed notice accepted by JS verifyNotice');
    else         bad('shell-signed notice REJECTED by JS verifyNotice (CRITICAL: paths diverge)');
}

// Test C — tampered message rejected.
{
    const tampered = { ...signed, message_en: 'TAMPERED — download evil binary from attacker.com' };
    const verdict = await verifyNotice(tampered, PUBKEY_HEX);
    if (!verdict) ok('tampered message rejected by JS');
    else          bad('tampered message ACCEPTED (CRITICAL: signature does not bind payload in JS)');
}

// Test D — wrong pubkey rejected (flip a single byte of the hex).
{
    const flipped = PUBKEY_HEX.slice(0, -2) + (PUBKEY_HEX.slice(-2) === 'aa' ? 'bb' : 'aa');
    const verdict = await verifyNotice(signed, flipped);
    if (!verdict) ok('wrong pubkey rejected by JS');
    else          bad('wrong pubkey ACCEPTED (CRITICAL: any-key bypass in JS)');
}

// Test E — empty signature rejected.
{
    const stripped = { ...signed, signature: '' };
    const verdict = await verifyNotice(stripped, PUBKEY_HEX);
    if (!verdict) ok('empty signature rejected by JS');
    else          bad('empty signature ACCEPTED (CRITICAL: empty-sig bypass in JS)');
}

// Test F — garbage base64 rejected.
{
    const garbage = { ...signed, signature: 'not-valid-base64!!!' };
    const verdict = await verifyNotice(garbage, PUBKEY_HEX);
    if (!verdict) ok('garbage signature rejected by JS');
    else          bad('garbage signature ACCEPTED');
}

// Test G — missing required field rejected.
{
    const { commands: _drop, ...incomplete } = signed;
    const verdict = await verifyNotice(incomplete, PUBKEY_HEX);
    if (!verdict) ok('notice with missing required field rejected');
    else          bad('notice with missing field ACCEPTED');
}

console.log(`\nTests passed: ${pass}\nTests failed: ${fail}`);
exit(fail === 0 ? 0 : 1);
