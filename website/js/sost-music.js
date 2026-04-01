/**
 * SOST Procedural Music Engine — 60 unique melodies via Web Audio API
 * No external audio files. Pure synthesis.
 *
 * Usage:
 *   playRandomMelody()       — plays a random melody (requires prior user interaction)
 *   playMelodyByIndex(n)     — plays melody #n (0-59)
 *   stopMelody()             — fade out current melody
 *   toggleMute()             — mute/unmute, persisted in localStorage
 *   isMuted()                — check mute state
 */

(function() {
'use strict';

// ═══════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════
var _ctx = null;
var _master = null;
var _playing = false;
var _activeNodes = [];
var _fadeTimer = null;
var VOLUME = 0.30;
var MUTE_KEY = 'sost_music_muted';

function isMuted() {
  try { return localStorage.getItem(MUTE_KEY) === 'true'; } catch(e) { return false; }
}
function setMuted(v) {
  try { localStorage.setItem(MUTE_KEY, v ? 'true' : 'false'); } catch(e) {}
}

function getCtx() {
  if (!_ctx) {
    _ctx = new (window.AudioContext || window.webkitAudioContext)();
    _master = _ctx.createGain();
    _master.gain.value = isMuted() ? 0 : VOLUME;
    _master.connect(_ctx.destination);
  }
  if (_ctx.state === 'suspended') _ctx.resume();
  return _ctx;
}

// ═══════════════════════════════════════════════════════════
// SYNTHESIS HELPERS
// ═══════════════════════════════════════════════════════════
var NOTE_FREQ = {};
(function() {
  var names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  for (var o = 0; o <= 8; o++) {
    for (var i = 0; i < 12; i++) {
      var n = (o - 4) * 12 + (i - 9);
      NOTE_FREQ[names[i] + o] = 440 * Math.pow(2, n / 12);
    }
  }
})();

function freq(note) { return NOTE_FREQ[note] || 440; }

// Scales (semitone intervals from root)
var SCALES = {
  major:      [0,2,4,5,7,9,11],
  minor:      [0,2,3,5,7,8,10],
  dorian:     [0,2,3,5,7,9,10],
  mixolydian: [0,2,4,5,7,9,10],
  phrygian:   [0,1,3,5,7,8,10],
  pentatonic: [0,2,4,7,9],
  minPenta:   [0,3,5,7,10],
  chromatic:  [0,1,2,3,4,5,6,7,8,9,10,11],
  lydian:     [0,2,4,6,7,9,11],
  harmMinor:  [0,2,3,5,7,8,11],
};

function scaleFreqs(rootNote, scaleName, octaves) {
  var root = freq(rootNote);
  var intervals = SCALES[scaleName] || SCALES.major;
  var out = [];
  for (var oc = 0; oc < (octaves || 2); oc++) {
    for (var i = 0; i < intervals.length; i++) {
      out.push(root * Math.pow(2, (intervals[i] + oc * 12) / 12));
    }
  }
  return out;
}

function osc(ctx, type, f, detune) {
  var o = ctx.createOscillator();
  o.type = type; o.frequency.value = f;
  if (detune) o.detune.value = detune;
  return o;
}

function lpf(ctx, cutoff, Q) {
  var f = ctx.createBiquadFilter();
  f.type = 'lowpass'; f.frequency.value = cutoff || 2000; f.Q.value = Q || 1;
  return f;
}

function gain(ctx, v) {
  var g = ctx.createGain(); g.gain.value = v || 0; return g;
}

function delay(ctx, time, feedback) {
  var d = ctx.createDelay(5); d.delayTime.value = time || 0.3;
  var fb = ctx.createGain(); fb.gain.value = feedback || 0.3;
  var out = ctx.createGain(); out.gain.value = 0.5;
  d.connect(fb); fb.connect(d); d.connect(out);
  return { input: d, output: out };
}

function playNote(ctx, dest, f, start, dur, type, vol, attack, release, filterFreq, detune2) {
  var o1 = osc(ctx, type || 'sine', f, 0);
  var g1 = gain(ctx, 0);
  var chain = [o1, g1];

  // Optional detuned second oscillator for chorus
  if (detune2) {
    var o2 = osc(ctx, type || 'sine', f, detune2);
    var g2 = gain(ctx, 0);
    o2.connect(g2); g2.connect(dest);
    g2.gain.setValueAtTime(0, start);
    g2.gain.linearRampToValueAtTime((vol || 0.3) * 0.7, start + (attack || 0.05));
    g2.gain.setValueAtTime((vol || 0.3) * 0.7, start + dur - (release || 0.1));
    g2.gain.linearRampToValueAtTime(0, start + dur);
    o2.start(start); o2.stop(start + dur + 0.1);
    _activeNodes.push(o2, g2);
  }

  // Filter
  if (filterFreq) {
    var flt = lpf(ctx, filterFreq, 2);
    g1.connect(flt); flt.connect(dest);
    _activeNodes.push(flt);
  } else {
    g1.connect(dest);
  }

  // Envelope
  var v = vol || 0.3;
  var att = attack || 0.05;
  var rel = release || 0.1;
  g1.gain.setValueAtTime(0, start);
  g1.gain.linearRampToValueAtTime(v, start + att);
  g1.gain.setValueAtTime(v, start + dur - rel);
  g1.gain.linearRampToValueAtTime(0, start + dur);

  o1.connect(g1);
  o1.start(start); o1.stop(start + dur + 0.1);
  _activeNodes.push(o1, g1);
}

function playChord(ctx, dest, freqs, start, dur, type, vol, attack, release, filterFreq) {
  var v = (vol || 0.3) / Math.max(freqs.length, 1);
  for (var i = 0; i < freqs.length; i++) {
    playNote(ctx, dest, freqs[i], start, dur, type, v, attack, release, filterFreq, 6);
  }
}

// ═══════════════════════════════════════════════════════════
// MELODY DEFINITIONS (60 melodies, parametric)
// ═══════════════════════════════════════════════════════════

var MELODIES = [];

// Helper: create melody from parameters
function defMelody(name, category, fn) {
  MELODIES.push({ name: name, category: category, play: fn });
}

// ── UTILITY: Generate arpeggio pattern ──
function arpeggio(ctx, dest, freqs, startT, noteDur, gap, type, vol, filter) {
  for (var i = 0; i < freqs.length; i++) {
    playNote(ctx, dest, freqs[i], startT + i * gap, noteDur, type, vol, 0.03, noteDur * 0.3, filter, 5);
  }
}

// ── UTILITY: Generate chord progression ──
function progression(ctx, dest, chords, startT, chordDur, type, vol, filter) {
  for (var i = 0; i < chords.length; i++) {
    playChord(ctx, dest, chords[i], startT + i * chordDur, chordDur * 0.95, type, vol, 0.1, chordDur * 0.3, filter);
  }
}

// ═══════════════════════════════════════════════════════════
// EPIC MELODIES (0-19)
// ═══════════════════════════════════════════════════════════

// Keys and chord factories
function majorTriad(root) { return [root, root * 5/4, root * 3/2]; }
function minorTriad(root) { return [root, root * 6/5, root * 3/2]; }
function powerChord(root) { return [root, root * 3/2, root * 2]; }
function sus4(root) { return [root, root * 4/3, root * 3/2]; }

var EPIC_KEYS = [
  {root: 'C3', scale: 'major'},  {root: 'D3', scale: 'major'},
  {root: 'D#3', scale: 'major'}, {root: 'F3', scale: 'major'},
  {root: 'G3', scale: 'major'},  {root: 'A3', scale: 'major'},
  {root: 'B3', scale: 'major'},  {root: 'C3', scale: 'lydian'},
  {root: 'D3', scale: 'mixolydian'}, {root: 'E3', scale: 'major'},
];

for (var ei = 0; ei < 20; ei++) {
  (function(idx) {
    var key = EPIC_KEYS[idx % EPIC_KEYS.length];
    var variation = idx; // Use index for deterministic variation
    defMelody('Epic ' + (idx+1), 'epic', function(ctx, dest) {
      var t = ctx.currentTime + 0.3;
      var sc = scaleFreqs(key.root, key.scale, 3);
      var bpm = 80 + (variation % 5) * 10;
      var beat = 60 / bpm;
      var dl = delay(ctx, beat * 0.75, 0.25);
      dl.output.connect(dest);
      _activeNodes.push(dl.input, dl.output);

      // Pad background
      var padF = sc[0] * 0.5;
      playNote(ctx, dest, padF, t, 10, 'sine', 0.08, 2, 3, 400, 3);
      playNote(ctx, dest, padF * 1.5, t, 10, 'sine', 0.05, 2, 3, 500, 4);

      // Pattern variations
      var pat = variation % 4;
      if (pat === 0) {
        // Power chord crescendo
        for (var i = 0; i < 4; i++) {
          var ch = powerChord(sc[i % sc.length]);
          playChord(ctx, dl.input, ch, t + i * beat * 2, beat * 1.8, 'sawtooth', 0.04 + i * 0.02, 0.2, beat, 800 + i * 200);
        }
        arpeggio(ctx, dl.input, [sc[4],sc[5],sc[6],sc[7],sc[8]], t + beat * 8, beat * 0.8, beat * 0.5, 'sawtooth', 0.06, 1200);
      } else if (pat === 1) {
        // Rising triads
        for (var i = 0; i < 5; i++) {
          playChord(ctx, dl.input, majorTriad(sc[i]), t + i * beat * 1.5, beat * 1.4, 'sawtooth', 0.05, 0.15, beat * 0.5, 900);
        }
        playChord(ctx, dest, majorTriad(sc[7]), t + beat * 8, beat * 3, 'sawtooth', 0.07, 0.3, 1.5, 1500);
      } else if (pat === 2) {
        // Staccato + legato alternation
        for (var i = 0; i < 8; i++) {
          var dur = (i % 2 === 0) ? beat * 0.3 : beat * 1.2;
          playNote(ctx, dl.input, sc[i % sc.length], t + i * beat, dur, 'sawtooth', 0.06, 0.02, dur * 0.3, 1000, 8);
        }
        playChord(ctx, dest, majorTriad(sc[0] * 2), t + beat * 9, beat * 3, 'sine', 0.06, 0.5, 1.5);
      } else {
        // Fanfare
        var fanfare = [sc[0],sc[2],sc[4],sc[4],sc[2],sc[4],sc[7]];
        for (var i = 0; i < fanfare.length; i++) {
          playNote(ctx, dl.input, fanfare[i], t + i * beat * 0.7, beat * 0.6, 'sawtooth', 0.06, 0.02, 0.15, 1100, 7);
        }
        playChord(ctx, dest, majorTriad(sc[0] * 2), t + beat * 6, beat * 4, 'sawtooth', 0.06, 0.4, 2, 1400);
      }
    });
  })(ei);
}

// ═══════════════════════════════════════════════════════════
// CINEMATIC MELODIES (20-34)
// ═══════════════════════════════════════════════════════════

var CINE_KEYS = [
  {root: 'A2', scale: 'minor'},    {root: 'D3', scale: 'minor'},
  {root: 'E3', scale: 'harmMinor'},{root: 'B2', scale: 'minor'},
  {root: 'F3', scale: 'minor'},    {root: 'C3', scale: 'minor'},
  {root: 'G2', scale: 'harmMinor'},{root: 'C#3', scale: 'phrygian'},
];

for (var ci = 0; ci < 15; ci++) {
  (function(idx) {
    var key = CINE_KEYS[idx % CINE_KEYS.length];
    defMelody('Cinematic ' + (idx+1), 'cinematic', function(ctx, dest) {
      var t = ctx.currentTime + 0.2;
      var sc = scaleFreqs(key.root, key.scale, 3);
      var beat = 60 / (70 + (idx % 4) * 8);
      var dl = delay(ctx, 0.4, 0.35);
      dl.output.connect(dest);
      _activeNodes.push(dl.input, dl.output);

      // Deep drone
      playNote(ctx, dest, sc[0] * 0.5, t, 12, 'sine', 0.07, 3, 4, 300, 2);

      var pat = idx % 3;
      if (pat === 0) {
        // Suspense → reveal
        for (var i = 0; i < 5; i++) {
          playNote(ctx, dl.input, sc[i], t + 1 + i * beat * 1.2, beat * 1, 'sine', 0.04 + i * 0.01, 0.2, beat * 0.4, 600 + i * 150);
        }
        playChord(ctx, dest, majorTriad(sc[4]), t + 8, beat * 4, 'sawtooth', 0.06, 0.5, 2, 1200);
      } else if (pat === 1) {
        // Slow reveal with octave jumps
        var notes = [sc[0], sc[2], sc[4], sc[0]*2, sc[7], sc[4]*2];
        for (var i = 0; i < notes.length; i++) {
          playNote(ctx, dl.input, notes[i], t + 0.5 + i * beat * 1.5, beat * 1.3, 'triangle', 0.05, 0.3, beat * 0.5);
        }
      } else {
        // Heartbeat + melody
        for (var i = 0; i < 6; i++) {
          playNote(ctx, dest, sc[0] * 0.5, t + i * beat * 1.8, 0.15, 'sine', 0.08, 0.01, 0.1);
          playNote(ctx, dest, sc[0] * 0.5, t + i * beat * 1.8 + 0.2, 0.1, 'sine', 0.05, 0.01, 0.08);
        }
        for (var i = 0; i < 4; i++) {
          playNote(ctx, dl.input, sc[3 + i], t + 2 + i * beat * 2, beat * 1.5, 'sine', 0.05, 0.2, beat, 800);
        }
      }
    });
  })(ci);
}

// ═══════════════════════════════════════════════════════════
// CYBERPUNK / TECH MELODIES (35-49)
// ═══════════════════════════════════════════════════════════

var CYBER_KEYS = [
  {root: 'A2', scale: 'phrygian'},  {root: 'D3', scale: 'minor'},
  {root: 'E2', scale: 'minPenta'},  {root: 'C3', scale: 'chromatic'},
  {root: 'F#2', scale: 'phrygian'}, {root: 'B2', scale: 'minor'},
  {root: 'G2', scale: 'dorian'},    {root: 'D#3', scale: 'minPenta'},
];

for (var ti = 0; ti < 15; ti++) {
  (function(idx) {
    var key = CYBER_KEYS[idx % CYBER_KEYS.length];
    defMelody('Cyber ' + (idx+1), 'cyberpunk', function(ctx, dest) {
      var t = ctx.currentTime + 0.1;
      var sc = scaleFreqs(key.root, key.scale, 3);
      var bpm = 110 + (idx % 4) * 10;
      var beat = 60 / bpm;
      var dl = delay(ctx, beat * 0.5, 0.3);
      dl.output.connect(dest);
      _activeNodes.push(dl.input, dl.output);

      // Pulsing bass
      for (var i = 0; i < Math.floor(10 / beat); i++) {
        playNote(ctx, dest, sc[0] * 0.5, t + i * beat, beat * 0.4, 'sawtooth', 0.07, 0.01, beat * 0.2, 400);
      }

      var pat = idx % 4;
      if (pat === 0) {
        // Fast arpeggio
        var arpNotes = [sc[0],sc[2],sc[4],sc[5],sc[7],sc[5],sc[4],sc[2]];
        for (var r = 0; r < 3; r++) {
          for (var i = 0; i < arpNotes.length; i++) {
            playNote(ctx, dl.input, arpNotes[i] * (1 + r * 0.5), t + 1 + (r * arpNotes.length + i) * beat * 0.5, beat * 0.4, 'square', 0.04, 0.01, beat * 0.2, 1500, 10);
          }
        }
      } else if (pat === 1) {
        // Glitch bleeps
        for (var i = 0; i < 12; i++) {
          var f = sc[Math.floor(Math.abs(Math.sin(i * 7.3)) * sc.length)];
          playNote(ctx, dl.input, f, t + 0.5 + i * beat * 0.7, beat * 0.2, 'square', 0.04, 0.005, 0.05, 2000);
        }
      } else if (pat === 2) {
        // Saw lead + resonant filter sweep
        for (var i = 0; i < 8; i++) {
          playNote(ctx, dl.input, sc[i % sc.length] * 2, t + 0.3 + i * beat * 0.8, beat * 0.6, 'sawtooth', 0.04, 0.02, beat * 0.3, 800 + i * 200, 15);
        }
      } else {
        // Stab chords
        for (var i = 0; i < 6; i++) {
          var ch = minorTriad(sc[(i * 2) % sc.length]);
          playChord(ctx, dl.input, ch, t + 0.5 + i * beat * 1.5, beat * 0.3, 'sawtooth', 0.05, 0.01, 0.1, 1200);
        }
        playNote(ctx, dest, sc[0], t + beat * 10, beat * 3, 'sawtooth', 0.05, 0.3, 1.5, 600, 8);
      }
    });
  })(ti);
}

// ═══════════════════════════════════════════════════════════
// AMBIENT / MINIMAL MELODIES (50-59)
// ═══════════════════════════════════════════════════════════

var AMB_KEYS = [
  {root: 'C3', scale: 'pentatonic'}, {root: 'D3', scale: 'pentatonic'},
  {root: 'G3', scale: 'pentatonic'}, {root: 'A3', scale: 'minPenta'},
  {root: 'E3', scale: 'pentatonic'}, {root: 'F3', scale: 'lydian'},
  {root: 'B3', scale: 'pentatonic'}, {root: 'D#3', scale: 'pentatonic'},
];

for (var ai = 0; ai < 10; ai++) {
  (function(idx) {
    var key = AMB_KEYS[idx % AMB_KEYS.length];
    defMelody('Ambient ' + (idx+1), 'ambient', function(ctx, dest) {
      var t = ctx.currentTime + 0.5;
      var sc = scaleFreqs(key.root, key.scale, 3);
      var beat = 60 / (60 + (idx % 3) * 5);
      var dl = delay(ctx, 0.6, 0.4);
      dl.output.connect(dest);
      _activeNodes.push(dl.input, dl.output);

      // Wide pad
      playNote(ctx, dest, sc[0] * 0.5, t, 13, 'sine', 0.05, 3, 4, 500, 3);
      playNote(ctx, dest, sc[4] * 0.5, t + 1, 11, 'sine', 0.03, 3, 4, 400, 4);

      // Sparse bell-like notes
      var pat = idx % 3;
      var noteCount = 4 + (idx % 3);
      for (var i = 0; i < noteCount; i++) {
        var ni = (i * 3 + idx) % sc.length;
        var startT = t + 1.5 + i * beat * (2 + pat * 0.5);
        playNote(ctx, dl.input, sc[ni], startT, beat * 1.5, 'sine', 0.06, 0.01, beat, 3000);
        // Harmonic overtone
        playNote(ctx, dl.input, sc[ni] * 2, startT + 0.05, beat * 0.8, 'sine', 0.02, 0.01, beat * 0.5, 4000);
      }
    });
  })(ai);
}

// ═══════════════════════════════════════════════════════════
// PLAYBACK ENGINE
// ═══════════════════════════════════════════════════════════

function stopMelody() {
  if (_master) {
    _master.gain.linearRampToValueAtTime(0, _ctx.currentTime + 1.5);
    setTimeout(function() {
      for (var i = 0; i < _activeNodes.length; i++) {
        try { _activeNodes[i].disconnect(); } catch(e) {}
      }
      _activeNodes = [];
      _playing = false;
      if (_master) _master.gain.value = isMuted() ? 0 : VOLUME;
    }, 2000);
  }
}

function playMelodyByIndex(idx) {
  if (isMuted() || _playing) return;
  if (document.hidden) return;
  if (idx < 0 || idx >= MELODIES.length) return;

  var ctx = getCtx();
  _playing = true;
  _activeNodes = [];

  try {
    MELODIES[idx].play(ctx, _master);
  } catch(e) {
    _playing = false;
    return;
  }

  // Auto-stop after melody duration
  if (_fadeTimer) clearTimeout(_fadeTimer);
  _fadeTimer = setTimeout(function() {
    stopMelody();
  }, 13000);
}

function playRandomMelody() {
  var idx = Math.floor(Math.random() * MELODIES.length);
  playMelodyByIndex(idx);
  return idx;
}

function toggleMute() {
  var muted = !isMuted();
  setMuted(muted);
  if (_master) _master.gain.value = muted ? 0 : VOLUME;
  return muted;
}

// ═══════════════════════════════════════════════════════════
// MUTE BUTTON (auto-injected)
// ═══════════════════════════════════════════════════════════

function createMuteButton() {
  if (document.getElementById('sost-mute-btn')) return;
  var btn = document.createElement('button');
  btn.id = 'sost-mute-btn';
  btn.setAttribute('aria-label', 'Toggle music');
  btn.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:99999;background:rgba(10,10,10,0.85);' +
    'border:1px solid #333;border-radius:50%;width:40px;height:40px;cursor:pointer;font-size:18px;' +
    'color:#888;display:flex;align-items:center;justify-content:center;transition:all 0.2s;' +
    'backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);box-shadow:0 2px 8px rgba(0,0,0,0.5);';
  btn.textContent = isMuted() ? '\uD83D\uDD07' : '\uD83D\uDD0A';
  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    var m = toggleMute();
    btn.textContent = m ? '\uD83D\uDD07' : '\uD83D\uDD0A';
    btn.style.borderColor = m ? '#333' : '#4ade80';
  });
  btn.addEventListener('mouseenter', function() { btn.style.borderColor = '#fb010d'; });
  btn.addEventListener('mouseleave', function() { btn.style.borderColor = isMuted() ? '#333' : '#4ade80'; });
  document.body.appendChild(btn);
}

// Auto-create button when DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', createMuteButton);
} else {
  createMuteButton();
}

// ═══════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════
window.SOSTMusic = {
  playRandom: playRandomMelody,
  playByIndex: playMelodyByIndex,
  stop: stopMelody,
  toggleMute: toggleMute,
  isMuted: isMuted,
  count: function() { return MELODIES.length; },
  list: function() { return MELODIES.map(function(m,i) { return i + ': ' + m.name + ' [' + m.category + ']'; }); },
};
// Convenience globals
window.playRandomMelody = playRandomMelody;
window.playMelodyByIndex = playMelodyByIndex;
window.stopMelody = stopMelody;
window.toggleMute = toggleMute;
window.isMuted = isMuted;

})();
