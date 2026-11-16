/* SOST Universe scene module: harmonic-strings (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('harmonic-strings', {
  "p": " if(kind<=.92){ float k=floor(a_s.z*12.); float x=(a_s.x-.5)*6.; float n=1.+mod(k,6.); float pl=fract(u_t*.12+k*.083); float amp=.32*exp(-pl*4.)*(1.+.3*u_audio); float y=-1.3+k*.24+amp*sin(n*3.1416*a_s.x)*cos(u_t*(5.+n*1.5)); p=rotX(vec3(x,y,(a_s.y-.5)*.02-.4+k*.05),-u_tilt+.08); float e=amp/.32; col=mix(u_col[int(mod(k,7.))]*1.2,vec3(1.),e*.3); alpha=.35+.6*e; sz=.85+.8*e; }",
  "l": " { float k=mod(cid,12.); float x=(u-.5)*6.; float n=1.+mod(k,6.); float pl=fract(u_t*.12+k*.083); float amp=.32*exp(-pl*4.); float y=-1.3+k*.24+amp*sin(n*3.1416*u)*cos(u_t*(5.+n*1.5))+(j1-.5)*.01; p=rotX(vec3(x,y,-.4+k*.05),-u_tilt+.08); col=u_col[int(mod(k,7.))]*1.3*(.4+amp*2.); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.8
 });
