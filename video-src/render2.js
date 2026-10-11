/* SOST film renderer v2 — continuous timelines.
 *
 * render.js reloads the page for every frame, which is fine for looped cards but far too slow
 * for scenes whose diagrams build up over 10–15 seconds. Here the page is loaded ONCE and the
 * page itself exposes window.frame(t) -> Promise, which redraws the whole scene as a pure
 * function of t (no CSS animation, no timers), so every frame is still reproducible.
 *
 *   node render2.js film-intro.html?scene=3 out/s3 12.0 30 [workers]
 *     -> out/s3/f_00000.png ... (12.0 s at 30 fps), split across N browsers
 *   node render2.js still film-intro.html?scene=3 out.png 6.5
 */
const puppeteer = require('./node_modules/puppeteer-core');
const path = require('path'), fs = require('fs');
const CHROME = '/home/sost/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome';
const HERE = __dirname, W = 1920, H = 1080;

async function page(card) {
  const b = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-device-scale-factor=1', '--font-render-hinting=none'],
  });
  const p = await b.newPage();
  await p.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  const [file, qs] = card.split('?');
  await p.goto(`file://${path.join(HERE, file)}${qs ? '?' + qs : ''}`, { waitUntil: 'networkidle0', timeout: 60000 });
  await p.waitForFunction('typeof window.frame==="function"', { timeout: 20000 });
  await p.evaluate(() => document.fonts.ready);
  return { b, p };
}

async function shot(p, t, dest) {
  await p.evaluate((t) => window.frame(t), t);
  await p.screenshot({ path: dest, type: 'png' });
}

(async () => {
  const args = process.argv.slice(2);
  if (args[0] === 'still') {
    const [, card, out, t] = args;
    const { b, p } = await page(card);
    try { await shot(p, parseFloat(t || '0'), out); } finally { await b.close(); }
    console.log('  still -> ' + out);
    return;
  }
  const [card, out, durS, fpsS, workersS] = args;
  const fps = parseInt(fpsS || '30', 10), n = Math.round(parseFloat(durS) * fps), workers = parseInt(workersS || '3', 10);
  fs.mkdirSync(out, { recursive: true });
  const per = Math.ceil(n / workers);
  await Promise.all(Array.from({ length: workers }, async (_, w) => {
    const a = w * per, z = Math.min(n, a + per);
    if (a >= z) return;
    const { b, p } = await page(card);
    try {
      for (let i = a; i < z; i++) await shot(p, i / fps, path.join(out, `f_${String(i).padStart(5, '0')}.png`));
    } finally { await b.close(); }
  }));
  console.log(`  ${n} frames -> ${out}`);
})().catch((e) => { console.error(e); process.exit(1); });
