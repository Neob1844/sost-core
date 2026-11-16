/* SOST Universe scene module: black-widow (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("black-widow", {
 "p": " if(kind<=.92){ float ph=u_t*.6; vec3 C=vec3(cos(ph),0.,sin(ph))*1.45; if(kind<.06){ float cz=2.*a_s.z-1.; p=.07*vec3(sqrt(1.-cz*cz)*cos(a_s.y*6.28),cz,sqrt(1.-cz*cz)*sin(a_s.y*6.28)); col=u_col[3]*1.2; alpha=.6; sz=1.1; } else if(kind<.22){ float cz=2.*a_s.z-1.; vec3 n=vec3(sqrt(1.-cz*cz)*cos(a_s.y*6.28),cz,sqrt(1.-cz*cz)*sin(a_s.y*6.28)); p=C+n*.24; float day=clamp(dot(n,normalize(-C)),0.,1.); col=mix(u_col[6]*.5,u_col[5],day)*1.1; alpha=.10+.35*day; sz=1.; } else if(kind<.82){ float f=a_s.x; float a2=ph-f*1.5; vec3 Cf=vec3(cos(a2),0.,sin(a2))*1.45; vec3 rd=normalize(Cf); float w=(.05+f*.45); p=Cf+rd*(.24+f*2.2)+vec3(fract(a_s.y*13.)-.5,(a_s.z-.5),fract(a_s.y*7.3)-.5)*w; col=mix(u_col[6],mix(u_col[1],u_col[0],f),smoothstep(0.,.4,f))*1.2; alpha=.30*(1.-f)*(1.-f); sz=.9+.5*f; } else { float f=fract(a_s.x+u_t*.3); float cz=2.*a_s.z-1.; vec3 n=vec3(sqrt(1.-cz*cz)*cos(a_s.y*6.28),cz,sqrt(1.-cz*cz)*sin(a_s.y*6.28)); p=n*(.1+f*2.6); col=u_col[2]; alpha=.06*(1.-f); sz=.8; } p=rotX(p,.15); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
