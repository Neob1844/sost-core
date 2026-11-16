/* SOST Universe scene module: timing-array (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("timing-array", {
 "p": " if(kind<=.92){ float id=floor(a_s.x*26.); vec3 P=fibp(id,26.)*2.7; P=rotY(P,u_t*.03); float per=.6+fract(id*.618)*1.6; vec3 kdir=normalize(vec3(.4,.2,1.)); float gw=.06*sin(dot(normalize(P),kdir)*3.-u_t*.8); if(kind<.12){ float cz=2.*a_s.z-1.; p=P+.05*vec3(sqrt(1.-cz*cz)*cos(a_s.y*6.28),cz,sqrt(1.-cz*cz)*sin(a_s.y*6.28)); float bl=pow(max(0.,sin(u_t*6.2832/per)),16.); col=mix(u_col[int(mod(id,7.))],vec3(1.),.2)*1.2; alpha=.25+.6*bl; sz=1.2+bl; } else { float k=floor(a_s.y*9.); float f=fract((u_t/per+k)/9.*1.+gw); p=P*(1.-f); col=u_col[int(mod(id,7.))]*1.2; alpha=.32*smoothstep(0.,.05,f)*(1.-smoothstep(.9,1.,f))*step(fract(a_s.z*3.),.6); sz=.9; } if(kind>.88){ float cz=2.*a_s.z-1.; p=.08*vec3(sqrt(1.-cz*cz)*cos(a_s.y*6.28),cz,sqrt(1.-cz*cz)*sin(a_s.y*6.28)); col=u_col[3]; alpha=.25; sz=.9; } }",
 "l": " { float id=mod(cid,26.); vec3 P=rotY(fibp(id,26.)*2.7,u_t*.03); p=P*u; col=u_col[int(mod(id,7.))]*.35; }",
 "la": 0.5,
 "rc": "vec3(0.)",
 "rad": 0
});
