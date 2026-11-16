/* SOST Universe scene module: irregular (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("irregular", {
 "p": " if(kind<=.92){ if(kind<.45){ float id=floor(a_s.x*11.); vec3 c0=vec3(fract(sin(id*12.9898)*43758.5)-.5,(fract(sin(id*78.233)*43758.5)-.5)*.4,fract(sin(id*39.425)*43758.5)-.5)*vec3(3.4,1.,2.4)+vec3(.3,0.,0.); float br=pow(.5+.5*sin(u_t*.55+id*2.1),5.); float rr=(.06+.16*fract(id*.77))*pow(a_s.y,.6); float cz=2.*a_s.z-1.; float s0=sqrt(1.-cz*cz); p=c0+rr*vec3(s0*cos(a_s.y*91.),cz,s0*sin(a_s.y*91.))*(1.+br*.4); col=mix(u_col[int(mod(id,2.))==0?1:3],u_col[2],.25)*1.2; alpha=.05+.30*br; sz=.9+.8*br; } else { vec3 g=vec3(a_s.x+fract(a_s.x*7.1),a_s.y+fract(a_s.y*5.3),a_s.z+fract(a_s.z*3.7))-1.; g.x+=.25*g.y*g.y; p=g*vec3(2.6,.55,1.9); p.xz+=flow(p.xz*.5,u_t*.05)*.15; col=mix(u_col[2],u_col[5],fract(a_s.y*3.))*.8; alpha=.12; sz=.8; } p=rotY(rotX(p,.35),u_t*.03); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
