/* SOST Universe scene module: deflagration (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("deflagration", {
 "p": " if(kind<=.92){ float T=fract(u_t/11.); vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float R=.25+1.55*smoothstep(0.,.85,T); float tt=u_t*.4; float n=sin(d.x*6.+tt)*sin(d.y*7.-tt*.7)*sin(d.z*6.5+tt*.5)+.5*sin(d.x*15.-tt)*sin(d.y*13.+tt*.8)*sin(d.z*14.)+.25*sin(d.x*31.+d.z*27.+tt); float fing=max(n,-.35); vec3 q; if(kind<.55){ q=d*R*(1.+.30*fing*smoothstep(0.,.3,T)); col=mix(u_col[6],u_col[5],smoothstep(.1,.8,fing))*1.15; alpha=(.22+.40*smoothstep(0.,.8,fing))*smoothstep(1.,.88,T); sz=1.05; } else if(kind<.80){ q=d*R*pow(fract(a_s.x*7.3),.5)*(1.+.2*fing); col=mix(u_col[0],u_col[1],fract(a_s.x*3.))*.9; alpha=.12*smoothstep(1.,.88,T); sz=1.1; } else { q=d*1.95; col=u_col[2]*.8; alpha=.05*(1.-smoothstep(.6,.9,T)); sz=.8; } p=rotY(q,u_t*.08); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
