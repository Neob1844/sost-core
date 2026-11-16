/* SOST Universe scene module: quantum-field (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('quantum-field', {
  "p": " if(kind<=.92){ float g=(a_s.y-.5)*5.6, lq=(floor(a_s.z*64.)/63.-.5)*5.6; vec2 xz=kind<.46?vec2(g,lq):vec2(lq,g); float h=0.; for(int i=0;i<3;i++){ float fi=float(i); vec2 sr=1.35*vec2(cos(u_t*.21+fi*2.094),sin(u_t*.17+fi*2.094)); float di=length(xz-sr); h+=cos(5.*di-2.2*u_t+fi)*exp(-.28*di); } h*=.16; p=vec3(xz.x,h-.12,xz.y); float ph=fract(h*1.6+length(xz)*.12-u_t*.05); col=u_col[int(floor(ph*7.))]*1.35; float pk=smoothstep(.22,.42,h); col=mix(col,vec3(1.),pk*.35); alpha=(.62+.7*pk)*smoothstep(2.95,1.6,length(xz)); sz=.95+.9*pk; }",
  "l": " { float g=(u-.5)*5.6, lq=(mod(cid,30.)/29.-.5)*5.6; vec2 xz=j1<.5?vec2(g,lq):vec2(lq,g); float h=0.; for(int i=0;i<3;i++){ float fi=float(i); vec2 sr=1.35*vec2(cos(u_t*.21+fi*2.094),sin(u_t*.17+fi*2.094)); float di=length(xz-sr); h+=cos(5.*di-2.2*u_t+fi)*exp(-.28*di); } h*=.16; p=vec3(xz.x,h-.12,xz.y); float ph=fract(h*1.6+length(xz)*.12-u_t*.05); col=u_col[int(floor(ph*7.))]*1.5; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 1
 });
