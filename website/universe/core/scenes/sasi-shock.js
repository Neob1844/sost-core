/* SOST Universe scene module: sasi-shock (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("sasi-shock", {
 "p": " if(kind<=.92){ float w=u_t*.9; vec3 dir=vec3(cos(w),.25*sin(w*.6),sin(w)); float amp=.22+.08*sin(u_t*.37); vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); vec3 q; if(kind<.50){ float r=1.15*(1.+amp*dot(d,dir)+.04*sin(d.x*12.+u_t)*sin(d.y*10.)); q=d*r+dir*amp*.3; col=mix(u_col[2],u_col[0],.5+.5*dot(d,dir))*1.15; alpha=.22+.22*smoothstep(.0,1.,dot(d,dir)); sz=1.; } else if(kind<.88){ float r=1.1*pow(fract(a_s.w*11.),.5); vec3 c=d*r; for(int i=0;i<3;i++){ c.xz+=flow(c.xz*1.6+float(i),u_t*.5)*.08; c.y+=.06*sin(c.x*4.+u_t); } q=c*(1.+amp*.5*dot(normalize(c+1e-4),dir)); col=mix(u_col[6],u_col[5],r)*1.05; alpha=.12; sz=1.05; } else { q=d*.18*pow(a_s.x,.5); col=u_col[3]; alpha=.25; sz=.9; } p=q; }",
 "l": " { float w=u_t*.9; vec3 dir=vec3(cos(w),.25*sin(w*.6),sin(w)); float amp=.22+.08*sin(u_t*.37); float ph=(mod(cid,16.)+.5)/16.*3.1416; float th=u*6.2832; vec3 d=vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); float r=1.15*(1.+amp*dot(d,dir)); p=d*r+dir*amp*.3; col=u_col[2]*.6; }",
 "la": 0.4,
 "rc": "vec3(0.)",
 "rad": 0
});
