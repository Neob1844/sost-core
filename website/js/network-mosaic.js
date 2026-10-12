/* ============================================================================
 * SOST Network Mosaic — self-contained explorer dashboard card
 * ----------------------------------------------------------------------------
 * PURELY ADDITIVE. This IIFE renders one visual card ("SOST Network Mosaic")
 * into the pre-existing empty container #networkMosaicCard. It does NOT modify,
 * wrap, or override any existing explorer function, RPC call, timer, or DOM.
 *
 * Data sources (all REUSED from the explorer, read-only):
 *   - window._diffHistory : last ~288 blocks [{h,d,t,miner,lp,lw}] set by
 *                            loadStats() (h=height, d=bits_q, t=unix time,
 *                            miner=miner_address, lp=reward payout, lw=winner).
 *   - #dMempool textContent : current mempool size (pending tx count).
 *   - window.rpc(method,params) : the explorer's own RPC helper, used ONLY for
 *                            lazy on-hover block enrichment (hash / tx count /
 *                            reward / cASERT profile) — read-only getblock.
 *
 * Refresh cadence: NO new interval. A MutationObserver watches the stat cells
 * the explorer already updates on every refresh (#dMinersSub, #dMempool) and
 * re-renders from the fresh globals — it piggybacks on the existing cadence and
 * never competes with the version-poll auto-reload.
 * ========================================================================== */
