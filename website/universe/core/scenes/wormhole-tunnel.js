/* SOST Universe scene module: wormhole-tunnel (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('wormhole-tunnel', {
  "p": " if(kind<=.92){ float z=fract(a_s.x-u_t*.12); float zz=mix(2.6,-14.,z); float a=a_s.y*6.2832+zz*.12+u_t*.2; float R=1.15+.08*sin(a*6.+zz); float far=max(0.,-zz)*.12; vec2 bend=vec2(sin(zz*.18+u_t*.3),cos(zz*.13))*.9*far+u_ptr*u_ptrA*vec2(2.,1.5)*clamp(-zz/14.,0.,1.); p=vec3(R*cos(a)+bend.x,R*sin(a)+bend.y,zz); float ring=pow(max(0.,sin(zz*3.-u_t*4.)),10.); col=mix(u_col[int(mod(floor(zz*.6+u_t*.5),7.))],vec3(1.),ring*.4)*1.3; alpha=(.8+.8*ring)*smoothstep(.0,.2,z)*(1.-smoothstep(.85,1.,z)); sz=.95+.7*ring; p=rotY(rotX(p,-u_tilt),-u_yaw); }",
  "l": " { float zz=mix(2.6,-14.,u); float a=mod(cid,24.)/24.*6.2832+zz*.12+u_t*.2; float far=max(0.,-zz)*.12; vec2 bend=vec2(sin(zz*.18+u_t*.3),cos(zz*.13))*.9*far+u_ptr*u_ptrA*vec2(2.,1.5)*clamp(-zz/14.,0.,1.); p=rotY(rotX(vec3(1.15*cos(a)+bend.x,1.15*sin(a)+bend.y,zz),-u_tilt),-u_yaw); col=u_col[int(mod(cid,7.))]*1.1*(1.-smoothstep(.85,1.,u))*smoothstep(0.,.35,u); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.35
 });
