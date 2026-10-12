// Cross-implementation matrix: web crypto core  <->  release sost-cli / sost-miner.
// TEST-ONLY throwaway wallets in a temp dir. No funded key, no mainnet mining.
//   node tests/web/cli_tools_compat.mjs <release_dir>
import { spawnSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import * as W from '../../tools/web/cli-tools/dist/core.node.mjs';

const REL = process.argv[2];
const CLI = path.join(REL, 'sost-cli'), MINER = path.join(REL, 'sost-miner');
const GENESIS = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../genesis_block.json');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sost-clitools-'));
fs.chmodSync(tmp, 0o700);
const PASS = 'correct horse battery 9';
let n = 0, ok = 0;
const step = (name, cond, detail = '') => { n++; if (cond) ok++; console.log(`[${cond ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`); };
const cli = (wallet, args, pass) => spawnSync(CLI, ['--wallet', wallet, ...args, ...(pass !== undefined ? ['--passphrase-fd', '3'] : [])],
  { stdio: ['ignore', 'pipe', 'pipe', 'pipe'], input: undefined, encoding: 'utf8', ...(pass !== undefined ? { stdio: ['ignore', 'pipe', 'pipe', 'pipe'] } : {}) });
function cliWithFd(wallet, args, pass) {
  // feed the passphrase on fd 3 (never on argv / env)
  const r = spawnSync('bash', ['-c', `exec 3<"$P"; exec "$0" "$@"`, CLI, '--wallet', wallet, ...args, '--passphrase-fd', '3'],
                      { env: { P: writeSecret(pass), PATH: process.env.PATH }, encoding: 'utf8' });
  return r;
}
function writeSecret(s) { const f = path.join(tmp, 'p' + Math.random().toString(16).slice(2)); fs.writeFileSync(f, s + '\n', { mode: 0o600 }); return f; }
const expectThrow = async (fn) => { try { await fn(); return null; } catch (e) { return e.message; } };

// ---- test wallet (v1) made by the real CLI, two keys, one labelled for mining
const v1 = path.join(tmp, 'test.json');
spawnSync(CLI, ['--wallet', v1, 'newwallet'], { encoding: 'utf8' });
spawnSync(CLI, ['--wallet', v1, 'getnewaddress', 'MINING TEST'], { encoding: 'utf8' });
const v1text = fs.readFileSync(v1, 'utf8');
const meta = W.inspectWallet(v1text);
const addrs = JSON.parse(v1text).keys.map((k) => k.address);
step('V1_IMPORT: real CLI v1 detected', meta.format === 'v1' && meta.keys === 2, `${meta.keys} keys, labels ${JSON.stringify(meta.labels)}`);

// ---- A: web encrypt -> CLI opens
const webv2 = path.join(tmp, 'test.web.v2.json');
fs.writeFileSync(webv2, await W.encryptV1(v1text, PASS), { mode: 0o600 });
const back = path.join(tmp, 'back-from-web.json');
spawnSync(CLI, ['--wallet', back, 'newwallet'], { encoding: 'utf8' });          // import target must exist; it is overwritten
let r = cliWithFd(back, ['wallet-import', '--encrypted', '--input', webv2], PASS);
const backKeys = r.status === 0 ? JSON.parse(fs.readFileSync(back, 'utf8')).keys : [];
step('A: CLI_OPENS_WEB_V2 (release sost-cli wallet-import)', r.status === 0
     && JSON.stringify(backKeys.map((k) => [k.address, k.label, k.privkey])) === JSON.stringify(JSON.parse(v1text).keys.map((k) => [k.address, k.label, k.privkey])),
     r.status === 0 ? 'same keys, labels and addresses' : r.stderr.trim());
const xw = path.join(tmp, 'x.json'); spawnSync(CLI, ['--wallet', xw, 'newwallet'], { encoding: 'utf8' });
r = cliWithFd(xw, ['wallet-import', '--encrypted', '--input', webv2], 'wrong passphrase!!');
step('A2: CLI rejects web v2 with wrong passphrase', r.status !== 0 && /decryption failed/.test(r.stderr), r.stderr.trim().slice(0, 80));

// ---- B: CLI encrypt -> web opens
const cliv2 = path.join(tmp, 'test.cli.v2.json');
r = cliWithFd(v1, ['wallet-export', '--encrypted', '--output', cliv2], PASS);
const cliText = fs.readFileSync(cliv2, 'utf8');
const ver = await W.verifyV2(cliText, PASS);
step('B: CLI_V2_OPENS_IN_WEB', r.status === 0 && JSON.stringify(ver.keys.map((k) => k.address)) === JSON.stringify(addrs) && ver.addressListMatches,
     ver.keys.map((k) => `${k.address.slice(0, 14)}…(${k.label})`).join(', '));
