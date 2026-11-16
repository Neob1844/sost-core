/* SOST Universe scene module: elliptical (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("elliptical", {
 "p": " if(kind<=.92){ if(kind<.07){ float id=floor(a_s.x*44.); vec3 c0=fibp(id,44.)*(1.5+1.2*fract(id*.618)); c0=rotY(c0,u_t*(.05+.04*fract(id*.37))); float rr=.05*pow(a_s.y,.5); float cz=2.*a_s.z-1.; p=c0+rr*vec3(sqrt(1.-cz*cz)*cos(a_s.y*80.),cz,sqrt(1.-cz*cz)*sin(a_s.y*80.)); col=mix(u_col[3],u_col[4],fract(id*.29))*1.1; alpha=.30; sz=.8; } else { float r=.06*pow(-log(1.-a_s.x*.995),2.6); r=min(r,3.2); float cz=2.*a_s.z-1.; float s0=sqrt(1.-cz*cz); float ph=a_s.y*6.2832; vec3 d=vec3(s0*cos(ph),cz,s0*sin(ph)); p=rotY(d*r*vec3(1.,.62,.8),u_t*.03+.4); float tr=clamp(r/2.,0.,1.); col=mix(u_col[5],mix(u_col[6],u_col[0],tr),smoothstep(.05,.8,tr)); alpha=.035+.06*smoothstep(.1,1.,r); sz=1.2+.6*tr; } }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
