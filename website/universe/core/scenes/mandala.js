/* SOST Universe scene module: mandala (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('mandala', {
  "p": " if(kind<=.92){ float L=floor(a_s.z*9.); float n=3.+L; float R=.25+L*.2; float rot=u_t*(.08+.03*L)*(mod(L,2.)<.5?1.:-1.)+u_ptr.x*u_ptrA*.6*(L-4.)*.25; float side=floor(a_s.x*n), ft=fract(a_s.x*n); float a0=side/n*6.2832+rot, a1=(side+1.)/n*6.2832+rot; vec2 q=mix(vec2(cos(a0),sin(a0)),vec2(cos(a1),sin(a1)),ft)*R; if(a_s.y<.35){ float pet=a_s.y/.35*6.2832; q=vec2(cos(pet+rot),sin(pet+rot))*R*(.55+.45*abs(cos(n*.5*pet))); } p=rotX(vec3(q,(a_s.y-.5)*.03),-u_tilt); float br=pow(max(0.,sin(u_t*1.2-L*.7)),4.); col=mix(u_col[int(mod(L,7.))],vec3(1.),br*.35)*1.3; alpha=.5+.45*br; sz=1.; }",
  "l": " { float L=mod(cid,9.); float n=3.+L; float R=.25+L*.2+floor(cid/9.)*.012; float rot=u_t*(.08+.03*L)*(mod(L,2.)<.5?1.:-1.)+u_ptr.x*u_ptrA*.6*(L-4.)*.25; float side=floor(u*n), ft=fract(u*n); float a0=side/n*6.2832+rot, a1=(side+1.)/n*6.2832+rot; p=rotX(vec3(mix(vec2(cos(a0),sin(a0)),vec2(cos(a1),sin(a1)),ft)*R,0.),-u_tilt); col=u_col[int(mod(L,7.))]*1.1; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.5
 });
