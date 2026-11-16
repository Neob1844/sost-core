/* SOST Universe scene module: kilonova (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("kilonova", {
 "p": " if(kind<=.92){ float T=fract(u_t/14.); vec3 q; float ins=smoothstep(.0,.35,T); float ex=smoothstep(.35,.42,T); float ag=clamp((T-.4)/.6,0.,1.); if(kind<.40){ float k=step(.5,a_s.x); float sep=mix(1.,.0,ins*ins); float ph=u_t*(2.+12.*ins*ins)+k*3.1416; vec3 C=vec3(cos(ph),0.,sin(ph))*sep*.9; q=C+.17*pow(fract(a_s.w*7.),.4)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832))*(1.-ex); col=k>.5?u_col[2]:u_col[3]; col*=1.1; alpha=.18*(1.-ex); sz=.9; } else { vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float pol=abs(d.y); float v=mix(1.,1.7,pol); float R=ag*3.*v*pow(fract(a_s.w*13.),.25); q=d*R*vec3(1.,1.,1.); float hot=1.-ag; col=pol>.5?mix(u_col[5],u_col[3],ag):mix(u_col[5],u_col[1],pow(ag,.7)); col=mix(col,u_col[0],ag*ag*.6)*1.1; alpha=ex*(.05+.25*hot)*(1.-smoothstep(.9,1.,T)); sz=1.+.5*hot; } p=rotY(rotX(q,.3),u_t*.04); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
