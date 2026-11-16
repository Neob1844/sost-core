/* SOST Universe scene module: trapped-fireball (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("trapped-fireball", {
 "p": " if(kind<=.92){ vec3 q; float pul=.5+.5*sin(u_t*5.); vec3 C=vec3(0.,.55,0.); if(kind<.75){ vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float r=.75*pow(fract(a_s.w*11.),.45); vec3 c=d*r; for(int i=0;i<3;i++){ c.xy+=flow(c.xy*2.2+float(i)*1.3,u_t*.7)*.05; c.z+=.04*sin(c.x*5.+u_t*1.3); } q=C+c*(1.+.12*pul)*vec3(1.15,.85,1.); col=mix(u_col[5],mix(u_col[1],u_col[0],r/.75),smoothstep(.1,.7,r/.75))*1.15; alpha=.16*(1.2-r/.75)*(.7+.5*pul); sz=1.3; } else { q=vec3(0.,-.8,0.)+.22*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[3]; alpha=.2; sz=.9; } p=rotY(q,u_t*.1); }",
 "l": " { float L=1.5+.22*mod(cid,5.); float az=floor(cid/5.)*.34+j1*.1+u_t*.1; float th_=mix(.2,2.94,u); float rr_=L*sin(th_)*sin(th_); vec3 dq=vec3(rr_*sin(th_)*cos(az),rr_*cos(th_),rr_*sin(th_)*sin(az)); p=rotY(dq*vec3(1.,1.,1.)+vec3(0.,-.8,0.)+vec3(0.,dq.y*0.,0.),0.); col=mix(u_col[2],u_col[0],u)*.7; }",
 "la": 0.8,
 "rc": "vec3(0.)",
 "rad": 0
});
