/* SOST Universe scene module: hubble-grid (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("hubble-grid", {
 "p": " if(kind<=.92){ float a=1.+.5*fract(u_t*.06)*2.; float k=floor(a_s.x*343.); vec3 g=vec3(mod(k,7.),mod(floor(k/7.),7.),floor(k/49.))-3.; vec3 q=g*.48*a+(vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)))*.03*pow(fract(a_s.w*11.),.5); float rd=length(g)/5.2; col=mix(u_col[2],u_col[1],rd*(a-1.))*1.15; alpha=.30*(1.-smoothstep(.9,1.,fract(u_t*.06)))*smoothstep(0.,.05,fract(u_t*.06))+.0; sz=.9; p=rotY(rotX(q,.25),u_t*.05); }",
 "l": " { float a=1.+.5*fract(u_t*.06)*2.; float k=mod(cid,147.); float ax=floor(k/49.); float r=mod(k,49.); vec2 ab=vec2(mod(r,7.),floor(r/7.))-3.; float s=(u-.5)*6.; vec3 g=ax<.5?vec3(s,ab):ax<1.5?vec3(ab.x,s,ab.y):vec3(ab,s); p=rotY(rotX(g*.48*a,.25),u_t*.05); col=u_col[0]*.5*(1.-smoothstep(.9,1.,fract(u_t*.06)))*smoothstep(0.,.05,fract(u_t*.06)); }",
 "la": 1.0,
 "rc": "vec3(0.)",
 "rad": 0
});
