/* SOST Universe scene module: striped-wind (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("striped-wind", {
 "p": " if(kind<=.92){ float al=.75; float r=.25+2.3*pow(a_s.x,.8); float ph=a_s.y*6.2832; float W=u_t*1.1; float y=r*sin(al)*sin(ph-W+r*2.2)*.42; vec3 q=vec3(r*cos(ph),y,r*sin(ph)); float pol=sin(ph-W+r*2.2); col=(pol>0.?mix(u_col[2],u_col[3],r/3.3):mix(u_col[1],u_col[0],r/3.3))*1.2; alpha=(.18+.25*smoothstep(.9,.2,abs(pol)))*smoothstep(2.55,1.2,r); sz=.9; if(kind<.04){ float cz=2.*a_s.z-1.; q=.12*vec3(sqrt(1.-cz*cz)*cos(ph),cz,sqrt(1.-cz*cz)*sin(ph)); col=u_col[5]; alpha=.6; } p=rotX(q,.5); }",
 "l": " { float al=.75; float r=.35+mod(cid,24.)*.09; float ph=u*6.2832; float W=u_t*1.1; float y=r*sin(al)*sin(ph-W+r*2.2)*.42; p=rotX(vec3(r*cos(ph),y,r*sin(ph)),.5); col=mix(u_col[2],u_col[1],r/2.6)*(1.-r/2.8); }",
 "la": 0.6,
 "rc": "vec3(0.)",
 "rad": 0
});
