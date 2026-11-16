/* SOST Universe scene module: magnetic-dipole (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('magnetic-dipole', {
  "p": " if(kind<=.92){ float sh=floor(a_s.z*6.); float Lsh=.7+sh*.38; float az=floor(a_s.y*14.)/14.*6.2832+u_t*.05; float s=fract(a_s.x+u_t*.08*(mod(sh,2.)<.5?1.:-1.)); float th=mix(.18,2.96,s); float r=Lsh*sin(th)*sin(th); vec3 q=vec3(r*sin(th)*cos(az),r*cos(th),r*sin(th)*sin(az)); if(kind<.12){ float a2=a_s.x*6.2832, b2=acos(2.*a_s.y-1.); q=.3*vec3(sin(b2)*cos(a2),cos(b2),sin(b2)*sin(a2)); col=vec3(1.,.45,.3); alpha=.5; sz=.9; } else { col=u_col[int(mod(sh+floor(a_s.y*14.),7.))]*1.3; float pulse=pow(max(0.,sin(s*25.-u_t*3.)),6.); col=mix(col,vec3(1.),pulse*.4); alpha=.45+.5*pulse; sz=.9+pulse; } p=rotX(q,-.35); }",
  "l": " { float Lsh=.7+mod(cid,6.)*.38; float az=floor(cid/6.)/21.*6.2832+u_t*.05; float th=mix(.18,2.96,u); float r=Lsh*sin(th)*sin(th); p=rotX(vec3(r*sin(th)*cos(az),r*cos(th),r*sin(th)*sin(az)),-.35); col=u_col[int(mod(cid,7.))]*1.1; }",
  "rc": "vec3(1.,.35,.2)",
  "rad": 0.3,
  "la": 0.6
 });
