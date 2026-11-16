/* SOST Universe scene module: tornado (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('tornado', {
  "p": " if(kind<=.92){ float s=fract(a_s.x+u_t*.12); float y=-1.7+s*3.6; float R=.12+.9*pow(s,1.6)+.06*sin(y*4.+u_t*2.); float a=a_s.y*6.2832+u_t*(1.6-s*.9)+y*2.; vec2 sw=vec2(sin(y*1.3+u_t*.6),cos(y*.9+u_t*.5))*.18*s; p=rotX(vec3(R*cos(a)+sw.x,y,R*sin(a)+sw.y),-u_tilt+.15); col=u_col[int(mod(floor(s*7.+u_t*.2),7.))]*1.25; alpha=(.35+.5*s)*smoothstep(0.,.05,s)*(1.-smoothstep(.95,1.,s)); sz=.8+.7*s; if(kind<.15){ float r=.3+a_s.z*2.6; float a2=a_s.y*6.2832+u_t*.5/(r+.3); p=rotX(vec3(r*cos(a2),-1.75+(a_s.x-.5)*.05,r*sin(a2)),-u_tilt+.15); col=u_col[int(mod(floor(r*2.),7.))]*.9; alpha=.35; sz=.8; } }",
  "l": " { float y=-1.7+u*3.6; float R=.12+.9*pow(u,1.6); float a=j1*6.2832+u_t*(1.6-u*.9)+y*2.; vec2 sw=vec2(sin(y*1.3+u_t*.6),cos(y*.9+u_t*.5))*.18*u; p=rotX(vec3(R*cos(a)+sw.x,y,R*sin(a)+sw.y),-u_tilt+.15); col=u_col[int(mod(cid,7.))]*1.1; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.45
 });
