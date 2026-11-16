/* SOST Universe scene module: giant-flare (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("giant-flare", {
 "p": " if(kind<=.92){ float T=fract(u_t/12.); float fl=smoothstep(.58,.6,T)*(1.-smoothstep(.6,.75,T)); float tail=smoothstep(.6,.65,T)*(1.-smoothstep(.65,1.,T)); float pul=.5+.5*sin(u_t*8.); vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); vec3 q; if(kind<.35){ q=d*.5; float cr=step(.985,abs(sin(d.x*9.+d.z*4.)*sin(d.y*7.-d.x*3.)))+step(.99,abs(sin(d.z*13.+d.y*5.))); float b=smoothstep(.2,.58,T)*(1.-smoothstep(.6,1.,T)); col=mix(u_col[0]*.7,u_col[5],min(cr,1.)*b)*1.1; alpha=.10+.45*min(cr,1.)*b; sz=.9; } else if(kind<.75){ float R=(T-.6)*9.; q=d*R*(1.+.1*sin(d.x*10.)); col=mix(u_col[5],u_col[1],smoothstep(.5,3.5,R))*1.2; alpha=.30*step(.6,T)*(1.-smoothstep(1.,4.,R))*(1.-.5*smoothstep(.62,.7,T)); sz=1.; } else { float r=.55+.25*pow(a_s.x,2.); q=d*r*vec3(1.,.8,1.)+vec3(.9,0.,0.); col=mix(u_col[1],u_col[5],pul); alpha=.25*tail*pul; sz=1.1; } alpha*=1.+fl; p=rotY(q,u_t*.15); }",
 "l": " { float T=fract(u_t/12.); float op=smoothstep(.58,.62,T)*(1.-smoothstep(.7,1.,T)); float L=.7+.18*mod(cid,8.); float az=floor(cid/8.)*.4+j1*.2; float th_=mix(.2,2.94,u); float rr_=L*sin(th_)*sin(th_); vec3 dq=vec3(rr_*sin(th_)*cos(az),rr_*cos(th_),rr_*sin(th_)*sin(az)); vec3 rad=normalize(dq+1e-4); dq+=rad*op*u*(1.-u)*4.*L*step(.5,j2); p=rotY(dq,u_t*.15); col=mix(u_col[2],u_col[1],op)*(1.+op); }",
 "la": 0.9,
 "rc": "vec3(0.)",
 "rad": 0
});
