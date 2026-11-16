/* SOST Universe scene module: fractal (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('fractal', {
  "p": " if(kind<=.92){ float n=floor(a_s.x*65536.); vec3 acc=vec3(0.); float sc=.5; float dg0=0.; for(int k=0;k<8;k++){ float d=mod(floor(n/pow(4.,7.-float(k))),4.); if(k==0) dg0=d; vec3 v=d<.5?vec3(1.,1.,1.):d<1.5?vec3(1.,-1.,-1.):d<2.5?vec3(-1.,1.,-1.):vec3(-1.,-1.,1.); float an=float(k)*.42*sin(u_t*.17); acc+=rotY(rotX(v,an),an*.7)*sc; sc*=.5; } p=rotY(acc*1.05,u_t*.12)+(a_s.yzx-.5)*.008; col=mix(u_col[int(mod(dg0*2.+floor(a_s.y*2.),7.))],vec3(1.),.12); alpha=.8; sz=.8; }",
  "l": " { float n=mod(cid,64.)*1024.+floor(u*255.)*4.; vec3 acc=vec3(0.); float sc=.5; float dg0=0.; for(int k=0;k<8;k++){ float d=mod(floor(n/pow(4.,7.-float(k))),4.); if(k==0) dg0=d; vec3 v=d<.5?vec3(1.,1.,1.):d<1.5?vec3(1.,-1.,-1.):d<2.5?vec3(-1.,1.,-1.):vec3(-1.,-1.,1.); float an=float(k)*.42*sin(u_t*.17); acc+=rotY(rotX(v,an),an*.7)*sc; sc*=.5; } p=rotY(acc*1.05,u_t*.12); col=u_col[int(mod(dg0*2.,7.))]; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.3
 });