// format shape identical (only random salt/iv/tag/ct differ)
const strip = (t) => t.replace(/"(salt|iv|tag|keys_ct)": "[0-9a-f]+"/g, '"$1": "*"');
step('B2: web v2 file layout byte-identical to CLI v2 (except random fields)', strip(cliText) === strip(fs.readFileSync(webv2, 'utf8')));

// ---- C: miner opens web v2 (no node: --rpc points at a closed port; we only read its startup lines)
const pf = writeSecret(PASS);
// run under a pty (script) so the miner's stdout is line-buffered
const q = (a) => `'${a.replace(/'/g, `'\\''`)}'`;
const mcmd = [MINER, '--profile', 'dev', '--genesis', GENESIS, '--wallet', webv2, '--wallet-passphrase-file', pf,
              '--mining-key-label', 'MINING TEST', '--rpc', '127.0.0.1:9', '--blocks', '1', '--threads', '1'].map(q).join(' ');
const mp = spawn('script', ['-qfc', `timeout 10 ${mcmd}`, '/dev/null'], { stdio: ['ignore', 'pipe', 'pipe'] });
let mout = '';
mp.stdout.on('data', (d) => { mout += d; }); mp.stderr.on('data', (d) => { mout += d; });
await new Promise((res) => { const t = setTimeout(res, 15000); mp.on('exit', () => { clearTimeout(t); res(); }); });
if (mp.exitCode === null) mp.kill('SIGTERM');
fs.writeFileSync(path.join(os.tmpdir(), 'clitools-miner-out.txt'), mout.replace(PASS, '<PASS>'));
const mined = (mout.match(/Miner address: (sost1[0-9a-f]{40})/) || [])[1];
step('C: MINER_OPENS_WEB_V2 (release sost-miner, label "MINING TEST")', mined === addrs[1] && /label='MINING TEST'/.test(mout),
     `miner address ${mined}`);
step('C2: miner never printed the passphrase', !mout.includes(PASS));

// ---- D..H: failures
const v2 = JSON.parse(cliText);
const mutate = (f) => { const o = JSON.parse(cliText); f(o); return JSON.stringify(o); };
const flip = (h) => (h[0] === '0' ? '1' : '0') + h.slice(1);
step('D: wrong passphrase fails cleanly', /decryption failed/.test(await expectThrow(() => W.verifyV2(cliText, 'not the passphrase'))));
step('E: modified ciphertext fails (GCM auth)', /decryption failed/.test(await expectThrow(() => W.verifyV2(mutate((o) => { o.keys_ct = flip(o.keys_ct); }), PASS))));
step('F: modified tag fails', /decryption failed/.test(await expectThrow(() => W.verifyV2(mutate((o) => { o.tag = flip(o.tag); }), PASS))));
step('G1: modified salt fails', /decryption failed/.test(await expectThrow(() => W.verifyV2(mutate((o) => { o.salt = flip(o.salt); }), PASS))));
step('G2: modified IV fails', /decryption failed/.test(await expectThrow(() => W.verifyV2(mutate((o) => { o.iv = flip(o.iv); }), PASS))));
step('G3: weakened KDF params refused', /unexpected KDF/.test(await expectThrow(() => W.verifyV2(mutate((o) => { o.scrypt_N = 1024; }), PASS))));
step('H1: truncated JSON refused', /not valid JSON/.test(await expectThrow(() => W.verifyV2(cliText.slice(0, cliText.length / 2), PASS))));
step('H2: arbitrary JSON refused', /unsupported wallet version/.test(await expectThrow(() => W.verifyV2('{"hello":1}', PASS))));
step('H3: forged public address list is flagged', (await W.verifyV2(mutate((o) => { o.addresses[0] = 'sost1' + '0'.repeat(40); }), PASS)).addressListMatches === false);
step('H4: v1 with inconsistent key/address refused', /mismatch/.test(await expectThrow(() => W.encryptV1(v1text.replace(addrs[0], 'sost1' + 'f'.repeat(40)), PASS))));
step('H5: short passphrase refused', /at least 8/.test(await expectThrow(() => W.encryptV1(v1text, 'short'))));
step('H6: trailing-space passphrase refused (miner trims it)', /space/.test(await expectThrow(() => W.encryptV1(v1text, 'abcdefgh '))));
step('H7: expected-address check', W.checkExpected(ver.keys, addrs[1]) === true && W.checkExpected(ver.keys, 'sost1' + '1'.repeat(40)) === false);
step('original v1 untouched', fs.readFileSync(v1, 'utf8') === v1text);

fs.rmSync(tmp, { recursive: true, force: true });
console.log(`\nRESULT: ${ok}/${n} PASS`);
process.exit(ok === n ? 0 : 1);
