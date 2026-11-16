/* SOST Universe scene module: lorenz-attractor (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('lorenz-attractor', {
  "p": " if(kind<=.92){ float sg=a_s.y<.5?-1.:1.; vec3 L=vec3(8.49*sg,8.49*sg,27.)+(a_s.xyz-.5)*6.; for(int i=0;i<110;i++){ L+=.014*vec3(10.*(L.y-L.x),L.x*(28.-L.z)-L.y,L.x*L.y-2.6667*L.z); } float f=fract(u_t*.35+a_s.z*5.3); for(int i=0;i<10;i++){ L+=.014*f*vec3(10.*(L.y-L.x),L.x*(28.-L.z)-L.y,L.x*L.y-2.6667*L.z); } p=rotX(rotY(vec3(L.x,L.z-25.,L.y)*.072,.5*sin(u_t*.09)),-u_tilt+.1); float sp=length(vec3(10.*(L.y-L.x),L.x*(28.-L.z)-L.y,L.x*L.y-2.6667*L.z)); col=u_col[int(mod(floor(sp/24.),7.))]*1.3; alpha=sin(f*3.1416)*.55; sz=.9+.5*sin(f*3.1416); }",
  "l": " { vec3 L=vec3(1.+j1*2.,1.+j2*2.,20.+j3*5.); int n=40+int(u*360.); for(int i=0;i<n;i++){ L+=.01*vec3(10.*(L.y-L.x),L.x*(28.-L.z)-L.y,L.x*L.y-2.6667*L.z); } p=rotX(rotY(vec3(L.x,L.z-25.,L.y)*.072,.5*sin(u_t*.09)),-u_tilt+.1); col=u_col[int(mod(cid,7.))]*1.2; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.3
 });