(function () {
  'use strict';

  var MAX_BLOCKS = 288;
  var mount, tabsEl, bodyEl, tipEl;
  var canvas, ctx, offCanvas, offCtx;
  var currentTab = 'blocks';
  var rafId = 0, animStart = 0;
  var lastLayout = null;            // {cols,rows,tile,pad,w,h,dpr}
  var lastBlocks = [];             // snapshot used for hit-testing
  var hoverIdx = -1;
  var blockCache = {};             // height -> enriched getblock result
  // LIVE NETWORK PULSE (v2). Every visual channel encodes a real block property:
  //   colour = producer · glow = recency · border = bitsQ · texture = Equalizer profile
  //   symbol = block type (R = DTD reward, J = Jackpot draw height) · side mark = slow block
  //   pulse  = a block that arrived while the page is open (LIVE only).
  var colorMode = 'producer';      // producer | difficulty | timing
  var live = true;
  var pulses = {};                 // height -> performance.now() when it arrived
  var lastTipSeen = 0;
  var hoverMiner = '', focusMiner = '';
  var dtByH = {};                  // height -> seconds since the previous block (when known)
  var panelEl = null, modesEl = null;
  try {
    var _cm = localStorage.getItem('sost_mosaic_mode'); if (/^(producer|difficulty|timing)$/.test(_cm || '')) colorMode = _cm;
    var _lv = localStorage.getItem('sost_mosaic_live');
    if (_lv === '0') live = false;
    else if (_lv == null && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) live = false;
  } catch (e) {}
  // Linked crosshair with the ConvergenceX Control Room (js/control-room.js).
  var crossInH = null, crossOutH = null;
  function crossOut(h) {
    if (h === crossOutH) return; crossOutH = h;
    try { window.dispatchEvent(new CustomEvent('sost-cross', { detail: { h: h, src: 'mosaic' } })); } catch (e) {}
  }
  window.addEventListener('sost-cross', function (ev) {
    if (!ev.detail || ev.detail.src === 'mosaic') return;
    crossInH = ev.detail.h;
    if (!live && typeof blitFrame === 'function') { try { blitFrame(0); } catch (e) {} }
  });
  function isJackpotHeight(h) { return h >= 25290 && (h - 25290) % 288 === 0; }
  function profName(p, pm) {
    if (pm) return pm;
    if (p == null || isNaN(p)) return '';
    return p < 0 ? 'E' + (-p) : (p === 0 ? 'B0' : 'H' + p);
  }
  function fmtDur(s) {
    if (s == null) return '—';
    var m = Math.floor(s / 60), r = Math.round(s % 60);
    return m ? (m + 'm ' + (r < 10 ? '0' : '') + r + 's') : (r + 's');
  }
  function timingColor(dt) {
    if (dt == null) return 'hsl(0,0%,26%)';
    if (dt < 300) return '#38bdf8';      // fast  (< 5 min)
    if (dt < 900) return '#22c55e';      // on target (5-15 min)
    if (dt < 1800) return '#eab308';     // slow  (15-30 min)
    if (dt < 3600) return '#f97316';     // very slow (30-60 min)
    return '#ef4444';                    // stall (> 60 min)
  }

  /* -- helpers ------------------------------------------------------------- */
  function el(tag, css, txt) {
    var e = document.createElement(tag);
    if (css) e.style.cssText = css;
    if (txt != null) e.textContent = txt;
    return e;
  }
  function getBlocks() {
    var d = (typeof window._diffHistory !== 'undefined' && window._diffHistory) || [];
    if (!d.length) return [];
    // _diffHistory is ascending by height; keep the most recent MAX_BLOCKS.
    return d.slice(Math.max(0, d.length - MAX_BLOCKS));
  }
  function getMempoolCount() {
    // Test hook: allow a faked value without touching the node.
    if (typeof window.__mosaicFakeMempool === 'number') return window.__mosaicFakeMempool;
    var m = document.getElementById('dMempool');
    if (!m) return 0;
    var n = parseInt(String(m.textContent || '').replace(/[^0-9]/g, ''), 10);
    return isFinite(n) ? n : 0;
  }
  // Stable string hash -> hue, so each producer keeps a consistent colour.
  function hashHue(s) {
    s = s || 'unknown';
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return ((h % 360) + 360) % 360;
  }
  function shortHash(h) {
    return h && h.length >= 16 ? h.slice(0, 8) + '…' + h.slice(-6) : (h || '');
  }
  function shortAddr(a) {
    return a && a.length > 16 ? a.slice(0, 8) + '…' + a.slice(-5) : (a || '');
  }
  function fmtAgo(ts) {
    var d = Date.now() / 1000 - ts;
    if (d < 60) return Math.floor(d) + 's ago';
    if (d < 3600) return Math.floor(d / 60) + 'm ago';
    if (d < 86400) return Math.floor(d / 3600) + 'h ago';
    return Math.floor(d / 86400) + 'd ago';
  }
  function fmtSost(sat) {
    var v = (parseFloat(sat) || 0) / 1e8;
    return v.toFixed(4);
  }

  /* -- card skeleton ------------------------------------------------------- */
  function build() {
    mount = document.getElementById('networkMosaicCard');
    if (!mount) return false;
    mount.innerHTML = '';
    mount.style.cssText =
      'background:var(--bg2);border:1px solid var(--border);padding:14px 16px;position:relative;';

    var head = el('div',
      'display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;margin-bottom:12px;');
    var titleWrap = el('div');
    var title = el('div',
      'font-size:11px;letter-spacing:2px;color:var(--text3);');
    title.innerHTML = '// <b style="color:var(--purple)">SOST NETWORK MOSAIC</b>';
    var sub = el('div',
      'font-size:9px;letter-spacing:1px;color:var(--text3);margin-top:3px;',
      'Last 288 blocks · mempool · producer distribution');
    titleWrap.appendChild(title);
    titleWrap.appendChild(sub);

    tabsEl = el('div', 'display:flex;gap:6px;');
    ['blocks', 'mempool', 'producers'].forEach(function (name) {
      var b = el('button',
        'background:var(--bg3);color:var(--text2);border:1px solid var(--border);' +
        'font-family:var(--code);font-size:9px;letter-spacing:1.5px;padding:6px 12px;' +
        'cursor:pointer;text-transform:uppercase;transition:all .15s;border-radius:2px;',
        name);
      b.setAttribute('data-tab', name);
      b.onmouseenter = function () { if (currentTab !== name) b.style.color = 'var(--text)'; };
      b.onmouseleave = function () { if (currentTab !== name) b.style.color = 'var(--text2)'; };
      b.onclick = function () { setTab(name); };
      tabsEl.appendChild(b);
    });

    head.appendChild(titleWrap);
    head.appendChild(tabsEl);
    mount.appendChild(head);

    modesEl = el('div', 'display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin:-4px 0 10px;font-size:8.5px;letter-spacing:1.2px;color:var(--text3);');
    mount.appendChild(modesEl);
    bodyEl = el('div', 'position:relative;min-height:150px;');
    mount.appendChild(bodyEl);

    tipEl = el('div',
      'display:none;position:absolute;background:rgba(6,6,6,.96);border:1px solid #444;' +
      'border-radius:4px;padding:8px 11px;font-family:var(--code);font-size:9.5px;' +
      'line-height:1.7;color:#e2e8f0;pointer-events:none;z-index:300;white-space:nowrap;' +
      'box-shadow:0 0 14px rgba(192,132,252,.25);');
    mount.appendChild(tipEl);

    var foot = el('div',
      'font-size:8px;color:var(--text3);margin-top:8px;line-height:1.6;',
      '');
    foot.id = 'mosaicFoot';
    mount.appendChild(foot);

    highlightTab();
    return true;
  }

  function renderModes() {
    if (!modesEl) return;
    modesEl.style.display = currentTab === 'blocks' ? 'flex' : 'none';
    modesEl.innerHTML = '';
    modesEl.appendChild(el('span', 'margin-right:2px', 'COLOR BY'));
    [['producer', 'MINER'], ['difficulty', 'DIFFICULTY'], ['timing', 'TIMING']].forEach(function (m) {
      var a = colorMode === m[0];
      var b = el('button', 'background:' + (a ? 'var(--bg4)' : 'transparent') + ';color:' + (a ? 'var(--cyan)' : 'var(--text2)') +
        ';border:1px solid ' + (a ? 'var(--cyan)' : 'var(--border)') + ';font-family:var(--code);font-size:8.5px;letter-spacing:1.2px;padding:4px 9px;cursor:pointer;border-radius:2px', m[1]);
      b.onclick = function () { colorMode = m[0]; try { localStorage.setItem('sost_mosaic_mode', colorMode); } catch (e) {} render(); };
      modesEl.appendChild(b);
    });
    var lv = el('button', 'margin-left:6px;background:transparent;color:' + (live ? '#22c55e' : 'var(--text3)') + ';border:1px solid ' +
      (live ? 'rgba(34,197,94,.6)' : 'var(--border)') + ';font-family:var(--code);font-size:8.5px;letter-spacing:1.2px;padding:4px 9px;cursor:pointer;border-radius:2px',
      (live ? '\u25CF ' : '\u25CB ') + 'LIVE');
    lv.title = 'LIVE: a block that arrives while this page is open pulses once and the newest blocks glow. Off = static mosaic.';
    lv.onclick = function () { live = !live; try { localStorage.setItem('sost_mosaic_live', live ? '1' : '0'); } catch (e) {} render(); };
    modesEl.appendChild(lv);
  }

  function highlightTab() {
    if (!tabsEl) return;
    var btns = tabsEl.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var active = btns[i].getAttribute('data-tab') === currentTab;
      btns[i].style.background = active ? 'var(--bg4)' : 'var(--bg3)';
      btns[i].style.color = active ? 'var(--purple)' : 'var(--text2)';
      btns[i].style.borderColor = active ? 'var(--purple)' : 'var(--border)';
    }
  }
  function setTab(name) {
    currentTab = name;
    closePanel();
    highlightTab();
    render();
  }

  /* -- BLOCKS (canvas mosaic) --------------------------------------------- */
  function renderBlocks() {
    stopAnim();
    hideTip();
    bodyEl.innerHTML = '';
    var blocks = getBlocks();
    var foot = document.getElementById('mosaicFoot');

    if (!blocks.length) {
      bodyEl.appendChild(placeholder('Waiting for block data…',
        'The mosaic paints as soon as the explorer finishes its first 288-block scan.'));
      if (foot) foot.textContent = '';
      return;
    }
    lastBlocks = blocks;
    dtByH = {};
    for (var k = 1; k < blocks.length; k++) {
      if (blocks[k].h === blocks[k - 1].h + 1) dtByH[blocks[k].h] = blocks[k].t - blocks[k - 1].t;
    }
    var newest = blocks[blocks.length - 1].h, nowT = performance.now();
    if (lastTipSeen && newest > lastTipSeen && live) {
      for (var nh = Math.max(lastTipSeen + 1, newest - 5); nh <= newest; nh++) pulses[nh] = nowT;
    }
    if (newest > lastTipSeen) lastTipSeen = newest;
    for (var ph in pulses) { if (nowT - pulses[ph] > 4000) delete pulses[ph]; }

    var wrap = el('div', 'position:relative;');
    canvas = document.createElement('canvas');
    canvas.style.cssText = 'width:100%;display:block;cursor:crosshair;';
    wrap.appendChild(canvas);
    bodyEl.appendChild(wrap);
    ctx = canvas.getContext('2d');

    layoutAndPaint();

    canvas.onmousemove = onCanvasMove;
    canvas.onmouseleave = function () { hoverIdx = -1; hoverMiner = ''; hideTip(); crossOut(null); };
    canvas.onclick = onCanvasClick;

    var uniqueMiners = {};
    for (var i = 0; i < blocks.length; i++) uniqueMiners[blocks[i].miner || '?'] = 1;
    var dMin = Infinity, dMax = -Infinity;
    for (i = 0; i < blocks.length; i++) { if (blocks[i].d < dMin) dMin = blocks[i].d; if (blocks[i].d > dMax) dMax = blocks[i].d; }
    if (foot) {
      var chip = function (bg, txt) { return '<b style="color:#000;background:' + bg + ';border-radius:3px;padding:0 4px">' + txt + '</b>'; };
      var pMin = 99, pMax = -99;
      for (i = 0; i < blocks.length; i++) if (blocks[i].p != null) { if (blocks[i].p < pMin) pMin = blocks[i].p; if (blocks[i].p > pMax) pMax = blocks[i].p; }
      var head = colorMode === 'difficulty'
        ? 'colour = Equalizer profile (<span style="color:hsl(220,70%,60%)">E7</span> → <span style="color:hsl(150,70%,50%)">B0</span> → <span style="color:hsl(0,70%,55%)">H35</span>; in view ' +
          (pMin <= pMax ? profName(pMin) + '–' + profName(pMax) : 'n/a') + ') · border = bitsQ (' +
          (dMin === dMax ? 'constant in view: ' + (dMin / 65536).toFixed(4) : (dMin / 65536).toFixed(4) + '–' + (dMax / 65536).toFixed(4)) + ')'
        : colorMode === 'timing'
          ? 'colour = time since previous block: <span style="color:#38bdf8">&lt;5m</span> · <span style="color:#22c55e">5–15m</span> · <span style="color:#eab308">15–30m</span> · <span style="color:#f97316">30–60m</span> · <span style="color:#ef4444">&gt;60m</span> (target 10m)'
          : 'colour = producer';
      foot.innerHTML = 'Each tile = one block, newest top-left · ' + head +
        ' · glow = recency · border = bitsQ (thicker = higher) · texture = Equalizer profile (hatch density rises with H level, dots = E easing profiles, plain = B0) · ' +
        chip('#c9b3ff', 'R') + ' DTD reward · ' + chip('#ffd166', 'J') + ' Jackpot draw height · ' +
        '<span style="color:#f97316">▌</span> side mark = block took &gt;45 min · ' +
        Object.keys(uniqueMiners).length + ' producers in view · hover = that producer\'s blocks · tap/click = producer card';
    }
    renderModes();
    startAnim();
  }

  function computeLayout() {
    var cssW = Math.max(200, bodyEl.clientWidth || mount.clientWidth || 320);
    var mobile = cssW < 520;
    var target = mobile ? 18 : 26;              // desired tile edge (css px)
    var pad = mobile ? 2 : 3;
    var cols = Math.max(6, Math.floor(cssW / (target + pad)));
    var n = lastBlocks.length;
    var rows = Math.ceil(n / cols);
    var tile = Math.floor((cssW - pad) / cols) - pad;
    if (tile < 8) tile = 8;
    var cssH = rows * (tile + pad) + pad;
    var dpr = window.devicePixelRatio || 1;
    return { cols: cols, rows: rows, tile: tile, pad: pad, w: cssW, h: cssH, dpr: dpr };
  }

  function layoutAndPaint() {
    if (!canvas || !ctx) return;
    // Skip while the mosaic is hidden (e.g. an address/detail panel is open): its
    // clientWidth is 0 then, so computeLayout would fall back to a narrow width and
    // paint a wrong tile grid (fewer cols / more rows) that flashes "squished/stretched"
    // for a moment when the section is shown again. Stay with the last good layout;
    // the ResizeObserver repaints correctly once the container is visible again.
    if (bodyEl && (bodyEl.offsetParent === null || (bodyEl.clientWidth || 0) === 0)) return;
    var L = computeLayout();
    lastLayout = L;
    canvas.width = Math.round(L.w * L.dpr);
    canvas.height = Math.round(L.h * L.dpr);
    canvas.style.height = L.h + 'px';

    // Offscreen static layer (tiles) — animation only re-blits + glows.
    offCanvas = document.createElement('canvas');
    offCanvas.width = canvas.width;
    offCanvas.height = canvas.height;
    offCtx = offCanvas.getContext('2d');
    offCtx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);
    ctx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);

    // Difficulty range for brightness normalisation.
    var dMin = Infinity, dMax = -Infinity, i;
    for (i = 0; i < lastBlocks.length; i++) {
      var dv = lastBlocks[i].d || 0;
      if (dv < dMin) dMin = dv;
      if (dv > dMax) dMax = dv;
    }
    var span = (dMax - dMin) || 1;
    var n = lastBlocks.length;

    offCtx.clearRect(0, 0, L.w, L.h);
    var rr = Math.min(3, L.tile / 6);
    for (i = 0; i < n; i++) {
      var b = lastBlocks[i];
      var order = n - 1 - i;                    // 0 = newest
      var col = order % L.cols;
      var row = Math.floor(order / L.cols);
      var x = L.pad + col * (L.tile + L.pad);
      var y = L.pad + row * (L.tile + L.pad);
      var norm = ((b.d || dMin) - dMin) / span;          // 0..1 bitsQ within view
      var recency = 1 - (order / Math.max(1, n));         // 0..1 (newest ~1)
      var fill;
      if (colorMode === 'difficulty') {
        // ConvergenceX difficulty = bitsQ (border) + Equalizer profile (colour): E7 blue -> B0 green -> H35 red.
        var pp = (b.p != null && !isNaN(b.p)) ? b.p : 0;
        var hueD = pp <= 0 ? 150 + (-pp / 7) * 70 : 150 - Math.min(1, pp / 35) * 150;
        fill = 'hsl(' + Math.round(hueD) + ',70%,' + (30 + Math.min(1, Math.abs(pp) / 35) * 14 + recency * 10).toFixed(1) + '%)';
      } else if (colorMode === 'timing') {
        fill = timingColor(dtByH[b.h]);
      } else {
        fill = 'hsl(' + hashHue(b.miner) + ',' + (56 + recency * 16).toFixed(1) + '%,' + (30 + recency * 26).toFixed(1) + '%)';
      }
      offCtx.fillStyle = fill;
      roundRect(offCtx, x, y, L.tile, L.tile, rr);
      offCtx.fill();
      if (colorMode === 'timing') {            // recency still readable in timing mode
        offCtx.fillStyle = 'rgba(0,0,0,' + (0.42 * (1 - recency)).toFixed(3) + ')';
        roundRect(offCtx, x, y, L.tile, L.tile, rr); offCtx.fill();
      }
      // texture = Equalizer profile
      var p = b.p;
      if (p != null && !isNaN(p) && p !== 0 && L.tile >= 10) {
        offCtx.save();
        roundRect(offCtx, x, y, L.tile, L.tile, rr); offCtx.clip();
        offCtx.strokeStyle = 'rgba(0,0,0,.30)'; offCtx.fillStyle = 'rgba(0,0,0,.34)';
        if (p > 0) {
          var lines = 1 + Math.floor(p / 6);            // H1-H5:1 ... H30-H35:6 hatch lines
          var stepH = (L.tile * 2) / (lines + 1);
          offCtx.lineWidth = 1;
          for (var hl = 1; hl <= lines; hl++) {
            var o2 = hl * stepH;
            offCtx.beginPath(); offCtx.moveTo(x + o2, y); offCtx.lineTo(x + o2 - L.tile, y + L.tile); offCtx.stroke();
          }
        } else {
          var dots = -p, rad = Math.max(1, L.tile / 16);   // E1..E7: 1..7 dots
          for (var dd = 0; dd < dots; dd++) {
            var ang = (dd / dots) * Math.PI * 2;
            offCtx.beginPath(); offCtx.arc(x + L.tile / 2 + Math.cos(ang) * L.tile * 0.28, y + L.tile / 2 + Math.sin(ang) * L.tile * 0.28, rad, 0, Math.PI * 2); offCtx.fill();
          }
        }
        offCtx.restore();
      }
      // border = bitsQ (thicker/brighter = higher numeric difficulty in view)
      {
        offCtx.strokeStyle = 'rgba(255,255,255,' + (0.10 + 0.55 * norm).toFixed(3) + ')';
        offCtx.lineWidth = 0.6 + 1.6 * norm;
      }
      var lw2 = offCtx.lineWidth / 2;
      roundRect(offCtx, x + lw2, y + lw2, L.tile - 2 * lw2, L.tile - 2 * lw2, rr);
      offCtx.stroke();
      // side mark = slow block (> 45 min since the previous block)
      var dt = dtByH[b.h];
      if (dt != null && dt > 2700) {
        offCtx.fillStyle = dt > 7200 ? '#ef4444' : '#f97316';
        offCtx.fillRect(x, y + 1, Math.max(2, L.tile / 9), L.tile - 2);
      }
      // symbol = block type
      if (L.tile >= 10) {
        offCtx.textAlign = 'center'; offCtx.textBaseline = 'middle';
        var cx = x + L.tile / 2, cy = y + L.tile / 2 + 0.5;
        if (isJackpotHeight(b.h)) {
          var dr = L.tile * 0.34;
          offCtx.beginPath(); offCtx.moveTo(cx, cy - dr); offCtx.lineTo(cx + dr, cy); offCtx.lineTo(cx, cy + dr); offCtx.lineTo(cx - dr, cy); offCtx.closePath();
          offCtx.fillStyle = '#ffd166'; offCtx.fill(); offCtx.strokeStyle = 'rgba(0,0,0,.6)'; offCtx.lineWidth = 1; offCtx.stroke();
          offCtx.font = '900 ' + Math.max(7, Math.round(L.tile * 0.36)) + 'px system-ui,Segoe UI,Arial,sans-serif';
          offCtx.fillStyle = '#000'; offCtx.fillText('J', cx, cy + 0.5);
        } else if (b.lp > 0) {
          var lfs = Math.max(8, Math.round(L.tile * 0.46));
          offCtx.font = '800 ' + lfs + 'px system-ui,Segoe UI,Arial,sans-serif';
          offCtx.lineWidth = Math.max(1.5, lfs * 0.14);
          offCtx.strokeStyle = 'rgba(255,255,255,.55)'; offCtx.strokeText('R', cx, cy);
          offCtx.fillStyle = 'rgba(0,0,0,.78)'; offCtx.fillText('R', cx, cy);
        } else {
          offCtx.beginPath(); offCtx.arc(cx, cy, Math.max(1.2, L.tile / 12), 0, Math.PI * 2);
          offCtx.fillStyle = 'rgba(255,255,255,.55)'; offCtx.fill();
        }
      }
    }
    // store tile geometry for hit-testing (map order-slot -> block index)
    L.geo = { n: n };
    blitFrame(0);
  }

  function tileRectForOrder(order, L) {
    var col = order % L.cols;
    var row = Math.floor(order / L.cols);
    return {
      x: L.pad + col * (L.tile + L.pad),
      y: L.pad + row * (L.tile + L.pad),
      s: L.tile
    };
  }

  function blitFrame(t) {
    if (!ctx || !offCanvas || !lastLayout) return;
    var L = lastLayout;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(offCanvas, 0, 0);
    ctx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);

    var n = L.geo ? L.geo.n : 0, rr = Math.min(3, L.tile / 6);
    // Producer trajectory: hovering (or the open producer card) dims every other producer.
    var hm = hoverMiner || focusMiner;
    if (hm) {
      ctx.fillStyle = 'rgba(6,6,6,.66)';
      for (var di = 0; di < n; di++) {
        if ((lastBlocks[di].miner || '') === hm) continue;
        var dr = tileRectForOrder(n - 1 - di, L);
        ctx.fillRect(dr.x - 0.5, dr.y - 0.5, dr.s + 1, dr.s + 1);
      }
    }
    if (live) {
      // Recency glow on the newest few blocks.
      var pulse = 0.5 + 0.5 * Math.sin(t / 620);
      var recent = Math.min(5, n);
      for (var o = 0; o < recent; o++) {
        var r = tileRectForOrder(o, L);
        var a = (0.10 + 0.22 * pulse) * (1 - o / 6);
        ctx.save();
        ctx.shadowColor = 'rgba(192,132,252,' + (0.55 * (1 - o / 6)) + ')';
        ctx.shadowBlur = 8 + 8 * pulse;
        ctx.strokeStyle = 'rgba(192,132,252,' + a + ')';
        ctx.lineWidth = 1.5;
        roundRect(ctx, r.x + .5, r.y + .5, r.s - 1, r.s - 1, rr);
        ctx.stroke();
        ctx.restore();
      }
      // Jackpot draw heights: a discreet animated gold border.
      for (var ji = 0; ji < n; ji++) {
        if (!isJackpotHeight(lastBlocks[ji].h)) continue;
        var jr = tileRectForOrder(n - 1 - ji, L);
        ctx.save(); ctx.setLineDash([3, 3]); ctx.lineDashOffset = -(t / 90) % 6;
        ctx.strokeStyle = 'rgba(255,209,102,.95)'; ctx.lineWidth = 1.5;
        roundRect(ctx, jr.x - 1, jr.y - 1, jr.s + 2, jr.s + 2, rr + 1); ctx.stroke(); ctx.restore();
      }
      // New-block pulse: the tile swells ~15% and emits one ring (1.1 s); a new Jackpot
      // height also sends one gold sweep across its row.
      var now = performance.now();
      for (var ph in pulses) {
        var age = now - pulses[ph];
        if (age > 1400) continue;
        var idx = -1;
        for (var q = n - 1; q >= 0 && q >= n - 12; q--) { if (lastBlocks[q].h === +ph) { idx = q; break; } }
        if (idx < 0) continue;
        var pr = tileRectForOrder(n - 1 - idx, L), k = Math.min(1, age / 1100), ease = 1 - Math.pow(1 - k, 3);
        var sc = 1 + 0.15 * (1 - ease), sw = pr.s * sc, sx = pr.x - (sw - pr.s) / 2, sy = pr.y - (sw - pr.s) / 2;
        ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(offCanvas, pr.x * L.dpr, pr.y * L.dpr, pr.s * L.dpr, pr.s * L.dpr, sx * L.dpr, sy * L.dpr, sw * L.dpr, sw * L.dpr);
        ctx.restore();
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,' + (0.7 * (1 - ease)).toFixed(3) + ')';
        ctx.lineWidth = 1.5;
        var ring = pr.s * (0.6 + 1.2 * ease);
        roundRect(ctx, pr.x + pr.s / 2 - ring / 2, pr.y + pr.s / 2 - ring / 2, ring, ring, rr + 2); ctx.stroke();
        if (isJackpotHeight(+ph)) {
          var rowY = pr.y, sweepX = L.pad + (L.w - 2 * L.pad) * k;
          ctx.fillStyle = 'rgba(255,209,102,' + (0.55 * (1 - k)).toFixed(3) + ')';
          ctx.fillRect(sweepX - 3, rowY, 6, pr.s);
        }
        ctx.restore();
      }
    }
    // Block under the Control Room crosshair
    if (crossInH != null && hoverIdx < 0) {
      for (var ci = n - 1; ci >= 0; ci--) if (lastBlocks[ci].h === crossInH) {
        var cr2 = tileRectForOrder(n - 1 - ci, L);
        ctx.save(); ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2; ctx.shadowColor = 'rgba(34,211,238,.9)'; ctx.shadowBlur = 10;
        roundRect(ctx, cr2.x - 1, cr2.y - 1, cr2.s + 2, cr2.s + 2, rr + 1); ctx.stroke(); ctx.restore();
        break;
      }
    }
    // Hover ring
    if (hoverIdx >= 0 && lastLayout.geo) {
      var hr = tileRectForOrder(lastLayout.geo.n - 1 - hoverIdx, L);
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      roundRect(ctx, hr.x + .5, hr.y + .5, hr.s - 1, hr.s - 1, rr);
      ctx.stroke();
    }
  }

  function startAnim() {
    stopAnim();
    animStart = performance.now();
    var lastDraw = 0;
    var loop = function (now) {
      if (currentTab !== 'blocks' || !canvas) { rafId = 0; return; }
      if (live || now - lastDraw > 120) { blitFrame(now - animStart); lastDraw = now; }
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);
  }
  function stopAnim() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
  }

  function roundRect(c, x, y, w, h, r) {
    if (w < 2 * r) r = w / 2;
    if (h < 2 * r) r = h / 2;
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }

  function hitTest(px, py) {
    var L = lastLayout;
    if (!L) return -1;
    var col = Math.floor((px - L.pad) / (L.tile + L.pad));
    var row = Math.floor((py - L.pad) / (L.tile + L.pad));
    if (col < 0 || col >= L.cols || row < 0) return -1;
    var order = row * L.cols + col;
    if (order < 0 || order >= L.geo.n) return -1;
    // verify inside tile (not in the gap)
    var r = tileRectForOrder(order, L);
    if (px < r.x || px > r.x + r.s || py < r.y || py > r.y + r.s) return -1;
    return L.geo.n - 1 - order;                 // -> blocks[] index
  }

  function onCanvasMove(ev) {
    var rect = canvas.getBoundingClientRect();
    var px = ev.clientX - rect.left;
    var py = ev.clientY - rect.top;
    var idx = hitTest(px, py);
    if (idx !== hoverIdx) hoverIdx = idx;
    if (idx < 0) { hoverMiner = ''; hideTip(); crossOut(null); return; }
    hoverMiner = lastBlocks[idx].miner || '';
    crossOut(lastBlocks[idx].h);
    if (panelEl && ev.sourceCapabilities && ev.sourceCapabilities.firesTouchEvents) return;
    showBlockTip(lastBlocks[idx], ev);
    maybeEnrich(lastBlocks[idx], ev);
  }
  function onCanvasClick(ev) {
    var rect = canvas.getBoundingClientRect();
    var idx = hitTest(ev.clientX - rect.left, ev.clientY - rect.top);
    if (idx < 0) { closePanel(); return; }
    hideTip();
    openPanel(lastBlocks[idx]);
  }

  /* -- producer card (stays inside the mosaic) ------------------------------ */
  function closePanel() { focusMiner = ''; if (panelEl) { panelEl.remove(); panelEl = null; } }
  function esc(x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function openPanel(b) {
    closePanel();
    var m = b.miner || '';
    focusMiner = m;
    var blocks = lastBlocks, n = blocks.length, mine = 0, last = 0;
    for (var i = 0; i < n; i++) if ((blocks[i].miner || '') === m) { mine++; if (blocks[i].h > last) last = blocks[i].h; }
    var share = n ? (100 * mine / n) : 0, segs = 20, full = Math.round(share / 100 * segs);
    var bar = '<span style="color:hsl(' + hashHue(m) + ',70%,60%)">' + new Array(full + 1).join('\u2588') + '</span><span style="color:var(--text3)">' + new Array(segs - full + 1).join('\u2591') + '</span>';
    var mob = (mount.clientWidth || 400) < 520;
    panelEl = el('div', 'position:absolute;z-index:320;top:' + (mob ? '58px' : '46px') + ';' + (mob ? 'left:8px;right:8px;' : 'right:12px;width:300px;') +
      'background:#08080a;isolation:isolate;opacity:1;border:1px solid hsl(' + hashHue(m) + ',60%,45%);border-radius:4px;padding:11px 13px;font-family:var(--code);font-size:10px;line-height:1.75;color:#e2e8f0;box-shadow:0 0 18px rgba(0,0,0,.6)');
    var dtx = dtByH[b.h];
    panelEl.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b style="color:hsl(' + hashHue(m) + ',70%,62%);word-break:break-all">' + esc(m ? (m.slice(0, 12) + '\u2026' + m.slice(-6)) : 'unknown') + '</b>' +
      '<span data-x style="cursor:pointer;color:var(--text3);font-size:13px;padding:0 4px">\u00D7</span></div>' +
      '<div style="color:var(--text3);font-size:9px;letter-spacing:1px;margin-top:4px">LAST ' + n + ' BLOCKS</div>' +
      '<div style="letter-spacing:0;font-size:11px">' + bar + '</div>' +
      '<div>Blocks: <b>' + mine + '</b> &middot; Share: <b>' + share.toFixed(1) + '%</b></div>' +
      '<div>Last block: <b>#' + (last ? last.toLocaleString('en-US') : '\u2014') + '</b></div>' +
      '<div>Current DTD: <b data-dtd style="color:var(--text3)">checking\u2026</b></div>' +
      '<div>Jackpot V2: <b data-jp style="color:var(--text3)">checking\u2026</b></div>' +
      '<div style="margin-top:6px;padding-top:6px;border-top:1px solid #222;color:var(--text3);font-size:9px">Tapped block #' + b.h.toLocaleString('en-US') + ' &middot; ' +
        esc(profName(b.p, b.pm) || '\u2014') + ' &middot; bitsQ ' + ((b.d || 0) / 65536).toFixed(4) + ' &middot; ' + (dtx != null ? fmtDur(dtx) : '\u2014') + ' after previous</div>' +
      '<div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">' +
        '<button data-blk style="background:var(--bg3);color:var(--text2);border:1px solid var(--border);font-family:var(--code);font-size:9px;padding:4px 8px;cursor:pointer">OPEN BLOCK #' + b.h + '</button>' +
        (m ? '<button data-addr style="background:var(--bg3);color:var(--text2);border:1px solid var(--border);font-family:var(--code);font-size:9px;padding:4px 8px;cursor:pointer">OPEN ADDRESS</button>' : '') +
      '</div>';
    mount.appendChild(panelEl);
    panelEl.querySelector('[data-x]').onclick = closePanel;
    panelEl.querySelector('[data-blk]').onclick = function () {
      try { var inp = document.getElementById('searchIn'); if (inp && typeof window.doSearch === 'function') { inp.value = String(b.h); window.doSearch(); } } catch (e) {}
      closePanel();
    };
    var ab = panelEl.querySelector('[data-addr]');
    if (ab) ab.onclick = function () { try { if (typeof window.showAddress === 'function') window.showAddress(m); } catch (e) {} closePanel(); };
    var myPanel = panelEl;
    // Current DTD status: the explorer's canonical current state (getlotterystate based).
    (function () {
      var put = function (txt, col) { var e2 = myPanel.querySelector('[data-dtd]'); if (e2) { e2.textContent = txt; e2.style.color = col; } };
      var st = window._dtdCurState;
      var p0 = (st && st.tip === lastTipSeen) ? Promise.resolve(st)
        : (typeof window.dtdComputeCurrent === 'function' ? window.dtdComputeCurrent() : Promise.reject('n/a'));
      p0.then(function () {
        if (typeof window.dtdCurrentStatus !== 'function') throw 'n/a';
        var cs = window.dtdCurrentStatus({ addr: m, minedBlocks: mine });
        put(cs.l.charAt(0) + cs.l.slice(1).toLowerCase() + (cs.n ? ' (' + cs.n + ')' : ''), cs.c);
      }).catch(function () { put('open the DTD panel', 'var(--text3)'); });
    })();
    // Jackpot V2: the node's own audit for the next draw (read-only).
    (function () {
      var put = function (txt, col) { var e3 = myPanel.querySelector('[data-jp]'); if (e3) { e3.textContent = txt; e3.style.color = col; } };
      if (typeof window.rpc !== 'function' || !lastTipSeen) { put('\u2014', 'var(--text3)'); return; }
      var f = 30186, nx = lastTipSeen < f ? f : f + Math.ceil((lastTipSeen + 1 - f) / 288) * 288;
      window.rpc('getjackpotv2audit', [String(nx)]).then(function (a) {
        var c = null, cs2 = (a && a.candidates) || [];
        for (var j = 0; j < cs2.length; j++) if (cs2[j].address === m) { c = cs2[j]; break; }
        if (!c) { put('not a candidate for #' + nx.toLocaleString('en-US'), 'var(--text3)'); return; }
        if (c.eligible) put('Eligible for #' + nx.toLocaleString('en-US') + ' (' + c.pow_blocks + ' PoW blocks)', '#22c55e');
        else put((c.node_bound ? 'Bound' : 'Not bound') + ' \u00B7 ' + c.pow_blocks + ' PoW blocks \u00B7 not eligible for #' + nx.toLocaleString('en-US'), '#fbbf24');
      }).catch(function () { put('\u2014', 'var(--text3)'); });
    })();
  }

  function showBlockTip(b, ev) {
    if (!b) return;
    var enr = blockCache[b.h];
    var lines = [];
    lines.push('<b style="color:var(--purple)">BLOCK #' + b.h + '</b>');
    if (enr && enr.hash) lines.push('hash&nbsp;&nbsp;&nbsp;' + shortHash(enr.hash));
    lines.push('miner&nbsp;&nbsp;' + (b.miner ? shortAddr(b.miner) : '<i>unknown</i>'));
    lines.push('time&nbsp;&nbsp;&nbsp;' + fmtAgo(b.t) + (dtByH[b.h] != null ? ' &middot; ' + fmtDur(dtByH[b.h]) + ' after previous' : ''));
    if (isJackpotHeight(b.h)) lines.push('<span style="color:#ffd166">&#9670; Jackpot draw height' + (b.h >= 30186 ? ' (V2)' : ' (V15)') + '</span>');
    if (enr && enr.tx_count != null) lines.push('txs&nbsp;&nbsp;&nbsp;&nbsp;' + enr.tx_count);
    if (enr && enr.subsidy != null) lines.push('reward&nbsp;' + fmtSost(enr.subsidy) + ' SOST');
    else if (b.lp > 0) lines.push('reward&nbsp;' + fmtSost(b.lp) + ' SOST');
    if (b.lp > 0 && b.lw) {
      lines.push('<span style="color:var(--purple)">&#127881; DTD winner&nbsp;' + shortAddr(b.lw) + '</span>');
    }
    var prof = profName(b.p, b.pm) || (enr && enr.casert_mode) || '';
    if (prof) lines.push('Equalizer&nbsp;' + prof);
    if (b.d != null) lines.push('bitsQ&nbsp;&nbsp;' + (b.d / 65536).toFixed(4) + ' <span style="color:var(--text3)">(' + b.d.toLocaleString() + ')</span>');
    if (b.miner) {
      var cnt = 0; for (var ci = 0; ci < lastBlocks.length; ci++) if (lastBlocks[ci].miner === b.miner) cnt++;
      lines.push('<span style="color:var(--text3)">producer: ' + cnt + ' of ' + lastBlocks.length + ' blocks in view &middot; click for card</span>');
    }
    if (!enr) lines.push('<span style="color:var(--text3)">loading detail…</span>');
    tipEl.innerHTML = lines.join('<br>');
    positionTip(ev);
  }
  function positionTip(ev) {
    tipEl.style.display = 'block';
    var host = mount.getBoundingClientRect();
    var tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
    var x = ev.clientX - host.left + 14;
    var y = ev.clientY - host.top + 14;
    if (x + tw > host.width - 4) x = ev.clientX - host.left - tw - 14;
    if (y + th > host.height - 4) y = ev.clientY - host.top - th - 14;
    if (x < 2) x = 2; if (y < 2) y = 2;
    tipEl.style.left = x + 'px';
    tipEl.style.top = y + 'px';
  }
  function hideTip() { if (tipEl) tipEl.style.display = 'none'; }

  // Lazy, cached, read-only enrichment via the explorer's own rpc() helper.
  function maybeEnrich(b, ev) {
    if (!b || blockCache[b.h] || typeof window.rpc !== 'function') return;
    blockCache[b.h] = null;                     // in-flight sentinel
    var h = b.h;
    window.rpc('getblockhash', [String(h)]).then(function (hash) {
      return window.rpc('getblock', [hash]);
    }).then(function (blk) {
      if (!blk) { delete blockCache[h]; return; }
      blockCache[h] = blk;
      // If still hovering this block, refresh the tooltip in place.
      if (currentTab === 'blocks' && hoverIdx >= 0 && tipEl && tipEl.style.display === 'block' && !panelEl &&
          lastBlocks[hoverIdx] && lastBlocks[hoverIdx].h === h) {
        showBlockTip(lastBlocks[hoverIdx], ev);
      }
    }).catch(function () { delete blockCache[h]; });
  }

  /* -- MEMPOOL ------------------------------------------------------------- */
  function renderMempool() {
    stopAnim();
    hideTip();
    bodyEl.innerHTML = '';
    var foot = document.getElementById('mosaicFoot');
    var n = getMempoolCount();

    if (!n || n <= 0) {
      var empty = el('div',
        'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
        'min-height:150px;text-align:center;gap:8px;');
      var badge = el('div',
        'width:44px;height:44px;border-radius:50%;border:1.5px solid var(--green);' +
        'display:flex;align-items:center;justify-content:center;color:var(--green);' +
        'font-size:20px;box-shadow:0 0 16px var(--green-dim);', '✓');
      var t1 = el('div', 'color:var(--green);font-size:12px;letter-spacing:1px;',
        'Mempool clear');
      var t2 = el('div', 'color:var(--text3);font-size:9.5px;',
        'No pending transactions — the chain is caught up.');
      empty.appendChild(badge); empty.appendChild(t1); empty.appendChild(t2);
      bodyEl.appendChild(empty);
      if (foot) foot.textContent = '';
      return;
    }

    var grid = el('div',
      'display:flex;flex-wrap:wrap;gap:5px;align-items:flex-start;padding:4px 0;');
    var shown = Math.min(n, 240);
    for (var i = 0; i < shown; i++) {
      var hue = (i * 47) % 360;
      var tile = el('div',
        'width:16px;height:16px;border-radius:2px;' +
        'background:hsl(' + (200 + (hue % 60)) + ',70%,' + (42 + (i % 5) * 4) + '%);' +
        'box-shadow:0 0 4px rgba(103,232,249,.35);' +
        'animation:mosaicPend 2.4s ease-in-out infinite;' +
        'animation-delay:' + ((i % 12) * 0.12).toFixed(2) + 's;');
      grid.appendChild(tile);
    }
    bodyEl.appendChild(grid);
    if (foot) {
      foot.textContent = n + ' pending transaction' + (n === 1 ? '' : 's') +
        (n > shown ? ' (showing ' + shown + ')' : '') + ' · each tile = one queued tx';
    }
  }

  /* -- PRODUCERS ----------------------------------------------------------- */
  function renderProducers() {
    stopAnim();
    hideTip();
    bodyEl.innerHTML = '';
    var foot = document.getElementById('mosaicFoot');
    var blocks = getBlocks();
    if (!blocks.length) {
      bodyEl.appendChild(placeholder('Waiting for block data…',
        'Producer concentration appears once the 288-block window is loaded.'));
      if (foot) foot.textContent = '';
      return;
    }
    var counts = {}, total = 0, i;
    for (i = 0; i < blocks.length; i++) {
      var m = blocks[i].miner || 'unknown';
      counts[m] = (counts[m] || 0) + 1;
      total++;
    }
    var arr = Object.keys(counts).map(function (k) { return { m: k, c: counts[k] }; });
    arr.sort(function (a, b) { return b.c - a.c; });

    var top3 = 0;
    for (i = 0; i < Math.min(3, arr.length); i++) top3 += arr[i].c;
    var top3pct = total ? Math.round(top3 * 100 / total) : 0;

    var header = el('div',
      'display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;gap:6px;');
    header.appendChild(el('div', 'font-size:9px;letter-spacing:1.5px;color:var(--text3);',
      arr.length + ' PRODUCERS · ' + total + ' BLOCKS'));
    var badgeColor = top3pct >= 80 ? 'var(--red)' : (top3pct >= 60 ? 'var(--orange)' : 'var(--green)');
    var t3 = el('div', 'font-size:10px;color:' + badgeColor + ';font-weight:600;');
    t3.innerHTML = 'Top 3: ' + top3pct + '%';
    header.appendChild(t3);
    bodyEl.appendChild(header);

    var maxC = arr[0].c || 1;
    var list = el('div', 'display:flex;flex-direction:column;gap:6px;');
    var limit = Math.min(arr.length, 12);
    for (i = 0; i < limit; i++) {
      var p = arr[i];
      var pct = Math.round(p.c * 100 / total);
      var hue = hashHue(p.m);
      var row = el('div', 'display:flex;align-items:center;gap:8px;');
      var swatch = el('div',
        'width:10px;height:10px;border-radius:2px;flex:0 0 auto;' +
        'background:hsl(' + hue + ',62%,52%);');
      var label = el('div',
        'flex:0 0 130px;font-size:9.5px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;',
        p.m === 'unknown' ? 'unknown' : shortAddr(p.m));
      if (i === 0) label.style.color = 'var(--purple)';
      var barWrap = el('div',
        'flex:1;height:12px;background:var(--bg3);border:1px solid var(--border);border-radius:2px;overflow:hidden;');
      var bar = el('div',
        'height:100%;width:' + Math.max(2, Math.round(p.c * 100 / maxC)) + '%;' +
        'background:linear-gradient(90deg,hsl(' + hue + ',62%,46%),hsl(' + hue + ',62%,58%));' +
        'transition:width .5s ease;');
      barWrap.appendChild(bar);
      var val = el('div',
        'flex:0 0 66px;text-align:right;font-size:9.5px;color:var(--text3);',
        p.c + ' · ' + pct + '%');
      row.appendChild(swatch); row.appendChild(label);
      row.appendChild(barWrap); row.appendChild(val);
      list.appendChild(row);
    }
    bodyEl.appendChild(list);
    if (foot) {
      foot.textContent = 'Concentration over the last ' + total + ' blocks' +
        (arr.length > limit ? ' (top ' + limit + ' of ' + arr.length + ' shown)' : '') + '.';
    }
  }

  /* -- shared -------------------------------------------------------------- */
  function placeholder(title, subtitle) {
    var box = el('div',
      'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
      'min-height:150px;text-align:center;gap:6px;');
    // faint idle mosaic backdrop
    var grid = el('div', 'display:flex;flex-wrap:wrap;gap:3px;justify-content:center;max-width:260px;opacity:.25;margin-bottom:6px;');
    for (var i = 0; i < 48; i++) {
      grid.appendChild(el('div',
        'width:14px;height:14px;border-radius:2px;background:hsl(' + ((i * 33) % 360) + ',30%,22%);'));
    }
    box.appendChild(grid);
    box.appendChild(el('div', 'color:var(--text2);font-size:11px;letter-spacing:1px;', title));
    box.appendChild(el('div', 'color:var(--text3);font-size:9px;max-width:280px;', subtitle));
    return box;
  }

  function render() {
    if (!bodyEl) return;
    renderModes();
    if (currentTab === 'blocks') renderBlocks();
    else if (currentTab === 'mempool') renderMempool();
    else renderProducers();
  }

  /* -- lifecycle: piggyback on the explorer's existing refresh cadence ----- */
  function hookRefresh() {
    // Re-render when the explorer updates the stat cells it already touches on
    // every refresh cycle. No new interval, no override of existing functions.
    var targets = ['dMinersSub', 'dMempool'].map(function (id) {
      return document.getElementById(id);
    }).filter(Boolean);
    if (!targets.length) return;
    var scheduled = false;
    var obs = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        render();
      });
    });
    targets.forEach(function (t) {
      obs.observe(t, { childList: true, characterData: true, subtree: true });
    });
  }

  function onResize() {
    // Re-render the active tab (blocks re-lays the canvas; mempool/producers reflow).
    render();
  }

  function init() {
    if (!build()) return;
    render();
    hookRefresh();
    // Re-render the moment the card regains width (e.g. returning from a block /
    // search view) so the mosaic never stays squished waiting ~10 s for the next
    // refresh cycle. Event-driven (no interval).
    if (typeof ResizeObserver === 'function' && bodyEl) {
      var roLastW = 0, roT;
      var ro = new ResizeObserver(function () {
        var w = bodyEl.clientWidth || 0;
        if (w > 0 && Math.abs(w - roLastW) >= 2) {
          roLastW = w;
          clearTimeout(roT);
          roT = setTimeout(render, 60);
        }
      });
      try { ro.observe(bodyEl); } catch (e) {}
    }
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(onResize, 150);
    });
    // First data may land slightly after load; nudge once when it appears.
    var tries = 0;
    var poke = setInterval(function () {
      tries++;
      if (getBlocks().length || tries > 20) {
        clearInterval(poke);
        if (getBlocks().length) render();
      }
    }, 500);
  }

  // Inject the pending-tile keyframes once (scoped name, no clash).
  (function injectCss() {
    if (document.getElementById('mosaicKeyframes')) return;
    var s = document.createElement('style');
    s.id = 'mosaicKeyframes';
    s.textContent = '@keyframes mosaicPend{0%,100%{opacity:.55;transform:scale(1)}50%{opacity:1;transform:scale(1.08)}}';
    document.head.appendChild(s);
  })();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
