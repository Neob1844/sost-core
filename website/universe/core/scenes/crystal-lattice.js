/* SOST Universe scene module: crystal-lattice (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('crystal-lattice', {
  "p": " if(kind<=.92){ vec3 g=floor(a_s.xyz*9.); vec3 q=(g-4.)*.32; if(kind<.5){ q+=(fract(a_s.yzx*9.)-.5)*.02; } else { float ax=mod(floor(a_s.w*30.),3.); vec3 dir=ax<.5?vec3(1.,0.,0.):ax<1.5?vec3(0.,1.,0.):vec3(0.,0.,1.); q+=dir*.32*fract(a_s.y*97.); } float T=u_t*.5; vec3 o=vec3(sin(floor(T)*12.9),sin(floor(T)*78.2),sin(floor(T)*37.7))*1.2; float d=length(q-o); float w=exp(-pow((d-fract(T)*3.)*5.,2.)); p=rotY(rotX(q,.3),u_t*.1); col=mix(u_col[int(mod(g.x+g.y+g.z,7.))]*.9,vec3(1.),w*.5)*1.2; alpha=(kind<.5?.6:.18)+.8*w; sz=(kind<.5?1.3:.7)+1.2*w; }",
  "l": " { float T=u_t*.5; vec3 o=vec3(sin(floor(T)*12.9),sin(floor(T)*78.2),sin(floor(T)*37.7))*1.2; float r=fract(T)*3.; float a=u*6.2832; float b=(j1-.5)*3.1416; p=rotY(rotX(o+r*vec3(cos(b)*cos(a),sin(b),cos(b)*sin(a)),.3),u_t*.1); col=u_col[int(mod(cid,7.))]*(1.-fract(T))*.9; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.35
 });
