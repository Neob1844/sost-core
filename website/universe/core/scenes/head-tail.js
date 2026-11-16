/* SOST Universe scene module: head-tail (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("head-tail", {
 "p": " if(kind<=.92){ vec3 H=vec3(-2.1+.2*sin(u_t*.1),.1,0.); vec3 q; float wind=1.+u_ptr.x*u_ptrA*.6; if(kind<.12){ float r=.25*pow(a_s.x,1.4); q=H+r*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832))*vec3(1.,.7,.8); col=mix(u_col[5],u_col[6],a_s.x); alpha=.14; sz=1.; } else if(kind<.80){ float sd=a_s.y<.5?1.:-1.; float s=pow(a_s.x,.8); float y=sd*.45*min(s*4.,1.)*(1.-.55*smoothstep(.25,1.,s)); float x=s*s*4.6*wind; float wv=.18*sin(s*7.-u_t*1.3)*s; q=H+vec3(x,y+wv,(a_s.z-.5)*(.03+.25*s))+vec3(fract(a_s.w*11.)-.5,fract(a_s.w*7.)-.5,0.)*(.02+.22*s*s); col=mix(u_col[3],mix(u_col[1],u_col[0],s),smoothstep(.05,.5,s))*1.15; alpha=.28*(1.-s*.75); sz=.9+s*.5; } else { q=vec3((a_s.x-.5)*8.,(a_s.y-.5)*4.,(a_s.z-.5)*3.); col=u_col[0]*.6; alpha=.012; sz=1.6; } p=rotX(rotY(q,-u_yaw*.4),-u_tilt+.12); }",
 "l": " { vec3 H=vec3(-2.1+.2*sin(u_t*.1),.1,0.); float wind=1.+u_ptr.x*u_ptrA*.6; float sd=mod(cid,2.)<.5?1.:-1.; float s=u; float y=sd*.45*min(s*4.,1.)*(1.-.55*smoothstep(.25,1.,s)); float wv=.18*sin(s*7.-u_t*1.3)*s; p=rotX(rotY(H+vec3(s*s*4.6*wind,y+wv+(j1-.5)*.1*s,(j2-.5)*.2*s),-u_yaw*.4),-u_tilt+.12); col=mix(u_col[3],u_col[1],s)*.6; }",
 "la": 0.6,
 "rc": "vec3(0.)",
 "rad": 0
});
