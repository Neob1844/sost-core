/* SOST Universe — EPIC SOUNDTRACK player, 45 tracks (DIRECTIVAS 4C-3 + 4I: style selector, 4H family recommendations). Independent module: no dependency on the scene engine.
 *
 * Rules it enforces:
 *  - sound ON and PLAYING by default (owner decisions, 4 Nov 2026): on the home page (script attribute data-autoplay) the player
 *    tries to start a random track as soon as the page has loaded. If the browser allows audible autoplay it really plays; if it
 *    blocks it, the pill says «Click to play» and the music starts on the first valid interaction anywhere (click, tap, Enter,
 *    the intro, SKIP INTRO…), never on form fields. The pill says «Playing» ONLY while the audio is really audible (element
 *    playing, time advancing, Web Audio graph running): no silent playback is ever shown as playing. Pause / mute are remembered
 *    (pref.on=false, pref.muted) and then nothing starts by itself;
 *  - nothing is downloaded on page open: the manifest is fetched on the first open/play, and only the selected track file is requested;
 *  - preferences (volume, mute, track, shuffle, repeat, panel, reactive) persist in localStorage inside try/catch, but sound NEVER
 *    starts without an interaction: on a later visit it waits again for the first interaction (only if pref.on);
 *  - Save-Data (navigator.connection.saveData) asks for a second confirmation, with the size of the file, before the first download;
 *  - never runs on wallet / security / key-handling pages (path guard below); no external services, no CDN, no RPC;
 *  - smooth gain fades between tracks (two media elements, Web Audio gains; element.volume fallback without Web Audio);
 *  - the credit of the active track is always visible in the panel (title, artist, licence, link to Music Credits).
 *
 * Optional Chromatic Audio Reactivity: while music plays, a modest energy value (0..1, smoothed) is emitted at <= 30 Hz as
 *   window CustomEvent 'sost:audio-energy'  detail {energy, low, mid, high, t}
 * and, if the scene engine exposes it, forwarded to window.SOSTUniverse.scene.setAudioEnergy(energy) (0 is sent when the music stops).
 * Scene integration: on 'sostu:scenechange' the player only SUGGESTS the mapped track (shown in the panel); it never starts or switches.
 *
 * Public API (window.SOSTAudio): play(id?), pause(), toggle(), next(), prev(), select(id, {play}), setVolume(0..1), mute(bool),
 *   open(), close(), state(), suggestFor(sceneId), splashCue(ms), mount(el)
 */
