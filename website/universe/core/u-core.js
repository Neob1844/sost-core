/* SOST Universe — Convergence Core engine (WebGL2, no library). Phase 4.
 *
 * Fixes over prototype A (Phase 3):
 *  - No synchronous shader compile on the main thread. Programs are compiled and linked without querying
 *    their status; completion is polled with KHR_parallel_shader_compile when the GPU exposes it, otherwise
 *    the status is read only after a delay, when the GPU process has already finished (the query then returns
 *    immediately). Uniform reflection and the first (warm-up) draw happen after completion.
 *  - Boot is deferred until after the first paint and an idle period: the static poster stays the LCP element
 *    and the canvas only fades in once a real frame exists.
 *  - preserveDrawingBuffer is off (cheaper); the static freeze reads the canvas right after a draw.
 *
 * API: SOSTU.core.mount({ canvas, offx:fn, height:fn, onState:fn, scene }) -> { setBlocks, pulse, setTier, tier, perf, stop, start, setScene, setAudio }
 * DIRECTIVAS 4C (3 nov 2026): this is the ORIGINAL singularity restored (code of 2b34e0ac: multicolour distribution, red only in the
 * inflow and the rim, free centre; no eye, no SOST text) and it is the engine of the Singularity Library (core/u-scenes.js). A scene is
 * a shader branch on the same matter (same seeds, flow field, palette, intro and energy wave), so every scene is a variant of one SOST
 * universe: 0 = Convergence Vortex (the original), 1 = Chromatic Event Horizon, 2 = Golden Spiral. setAudio(0..1) is the optional
 * audio-energy input of the soundtrack (4C-3): a subtle gain / size lift, never required (the scene animates on its own).
 * Particles live on a divergence-free analytic flow field and settle on a twisted torus; colours are the
 * official spectrum (css/atomix-btn.css) and SOST red (#fb010d). Crystal blocks take the colour of the real
 * producer of each of the latest 12 blocks (data from the shared layer, never invented).
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  var SPEC = ['#8b5cf6', '#e879f9', '#3b82f6', '#22d3ee', '#a3e635', '#facc15', '#fb923c'].map(rgb);
  function rgb(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; }

  var COMMON = [
    'vec3 rotX(vec3 p,float a){float c=cos(a),s=sin(a);return vec3(p.x,c*p.y-s*p.z,s*p.y+c*p.z);}',
    'vec3 rotY(vec3 p,float a){float c=cos(a),s=sin(a);return vec3(c*p.x+s*p.z,p.y,-s*p.x+c*p.z);}',
    // divergence-free 2D flow from an analytic stream function psi(x,z,t); v = (dpsi/dz, -dpsi/dx)
    'vec2 flow(vec2 p,float t){float a=1.3*p.x+.3*t,b=1.1*p.y-.2*t,c=2.7*p.x-1.9*p.y+.5*t,d=.8*p.x+2.3*p.y-.35*t;',
    ' float dx=1.3*cos(a)*cos(b)+.5*2.7*cos(c)+.35*.8*cos(d); float dz=-1.1*sin(a)*sin(b)-.5*1.9*cos(c)+.35*2.3*cos(d); return vec2(dz,-dx);}',
    'vec3 fibp(float i,float n){float y=1.-2.*(i+.5)/n; float r=sqrt(1.-y*y); float a=i*2.39996; return vec3(r*cos(a),y,r*sin(a));}',
    'vec4 project(vec3 p,float aspect,float offx){float zv=4.6-p.z; vec2 cl=vec2(p.x*1.9/aspect,p.y*1.9)/zv; cl.x+=offx; return vec4(cl,(zv-.5)/12.*2.-1.,zv);}'
  ].join('\n');
  var VS_P_T = '#version 300 es\nprecision highp float;\nin vec4 a_s; uniform float u_t,u_intro,u_wave,u_size,u_dpr,u_aspect,u_offx,u_tilt,u_yaw,u_ptrA,u_gain,u_scene,u_audio; uniform vec2 u_ptr; uniform vec3 u_col[7];\nout vec3 v_c; out float v_a;\n' + COMMON + '\n' + [
    'void main(){ float kind=a_s.w; float band=floor(a_s.z*7.); vec3 col=u_col[int(band)]; vec3 p; float alpha=.85; float sz=1.;',
    ' if(kind<.12){ float f=fract(u_t*.07+a_s.x); float rad=mix(2.4,.16,f*f); float ang=a_s.y*6.2832+f*10.;',
    '   p=vec3(rad*cos(ang),(a_s.z-.5)*.18*(1.-f),rad*sin(ang)); col=mix(vec3(.98,.0,.05),vec3(1.,.55,.45),f*f*f); alpha=(.55+.45*f)*smoothstep(.28,.6,rad); sz=.9+f;',
    ' } else if(kind>.92){ float r=2.6+a_s.x*3.6; float th=a_s.y*6.2832; float ph=acos(2.*a_s.z-1.);',
    '   p=vec3(r*sin(ph)*cos(th),r*cos(ph)*.55,r*sin(ph)*sin(th)); p.xz+=flow(p.xz*.35,u_t*.15)*.18; alpha=.26; sz=.8;',
    ' } else { float th=a_s.x*12.5664+u_t*(.16+.025*band); float R=1.28+.07*sin(3.*th+band); float ph=1.5*th+band*.8976;',
    '   float r=.30+.11*sin(th*.5+band*1.3)+(a_s.y-.5)*.07; p=vec3((R+r*cos(ph))*cos(th),r*sin(ph)*.95,(R+r*cos(ph))*sin(th));',
    '   float hot=pow(max(0.,sin(ph*2.+u_t*.9+band)),8.); col=mix(col,vec3(1.),hot*.5); alpha=.62+.38*hot; }',
    '@@SCENE_P@@',
    ' vec3 c=(a_s.xyz-.5)*vec3(8.,4.6,8.); float sp=0.;',
    ' for(int i=0;i<4;i++){vec2 v=flow(c.xz*.42,u_t*.6+float(i)*.7); c.xz+=v*.32; c.y+=.18*sin(c.x*.9+u_t*.7); sp+=length(v);}',
    ' vec3 ccol=mix(u_col[int(mod(band+floor(sp),7.))],vec3(1.),.15);',
    ' float d0=fract(a_s.x*7.31+a_s.y*3.17)*.55; float k=smoothstep(d0,d0+.45,u_intro); p=mix(c,p,k); col=mix(ccol,col,k); p=rotY(p,(1.-k)*2.6);',
    ' float lw=abs(length(p)-u_wave*5.); float wglow=u_wave>0.?exp(-lw*9.)*(1.-u_wave):0.; col+=wglow*1.3; alpha=min(1.,alpha+wglow);',
    ' p=rotX(p,u_tilt); p=rotY(p,u_yaw); vec4 q=project(p,u_aspect,u_offx);',
    ' vec2 dd=q.xy-u_ptr; float pl=length(dd); q.xy+=normalize(dd+1e-5)*.05*exp(-pl*7.)*u_ptrA;',
    ' gl_Position=vec4(q.xy,q.z,1.); gl_PointSize=u_size*u_dpr*sz*(3.4/q.w)*(1.+wglow*2.+.10*u_audio);',
    ' v_c=col; v_a=alpha*mix(.5,1.,k)*u_gain*(1.+.12*u_audio); }'].join('\n');
  var FS_P = '#version 300 es\nprecision mediump float; in vec3 v_c; in float v_a; out vec4 o;\nvoid main(){vec2 q=gl_PointCoord-.5; float d=dot(q,q); float a=(exp(-d*30.)+exp(-d*7.)*.25)*v_a*1.25; if(a<.01)discard; o=vec4(v_c*a,a);}';
  var VS_Q = '#version 300 es\nin vec2 a_q; uniform float u_aspect,u_offx,u_rad; out vec2 v_q;\nvoid main(){v_q=a_q; vec2 p=a_q*u_rad; gl_Position=vec4(p.x/u_aspect+u_offx,p.y,.0,1.);}';
  var FS_Q_T = '#version 300 es\nprecision mediump float; in vec2 v_q; uniform float u_t,u_mode,u_pulse,u_scene; uniform vec2 u_ptr; uniform vec3 u_col[7]; out vec4 o;\n' + [
    'float n1(float x){return sin(x)*.5+sin(x*2.31+1.3)*.3+sin(x*4.7+2.1)*.2;}',
    'void main(){float d=length(v_q); float an=atan(v_q.y,v_q.x); float wob=.010*n1(an*3.+u_t*.6)+.006*n1(an*7.-u_t*.9);',
    ' if(u_mode<.5){ if(d>.42+wob)discard; o=vec4(0.,0.,0.,1.); return; }',
    ' float dop=.65+.35*cos(an-.6+u_ptr.x*.8); float rim=exp(-pow((d-.43-wob)*(30.+8.*n1(an*2.+u_t)),2.))*(.7+.3*dop+u_pulse*1.2);',
    ' float halo=exp(-pow((d-.47-wob*1.5)*6.,2.))*.20*dop; float flare=exp(-abs(v_q.y+.03*u_ptr.y)*55.)*exp(-d*2.2)*.30*step(.42,d);',
    ' float lr=.62+.012*n1(an*2.-u_t*.4)+.015*u_pulse; float lens=exp(-pow((d-lr)*38.,2.))*(.12+.08*dop);',
    ' float refl=exp(-pow(an-atan(u_ptr.y,u_ptr.x+1e-4),2.)*3.)*exp(-pow((d-.45)*20.,2.))*.25*length(u_ptr);',
    ' vec3 rc=@@SCENE_RC@@;',
    ' vec3 c=rc*(rim+halo+flare)+mix(rc,vec3(1.),.5)*rim*rim*.4+vec3(.6,.7,1.)*lens+vec3(1.,.8,.7)*refl; o=vec4(c,1.);}'].join('\n');
  var VS_B = '#version 300 es\nin vec3 a_p; in vec2 a_uv; in vec3 a_n; in vec4 a_i; in vec4 a_c;\nuniform float u_t,u_aspect,u_offx,u_yaw,u_new; out vec2 v_uv; out vec3 v_c; out float v_f; out float v_g;\n' + COMMON + '\n' + [
    'void main(){ float spin=u_t*.25+a_i.w*9.7; vec3 q=rotY(rotX(a_p,.35+spin*.15),.6+spin*.3); vec3 n=rotY(rotX(a_n,.35+spin*.15),.6+spin*.3);',
    ' float asmb=a_c.w>0.?clamp(u_new,0.,1.):1.; vec3 off=a_c.w>0.?(1.-asmb)*(a_p*2.4+vec3(-.6,.1,0.)):vec3(0.);',
    ' vec3 p=q*a_i.w*(a_c.w>0.?mix(.2,1.,asmb):1.)+a_i.xyz+off; p=rotY(p,u_yaw*.35);',
    ' vec4 c=project(p,u_aspect,u_offx); gl_Position=vec4(c.xy,c.z,1.); v_uv=a_uv; v_c=a_c.rgb; v_f=pow(1.-abs(n.z),2.); v_g=a_c.w>0.?(1.-asmb):0.;}'].join('\n');
  var FS_B = '#version 300 es\nprecision mediump float; in vec2 v_uv; in vec3 v_c; in float v_f; in float v_g; out vec4 o;\nvoid main(){ float e=min(min(v_uv.x,1.-v_uv.x),min(v_uv.y,1.-v_uv.y)); float edge=1.-smoothstep(.0,.05,e); float a=.07+edge*.85+v_f*.18+v_g*.4; vec3 c=v_c*(.35+edge*1.2)+vec3(1.)*(edge*edge*.35+v_g*.6); o=vec4(c*a,a);}';
  var VS_L_T = '#version 300 es\nin vec2 a_l; uniform float u_t,u_intro,u_wave,u_aspect,u_offx,u_tilt,u_yaw,u_gain,u_scene,u_audio,u_la,u_ptrA; uniform vec2 u_ptr; uniform vec3 u_col[7]; out vec3 v_c; out float v_a;\n' + COMMON + '\n' + [
    'float h(float n){return fract(sin(n*91.3458)*47453.5453);}',
    'void main(){ float cid=a_l.x, u=a_l.y; float band=mod(cid,7.); vec3 col=u_col[int(band)]; float j1=h(cid), j2=h(cid+7.1), j3=h(cid+3.3);',
    ' float th=u*12.5664+cid*.37+u_t*(.10+.02*band); float R=1.28+.07*sin(3.*th+band)+(j1-.5)*.12; float ph=1.5*th+band*.8976+(j2-.5)*.9;',
    ' float r=.30+.11*sin(th*.5+band*1.3)+(j3-.5)*.10; vec3 p=vec3((R+r*cos(ph))*cos(th),r*sin(ph)*.95,(R+r*cos(ph))*sin(th));',
    '@@SCENE_L@@',
    ' float k=smoothstep(.35+j1*.3,1.,u_intro); p*=mix(2.6,1.,k); float lw=abs(length(p)-u_wave*5.); float wg=u_wave>0.?exp(-lw*9.)*(1.-u_wave):0.;',
    ' p=rotX(p,u_tilt); p=rotY(p,u_yaw); vec4 c=project(p,u_aspect,u_offx); gl_Position=vec4(c.xy,c.z,1.);',
    ' float flick=.55+.45*sin(u*40.+u_t*2.+cid); v_c=mix(col,vec3(1.),wg*.6); v_a=(.10+.10*flick+wg)*k*(.6+.4*smoothstep(.2,.9,1.-abs(p.z)/2.))*u_gain*(1.+.12*u_audio)*u_la;}'].join('\n');
  // Singularity Library: per-scene shader code (compiled only for the active scene, so compile time stays flat as scenes grow)
  // Built-in scene: the original Convergence Vortex. Every other scene is a module in core/scenes/<id>.js (DIRECTIVA 4H).
  var BUILTIN = { vortex: {"p":"","l":"","rc":"vec3(.98,.01,.05)","rad":0.5,"la":1} };
  // ---- Scene library (DIRECTIVA 4H): the registry (core/u-scenes.js) gives the order and metadata; the shader code of a scene lives in
  // core/scenes/<id>.js and is fetched only when that scene is shown (never all at once). A module calls SOSTU.sceneLib.register(id, def)
  // with def = { p, l, rc, rad, la } (GLSL fragments, see core/scenes/README.md). Unknown or failing module -> the built-in vortex.
  var LIB = {}, WAIT = {}, LOADING = {};
  var BASE = (function () { try { var c = document.currentScript; if (c && c.src) return c.src.replace(/[^\/]*$/, ''); } catch (e) {} return 'core/'; })();
  function ids() { return U.scenes && U.scenes.SCENES ? U.scenes.SCENES.map(function (x) { return x.id; }) : ['vortex']; }
  function loadScene(id, cb) {
    if (BUILTIN[id]) return cb(BUILTIN[id]); if (LIB[id]) return cb(LIB[id]);
    if (!/^[a-z0-9-]{2,48}$/.test(id || '')) return cb(null);
    (WAIT[id] = WAIT[id] || []).push(cb); if (LOADING[id]) return; LOADING[id] = 1;
    var sc = document.createElement('script'); sc.src = BASE + 'scenes/' + id + '.js'; sc.async = true;
    sc.onerror = function () { LOADING[id] = 0; var w = WAIT[id] || []; delete WAIT[id]; w.forEach(function (f) { f(null); }); };
    document.head.appendChild(sc);
  }
  U.sceneLib = { register: function (id, d) { LIB[id] = d; var w = WAIT[id] || []; delete WAIT[id]; LOADING[id] = 0; w.forEach(function (f) { f(d); }); },
    load: loadScene, loaded: function () { return Object.keys(LIB); }, base: BASE };
  function VS_P(d) { return VS_P_T.replace('@@SCENE_P@@', (d.p || '').replace(/'/g, '')); }
  function VS_L(d) { return VS_L_T.replace('@@SCENE_L@@', d.l ? ' if(true)' + d.l : ''); }
  function FS_Q(d) { return FS_Q_T.replace('@@SCENE_RC@@', d.rc || 'vec3(0.)'); }
  // ---- Quality profiles (DIRECTIVA 4H stage A): every parameter that differs is listed here and reported in perf.cfg
  //   N particles, NL x SEG line vertices, scale = internal resolution (x CSS px, capped by devicePixelRatio), hdr = half-float
  //   render target + hue-preserving tone mapping (no clipping to white), bloom = thresholded mip bloom, size = point size.
  var CFG = {
    high:     { N: 160000, NL: 210, SEG: 420, dprMax: 2,   scale: 1,   hdr: true,  bloom: true,  size: 2.4 },
    balanced: { N: 70000,  NL: 126, SEG: 420, dprMax: 1.5, scale: .85, hdr: true,  bloom: false, size: 3.1 },
    lite:     { N: 22000,  NL: 56,  SEG: 260, dprMax: 1,   scale: .67, hdr: true,  bloom: false, size: 4.2 }   // HDR target at low res is cheap; without EXT_color_buffer_float the LDR 'screen' path below is used
  };
  var EXPOSURE = 1.55;
  var VS_C = '#version 300 es\nout vec2 v;\nvoid main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2)); v=p; gl_Position=vec4(p*2.-1.,0.,1.);}';
  var FS_C = '#version 300 es\nprecision highp float; in vec2 v; uniform sampler2D u_hdr; uniform float u_exp,u_bloom; out vec4 o;\n' + [
    // hue-preserving extended Reinhard on the max channel: highlights compress instead of clipping, so dense additive cores keep
    // their colour and detail; white point 6 (exposure-scaled) leaves only the hottest cores near white
    'vec3 tm(vec3 c){ float m=max(c.r,max(c.g,c.b)); float t=m*(1.+m/36.)/(1.+m); return c*(t/max(m,1e-5)); }',
    // bloom taps: a 9-tap tent filter at each mip level (one level-texel apart) instead of a single bilinear tap, which showed the
    // coarse mip texels as square blocks around bright cores
    'vec3 bt(float l){ vec2 px=.7*exp2(l)/vec2(textureSize(u_hdr,0)); vec2 a=vec2(px.x,0.),b=vec2(0.,px.y),d=px,e=vec2(px.x,-px.y);',
    ' return textureLod(u_hdr,v,l).rgb*.25+(textureLod(u_hdr,v+a,l).rgb+textureLod(u_hdr,v-a,l).rgb+textureLod(u_hdr,v+b,l).rgb+textureLod(u_hdr,v-b,l).rgb)*.125',
    '  +(textureLod(u_hdr,v+d,l).rgb+textureLod(u_hdr,v-d,l).rgb+textureLod(u_hdr,v+e,l).rgb+textureLod(u_hdr,v-e,l).rgb)*.0625; }',
    'void main(){ vec3 c=texture(u_hdr,v).rgb*u_exp;',
    ' if(u_bloom>0.){ vec3 b=max(bt(2.)*u_exp-1.2,0.)*.3+max(bt(3.5)*u_exp-.8,0.)*.4+max(bt(5.)*u_exp-.45,0.)*.6; c+=b*u_bloom; }',
    ' float l=dot(c,vec3(.2126,.7152,.0722)); c=max(vec3(0.),mix(vec3(l),c,1.12)); o=vec4(tm(c),1.);}'].join('\n');
  var FS_L = '#version 300 es\nprecision mediump float; in vec3 v_c; in float v_a; out vec4 o; void main(){o=vec4(v_c*v_a,v_a);}';

  function hasGL2() {
    if (new URLSearchParams(location.search).get('gl') === '0') return false;
    try { return !!root.WebGL2RenderingContext; } catch (e) { return false; }
  }
  var RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function mount(o) {
    var cv = o.canvas, gl = null, khr = null, prog = {}, buf = {}, N = 0, raf = 0, running = false, ready = false;
    var Qs = new URLSearchParams(location.search);
    var tier = Qs.get('q') || o.tier || 'auto', auto = tier === 'auto'; if (auto) tier = 'balanced';
    var t0 = performance.now(), settleFrom = 0, intro = 0, ptr = { x: 0, y: 0, tx: 0, ty: 0, a: 0, ta: 0 }, pulse = 0, wave = 0;
    var scene = Math.max(0, Math.min(ids().length - 1, +(o.scene || 0))), curDef = BUILTIN.vortex, scene0 = scene, fb = null, comp = null, cfg = CFG.balanced, swapGen = 0, audio = 0, audioT = 0, blocks = [], NB = 12, newAt = -1e9, dpr = 1, frames = [], last = 0, tunedAt = 0, gen = 0;
    var perf = { frames: 0, ms: [], tier: tier, longest: 0, gl: null, khr: false, compileMs: null, bootAt: null, readyAt: null, static: null };
    function state(s, why) { if (o.onState) try { o.onState(s, why); } catch (e) {} }

    function sh(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; }
    function link(vs, fs, bind) { var p = gl.createProgram(), a = sh(gl.VERTEX_SHADER, vs), b = sh(gl.FRAGMENT_SHADER, fs); gl.attachShader(p, a); gl.attachShader(p, b); if (bind) gl.bindAttribLocation(p, 0, bind); gl.linkProgram(p); return { p: p, vs: a, fs: b, u: {} }; }
    // scene programs: attribute pinned to location 0 so the vertex arrays stay valid when a scene is swapped live
    function sceneProgs(d) { return { q: link(VS_Q, FS_Q(d), 'a_q'), p: link(VS_P(d), FS_P, 'a_s'), l: link(VS_L(d), FS_L, 'a_l') }; }
    function reflect(P) {
      if (!gl.getProgramParameter(P.p, gl.LINK_STATUS)) throw new Error('link: ' + gl.getProgramInfoLog(P.p) + ' ' + gl.getShaderInfoLog(P.vs) + ' ' + gl.getShaderInfoLog(P.fs));
      var n = gl.getProgramParameter(P.p, gl.ACTIVE_UNIFORMS);
      for (var i = 0; i < n; i++) { var a = gl.getActiveUniform(P.p, i); P.u[a.name.replace('[0]', '')] = gl.getUniformLocation(P.p, a.name); }
    }
    // Deterministic seeds (mulberry32, period 2^32). The former LCG multiplied past 2^53 in doubles and cycled after ~5.8k distinct
    // (x,y) pairs, so HIGH/BAL/LITE drew the same few thousand particles stacked (reported by the scenes agent, REQUESTS_SCENES.md R1).
    function seeds(n) { var a = new Float32Array(n * 4), s = 1234567 >>> 0; for (var i = 0; i < a.length; i++) { s = (s + 0x6D2B79F5) >>> 0; var t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; a[i] = ((t ^ (t >>> 14)) >>> 0) / 4294967296; } return a; }
    function cube() {
      var F = [[0, 0, 1], [0, 0, -1], [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]], P = [], Uv = [], Nn = [];
      F.forEach(function (n) { var a = n[0] ? [0, 1, 2] : n[1] ? [1, 2, 0] : [2, 0, 1]; var ax = a[0], u = a[1], v = a[2];
        [[0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1]].forEach(function (c) { var p = [0, 0, 0]; p[ax] = n[ax] * .5; p[u] = c[0] - .5; p[v] = c[1] - .5; P.push.apply(P, p); Uv.push(c[0], c[1]); Nn.push(n[0], n[1], n[2]); }); });
      return { p: new Float32Array(P), uv: new Float32Array(Uv), n: new Float32Array(Nn) };
    }
    function vbo(data, loc, size, div) { var b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); if (loc >= 0) { gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0); if (div) gl.vertexAttribDivisor(loc, 1); } return b; }
    function blockPos(i) { return [1.6 + i * .34, -.02 - i * .04, -.1 - i * .42, .24 - i * .008]; }
    function instData() { var a = new Float32Array(NB * 4); for (var i = 0; i < NB; i++) a.set(blockPos(i), i * 4); return a; }
    function instCol() { var a = new Float32Array(NB * 4); for (var i = 0; i < NB; i++) { var b = blocks[i]; a.set((b ? rgb(b.color) : [.4, .45, .5]).concat([i === 0 && b && b.fresh ? 1 : 0]), i * 4); } return a; }

    /** Phase 1 (non-blocking): context + compile/link requests. Phase 2 (after completion): reflection + buffers. */
    function boot() {
      var my = ++gen; perf.bootAt = Math.round(performance.now());
      if (/[?&]gl=0\b/.test(location.search) || !root.WebGL2RenderingContext) return toStatic('no WebGL2');   // no probe canvas: one context only
      gl = cv.getContext('webgl2', { antialias: false, alpha: false, premultipliedAlpha: false, preserveDrawingBuffer: false, powerPreference: 'high-performance' });
      if (!gl) return toStatic('no WebGL2');
      khr = gl.getExtension('KHR_parallel_shader_compile'); perf.khr = !!khr;
      // Software rasteriser without async compile: linking would block the main thread 0.6–1.0 s (measured, SwiftShader).
      // In AUTO the static poster stays; choosing a quality explicitly still runs the animation.
      if (!khr && auto) {
        var dbg = gl.getExtension('WEBGL_debug_renderer_info'), rn = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
        perf.gl = rn;
        if (/swiftshader|llvmpipe|softpipe|software|basic render/i.test(rn || '')) return toStatic('software renderer');
      }
      cfg = CFG[tier] || CFG.balanced; perf.cfg = cfg;
      loadScene(ids()[scene], function (d) { if (my !== gen || !gl) return; if (!d) { perf.sceneError = ids()[scene]; scene = 0; d = BUILTIN.vortex; } curDef = d; compileAll(my); });
    }
    function compileAll(my) {
      var tc = performance.now();
      var S0 = sceneProgs(curDef); prog.q = S0.q; prog.p = S0.p; prog.l = S0.l; prog.b = link(VS_B, FS_B);
      var list = [prog.q, prog.p, prog.l, prog.b], polls = 0;
      if (cfg.hdr && gl.getExtension('EXT_color_buffer_float')) { prog.c = link(VS_C, FS_C); list.push(prog.c); } else prog.c = null;
      (function wait() {
        if (my !== gen || !gl) return;
        var done = true;
        if (khr) { for (var i = 0; i < list.length; i++) if (!gl.getProgramParameter(list[i].p, khr.COMPLETION_STATUS_KHR)) { done = false; break; } }
        else done = performance.now() - tc > 600;       // no KHR: read the status only once the GPU process has had time to finish
        if (!done && ++polls < 400) { setTimeout(wait, khr ? 16 : 120); return; }
        try { list.forEach(reflect); } catch (e) { console.error(e); return toStatic('shader error'); }
        perf.compileMs = Math.round(performance.now() - tc);
        try { perf.gl = (function () { var e = gl.getExtension('WEBGL_debug_renderer_info'); return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); })(); } catch (e) {}
        buffers(); dpr = size(); ready = true; settleFrom = performance.now(); perf.readyAt = Math.round(performance.now());
        start(); state('gl-ready');
      })();
    }
    function buffers() {
      N = cfg.N;
      buf.pv = gl.createVertexArray(); gl.bindVertexArray(buf.pv); vbo(seeds(N), gl.getAttribLocation(prog.p.p, 'a_s'), 4);
      var NL = cfg.NL, SEG = cfg.SEG; buf.nl = NL; buf.seg = SEG; buf.cv = gl.createVertexArray();
      var la = new Float32Array(NL * SEG * 2); for (var c = 0, k = 0; c < NL; c++) for (var i = 0; i < SEG; i++) { la[k++] = c; la[k++] = i / (SEG - 1); }
      buf.lv = gl.createVertexArray(); gl.bindVertexArray(buf.lv); vbo(la, gl.getAttribLocation(prog.l.p, 'a_l'), 2);
      buf.qv = gl.createVertexArray(); gl.bindVertexArray(buf.qv); vbo(new Float32Array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]), gl.getAttribLocation(prog.q.p, 'a_q'), 2);
      var cb = cube(); buf.bv = gl.createVertexArray(); gl.bindVertexArray(buf.bv);
      vbo(cb.p, gl.getAttribLocation(prog.b.p, 'a_p'), 3); vbo(cb.uv, gl.getAttribLocation(prog.b.p, 'a_uv'), 2); vbo(cb.n, gl.getAttribLocation(prog.b.p, 'a_n'), 3);
      buf.inst = vbo(instData(), gl.getAttribLocation(prog.b.p, 'a_i'), 4, 1); buf.icol = vbo(instCol(), gl.getAttribLocation(prog.b.p, 'a_c'), 4, 1);
      gl.bindVertexArray(null);
    }
    // Canvas size follows the LAYOUT width (clientWidth excludes a classic scrollbar; innerWidth would make the canvas wider than the
    // page and, without the hero's clipping, add a horizontal scrollbar). Internal resolution = CSS px x min(dpr, dprMax) x scale.
    function vw() { return (document.documentElement && document.documentElement.clientWidth) || innerWidth; }
    function size() {
      var d = Math.min(root.devicePixelRatio || 1, cfg.dprMax) * cfg.scale;
      var w = vw(), h = o.height ? o.height() : innerHeight;
      cv.width = Math.max(1, Math.round(w * d)); cv.height = Math.max(1, Math.round(h * d)); cv.style.width = '100%'; cv.style.height = h + 'px';
      if (gl) { gl.viewport(0, 0, cv.width, cv.height); target(); }
      perf.internal = cv.width + 'x' + cv.height; perf.scale = +d.toFixed(3); return d;
    }
    function target() {             // half-float scene target (+ depth) for tone mapping; mipmapped when bloom is on
      if (fb) { gl.deleteFramebuffer(fb.f); gl.deleteTexture(fb.t); gl.deleteRenderbuffer(fb.d); fb = null; }
      if (!prog.c || !cfg.hdr) { perf.hdr = false; perf.bloom = false; return; }
      var t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
      var lv = cfg.bloom ? Math.floor(Math.log2(Math.max(cv.width, cv.height))) + 1 : 1;
      gl.texStorage2D(gl.TEXTURE_2D, lv, gl.RGBA16F, cv.width, cv.height);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, cfg.bloom ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      var d = gl.createRenderbuffer(); gl.bindRenderbuffer(gl.RENDERBUFFER, d); gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, cv.width, cv.height);
      var f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f); gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
      gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, d);
      var ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE; gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      if (!ok) { gl.deleteFramebuffer(f); gl.deleteTexture(t); gl.deleteRenderbuffer(d); prog.c = null; perf.hdr = false; return; }
      fb = { f: f, t: t, d: d }; perf.hdr = true; perf.bloom = !!cfg.bloom;
    }
    function offx() { return o.offx ? o.offx() : 0; }
    function draw(now) {
      var t = (now - t0) / 1000, st = (now - settleFrom) / 1000;
      // ambient settle when the GL layer appears (0.8 s) — the Genesis 2D intro, if any, has already converged
      intro = RM || o.settled ? 1 : Math.min(1, .55 + st / 1.6);
      if (pulse > 0) { pulse = Math.max(0, pulse - (now - (draw.l || now)) / 1700); wave = 1 - pulse; } else wave = 0; draw.l = now;
      audio += (audioT - audio) * .12;
      ptr.x += (ptr.tx - ptr.x) * .06; ptr.y += (ptr.ty - ptr.y) * .06; ptr.a += (ptr.ta - ptr.a) * .08;
      var aspect = cv.width / cv.height, tilt = .62 + ptr.y * .12, yaw = ptr.x * .35, gain = (o.gain ? o.gain() : 1) * Math.min(1, st / .5 + (RM ? 1 : 0));
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb ? fb.f : null); gl.viewport(0, 0, cv.width, cv.height);
      gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.BLEND);
      gl.useProgram(prog.q.p); gl.bindVertexArray(buf.qv); var Qu = prog.q.u;
      gl.uniform1f(Qu.u_aspect, aspect); gl.uniform1f(Qu.u_offx, offx()); gl.uniform1f(Qu.u_rad, curDef.rad || 0); gl.uniform1f(Qu.u_scene, scene); gl.uniform3fv(Qu.u_col, new Float32Array([].concat.apply([], SPEC))); gl.uniform1f(Qu.u_mode, 0); gl.uniform1f(Qu.u_t, t); gl.uniform1f(Qu.u_pulse, pulse); gl.uniform2f(Qu.u_ptr, ptr.x, -ptr.y);
      if (curDef.rad > 0) gl.drawArrays(gl.TRIANGLES, 0, 6);
      // HDR target: plain additive (the tone map compresses later). LDR (LITE, or no float target): 'screen' accumulation
      // dst + src*(1-dst) approaches 1 per channel without clipping, so dense cores keep their hue instead of burning to white.
      gl.enable(gl.BLEND); if (fb) gl.blendFunc(gl.ONE, gl.ONE); else gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_COLOR); gl.depthMask(false);
      var Up = prog.p.u, cols = new Float32Array([].concat.apply([], SPEC)); gl.useProgram(prog.p.p); gl.bindVertexArray(buf.pv);
      gl.uniform1f(Up.u_t, t); gl.uniform1f(Up.u_intro, intro); gl.uniform1f(Up.u_wave, wave); gl.uniform1f(Up.u_size, cfg.size); gl.uniform1f(Up.u_dpr, dpr);
      gl.uniform1f(Up.u_aspect, aspect); gl.uniform1f(Up.u_offx, offx()); gl.uniform1f(Up.u_tilt, tilt); gl.uniform1f(Up.u_yaw, yaw); gl.uniform2f(Up.u_ptr, ptr.x - offx(), -ptr.y); gl.uniform1f(Up.u_ptrA, ptr.a); gl.uniform1f(Up.u_gain, fb ? gain : gain * .7); gl.uniform1f(Up.u_scene, scene); gl.uniform1f(Up.u_audio, audio);
      gl.uniform3fv(Up.u_col, cols); gl.drawArrays(gl.POINTS, 0, N);
      var L = prog.l.u; gl.useProgram(prog.l.p); gl.bindVertexArray(buf.lv);
      gl.uniform1f(L.u_t, t); gl.uniform1f(L.u_intro, intro); gl.uniform1f(L.u_wave, wave); gl.uniform1f(L.u_aspect, aspect); gl.uniform1f(L.u_offx, offx()); gl.uniform1f(L.u_tilt, tilt); gl.uniform1f(L.u_yaw, yaw); gl.uniform1f(L.u_gain, fb ? gain : gain * .7); gl.uniform1f(L.u_scene, scene); gl.uniform1f(L.u_audio, audio); gl.uniform1f(L.u_la, curDef.la == null ? 1 : curDef.la); if (L.u_ptr) gl.uniform2f(L.u_ptr, ptr.x - offx(), -ptr.y); if (L.u_ptrA) gl.uniform1f(L.u_ptrA, ptr.a);
      gl.uniform3fv(L.u_col, cols); for (var c = 0; c < buf.nl; c++) gl.drawArrays(gl.LINE_STRIP, c * buf.seg, buf.seg);
      if (blocks.length) { gl.useProgram(prog.b.p); gl.bindVertexArray(buf.bv); var B = prog.b.u;
        gl.uniform1f(B.u_t, t); gl.uniform1f(B.u_aspect, aspect); gl.uniform1f(B.u_offx, offx()); gl.uniform1f(B.u_yaw, yaw); gl.uniform1f(B.u_new, (now - newAt) / 1400);
        gl.drawArraysInstanced(gl.TRIANGLES, 0, 36, NB); }
      if (curDef.rad > 0) { gl.disable(gl.DEPTH_TEST); gl.useProgram(prog.q.p); gl.bindVertexArray(buf.qv); gl.uniform1f(Qu.u_mode, 1); gl.drawArrays(gl.TRIANGLES, 0, 6); }
      if (fb) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, cv.width, cv.height); gl.disable(gl.BLEND); gl.disable(gl.DEPTH_TEST);
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, fb.t); if (cfg.bloom) gl.generateMipmap(gl.TEXTURE_2D);
        gl.useProgram(prog.c.p); gl.bindVertexArray(buf.cv); gl.uniform1i(prog.c.u.u_hdr, 0); gl.uniform1f(prog.c.u.u_exp, EXPOSURE); gl.uniform1f(prog.c.u.u_bloom, cfg.bloom ? 1 : 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    }
    function frame(now) {
      raf = 0; if (!running) return;
      var dt = now - last; last = now; frames.push(dt); if (frames.length > 90) frames.shift();
      perf.frames++; if (perf.frames > 5) { perf.ms.push(dt); if (perf.ms.length > 600) perf.ms.shift(); if (dt > perf.longest) perf.longest = dt; }
      draw(now);
      if (perf.frames === 2) cv.classList.add('on');                 // reveal the canvas over the poster only once a real frame exists
      if (auto && now - tunedAt > 2500 && frames.length >= 90) { tunedAt = now; var avg = frames.reduce(function (a, b) { return a + b; }) / frames.length;
        if (avg > 24 && tier !== 'lite') { setTier(tier === 'high' ? 'balanced' : 'lite', true); return; } else if (avg < 11 && tier === 'balanced') { setTier('high', true); return; } }
      if (o.onFps && frames.length && perf.frames % 30 === 0) { var a = frames.reduce(function (x, y) { return x + y; }) / frames.length; perf.fps = +(1000 / a).toFixed(1); o.onFps((1000 / a).toFixed(0) + ' fps · ' + (N / 1000) + 'k · ' + perf.internal + (fb ? ' · HDR' + (cfg.bloom ? '+bloom' : '') : '') + ' · ' + tier + (auto ? ' (auto)' : '')); }
      if (RM && pulse <= 0 && perf.frames > 2) { running = false; return; }   // reduced motion: one static frame (redrawn only for a real block pulse)
      raf = requestAnimationFrame(frame);
    }
    function start() { if (running || !ready || document.body.classList.contains('static') || document.hidden) return; running = true; last = performance.now(); raf = requestAnimationFrame(frame); }
    function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
    function setTier(q, isAuto) {
      if (!isAuto) { auto = q === 'auto'; if (auto) q = 'balanced'; }
      stop(); if (q === 'off') { toStatic('static version'); return; }
      tier = q; perf.tier = q; cfg = CFG[q] || CFG.balanced; perf.cfg = cfg; document.body.classList.remove('static', 'frame', 'noframe'); perf.static = null;
      var old = gl, fresh = cv.cloneNode(); cv.replaceWith(fresh); cv = fresh; gl = null; ready = false; hook();
      if (old) { var ext = old.getExtension('WEBGL_lose_context'); if (ext) ext.loseContext(); }
      boot();
    }
    function toStatic(why) {
      var img = o.frozen, had = false;
      if (gl && ready && img) { try { draw(performance.now()); img.src = cv.toDataURL('image/png'); had = true; } catch (e) {} }
      stop(); document.body.classList.add('static', had ? 'frame' : 'noframe'); perf.static = why; state('static', why);
    }
    function hook() {
      cv.addEventListener('webglcontextlost', function (e) { e.preventDefault(); if (e.target !== cv) return; stop(); ready = false; fb = null; document.body.classList.add('static', 'noframe'); perf.static = 'context lost'; state('static', 'context lost'); });
      cv.addEventListener('webglcontextrestored', function (e) { if (e.target !== cv) return; document.body.classList.remove('static', 'noframe', 'frame'); perf.static = null; gl = null; boot(); });
    }
    hook();
    addEventListener('pointermove', function (e) { var h = o.height ? o.height() : innerHeight; ptr.tx = (e.clientX / vw()) * 2 - 1; ptr.ty = (e.clientY / h) * 2 - 1; ptr.ta = 1; }, { passive: true });
    addEventListener('pointerdown', function (e) { if (e.pointerType !== 'mouse') { var h = o.height ? o.height() : innerHeight; ptr.tx = (e.clientX / vw()) * 2 - 1; ptr.ty = (e.clientY / h) * 2 - 1; ptr.ta = 1; } }, { passive: true });
    addEventListener('pointerup', function (e) { if (e.pointerType !== 'mouse') ptr.ta = 0; }, { passive: true });
    document.addEventListener('pointerleave', function () { ptr.ta = 0; ptr.tx = ptr.ty = 0; });
    var rzT = 0; addEventListener('resize', function () { clearTimeout(rzT); rzT = setTimeout(function () { if (gl && ready) { dpr = size(); if (RM) { running = false; start(); } } }, 120); });
    document.addEventListener('visibilitychange', function () { if (document.hidden) stop(); else start(); });
    // Pause when the hero is scrolled out of view (render conditioned by visibility).
    if (root.IntersectionObserver) new IntersectionObserver(function (es) { es.forEach(function (en) { if (en.isIntersecting) start(); else stop(); }); }).observe(cv);

    function swapTo(i, d, my, tc) {
        var P = sceneProgs(d), L3 = [P.q, P.p, P.l], polls = 0;
        (function wait() {
          if (my !== swapGen || !gl) return; var done = true;
          if (khr) { for (var k = 0; k < 3; k++) if (!gl.getProgramParameter(L3[k].p, khr.COMPLETION_STATUS_KHR)) { done = false; break; } } else done = performance.now() - tc > 600;
          if (!done && ++polls < 400) { setTimeout(wait, khr ? 16 : 120); return; }
          try { L3.forEach(reflect); } catch (e) { console.error(e); return; }
          ['q', 'p', 'l'].forEach(function (k) { gl.deleteProgram(prog[k].p); prog[k] = P[k]; });
          scene = i; curDef = d; swapGen = 0; perf.switchMs = Math.round(performance.now() - tc); if (RM) { running = false; start(); }
        })();
    }
    if (tier === 'off') toStatic('static version'); else boot();
    return {
      perf: perf,
      setTier: setTier, stop: stop, start: start, get tier() { return auto ? 'auto' : tier; },
      setBlocks: function (list, fresh) { blocks = list.slice(0, NB); if (fresh) newAt = performance.now(); if (gl && ready && buf.icol) { gl.bindBuffer(gl.ARRAY_BUFFER, buf.icol); gl.bufferData(gl.ARRAY_BUFFER, instCol(), gl.STATIC_DRAW); } },
      setScene: function (i) {            // live swap: compile the new scene's programs asynchronously, switch when linked (old ones keep drawing)
        i = Math.max(0, Math.min(ids().length - 1, +i || 0)); if (i === scene && !swapGen) return; scene0 = i;
        if (!gl || !ready) { scene = i; return; }
        var my = ++swapGen, tc = performance.now();
        loadScene(ids()[i], function (d) { if (my !== swapGen || !gl) return; if (!d) { perf.sceneError = ids()[i]; swapGen = 0; return; } swapTo(i, d, my, tc); });
      },
      setAudio: function (x) { audioT = Math.max(0, Math.min(1, +x || 0)); },
      scene: function () { return scene; }, get scenes() { return ids(); }, def: function () { return curDef; }, CFG: CFG,
      pulse: function () { pulse = 1; if (!running) start(); },
      blockScreen: function (i) {           // screen position of crystal i (for the hover tooltip)
        var W = vw(), H = o.height ? o.height() : innerHeight, aspect = W / H, yaw = ptr.x * .35 * .35, p = blockPos(i);
        var c = Math.cos(yaw), s = Math.sin(yaw), x = c * p[0] + s * p[2], z = -s * p[0] + c * p[2], zv = 4.6 - z;
        return { x: (x * 1.9 / aspect / zv + offx() + 1) / 2 * W, y: (1 - (p[1] * 1.9 / zv + 1) / 2) * H, r: p[3] * 1.9 / zv * H * .5 };
      },
      ready: function () { return ready; }, NB: NB
    };
  }
  U.core = { mount: mount, hasGL2: hasGL2, RM: RM };
})(window);
