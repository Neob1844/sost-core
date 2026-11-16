/* SOST Universe scene module: double-pulsar (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("double-pulsar", {
 "p": " if(kind<=.92){ float ph=u_t*.45; vec3 A=vec3(cos(ph),0.,sin(ph))*.75, B=-A*1.07; float gi=step(.5,fract(a_s.w*7.)); vec3 C=gi>.5?A:B; float spin=u_t*(gi>.5?2.2:.9)+gi*2.; vec3 ax=rotY(rotX(vec3(0.,1.,0.),gi>.5?.55:.9),spin); if(kind<.10){ float cz=2.*a_s.z-1.; p=C+.09*vec3(sqrt(1.-cz*cz)*cos(a_s.y*6.28),cz,sqrt(1.-cz*cz)*sin(a_s.y*6.28)); col=gi>.5?u_col[3]:u_col[5]; alpha=.55; sz=1.; } else { float s=a_s.x; float sd=a_s.y<.5?1.:-1.; vec3 t1=normalize(cross(ax,vec3(0.,0.,1.))); vec3 t2=cross(ax,t1); float an=a_s.z*6.2832; float rr=(.02+.22*s)*sqrt(fract(a_s.y*13.)); p=C+ax*sd*(s*2.2+.1)+(t1*cos(an)+t2*sin(an))*rr; col=(gi>.5?mix(u_col[3],u_col[2],s):mix(u_col[5],u_col[6],s))*1.15; alpha=.28*(1.-s); sz=.9; } }",
 "l": " { float ph=u_t*.45; vec3 A=vec3(cos(ph),0.,sin(ph))*.75; float gi=mod(cid,2.); vec3 C=gi>.5?A:-A*1.07; float spin=u_t*(gi>.5?2.2:.9)+gi*2.; float L=.25+.12*mod(floor(cid/2.),4.); float az=floor(cid/8.)*.785+j1*.2; float th=mix(.15,2.99,u); float r=L*sin(th)*sin(th); vec3 q=vec3(r*sin(th)*cos(az),r*cos(th),r*sin(th)*sin(az)); q=rotY(rotX(q,gi>.5?.55:.9),spin); p=C+q; col=(gi>.5?u_col[0]:u_col[1])*1.1; }",
 "la": 0.55,
 "rc": "vec3(0.)",
 "rad": 0
});
