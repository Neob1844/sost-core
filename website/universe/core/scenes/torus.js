/* SOST Universe scene module: torus (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('torus', {
  "p": " if(kind<=.92){ float tor=mod(band,4.); float eta=mix(.32,1.2,tor/3.); float b=floor(a_s.y*10.)/10.*6.2832+tor*.4; float s=a_s.x*6.2832+u_t*.35; vec4 x=vec4(cos(eta)*cos(s+b),cos(eta)*sin(s+b),sin(eta)*cos(s),sin(eta)*sin(s)); float ra=u_t*.07; x=vec4(x.x,x.y*cos(ra)-x.w*sin(ra),x.z,x.y*sin(ra)+x.w*cos(ra)); vec3 q3=x.xyz/(1.0001-x.w); float L=length(q3); p=q3*.78+(fract(a_s.z*37.)-.5)*.018; float hot=pow(max(0.,sin(s*3.-u_t*2.2+b)),14.); col=mix(u_col[int(mod(tor*2.+floor(a_s.y*10.),7.))],vec3(1.),hot*.7); alpha=(.48+.5*hot)*smoothstep(4.2,2.6,L); sz=1.05+.7*hot; }",
  "l": " { float tor=mod(cid,4.); float eta=mix(.32,1.2,tor/3.); float b=floor(cid/4.)/10.*6.2832+tor*.4; float s=u*6.2832+u_t*.35; vec4 x=vec4(cos(eta)*cos(s+b),cos(eta)*sin(s+b),sin(eta)*cos(s),sin(eta)*sin(s)); float ra=u_t*.07; x=vec4(x.x,x.y*cos(ra)-x.w*sin(ra),x.z,x.y*sin(ra)+x.w*cos(ra)); vec3 q3=x.xyz/(1.0001-x.w); float L=length(q3); p=q3*.78; col=u_col[int(mod(tor*2.+floor(cid/4.),7.))]*1.2; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.6
 });
