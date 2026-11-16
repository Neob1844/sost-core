/* SOST Universe scene module: grb-jet (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("grb-jet", {
 "p": " if(kind<=.92){ float T=fract(u_t/9.); vec3 q; float sd=a_s.x<.5?1.:-1.; if(kind<.55){ float k=floor(fract(a_s.x*2.)*10.); float ts=k*.06; float f=clamp((T-ts)/.6,0.,1.); float th=.05*sqrt(a_s.y); float an=a_s.z*6.2832; float R=.3+f*3.4*(1.-.08*k); q=sd*vec3(R*sin(th)*cos(an),R*cos(th),R*sin(th)*sin(an))*vec3(1.+f*2.,1.,1.+f*2.); float int_=exp(-f*3.)*step(ts,T); col=mix(u_col[5],mix(u_col[3],u_col[1],f),f)*1.2; alpha=.40*int_*(sd>0.?1.:.6); sz=1.+int_*.6; } else if(kind<.80){ float r=.2+.6*fract(a_s.w*11.); float th=a_s.y*6.2832+u_t*2./r; q=vec3(r*cos(th),(a_s.z-.5)*.06,r*sin(th)); col=mix(u_col[5],u_col[6],r); alpha=.15*(1.-smoothstep(.0,.3,T)*.5); sz=.9; } else { vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float R=.35+T*.9; q=d*R*(1.+.2*sin(d.x*6.+d.y*5.)); col=mix(u_col[0],u_col[6],T)*.9; alpha=.05*(1.-T); sz=1.1; } p=rotY(rotX(q,.35),.4+u_t*.03); }",
 "l": " { float sd=mod(cid,2.)<.5?1.:-1.; float an=floor(cid/2.)*.5+j1; float th=.035; float L=u*3.8; p=rotY(rotX(sd*vec3(L*sin(th)*cos(an),L,L*sin(th)*sin(an)),.35),.4+u_t*.03); col=u_col[2]*(1.-u)*.6; }",
 "la": 0.8,
 "rc": "vec3(0.)",
 "rad": 0
});
