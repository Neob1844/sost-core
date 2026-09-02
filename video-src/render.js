/* SOST video render pipeline.
 *
 * Renders a card HTML at 1920x1080 across a span of frames. Every frame is a
 * pure function of its timestamp (the card reads ?t= and derives the pulse
 * from it), so a re-render is reproducible and any card can be corrected later
 * by editing the HTML instead of re-authoring the film.
 *
 *   node render.js frames mech-title.html out/title 0 9.0 30
 *   node render.js still  mech-title.html out/poster.png 1.2
 */
const puppeteer = require('/home/sost/SOST/geaspirit-platform/node_modules/puppeteer-core');
const path = require('path'), fs = require('fs');
const CHROME = '/home/sost/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome';
const HERE = __dirname, W = 1920, H = 1080;

async function open() {
  const b = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-device-scale-factor=1',
           '--font-render-hinting=none'],
  });
  const p = await b.newPage();
  await p.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  return { b, p };
}

async function shoot(p, card, t, dest) {
  // `card` may already carry a query (e.g. intro.html?scene=3); keep it.
  const [file, qs] = card.split('?');
  const sep = qs ? '&' : '?';
  await p.goto(`file://${path.join(HERE, file)}${qs ? '?' + qs : ''}${sep}t=${t.toFixed(4)}`,
               { waitUntil: 'networkidle0', timeout: 60000 });
  await p.waitForFunction('document.documentElement.dataset.ready==="1"', { timeout: 20000 });
  await p.evaluate(() => document.fonts.ready);
  // ALPHA=1 keeps the page background transparent, for overlays composited onto
  // footage that cannot be re-authored.
  await p.screenshot({ path: dest, type: 'png', omitBackground: !!process.env.ALPHA });
}

(async () => {
  const [mode, card, out, a, b_, c] = process.argv.slice(2);
  const { b, p } = await open();
  try {
    if (mode === 'still') {
      await shoot(p, card, parseFloat(a || '0'), out);
      console.log('  still -> ' + out);
    } else {
      const t0 = parseFloat(a), t1 = parseFloat(b_), fps = parseInt(c || '30', 10);
      fs.mkdirSync(out, { recursive: true });
      const n = Math.round((t1 - t0) * fps);
      for (let i = 0; i < n; i++) {
        await shoot(p, card, t0 + i / fps, path.join(out, `f_${String(i).padStart(5, '0')}.png`));
        if (i % 30 === 0) console.log(`  ${i}/${n}`);
      }
      console.log(`  ${n} frames -> ${out}`);
    }
  } finally { await b.close(); }
})();
