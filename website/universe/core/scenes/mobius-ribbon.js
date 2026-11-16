/* SOST Universe scene module: mobius-ribbon (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('mobius-ribbon', {
  "p": " if(kind<=.92){ float u2=a_s.x*6.2832; float v=(a_s.y-.5)*.9; float tw=u2*.5+u_t*.2; vec3 q=vec3((1.3+v*cos(tw))*cos(u2),v*sin(tw),(1.3+v*cos(tw))*sin(u2)); p=rotY(rotX(q,.35*sin(u_t*.2)),u_t*.12); float sti=a_s.x*14.-u_t*.4; col=mix(u_col[int(mod(floor(sti),7.))]*1.3,vec3(1.),pow(fract(sti),14.)*.5); alpha=.5+.3*abs(sin(tw)); sz=1.; }",
  "l": " { float u2=u*12.5664; float v=.45*(1.-j1*.15); float tw=u2*.5+u_t*.2; vec3 q=vec3((1.3+v*cos(tw))*cos(u2),v*sin(tw),(1.3+v*cos(tw))*sin(u2)); p=rotY(rotX(q,.35*sin(u_t*.2)),u_t*.12); col=u_col[int(mod(floor(u*28.-u_t*.4),7.))]*1.2; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.3
 });
