// retro-melodies.js — 50 random retro melodies for SOST splash screens
// Each melody: array of [freq, startTime, duration, waveType, volume]
// Duration: 3-5 seconds each

var RETRO_MELODIES = [
  // 1: C major arpeggio up (square)
  [[262,0,.18,'square',.08],[330,.18,.18,'square',.08],[392,.36,.18,'square',.08],[523,.54,.3,'square',.10]],
  // 2: A minor arpeggio (sawtooth)
  [[220,0,.15,'sawtooth',.07],[262,.15,.15,'sawtooth',.07],[330,.3,.15,'sawtooth',.07],[440,.45,.3,'sawtooth',.09]],
  // 3: Descending pentatonic (triangle)
  [[880,0,.2,'triangle',.06],[660,.2,.2,'triangle',.06],[523,.4,.2,'triangle',.06],[440,.6,.2,'triangle',.06],[330,.8,.3,'triangle',.08]],
  // 4: Power chord stab (square)
  [[147,0,.4,'square',.10],[220,0,.4,'square',.07],[294,.5,.4,'square',.10],[440,.5,.4,'square',.07]],
  // 5: Chromatic climb (sawtooth)
  [[262,0,.12,'sawtooth',.06],[277,.12,.12,'sawtooth',.06],[294,.24,.12,'sawtooth',.06],[311,.36,.12,'sawtooth',.06],[330,.48,.12,'sawtooth',.06],[349,.6,.3,'sawtooth',.08]],
  // 6: Octave bounce (square)
  [[440,0,.15,'square',.08],[220,.15,.15,'square',.06],[440,.3,.15,'square',.08],[220,.45,.15,'square',.06],[440,.6,.3,'square',.10]],
  // 7: Sci-fi sweep up (sawtooth)
  [[110,0,.8,'sawtooth',.05],[220,.3,.6,'sawtooth',.06],[440,.6,.4,'sawtooth',.07],[880,.9,.3,'sawtooth',.08]],
  // 8: Bass pulse (square)
  [[55,0,.25,'square',.10],[55,.3,.25,'square',.10],[55,.6,.25,'square',.10],[110,.9,.4,'square',.08]],
  // 9: Triad cascade (triangle)
  [[330,0,.2,'triangle',.07],[392,0,.2,'triangle',.05],[494,0,.2,'triangle',.04],[262,.25,.2,'triangle',.07],[330,.25,.2,'triangle',.05],[392,.25,.2,'triangle',.04],[523,.5,.3,'triangle',.08]],
  // 10: Alert beeps (square)
  [[1047,0,.08,'square',.09],[0,.08,.08,'square',0],[1047,.16,.08,'square',.09],[0,.24,.08,'square',0],[1047,.32,.08,'square',.09],[1319,.5,.3,'square',.07]],
  // 11: E minor descent (sawtooth)
  [[659,0,.2,'sawtooth',.07],[587,.2,.2,'sawtooth',.07],[494,.4,.2,'sawtooth',.07],[392,.6,.2,'sawtooth',.07],[330,.8,.3,'sawtooth',.09]],
  // 12: Funk bass (square)
  [[98,0,.15,'square',.10],[131,.2,.1,'square',.08],[98,.35,.15,'square',.10],[165,.55,.1,'square',.08],[196,.7,.3,'square',.09]],
  // 13: Major 7th shimmer (triangle)
  [[262,0,.5,'triangle',.04],[330,0,.5,'triangle',.04],[392,0,.5,'triangle',.04],[494,0,.5,'triangle',.04],[523,.6,.4,'triangle',.06]],
  // 14: Staccato march (square)
  [[330,0,.08,'square',.08],[330,.12,.08,'square',.08],[392,.24,.08,'square',.08],[330,.36,.08,'square',.08],[440,.48,.08,'square',.08],[392,.6,.2,'square',.09]],
  // 15: Deep drone start (sawtooth)
  [[65,0,1.5,'sawtooth',.04],[130,.5,1,'sawtooth',.05],[196,1,.5,'sawtooth',.06],[262,1.3,.4,'sawtooth',.07]],
  // 16: Arp minor 7 (square)
  [[220,0,.12,'square',.07],[262,.12,.12,'square',.07],[330,.24,.12,'square',.07],[415,.36,.12,'square',.07],[440,.48,.3,'square',.09]],
  // 17: Two-tone siren (sawtooth)
  [[600,0,.25,'sawtooth',.07],[800,.25,.25,'sawtooth',.07],[600,.5,.25,'sawtooth',.07],[800,.75,.25,'sawtooth',.07],[1000,1,.3,'sawtooth',.06]],
  // 18: Pentatonic bounce (triangle)
  [[392,0,.15,'triangle',.07],[440,.15,.15,'triangle',.07],[523,.3,.15,'triangle',.07],[440,.45,.15,'triangle',.07],[392,.6,.15,'triangle',.07],[523,.75,.3,'triangle',.08]],
  // 19: Retro game start (square)
  [[523,0,.1,'square',.09],[659,.1,.1,'square',.09],[784,.2,.1,'square',.09],[1047,.3,.4,'square',.10]],
  // 20: Mysterious minor (sawtooth)
  [[165,0,.3,'sawtooth',.06],[196,.3,.3,'sawtooth',.06],[185,.6,.3,'sawtooth',.06],[165,.9,.4,'sawtooth',.07]],
  // 21: Quick scale blast (square)
  [[523,0,.06,'square',.07],[587,.06,.06,'square',.07],[659,.12,.06,'square',.07],[698,.18,.06,'square',.07],[784,.24,.06,'square',.07],[880,.3,.06,'square',.07],[988,.36,.06,'square',.07],[1047,.42,.2,'square',.09]],
  // 22: Low pulse rhythm (square)
  [[73,0,.2,'square',.09],[73,.25,.1,'square',.07],[110,.4,.2,'square',.09],[73,.65,.1,'square',.07],[147,.8,.3,'square',.08]],
  // 23: Bell-like high (triangle)
  [[1319,0,.4,'triangle',.05],[988,.1,.3,'triangle',.04],[1319,.5,.4,'triangle',.05],[1568,.9,.3,'triangle',.04]],
  // 24: Diminished tension (sawtooth)
  [[262,0,.2,'sawtooth',.06],[311,.2,.2,'sawtooth',.06],[370,.4,.2,'sawtooth',.06],[440,.6,.3,'sawtooth',.08]],
  // 25: Boot sequence (square)
  [[800,0,.05,'square',.08],[1200,.1,.05,'square',.08],[800,.2,.05,'square',.08],[1600,.3,.05,'square',.08],[800,.4,.05,'square',.08],[2000,.5,.15,'square',.07]],
  // 26: Whole tone climb (triangle)
  [[262,0,.15,'triangle',.06],[294,.15,.15,'triangle',.06],[330,.3,.15,'triangle',.06],[370,.45,.15,'triangle',.06],[415,.6,.15,'triangle',.06],[466,.75,.25,'triangle',.08]],
  // 27: Synth pad (sawtooth, slow)
  [[196,0,1,'sawtooth',.03],[247,0,1,'sawtooth',.03],[294,0,1,'sawtooth',.03],[392,.8,.5,'sawtooth',.05]],
  // 28: Chippy bounce (square)
  [[1047,0,.08,'square',.07],[784,.1,.08,'square',.07],[523,.2,.08,'square',.07],[784,.3,.08,'square',.07],[1047,.4,.15,'square',.08]],
  // 29: Dark bass (square)
  [[41,0,.4,'square',.10],[49,.5,.4,'square',.10],[55,1,.5,'square',.08]],
  // 30: Bright fanfare (square)
  [[392,0,.15,'square',.08],[392,.2,.08,'square',.06],[523,.3,.15,'square',.08],[659,.5,.1,'square',.07],[784,.65,.3,'square',.09]],
  // 31: Echo pulse (triangle)
  [[440,0,.2,'triangle',.08],[440,.3,.15,'triangle',.05],[440,.55,.1,'triangle',.03],[660,.7,.3,'triangle',.07]],
  // 32: Data stream (square fast)
  [[2000,0,.03,'square',.06],[1500,.04,.03,'square',.06],[2500,.08,.03,'square',.06],[1800,.12,.03,'square',.06],[2200,.16,.03,'square',.06],[3000,.2,.03,'square',.06],[1000,.24,.2,'square',.07]],
  // 33: Dorian mode (sawtooth)
  [[294,0,.18,'sawtooth',.06],[330,.18,.18,'sawtooth',.06],[349,.36,.18,'sawtooth',.06],[392,.54,.18,'sawtooth',.06],[440,.72,.25,'sawtooth',.08]],
  // 34: Robot greeting (square)
  [[200,0,.1,'square',.07],[300,.12,.1,'square',.07],[250,.24,.1,'square',.07],[400,.36,.1,'square',.07],[350,.48,.2,'square',.08]],
  // 35: Glass tones (triangle high)
  [[1568,0,.3,'triangle',.04],[2093,.15,.25,'triangle',.04],[1760,.35,.25,'triangle',.04],[2349,.55,.3,'triangle',.05]],
  // 36: Power up (sawtooth)
  [[131,0,.2,'sawtooth',.07],[175,.15,.2,'sawtooth',.07],[220,.3,.2,'sawtooth',.07],[262,.45,.2,'sawtooth',.08],[330,.6,.2,'sawtooth',.08],[392,.75,.3,'sawtooth',.09]],
  // 37: Tritone alarm (square)
  [[370,0,.15,'square',.08],[523,.15,.15,'square',.08],[370,.3,.15,'square',.08],[523,.45,.15,'square',.08],[698,.6,.3,'square',.07]],
  // 38: Jazz minor (sawtooth)
  [[220,0,.2,'sawtooth',.06],[262,.2,.2,'sawtooth',.06],[311,.4,.2,'sawtooth',.06],[415,.6,.2,'sawtooth',.06],[440,.8,.3,'sawtooth',.08]],
  // 39: Morse beep (square)
  [[700,0,.05,'square',.07],[700,.1,.15,'square',.07],[700,.3,.05,'square',.07],[700,.4,.05,'square',.07],[700,.5,.15,'square',.07],[900,.7,.2,'square',.06]],
  // 40: Space chord (triangle)
  [[196,0,.8,'triangle',.04],[247,0,.8,'triangle',.03],[330,0,.8,'triangle',.03],[440,.5,.5,'triangle',.05],[523,.8,.4,'triangle',.05]],
  // 41: Descending 4ths (square)
  [[784,0,.15,'square',.07],[587,.18,.15,'square',.07],[440,.36,.15,'square',.07],[330,.54,.15,'square',.07],[247,.72,.3,'square',.08]],
  // 42: Stutter bass (sawtooth)
  [[82,0,.08,'sawtooth',.09],[82,.1,.08,'sawtooth',.09],[82,.2,.08,'sawtooth',.09],[110,.35,.08,'sawtooth',.08],[82,.5,.08,'sawtooth',.09],[165,.65,.3,'sawtooth',.07]],
  // 43: Bright arp (triangle)
  [[523,0,.1,'triangle',.07],[659,.1,.1,'triangle',.07],[784,.2,.1,'triangle',.07],[1047,.3,.1,'triangle',.07],[784,.4,.1,'triangle',.07],[659,.5,.1,'triangle',.07],[523,.6,.2,'triangle',.08]],
  // 44: Minor 2nd grind (sawtooth)
  [[220,0,.4,'sawtooth',.05],[233,0,.4,'sawtooth',.05],[440,.5,.4,'sawtooth',.06],[466,.5,.4,'sawtooth',.06]],
  // 45: Upbeat shuffle (square)
  [[330,0,.1,'square',.07],[0,.1,.05,'square',0],[392,.15,.1,'square',.07],[0,.25,.05,'square',0],[440,.3,.1,'square',.07],[523,.45,.15,'square',.08],[659,.65,.2,'square',.09]],
  // 46: Low rumble rise (sawtooth)
  [[41,0,1.2,'sawtooth',.04],[55,.4,.8,'sawtooth',.05],[73,.8,.5,'sawtooth',.06],[110,1.1,.4,'sawtooth',.07]],
  // 47: Glitch burst (square)
  [[3000,0,.02,'square',.06],[1500,.03,.02,'square',.06],[4000,.06,.02,'square',.06],[500,.09,.02,'square',.06],[2000,.12,.02,'square',.06],[800,.15,.15,'square',.07]],
  // 48: Lydian bright (triangle)
  [[262,0,.15,'triangle',.06],[294,.15,.15,'triangle',.06],[330,.3,.15,'triangle',.06],[370,.45,.15,'triangle',.06],[392,.6,.15,'triangle',.06],[494,.75,.25,'triangle',.08]],
  // 49: Alarm resolve (square)
  [[880,0,.12,'square',.08],[880,.15,.12,'square',.08],[880,.3,.12,'square',.08],[1047,.45,.3,'square',.09],[784,.8,.3,'square',.07]],
  // 50: Victory fanfare (square+triangle)
  [[523,0,.15,'square',.08],[523,.18,.08,'square',.06],[523,.28,.08,'square',.06],[659,.4,.15,'square',.08],[784,.6,.1,'triangle',.07],[1047,.75,.35,'square',.10]]
];

function playRandomMelody(audioCtx) {
  if (!audioCtx) try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) { return; }
  var melody = RETRO_MELODIES[Math.floor(Math.random() * RETRO_MELODIES.length)];
  var t = audioCtx.currentTime;
  melody.forEach(function(n) {
    var freq = n[0], start = n[1], dur = n[2], type = n[3], vol = n[4];
    if (freq <= 0 || vol <= 0) return;
    var osc = audioCtx.createOscillator();
    var gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, t + start);
    gain.gain.linearRampToValueAtTime(vol, t + start + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.001, t + start + dur);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(t + start);
    osc.stop(t + start + dur + 0.05);
  });
}
