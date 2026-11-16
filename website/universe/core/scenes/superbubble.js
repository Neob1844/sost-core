/* SOST Universe scene module: superbubble (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("superbubble", {
 "p": " if(kind<=.92){ float T=fract(u_t/20.); float Rb=.35+1.3*smoothstep(0.,.7,T); float H=Rb*(1.4+1.6*T); vec3 q; if(kind<.45){ float r=.2+3.2*sqrt(a_s.x); float th=a_s.y*6.2832+u_t*.03; q=vec3(r*cos(th),(a_s.z-.5)*.10,r*sin(th)); float hole=1.-smoothstep(Rb*.9,Rb*1.05,r); float wall=exp(-pow((r-Rb)/.12,2.)); col=mix(u_col[0],u_col[2],fract(a_s.z*3.))*.9; col=mix(col,u_col[1],wall); alpha=(.24+.35*wall)*(1.-hole); sz=1.15; } else if(kind<.82){ float sd=a_s.x<.5?1.:-1.; float u2=a_s.y; float an=a_s.z*6.2832; float y=u2*H; float rr=Rb*sqrt(max(0.,1.-pow(u2,2.)*.75))*(1.+.35*smoothstep(.6,1.,u2)*T); float open=step(u2,.92-.3*T*step(.5,T)); q=vec3(rr*cos(an),sd*y,rr*sin(an))*(1.+.04*sin(an*9.+u2*12.)); col=mix(u_col[1],u_col[6],u2)*1.1; alpha=.22*open*(1.-u2*.5); sz=1.05; } else { float id=floor(a_s.x*14.); vec3 c0=(vec3(fract(sin(id*12.9)*43758.5),fract(sin(id*78.2)*43758.5),fract(sin(id*39.4)*43758.5))-.5)*.5; float sn=exp(-pow(fract(u_t*.3+id*.37)*12.,2.)); q=c0+(.02+.25*sn)*pow(fract(a_s.w*13.),.5)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(u_col[3],u_col[5],sn); alpha=.3+.4*sn; sz=.9; } p=rotX(q,-.15); alpha*=smoothstep(0.,.03,T)*smoothstep(1.,.95,T); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
