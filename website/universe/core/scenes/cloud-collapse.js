/* SOST Universe scene module: cloud-collapse (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("cloud-collapse", {
 "p": " if(kind<=.92){ float T=fract(u_t/18.); float f1=smoothstep(.05,.45,T), f2=smoothstep(.45,.8,T); float e=floor(a_s.x*9.); float ia=mod(e,6.), ib=mod(e*2.+1.,6.); if(ia==ib) ib=mod(ib+1.,6.); vec3 A=fibp(ia,6.)*1.6, B=fibp(ib,6.)*1.6; A.y*=.6; B.y*=.6; float s=a_s.y; vec3 fil=mix(A,B,s)+(vec3(fract(a_s.z*7.),fract(a_s.z*13.),fract(a_s.z*3.))-.5)*.12; vec3 core=(s<.5?A:B)+.08*pow(fract(a_s.w*11.),.5)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); vec3 g=(vec3(a_s.z,fract(a_s.y*7.31),fract(a_s.x*3.17))-.5)*vec3(5.,3.,3.); g.xz+=flow(g.xz*.6,u_t*.1)*.3; vec3 q=mix(mix(g,fil,f1),core,f2*smoothstep(.0,.5,abs(s-.5)*2.)*.0+f2*0.); q=mix(q,core,f2*step(.6,fract(a_s.w*5.))); float ign=f2*step(.6,fract(a_s.w*5.)); col=mix(mix(u_col[0],u_col[2],f1),u_col[5],ign)*1.1; alpha=(.14+.22*f1+.40*ign)*smoothstep(0.,.05,T)*smoothstep(1.,.93,T); sz=1.1; p=rotY(q,u_t*.04); }",
 "l": " { float T=fract(u_t/18.); float f1=smoothstep(.05,.45,T); float e=mod(cid,9.); float ia=mod(e,6.), ib=mod(e*2.+1.,6.); if(ia==ib) ib=mod(ib+1.,6.); vec3 A=fibp(ia,6.)*1.6, B=fibp(ib,6.)*1.6; A.y*=.6; B.y*=.6; p=rotY(mix(A,B,u)+(vec3(j1,j2,j3)-.5)*.1,u_t*.04); col=u_col[2]*f1*.35*smoothstep(1.,.93,T); }",
 "la": 0.5,
 "rc": "vec3(0.)",
 "rad": 0
});
