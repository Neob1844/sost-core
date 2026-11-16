/* SOST Universe scene module: bao-shells (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("bao-shells", {
 "p": " if(kind<=.92){ vec3 q; float k=floor(a_s.x*14.); vec3 C=(vec3(fract(sin(k*12.9898)*43758.5),fract(sin(k*78.233)*43758.5),fract(sin(k*39.425)*43758.5))-.5)*vec3(4.4,2.8,2.8); float T=fract(u_t*.05+k*.071); float R=1.15*smoothstep(0.,.6,T); if(kind<.70){ vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); q=C+d*R*(1.+(fract(a_s.w*13.)-.5)*.06); col=u_col[int(mod(k,7.))]*1.15; alpha=.07*smoothstep(0.,.1,T)*(1.-smoothstep(.85,1.,T)); sz=.9; } else if(kind<.80){ q=C+.06*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[5]; alpha=.4*(1.-smoothstep(.85,1.,T)); sz=1.; } else { q=(vec3(a_s.x,a_s.y,a_s.z)-.5)*vec3(5.,3.4,3.4); col=u_col[0]*.7; alpha=.02; sz=.9; } p=rotY(q,u_t*.03); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
