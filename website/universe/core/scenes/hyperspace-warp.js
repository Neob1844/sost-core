/* SOST Universe scene module: hyperspace-warp (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('hyperspace-warp', {
  "p": " if(kind<=.92){ float f=fract(u_t*.45+a_s.x); float a=a_s.y*6.2832; float rr=.25+a_s.z*2.4; vec2 vp=u_ptr*vec2(1.2,.8)*u_ptrA; p=vec3(rr*cos(a)+vp.x*(1.-f)*2.,rr*sin(a)+vp.y*(1.-f)*2.,mix(-9.,4.,f)); col=mix(u_col[int(band)],vec3(1.),smoothstep(.8,1.,f)*.2)*1.3; alpha=smoothstep(0.,.2,f)*(1.-smoothstep(.75,.92,f)); sz=.8+1.4*f; p=rotY(rotX(p,-u_tilt),-u_yaw); }",
  "l": " { float f=fract(u_t*.45+j1); float a=j2*6.2832; float rr=.3+j3*2.3; vec2 vp=u_ptr*vec2(1.2,.8)*u_ptrA; float z=mix(-9.,4.,f)-u*1.6*f; float g=clamp((4.-z)/13.,0.,1.); p=rotY(rotX(vec3(rr*cos(a)+vp.x*g*2.,rr*sin(a)+vp.y*g*2.,z),-u_tilt),-u_yaw); col=u_col[int(band)]*1.6*smoothstep(0.,.3,f)*(1.-smoothstep(.9,1.,f)); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 1
 });
