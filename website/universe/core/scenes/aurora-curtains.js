/* SOST Universe scene module: aurora-curtains (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('aurora-curtains', {
  "p": " if(kind<=.92){ float cu=floor(a_s.z*4.); float x=(floor(a_s.x*180.)/180.+(fract(a_s.x*180.)-.5)*.0015-.5)*6.; float wind=u_t*.4+u_ptr.x*u_ptrA*.8; float z=-1.2+cu*.6+.45*sin(x*1.1+wind+cu*1.7)+.2*sin(x*2.7-wind*1.3); float g=pow(a_s.y,1.8); float y=-1.+g*(2.1+.5*sin(x*.8+cu+u_t*.3)); p=rotX(vec3(x,y,z),-u_tilt+.32); col=mix(u_col[4],u_col[int(mod(cu*2.+5.,7.))],smoothstep(.04,.45,g))*1.25; float rays=.55+.45*sin(x*9.+cu*3.+u_t*1.5); alpha=(1.-g*.85)*rays*1.1*smoothstep(0.,.06,g); sz=1.25; }",
  "l": " { float cu=mod(cid,4.); float x=(j1-.5)*6.; float wind=u_t*.4+u_ptr.x*u_ptrA*.8; float z=-1.2+cu*.6+.45*sin(x*1.1+wind+cu*1.7)+.2*sin(x*2.7-wind*1.3); float y=-1.+u*(2.1+.5*sin(x*.8+cu+u_t*.3)); p=rotX(vec3(x,y,z),-u_tilt+.32); col=mix(u_col[4],u_col[int(mod(cu*2.+5.,7.))],smoothstep(0.,.5,u))*1.2*(1.-u); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 1.6
 });
