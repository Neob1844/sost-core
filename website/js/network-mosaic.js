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
 *                            miner=miner_address, lp=lottery payout, lw=winner).
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

    var wrap = el('div', 'position:relative;');
    canvas = document.createElement('canvas');
    canvas.style.cssText = 'width:100%;display:block;cursor:crosshair;';
    wrap.appendChild(canvas);
    bodyEl.appendChild(wrap);
    ctx = canvas.getContext('2d');

    layoutAndPaint();

    canvas.onmousemove = onCanvasMove;
    canvas.onmouseleave = function () { hoverIdx = -1; hideTip(); };
    canvas.onclick = onCanvasClick;

    var uniqueMiners = {};
    for (var i = 0; i < blocks.length; i++) uniqueMiners[blocks[i].miner || '?'] = 1;
    if (foot) {
      foot.innerHTML = 'Each tile = one block · colour = producer · brightness = difficulty &amp; recency · ' +
        Object.keys(uniqueMiners).length + ' producers in view · hover for detail';
    }
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
    for (i = 0; i < n; i++) {
      var b = lastBlocks[i];
      // Newest block last in array -> draw top-left as newest (reverse index).
      var order = n - 1 - i;                    // 0 = newest
      var col = order % L.cols;
      var row = Math.floor(order / L.cols);
      var x = L.pad + col * (L.tile + L.pad);
      var y = L.pad + row * (L.tile + L.pad);
      var hue = hashHue(b.miner);
      var norm = ((b.d || dMin) - dMin) / span;         // 0..1 difficulty
      var recency = 1 - (order / Math.max(1, n));        // 0..1 (newest ~1)
      var light = 30 + norm * 26 + recency * 10;         // 30..66%
      var sat = 58 + recency * 14;
      offCtx.fillStyle = 'hsl(' + hue + ',' + sat + '%,' + light + '%)';
      roundRect(offCtx, x, y, L.tile, L.tile, Math.min(3, L.tile / 6));
      offCtx.fill();
      // faint inner border for definition
      offCtx.strokeStyle = 'rgba(0,0,0,.35)';
      offCtx.lineWidth = 1;
      roundRect(offCtx, x + .5, y + .5, L.tile - 1, L.tile - 1, Math.min(3, L.tile / 6));
      offCtx.stroke();
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

    // Subtle pulsing glow on the newest few blocks (orders 0..4).
    var pulse = 0.5 + 0.5 * Math.sin(t / 620);
    var recent = Math.min(5, L.geo ? L.geo.n : 0);
    for (var o = 0; o < recent; o++) {
      var r = tileRectForOrder(o, L);
      var a = (0.10 + 0.22 * pulse) * (1 - o / 6);
      ctx.save();
      ctx.shadowColor = 'rgba(192,132,252,' + (0.55 * (1 - o / 6)) + ')';
      ctx.shadowBlur = 8 + 8 * pulse;
      ctx.strokeStyle = 'rgba(192,132,252,' + a + ')';
      ctx.lineWidth = 1.5;
      roundRect(ctx, r.x + .5, r.y + .5, r.s - 1, r.s - 1, Math.min(3, r.s / 6));
      ctx.stroke();
      ctx.restore();
    }
    // Hover ring
    if (hoverIdx >= 0 && lastLayout.geo) {
      var order = lastLayout.geo.n - 1 - hoverIdx;
      var hr = tileRectForOrder(order, L);
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      roundRect(ctx, hr.x + .5, hr.y + .5, hr.s - 1, hr.s - 1, Math.min(3, hr.s / 6));
      ctx.stroke();
    }
  }

  function startAnim() {
    stopAnim();
    animStart = performance.now();
    var loop = function (now) {
      if (currentTab !== 'blocks' || !canvas) { rafId = 0; return; }
      blitFrame(now - animStart);
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
    if (idx < 0) { hideTip(); return; }
    showBlockTip(lastBlocks[idx], ev);
    maybeEnrich(lastBlocks[idx], ev);
  }
  function onCanvasClick(ev) {
    var rect = canvas.getBoundingClientRect();
    var idx = hitTest(ev.clientX - rect.left, ev.clientY - rect.top);
    if (idx < 0) return;
    var h = lastBlocks[idx].h;
    // Reuse the explorer's own search if present; otherwise no-op.
    try {
      var inp = document.getElementById('searchIn');
      if (inp && typeof window.doSearch === 'function') {
        inp.value = String(h);
        window.doSearch();
      }
    } catch (e) {}
  }

  function showBlockTip(b, ev) {
    if (!b) return;
    var enr = blockCache[b.h];
    var lines = [];
    lines.push('<b style="color:var(--purple)">BLOCK #' + b.h + '</b>');
    if (enr && enr.hash) lines.push('hash&nbsp;&nbsp;&nbsp;' + shortHash(enr.hash));
    lines.push('miner&nbsp;&nbsp;' + (b.miner ? shortAddr(b.miner) : '<i>unknown</i>'));
    lines.push('time&nbsp;&nbsp;&nbsp;' + fmtAgo(b.t));
    if (enr && enr.tx_count != null) lines.push('txs&nbsp;&nbsp;&nbsp;&nbsp;' + enr.tx_count);
    if (enr && enr.subsidy != null) lines.push('reward&nbsp;' + fmtSost(enr.subsidy) + ' SOST');
    else if (b.lp > 0) lines.push('lottery&nbsp;' + fmtSost(b.lp) + ' SOST');
    var prof = enr && (enr.casert_mode || null);
    if (prof) lines.push('cASERT&nbsp;' + prof);
    if (b.d != null) lines.push('bits_q&nbsp;' + b.d.toLocaleString());
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
      if (currentTab === 'blocks' && hoverIdx >= 0 &&
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
    if (currentTab === 'blocks' && canvas && lastBlocks.length) {
      layoutAndPaint();
    }
  }

  function init() {
    if (!build()) return;
    render();
    hookRefresh();
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
