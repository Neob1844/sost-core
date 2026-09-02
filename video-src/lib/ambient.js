/* Ambient background for the SOST films.
 *
 * Three layers on one canvas: a slow aurora, a drifting particle field, and a faint
 * perspective grid. Every value is a function of t alone and every motion path is closed
 * with period LOOP, so rendering one LOOP-second cycle and repeating it is seamless -- which
 * is what makes a 91-second film cost 144 rendered frames per scene instead of 2,742.
 *
 * No Math.random() at draw time. The particle seeds come from a small integer hash, so the
 * same frame renders identically on any machine and on any re-render.
 */
window.GeaAmbient = (function () {
  var LOOP = 4.8;

  function rnd(i) {                       // deterministic per-particle seed
    var x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
  }

  function aurora(g, w, h, t, pal) {
    var p = 2 * Math.PI * t / LOOP;
    for (var i = 0; i < pal.length; i++) {
      var c = pal[i];
      // each blob travels a closed ellipse, at its own harmonic so they never lock in step
      var cx = w * (c.x + c.ax * Math.cos(p * c.k + c.ph));
      var cy = h * (c.y + c.ay * Math.sin(p * c.k + c.ph));
      var r = Math.min(w, h) * (c.r + 0.045 * Math.sin(p * c.k * 2 + c.ph));
      var gr = g.createRadialGradient(cx, cy, 0, cx, cy, r);
      gr.addColorStop(0, c.col.replace("ALPHA", String(c.a)));
      gr.addColorStop(0.55, c.col.replace("ALPHA", String(c.a * 0.35)));
      gr.addColorStop(1, c.col.replace("ALPHA", "0"));
      g.fillStyle = gr;
      g.fillRect(0, 0, w, h);
    }
  }

  function grid(g, w, h, t) {
    var p = 2 * Math.PI * t / LOOP;
    g.save();
    g.strokeStyle = "rgba(140,175,215,.085)";
    g.lineWidth = 1;
    var horizon = h * 0.70, rows = 16;
    for (var r = 0; r < rows; r++) {
      // rows march toward the horizon and wrap, so the drift never restarts visibly
      var f = ((r + (t / LOOP)) % rows) / rows;
      var y = horizon + Math.pow(f, 2.4) * (h - horizon) * 1.25;
      if (y > h) continue;
      g.globalAlpha = Math.min(1, f * 2.2);
      g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
    }
    g.globalAlpha = 1;
    for (var c = -10; c <= 10; c++) {
      g.globalAlpha = 0.5 - Math.abs(c) / 26;
      g.beginPath(); g.moveTo(w / 2 + c * w * 0.021, horizon);
      g.lineTo(w / 2 + c * w * 0.30, h); g.stroke();
    }
    g.restore();
  }

  function particles(g, w, h, t, n, tint) {
    var p = 2 * Math.PI * t / LOOP;
    for (var i = 0; i < n; i++) {
      var a = rnd(i), b = rnd(i + 991), c = rnd(i + 4177), d = rnd(i + 7331);
      var k = 1 + Math.floor(d * 3);                     // harmonic -> closed path
      var x = w * (a + 0.055 * Math.cos(p * k + b * 6.283));
      var y = h * (b + 0.055 * Math.sin(p * k + a * 6.283));
      var tw = 0.45 + 0.55 * (0.5 - 0.5 * Math.cos(p * (1 + Math.floor(c * 3)) + c * 6.283));
      var rad = 0.7 + c * 2.1;
      g.globalAlpha = (0.22 + 0.62 * c) * tw;
      g.fillStyle = c > 0.86 ? tint : "#9FB4C8";
      g.beginPath(); g.arc(x, y, rad, 0, 6.2832); g.fill();
    }
    g.globalAlpha = 1;
  }

  /* Palettes per scene. Colour is the main thing that changes between screens: the film
     should not be one navy wash for ninety seconds. */
  var PAL = {
    red:    [{x:.50,y:.34,ax:.06,ay:.05,r:.52,k:1,ph:0.0,col:"rgba(255,26,52,ALPHA)",a:.34},
             {x:.22,y:.66,ax:.05,ay:.06,r:.44,k:2,ph:1.9,col:"rgba(120,20,90,ALPHA)", a:.28}],
    ember:  [{x:.30,y:.30,ax:.07,ay:.05,r:.55,k:1,ph:0.4,col:"rgba(255,96,32,ALPHA)", a:.30},
             {x:.74,y:.62,ax:.05,ay:.06,r:.46,k:2,ph:2.6,col:"rgba(190,30,70,ALPHA)",  a:.30}],
    violet: [{x:.62,y:.32,ax:.06,ay:.05,r:.54,k:1,ph:1.1,col:"rgba(176,64,255,ALPHA)", a:.34},
             {x:.28,y:.68,ax:.06,ay:.05,r:.44,k:2,ph:3.4,col:"rgba(64,40,200,ALPHA)",  a:.28}],
    cyan:   [{x:.36,y:.36,ax:.06,ay:.06,r:.54,k:1,ph:2.0,col:"rgba(40,200,230,ALPHA)", a:.32},
             {x:.70,y:.64,ax:.05,ay:.05,r:.45,k:2,ph:0.7,col:"rgba(30,90,220,ALPHA)",  a:.28}],
    gold:   [{x:.50,y:.30,ax:.06,ay:.05,r:.55,k:1,ph:0.9,col:"rgba(255,178,60,ALPHA)", a:.28},
             {x:.30,y:.70,ax:.06,ay:.05,r:.46,k:2,ph:2.2,col:"rgba(200,70,40,ALPHA)",  a:.27}],
    teal:   [{x:.44,y:.62,ax:.06,ay:.05,r:.52,k:1,ph:1.5,col:"rgba(30,220,170,ALPHA)", a:.28},
             {x:.68,y:.30,ax:.05,ay:.06,r:.44,k:2,ph:3.0,col:"rgba(40,110,190,ALPHA)", a:.27}]
  };
  var TINT = { red:"#FF4A5E", ember:"#FF8A4A", violet:"#CE7BFF", cyan:"#6FE4F2", gold:"#FFC96B", teal:"#5FE9C4" };

  function paint(cv, t, name, opts) {
    opts = opts || {};
    var w = cv.width, h = cv.height, g = cv.getContext("2d");
    g.clearRect(0, 0, w, h);
    aurora(g, w, h, t, PAL[name] || PAL.red);
    if (opts.grid !== false) grid(g, w, h, t);
    particles(g, w, h, t, opts.n || 150, TINT[name] || "#FF4A5E");
  }

  return { paint: paint, LOOP: LOOP };
})();
