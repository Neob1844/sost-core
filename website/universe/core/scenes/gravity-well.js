/* SOST Universe scene module: gravity-well (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("gravity-well", {
 "p": " if(kind<=.92){ float RS=.22; if(kind<.46){ float r,ph; if(fract(a_s.x*2.)<.5){ r=RS+pow(floor(a_s.y*15.)/14.,1.6)*3.; ph=a_s.z*6.2832; } else { r=RS+pow(a_s.y,1.6)*3.; ph=floor(a_s.z*28.)/28.*6.2832; } float w=2.*sqrt(RS*(r-RS))-2.*sqrt(RS*(3.22-RS)); p=vec3(r*cos(ph),w*.9+.55,r*sin(ph)); col=mix(u_col[2],u_col[0],clamp(-w*.5,0.,1.))*.9; alpha=.30+.25*smoothstep(3.,.5,r); sz=1.1; } else { float o=floor(a_s.x*14.); float pp=.9+fract(o*.618)*1.5; float e=.25+.45*fract(o*.377); float k=.82+.06*fract(o*.29); float head=u_t*(.9/pow(pp,1.5))+o*1.7; float ph=head-a_s.y*3.5; float r=pp/(1.+e*cos(k*ph)); float w=2.*sqrt(RS*(max(r,RS)-RS))-2.*sqrt(RS*(3.22-RS)); float rot=o*.9; p=vec3(r*cos(ph+rot),w*.9+.58,r*sin(ph+rot)); float tail=1.-a_s.y; col=u_col[int(mod(o,7.))]*(1.+.5*pow(tail,8.)); alpha=pow(tail,2.)*.55; sz=.8+.9*pow(tail,10.); } p=rotX(p,-u_tilt+.38); }",
 "l": " { float RS=.22; float o=mod(cid,14.); float pp=.9+fract(o*.618)*1.5; float e=.25+.45*fract(o*.377); float k=.82+.06*fract(o*.29); float ph=u*6.2832*4.+(j1-.5)*.02; float r=pp/(1.+e*cos(k*ph)); float w=2.*sqrt(RS*(max(r,RS)-RS))-2.*sqrt(RS*(3.22-RS)); float rot=o*.9; p=rotX(vec3(r*cos(ph+rot),w*.9+.58,r*sin(ph+rot)),-u_tilt+.38); col=u_col[int(mod(o,7.))]*.6; }",
 "rad": 0,
 "la": 0.3,
 "rc": "vec3(0.)"
});