(function (root) {
  'use strict';
  var doc = root.document;
  // ---- hard guard: never on wallet or security tools ----
  // 4C-3 + 4J: no music on wallet pages (legacy wallet and the Digital Vault), security / key tools, trading flows, the hybrid /
  // legacy / Universe explorers, the Control Room nor the Explorer PWA. A page may also opt out with
  // <meta name="sost-audio" content="off"> or <html data-no-audio>.
  // Owner order 4 Nov 2026 (global music player): the public Explorer, sost-explorer.html, plays the same soundtrack as the rest of
  // the site (ALLOW below); every other blocked path stays blocked.
  var BLOCK = /(wallet|vault|security|seed|keys?[-_.]|sign(er|ing)?[-_.]|login|swap|dex|otc|cli-tools|e2e|troubleshooter|explorer|control-room|sost-app)/i;
  var ALLOW = /\/sost-explorer\.html$/i;
  function optedOut() { try { var m = doc.querySelector('meta[name="sost-audio"]'); return (m && /off|none|no/i.test(m.content)) || doc.documentElement.hasAttribute('data-no-audio'); } catch (e) { return false; } }
  if ((BLOCK.test(root.location.pathname) && !ALLOW.test(root.location.pathname)) || optedOut() || root.SOSTAudio) return;

  var SCRIPT = doc.currentScript;
  var BASE = (function () { try { return new URL((SCRIPT && SCRIPT.getAttribute('data-audio-base')) || '../audio/', SCRIPT ? SCRIPT.src : root.location.href).href; } catch (e) { return 'audio/'; } })();
  var CREDITS = (function () { try { return new URL('../music-credits.html', SCRIPT ? SCRIPT.src : root.location.href).href; } catch (e) { return 'music-credits.html'; } })();
  var KEY = 'sostu_audio_v1';
  var WAIT_READY = !!(SCRIPT && SCRIPT.hasAttribute('data-wait-ready'));
  function explorerReady() { return !WAIT_READY || !!(root.__exLoader && root.__exLoader.state); }
  var FADE = 1.6; // seconds, cross-fade between tracks
  var EN_HZ = 30;

  function lsGet() { try { var v = JSON.parse(root.localStorage.getItem(KEY) || 'null'); return v && typeof v === 'object' ? v : {}; } catch (e) { return {}; } }
  function lsSet(o) { try { root.localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  var saved = lsGet();
  var pref = {
    vol: typeof saved.vol === 'number' && saved.vol >= 0 && saved.vol <= 1 ? saved.vol : 0.6,
    muted: !!saved.muted,
    track: typeof saved.track === 'string' ? saved.track : null,
    shuffle: saved.shuffle === undefined ? true : !!saved.shuffle,   // random selection by default (owner, 4 Nov 2026)
    repeat: saved.repeat === 'one' || saved.repeat === 'off' ? saved.repeat : 'all',
    panel: !!saved.panel,
    reactive: saved.reactive !== false,
    picked: !!saved.picked,
    style: typeof saved.style === 'string' ? saved.style : 'all',
    on: saved.on !== false
  };
  function persist() { lsSet(pref); }
  // ---- continuity between pages (no SPA): this tab remembers the track, the second and whether it was really sounding ----
  var KR = 'sostu_audio_resume', lastSaveR = 0, resumeHint = null;
  function readResume() { try { var r = JSON.parse(root.sessionStorage.getItem(KR) || 'null'); return r && typeof r.id === 'string' && Date.now() - (r.at || 0) < 1800000 ? r : null; } catch (e) { return null; } }
  function saveResume() {
    try { var d = decks[live]; if (!d || !curId) return; var t = d.el.currentTime || 0, du = d.el.duration || 0;
      root.sessionStorage.setItem(KR, JSON.stringify({ id: curId, t: du && t > du - 4 ? 0 : Math.round(t * 10) / 10, on: !!(playing && audible), at: Date.now() })); } catch (e) {}
  }
  root.addEventListener('pagehide', saveResume);

  var M = null, manifestP = null;           // manifest (lazy)
  var ctx = null, master = null, analyser = null, freq = null;
  var decks = [], live = 0;                 // two decks {el, gain, src}
  var playing = false, curId = null, suggestion = null, sceneNow = null;
  var history = [], saveOk = false, enTimer = 0, enSmooth = 0;
  var audible = false, blocked = false, lastT = -1;   // audible: really sounding now (not the intent flag 'playing')
  var ui = {};

  function saveData() { try { var c = navigator.connection; return !!(c && c.saveData); } catch (e) { return false; } }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function loadManifest() {
    if (!manifestP) manifestP = fetch(BASE + 'manifest.json', { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw new Error('manifest ' + r.status); return r.json(); })
      .then(function (m) { M = m; if (!byId(pref.track)) pref.track = null; renderList(); showTrack(curId || pref.track || (M.tracks[0] && M.tracks[0].id)); applySuggestion(); return m; })
      .catch(function (e) { manifestP = null; setMsg('Music library unavailable (' + e.message + ').'); throw e; });
    return manifestP;
  }
  function byId(id) { if (!M || !id) return null; for (var i = 0; i < M.tracks.length; i++) if (M.tracks[i].id === id) return M.tracks[i]; return null; }
  function idx(id) { if (!M) return -1; for (var i = 0; i < M.tracks.length; i++) if (M.tracks[i].id === id) return i; return -1; }
  var probe = doc.createElement('audio');
  function pickSrc(t) {
    var s = t.sources || [];
    for (var i = 0; i < s.length; i++) if (probe.canPlayType && probe.canPlayType(s[i].type).replace(/no/, '')) return s[i];
    return s[s.length - 1];
  }

  // ---- audio graph (created on the first gesture only) ----
  // The media elements play on their own first (element.volume fades). They are routed through Web Audio only once the
  // AudioContext is really "running": a context that stays suspended (no audio device, strict autoplay policy) would
  // otherwise silence a routed element. If it never runs, playback simply continues without the analyser (energy 0).
  function ensureGraph(noCtx) {
    if (!decks.length) {
      for (var i = 0; i < 2; i++) {
        var el = new Audio(); el.preload = 'none'; el.crossOrigin = 'anonymous'; el.volume = 0;
        el.addEventListener('ended', onEnded);
        el.addEventListener('error', function () { if (this === decks[live].el && this.getAttribute('src')) setMsg('Could not load this track.'); });
        el.addEventListener('waiting', function () { if (this === decks[live].el) setBusy(true); });
        el.addEventListener('playing', function () { if (this === decks[live].el) { setBusy(false); blocked = false; setMsg(''); checkAudible(); } });
        el.addEventListener('pause', function () { if (this === decks[live].el) checkAudible(); });
        decks.push({ el: el, gain: null });
      }
      applyMaster(0);
    }
    // the Web Audio graph (analyser for the scene reactivity) is created on a user gesture only: an autoplay start plays the
    // element directly, so a suspended context can never silence it
    if (!ctx && !noCtx) { var AC = root.AudioContext || root.webkitAudioContext; if (AC) { try { ctx = new AC(); ctx.addEventListener('statechange', function () { wire(); checkAudible(); }); } catch (e) { ctx = null; } } }
    if (ctx && ctx.state !== 'running') { try { ctx.resume().then(wire, function () {}); } catch (e) {} }
    wire();
  }
  function wire() {
    if (!ctx || ctx.state !== 'running' || master) return;
    try {
      master = ctx.createGain(); analyser = ctx.createAnalyser(); analyser.fftSize = 256; analyser.smoothingTimeConstant = 0.82;
      freq = new Uint8Array(analyser.frequencyBinCount); master.connect(analyser); analyser.connect(ctx.destination);
      decks.forEach(function (d, k) {
        var src = ctx.createMediaElementSource(d.el); d.gain = ctx.createGain();
        d.gain.gain.value = (k === live && playing) ? 1 : 0; d.el.volume = 1; d.el.muted = false;
        src.connect(d.gain); d.gain.connect(master);
      });
      master.gain.value = 0; applyMaster(0.2);
      if (playing) energyLoop();
    } catch (e) { master = null; analyser = null; }
  }
  function now() { return ctx ? ctx.currentTime : 0; }
  function ramp(param, to, sec) { var t = now(); try { param.cancelScheduledValues(t); param.setValueAtTime(param.value, t); param.linearRampToValueAtTime(to, t + Math.max(0.01, sec)); } catch (e) { param.value = to; } }
  function applyMaster(sec) {
    var v = pref.muted ? 0 : pref.vol * pref.vol; // perceptual curve
    if (master) ramp(master.gain, v, sec == null ? 0.25 : sec);
    else decks.forEach(function (d, k) { d.el.muted = pref.muted; if (k === live && playing) d.el.volume = Math.max(0, Math.min(1, pref.vol * pref.vol)); });
  }
  var fadeRAF = {};
  function fadeDeck(d, to, sec, done) {
    if (d.gain) { ramp(d.gain.gain, to, sec); if (done) setTimeout(done, sec * 1000 + 30); return; }
    // fallback: element volume (no Web Audio)
    var k = decks.indexOf(d), from = d.el.volume, t0 = performance.now(), target = to * pref.vol * pref.vol;
    cancelAnimationFrame(fadeRAF[k]);
    (function step(tt) { var p = Math.max(0, Math.min(1, (tt - t0) / (sec * 1000))); d.el.volume = Math.max(0, Math.min(1, from + (target - from) * p)); if (p < 1) fadeRAF[k] = requestAnimationFrame(step); else if (done) done(); })(t0);
  }

  // ---- transport ----
  function start(id, opts) {
    opts = opts || {};
    var t = byId(id); if (!t) return Promise.resolve(false);
    if (saveData() && !saveOk && !opts.confirmed) { askSaveData(t); return Promise.resolve(false); }
    ensureGraph(opts.auto);
    var s = pickSrc(t), cur = decks[live], nxt = decks[1 - live];
    var same = curId === id && cur.el.getAttribute('src');
    if (same) { var pp = cur.el.play(); playing = true; afterState(); return (pp && pp.then ? pp : Promise.resolve()).then(function () { fadeDeck(cur, 1, 0.5); return true; }, function (e) { onPlayErr(e); return false; }); }
    if (curId && curId !== id) history.push(curId);
    curId = id; pref.track = id; persist();
    nxt.el.src = (s.src.indexOf('//') >= 0 ? s.src : BASE + s.src) + (opts.at > 1 ? '#t=' + opts.at.toFixed(1) : '');   // #t=: continue at that second
    if (!(opts.at > 1)) nxt.el.currentTime = 0;
    if (nxt.gain) nxt.gain.gain.value = 0; else nxt.el.volume = 0;
    setBusy(true);
    var p = nxt.el.play();
    var old = cur; live = 1 - live;
    if (playing && old.el.getAttribute('src')) fadeDeck(old, 0, FADE, function () { old.el.pause(); old.el.removeAttribute('src'); try { old.el.load(); } catch (e) {} });
    else { old.el.pause(); if (old.el.getAttribute('src')) { old.el.removeAttribute('src'); try { old.el.load(); } catch (e) {} } }
    fadeDeck(nxt, 1, playing ? FADE : 0.8);
    playing = true; showTrack(id); afterState();
    return (p && p.then ? p : Promise.resolve()).then(function () { return true; }).catch(function (e) { onPlayErr(e); return false; });
  }
  function onPlayErr(e) {
    if (e && e.name === 'AbortError') return; playing = false; setBusy(false);
    if (e && e.name === 'NotAllowedError') { blocked = true; setMsg('Your browser blocked autoplay. Click or tap anywhere, or press Enter, to start the soundtrack.'); armFirstInteraction(); }
    else setMsg('Playback could not start — press play again.');
    checkAudible(); afterState();
  }
  // audible = the live element is playing, its time advances, and (if it is routed through Web Audio) the context is running
  function checkAudible() {
    var el = decks.length ? decks[live].el : null, routed = !!(decks.length && decks[live].gain);
    var t = el ? el.currentTime : -1, adv = el && t !== lastT && t > 0; lastT = t;
    var a = !!(playing && el && !el.paused && !el.ended && el.readyState > 2 && (adv || audible) && (!routed || (ctx && ctx.state === 'running')));
    if (a !== audible) { audible = a; afterState(); }
  }
  function pause() {
    if (!decks.length || !playing) return;
    var d = decks[live]; playing = false;
    fadeDeck(d, 0, 0.35, function () { if (!playing) d.el.pause(); });
    afterState();
  }
  var STYLES = [['all', 'All'], ['epic', 'Epic'], ['cosmic', 'Cosmic'], ['dark', 'Dark'], ['electronic', 'Electronic'], ['ambient', 'Ambient'], ['orig', 'Original 20'], ['new', 'New 25']];
  function inStyle(t, st) { st = st || pref.style; return st === 'all' || (st === 'new' ? t.batch === '4I' : st === 'orig' ? t.batch !== '4I' : t.style === st); }
  function visible() { if (!M) return []; var v = M.tracks.filter(function (t) { return inStyle(t); }); return v.length ? v : M.tracks; }
  function order() { return visible().map(function (t) { return t.id; }); }
  function nextId(dir) {
    var ids = order(); if (!ids.length) return null;
    if (pref.shuffle && dir > 0) {
      var pool = ids.filter(function (x) { return x !== curId && history.slice(-6).indexOf(x) < 0; }); if (!pool.length) pool = ids.filter(function (x) { return x !== curId; });
      var a = new Uint32Array(1); try { root.crypto.getRandomValues(a); } catch (e) { a[0] = Math.floor(Math.random() * 1e9); }
      return pool[a[0] % pool.length];
    }
    if (dir < 0 && pref.shuffle && history.length) return history.pop();
    var i = ids.indexOf(curId || pref.track); if (i < 0) return ids[dir > 0 ? 0 : ids.length - 1]; return ids[(i + dir + ids.length) % ids.length];
  }
  function onEnded() {
    if (this !== decks[live].el) return;
    if (pref.repeat === 'one') { this.currentTime = 0; this.play().catch(onPlayErr); return; }
    var ids = order(), i = ids.indexOf(curId);
    if (pref.repeat === 'off' && !pref.shuffle && i === ids.length - 1) { playing = false; afterState(); return; }
    playing = false; start(nextId(1));
  }
  function gesture(fn) { return function (e) { ensureGraph(); loadManifest().then(function () { fn(e); }).catch(function () {}); }; }

  // ---- energy (audio reactivity) ----
  function energyLoop() {
    clearInterval(enTimer); enTimer = 0;
    if (!analyser || !playing) { emitEnergy(0); return; }
    enTimer = setInterval(function () {
      if (doc.hidden || !playing) return;
      analyser.getByteFrequencyData(freq);
      var n = freq.length, lo = 0, mi = 0, hi = 0, a = Math.floor(n * 0.08), b = Math.floor(n * 0.4);
      for (var i = 1; i < n; i++) { var v = freq[i] / 255; if (i < a) lo += v; else if (i < b) mi += v; else hi += v; }
      lo /= Math.max(1, a - 1); mi /= Math.max(1, b - a); hi /= Math.max(1, n - b);
      var e = Math.min(1, lo * 0.55 + mi * 0.35 + hi * 0.25);
      e = e * (pref.muted ? 0 : 1);
      enSmooth += (e - enSmooth) * (e > enSmooth ? 0.35 : 0.08); // fast attack, slow release: a breath, not an equaliser
      emitEnergy(enSmooth, lo, mi, hi);
    }, Math.round(1000 / EN_HZ));
  }
  function emitEnergy(e, lo, mi, hi) {
    var d = { energy: +e.toFixed(3), low: +(lo || 0).toFixed(3), mid: +(mi || 0).toFixed(3), high: +(hi || 0).toFixed(3), t: Date.now() };
    try { root.dispatchEvent(new CustomEvent('sost:audio-energy', { detail: d })); } catch (x) {}
    if (pref.reactive || e === 0) { try { var S = root.SOSTUniverse && root.SOSTUniverse.scene; if (S && S.setAudioEnergy) S.setAudioEnergy(pref.reactive ? d.energy : 0); } catch (x) {} }
    if (ui.meter) ui.meter.style.setProperty('--e', d.energy);
  }

  // ---- scene suggestions (never auto-start) ----
  function suggestFor(sceneId) {
    if (!M || !M.scenes) return null;
    var m = M.scenes[sceneId]; if (m && m.tracks && m.tracks.length) return m.tracks[0];
    return null;
  }
  function familyOf(sc) {
    if (sc.family) return sc.family;
    try { var R = root.SOSTU && root.SOSTU.scenes, x = R && R.byId && R.byId(sc.id); return x && x.family || null; } catch (e) { return null; }
  }
  /** Recommendation order: the scene's own entry, then its 4H cosmic family, then its mood. Rotates within a family list so the
   *  scenes of one family do not all suggest the same track; never starts playback. */
  function recommend(sc) {
    var id = suggestFor(sc.id); if (id) return id;
    var fam = familyOf(sc), F = fam && M.families && M.families[fam];
    if (F && F.tracks && F.tracks.length) { var k = 0; for (var i = 0; i < String(sc.id).length; i++) k = (k * 31 + String(sc.id).charCodeAt(i)) >>> 0; return F.tracks[k % F.tracks.length]; }
    return (M.moods && M.moods[sc.mood] && M.moods[sc.mood][0]) || null;
  }
  function applySuggestion() {
    if (!sceneNow || !M) return;
    var id = recommend(sceneNow);
    suggestion = byId(id) ? id : null;
    if (!playing && !pref.picked && suggestion) showTrack(suggestion);
    renderSuggestion();
  }
  root.addEventListener('sostu:scenechange', function (e) { sceneNow = e.detail || null; if (M) applySuggestion(); });

  // ---- UI ----
  var ICON = {
    note: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18V5l11-2v13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="18" r="3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17" cy="16" r="3" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l12.5-7.5z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 4.5h4v15h-4zM13.5 4.5h4v15h-4z" fill="currentColor"/></svg>',
    prev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h2.5v14H6zM20 5v14L9.5 12z" fill="currentColor"/></svg>',
    next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15.5 5H18v14h-2.5zM4 5v14l10.5-7z" fill="currentColor"/></svg>',
    vol: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    mute: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 9.5l5 5m0-5l-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    shuf: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h3.5c5 0 6 10 11 10H21M3 17h3.5c2 0 3.2-1.6 4.2-3.5M14 8.6C15 7.6 16 7 17.5 7H21M18.5 4.5L21 7l-2.5 2.5M18.5 14.5L21 17l-2.5 2.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    rep: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11V9a3 3 0 0 1 3-3h12M16 3l3 3-3 3M20 13v2a3 3 0 0 1-3 3H5M8 21l-3-3 3-3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    list: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };
  function mount(host) {
    if (ui.root) return ui.root;
    var r = doc.createElement('div'); r.className = 'ua' + (SCRIPT && SCRIPT.getAttribute('data-dock') === 'low' ? ' ua-low' : ''); r.setAttribute('data-state', 'off');
    r.innerHTML =
      '<button class="ua-fab" type="button" aria-expanded="false" aria-controls="uaPanel" aria-label="Soundtrack: sound off. Open the music player">' + ICON.note + '<span class="ua-fab-t">Sound off</span><i class="ua-meter" aria-hidden="true"></i></button>' +
      '<section class="ua-panel" id="uaPanel" role="region" aria-label="Music player" hidden>' +
        '<header class="ua-h"><span class="ua-k">EPIC SOUNDTRACK</span><button class="ua-ib ua-close" type="button" aria-label="Hide music player">' + ICON.x + '</button></header>' +
        '<div class="ua-now" aria-live="polite"><b class="ua-title">' + (pref.on ? 'Sound is on' : 'Sound is off') + '</b><span class="ua-artist">' + (pref.on ? 'Music starts when you click, tap or press a key. Press pause to turn it off.' : 'Nothing plays until you press play.') + '</span><small class="ua-credit"></small></div>' +
        '<div class="ua-sug" hidden></div>' +
        '<div class="ua-prog" aria-hidden="true"><i></i></div>' +
        '<div class="ua-ctl">' +
          '<button class="ua-ib ua-prev" type="button" aria-label="Previous track">' + ICON.prev + '</button>' +
          '<button class="ua-ib ua-play" type="button" aria-label="Play">' + ICON.play + '</button>' +
          '<button class="ua-ib ua-next" type="button" aria-label="Next track">' + ICON.next + '</button>' +
          '<button class="ua-ib ua-shuf" type="button" aria-pressed="false" aria-label="Shuffle">' + ICON.shuf + '</button>' +
          '<button class="ua-ib ua-rep" type="button" aria-label="Repeat: all">' + ICON.rep + '<em class="ua-rep-t">ALL</em></button>' +
          '<button class="ua-ib ua-mute" type="button" aria-pressed="false" aria-label="Mute">' + ICON.vol + '</button>' +
          '<input class="ua-vol" type="range" min="0" max="100" step="1" aria-label="Volume">' +
        '</div>' +
        '<div class="ua-msg" role="status"></div>' +
        '<details class="ua-lib"><summary>' + ICON.list + '<span class="ua-lib-t">All tracks</span></summary>' +
          '<div class="ua-styles" role="group" aria-label="Style">' + STYLES.map(function (x) { return '<button type="button" class="ua-st" data-style="' + x[0] + '" aria-pressed="false">' + x[1] + ' <i></i></button>'; }).join('') + '</div>' +
          '<ol class="ua-list" aria-label="Track list"><li class="ua-empty">The list loads when you open it.</li></ol></details>' +
        '<label class="ua-react"><input type="checkbox" class="ua-rx"> Visuals react subtly to the music</label>' +
        '<a class="ua-cr" href="' + esc(CREDITS) + '">Music credits &amp; licences</a>' +
      '</section>';
    (host || doc.body).appendChild(r);
    var q = function (s) { return r.querySelector(s); };
    ui = { root: r, fab: q('.ua-fab'), fabT: q('.ua-fab-t'), meter: q('.ua-fab'), panel: q('.ua-panel'), title: q('.ua-title'), artist: q('.ua-artist'), credit: q('.ua-credit'),
      sug: q('.ua-sug'), prog: q('.ua-prog i'), play: q('.ua-play'), prev: q('.ua-prev'), next: q('.ua-next'), shuf: q('.ua-shuf'), rep: q('.ua-rep'), repT: q('.ua-rep-t'),
      mute: q('.ua-mute'), vol: q('.ua-vol'), msg: q('.ua-msg'), list: q('.ua-list'), lib: q('.ua-lib'), libT: q('.ua-lib-t'), styles: q('.ua-styles'), rx: q('.ua-rx'), close: q('.ua-close') };
    ui.vol.value = Math.round(pref.vol * 100); ui.rx.checked = pref.reactive;
    ui.fab.addEventListener('click', function () { setPanel(ui.panel.hidden); if (!ui.panel.hidden) loadManifest().catch(function () {}); });
    ui.close.addEventListener('click', function () { setPanel(false); ui.fab.focus(); });
    ui.play.addEventListener('click', gesture(function () { if (playing) { pref.on = false; persist(); pause(); } else { pref.on = true; persist(); start(curId || pref.track || suggestion || M.tracks[0].id); } }));
    ui.next.addEventListener('click', gesture(function () { pref.picked = true; persist(); if (playing) start(nextId(1)); else showTrack(nextId(1), true); }));
    ui.prev.addEventListener('click', gesture(function () {
      pref.picked = true; persist();
      var d = decks[live]; if (playing && d && d.el.currentTime > 4) { d.el.currentTime = 0; return; }
      if (playing) start(nextId(-1)); else showTrack(nextId(-1), true);
    }));
    ui.shuf.addEventListener('click', function () { pref.shuffle = !pref.shuffle; persist(); afterState(); });
    ui.rep.addEventListener('click', function () { pref.repeat = { all: 'one', one: 'off', off: 'all' }[pref.repeat]; persist(); afterState(); });
    ui.mute.addEventListener('click', function () { pref.muted = !pref.muted; persist(); applyMaster(); afterState(); });
    ui.vol.addEventListener('input', function () { pref.vol = Math.max(0, Math.min(1, ui.vol.value / 100)); if (pref.muted && pref.vol > 0) pref.muted = false; applyMaster(0.08); persist(); afterState(); });
    ui.rx.addEventListener('change', function () { pref.reactive = ui.rx.checked; persist(); if (!pref.reactive) emitEnergy(0); });
    ui.styles.querySelectorAll('.ua-st').forEach(function (b) { b.addEventListener('click', function () { pref.style = b.getAttribute('data-style'); persist(); loadManifest().then(renderList).catch(function () {}); }); });
    ui.lib.addEventListener('toggle', function () { if (ui.lib.open) loadManifest().catch(function () {}); });
    r.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !ui.panel.hidden) { setPanel(false); ui.fab.focus(); } });
    setInterval(progress, 500);
    doc.addEventListener('visibilitychange', function () { if (!doc.hidden && playing) energyLoop(); });
    if (pref.panel) setPanel(true, true);
    armFirstInteraction();
    afterState();
    // home page: try to really start the soundtrack once the page has loaded (no muted or silent fake start)
    var RS = readResume(), resume = RS && RS.on ? RS : null;   // the previous page of this tab was really playing: continue it
    resumeHint = resume;
    if (SCRIPT && (SCRIPT.hasAttribute('data-autoplay') || resume) && pref.on && !pref.muted && !saveData()) {
      var go = function () { setTimeout(function () { if (playing || !pref.on) return;
        loadManifest().then(function () { if (playing || !pref.on) return; var ids = order(), id = resume && byId(resume.id) ? resume.id : pref.picked && pref.track ? pref.track : ids[Math.floor(Math.random() * ids.length)]; return start(id, { auto: true, at: resume && resume.id === id ? resume.t : 0 }); }).catch(function () {}); }, 300); };
      // data-wait-ready (Explorer): nothing is fetched or played before the Explorer's loading screen has finished
      var when = function () { if (!WAIT_READY) return go(); (function w(n) { if (explorerReady()) return go(); if (n < 450) setTimeout(function () { w(n + 1); }, 400); })(0); };
      if (doc.readyState === 'complete') when(); else root.addEventListener('load', when, { once: true });
    }
    return r;
  }
  function setPanel(open, silent) {
    ui.panel.hidden = !open; ui.fab.setAttribute('aria-expanded', String(open)); ui.root.classList.toggle('open', open);
    if (!silent) { pref.panel = open; persist(); }
    if (open && silent) { /* restored open panel: still nothing is fetched until the visitor interacts */ }
  }
  function setMsg(s) { if (ui.msg) { ui.msg.textContent = s || ''; } }
  function setBusy(b) { if (ui.root) ui.root.classList.toggle('busy', !!b); }
  function catLabel(c) { return (M && M.categories && M.categories[c]) || c; }
  function renderList() {
    if (!ui.list || !M) return;
    var h = '', last = null, vis = visible();
    vis.forEach(function (t) {
      var n = idx(t.id) + 1;
      if (t.category !== last) { h += '<li class="ua-cat" aria-hidden="true">' + esc(catLabel(t.category)) + '</li>'; last = t.category; }
      h += '<li><button type="button" class="ua-tr" data-id="' + esc(t.id) + '"><span class="ua-n">' + n + '</span><span class="ua-tt">' + esc(t.title) + (t.batch === '4I' ? ' <em class="ua-new">NEW</em>' : '') + '</span><span class="ua-ta">' + esc(t.artist) + ' · ' + esc(t.duration) + '</span></button></li>';
    });
    ui.list.innerHTML = h;
    if (ui.libT) ui.libT.textContent = (pref.style === 'all' ? 'All ' + M.tracks.length + ' tracks' : vis.length + ' of ' + M.tracks.length + ' tracks');
    if (ui.styles) ui.styles.querySelectorAll('.ua-st').forEach(function (b) {
      var k = b.getAttribute('data-style'), c = k === 'all' ? M.tracks.length : M.tracks.filter(function (t) { return inStyle(t, k); }).length;
      b.setAttribute('aria-pressed', String(k === pref.style)); b.querySelector('i').textContent = c; b.hidden = !c;
    });
    ui.list.querySelectorAll('.ua-tr').forEach(function (b) { b.addEventListener('click', function () { pref.picked = true; persist(); start(b.getAttribute('data-id')); }); });
    afterState();
  }
  function renderSuggestion() {
    if (!ui.sug) return;
    var t = byId(suggestion);
    if (!t || !sceneNow || (playing && curId === t.id)) { ui.sug.hidden = true; return; }
    ui.sug.hidden = false;
    ui.sug.innerHTML = '<span>Suggested for <b>' + esc(sceneNow.name || sceneNow.id) + '</b>: ' + esc(t.title) + '</span> <button type="button" class="ua-sugb">Play suggestion</button>';
    ui.sug.querySelector('.ua-sugb').addEventListener('click', function () { pref.picked = true; persist(); start(t.id); });
  }
  function showTrack(id, pick) {
    var t = byId(id); if (!t || !ui.title) return;
    if (pick) { pref.track = id; curId = playing ? curId : null; persist(); }
    ui.title.textContent = t.title;
    ui.artist.textContent = t.artist + (t.performer && t.performer !== t.artist ? ' — ' + t.performer : '');
    ui.credit.innerHTML = esc(t.credit_short) + (t.license_url ? ' · <a href="' + esc(t.license_url) + '" rel="license noopener" target="_blank">' + esc(t.license) + '</a>' : '');
    ui.root.setAttribute('data-track', id);
    if (pick) setMsg('');
    afterState();
  }
  function progress() {
    if (!decks.length || !ui.prog) return;
    checkAudible(); var el = decks[live].el; var p = el.duration ? el.currentTime / el.duration : 0;
    if (Date.now() - lastSaveR > 2000) { lastSaveR = Date.now(); saveResume(); }
    ui.prog.style.transform = 'scaleX(' + (p || 0).toFixed(4) + ')';
  }
  function askSaveData(t) {
    setPanel(true);
    var mb = t.bytes ? (t.bytes / 1048576).toFixed(1) + ' MB' : 'a few MB';
    ui.msg.innerHTML = 'Data saver is on. This track is ' + esc(mb) + '. <button type="button" class="ua-sd">Play anyway</button>';
    ui.msg.querySelector('.ua-sd').addEventListener('click', function () { saveOk = true; setMsg(''); start(t.id, { confirmed: true }); });
  }
  function afterState() {
    if (!ui.root) return;
    var t = byId(curId || pref.track);
    ui.root.setAttribute('data-state', audible ? (pref.muted ? 'muted' : 'on') : playing ? 'starting' : blocked ? 'blocked' : (pref.on ? 'armed' : 'off'));
    ui.play.innerHTML = playing ? ICON.pause : ICON.play; ui.play.setAttribute('aria-label', playing ? 'Pause' : 'Play');
    ui.shuf.setAttribute('aria-pressed', String(pref.shuffle));
    ui.rep.setAttribute('aria-label', 'Repeat: ' + pref.repeat); ui.repT.textContent = pref.repeat === 'one' ? '1' : pref.repeat === 'all' ? 'ALL' : 'OFF'; ui.rep.classList.toggle('on', pref.repeat !== 'off');
    ui.mute.innerHTML = pref.muted ? ICON.mute : ICON.vol; ui.mute.setAttribute('aria-pressed', String(pref.muted)); ui.mute.setAttribute('aria-label', pref.muted ? 'Unmute' : 'Mute');
    ui.vol.value = Math.round(pref.vol * 100); ui.vol.setAttribute('aria-valuetext', Math.round(pref.vol * 100) + '%');
    var lbl = audible ? (pref.muted ? 'Muted' : 'Playing') : playing ? 'Starting…' : (pref.on ? 'Click to play' : 'Sound off');
    ui.fabT.textContent = lbl;
    ui.fab.setAttribute('aria-label', 'Soundtrack: ' + lbl.toLowerCase() + (t && playing ? ', ' + t.title + ' by ' + t.artist : '') + (!playing && pref.on ? ' (the music starts on your first click, tap or Enter)' : '') + '. ' + (ui.panel.hidden ? 'Open' : 'Close') + ' the music player');
    if (ui.list) ui.list.querySelectorAll('.ua-tr').forEach(function (b) { var on = b.getAttribute('data-id') === (curId || pref.track); if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); });
    if (playing) energyLoop(); else { clearInterval(enTimer); enTimer = 0; enSmooth = 0; emitEnergy(0); }
    renderSuggestion();
    mediaSession(t);
  }
  function mediaSession(t) {
    var ms = navigator.mediaSession; if (!ms || !t || !playing) return;
    try {
      ms.metadata = new root.MediaMetadata({ title: t.title, artist: t.artist, album: 'SOST — Epic Soundtrack' });
      ms.setActionHandler('play', function () { start(curId); }); ms.setActionHandler('pause', pause);
      ms.setActionHandler('nexttrack', function () { start(nextId(1)); }); ms.setActionHandler('previoustrack', function () { start(nextId(-1)); });
    } catch (e) {}
  }

  // ---- sound ON by default: start on the first interaction with the page ----
  var armed = false;
  // touchstart / pointerdown of a touch are NOT a user activation in Chrome or Edge (touchend, pointerup and click are): every one is
  // listened to and the player stays armed until the audio really plays
  var ARM_EVENTS = ['pointerdown', 'pointerup', 'touchend', 'click', 'keydown'], trying = false;
  function disarm() { if (!armed) return; armed = false; ARM_EVENTS.forEach(function (t) { doc.removeEventListener(t, onFirst, true); }); }
  function onFirst(e) {
    if (e.type === 'keydown' && (e.key === 'Escape' || e.key === 'Tab' || e.altKey || e.ctrlKey || e.metaKey)) return; // not a user activation in every browser
    // never start sound while the visitor is filling a form: stay armed until an interaction outside form fields
    var t = e.target; if (t && t.closest && t.closest('input,textarea,select,[contenteditable],form,dialog')) return;
    if (!explorerReady()) return;                                      // Explorer still loading its data: stay armed, download nothing yet
    if (ui.root && ui.root.contains(e.target)) { disarm(); return; }   // the player's own buttons handle themselves
    if (!pref.on) { disarm(); return; }
    try { var ua = navigator.userActivation; if (ua && !ua.isActive) return; } catch (x) {}   // not an activating event (e.g. touchstart): wait for the next
    ensureGraph();                                      // creates / resumes the Web Audio context inside the gesture
    if (audible) { disarm(); return; }                  // autoplay already sounding: this gesture only enabled the analyser
    if ((playing && !blocked) || trying) return;        // a start is in progress: wait for its result, stay armed
    trying = true;
    loadManifest().then(function () { if (!pref.on || audible) return audible;
      var rh = !curId && resumeHint && byId(resumeHint.id) ? resumeHint : null;   // blocked autoplay on a continued page: same track, same second
      return start(curId || (rh && rh.id) || pref.track || suggestion || M.tracks[0].id, { at: rh ? rh.t : 0 }); })
      .then(function (ok) { trying = false; if (ok) disarm(); }, function () { trying = false; });
  }
  function armFirstInteraction() {
    if (!pref.on || playing || armed) return;
    armed = true; ARM_EVENTS.forEach(function (t) { doc.addEventListener(t, onFirst, { capture: true, passive: true }); });
  }

  var API = {
    play: function (id) { pref.on = true; persist(); disarm(); return loadManifest().then(function () { if (id) { pref.picked = true; persist(); } return start(id || curId || pref.track || suggestion || M.tracks[0].id); }); },
    pause: function () { pref.on = false; persist(); disarm(); pause(); },
    toggle: function () { return playing ? (API.pause(), Promise.resolve(false)) : API.play(); },
    next: function () { return loadManifest().then(function () { return start(nextId(1)); }); },
    prev: function () { return loadManifest().then(function () { return start(nextId(-1)); }); },
    select: function (id, o) { return loadManifest().then(function () { pref.picked = true; persist(); if (o && o.play) return start(id); showTrack(id, true); return false; }); },
    setVolume: function (v) { pref.vol = Math.max(0, Math.min(1, +v || 0)); persist(); applyMaster(0.1); afterState(); },
    mute: function (b) { pref.muted = b == null ? !pref.muted : !!b; persist(); applyMaster(); afterState(); },
    open: function () { setPanel(true); return loadManifest(); }, close: function () { setPanel(false); },
    suggestFor: function (sceneId) { return loadManifest().then(function () { return suggestFor(sceneId); }); },
    /** splashCue(ms): the splash may call this; it only acts if the visitor already turned sound on in this page (never starts audio by itself). */
    splashCue: function (ms) { if (!playing || !decks.length) return false; var d = decks[live]; if (d.gain) { d.gain.gain.value = 0.0001; fadeDeck(d, 1, Math.max(0.5, (ms || 3000) / 1000)); } return true; },
    state: function () { return { audible: audible, blocked: blocked, playing: playing, track: curId || pref.track, suggestion: suggestion, muted: pref.muted, volume: pref.vol, shuffle: pref.shuffle, repeat: pref.repeat, reactive: pref.reactive, context: ctx ? ctx.state : 'none', manifestLoaded: !!M, style: pref.style, count: M ? M.tracks.length : 0, src: decks.length ? decks[live].el.currentSrc || null : null, time: decks.length ? +decks[live].el.currentTime.toFixed(2) : 0, webAudio: !!master }; },
    setStyle: function (st) { pref.style = st || 'all'; persist(); return loadManifest().then(function () { renderList(); return order(); }); },
    recommendFor: function (sc) { return loadManifest().then(function () { return recommend(typeof sc === 'string' ? { id: sc } : sc); }); },
    mount: mount, BASE: BASE
  };
  root.SOSTAudio = API;
  function boot() { try { var S = root.SOSTUniverse && root.SOSTUniverse.scene; if (!sceneNow && S && S.id) sceneNow = { id: S.id, index: S.index, name: S.name, mood: S.mood, reason: 'current' }; } catch (e) {}
    var host = doc.getElementById('u-audio'); if (SCRIPT && SCRIPT.hasAttribute('data-no-ui')) return; mount(host || null); }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})(window);
