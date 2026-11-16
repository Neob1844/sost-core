/* SOST Universe scene module: cartwheel (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("cartwheel", {
 "p": " if(kind<=.92){ float T=fract(u_t/18.+.3); float R=.25+2.5*T; vec3 q; if(kind<.40){ float th=a_s.y*6.2832; float w=(a_s.z+fract(a_s.z*7.3)-1.)*.16; float r=R+w; q=vec3(r*cos(th),(a_s.x-.5)*.05,r*sin(th)); float kn=step(fract(a_s.x*13.+floor(th*6.)*.37),.3); col=mix(u_col[3],u_col[1],kn)*1.2; alpha=(.32+.2*kn)*(1.-T*.5); sz=.9+.5*kn; } else if(kind<.55){ float th=a_s.y*6.2832; float r=R*.38+(a_s.z-.5)*.08; q=vec3(r*cos(th),0.,r*sin(th)); col=u_col[0]*1.1; alpha=.25; sz=.9; } else if(kind<.70){ float sp=floor(a_s.y*11.); float th=sp/11.*6.2832+(a_s.z-.5)*.06+a_s.x*.5; float r=R*.4+(R*.6)*a_s.x; q=vec3(r*cos(th),0.,r*sin(th)); col=u_col[2]*.9; alpha=.16; sz=.8; } else if(kind<.80){ float r=.22*pow(a_s.x,1.5); float cz=2.*a_s.z-1.; float s0=sqrt(1.-cz*cz); q=r*vec3(s0*cos(a_s.y*6.28),cz*.6,s0*sin(a_s.y*6.28)); col=u_col[5]; alpha=.14; sz=1.; } else if(kind<.86){ vec3 c0=vec3(1.8+T*1.4,.9+T*1.6,-1.2); float r=.28*pow(a_s.x,.8); float th=a_s.y*6.2832; q=c0+vec3(r*cos(th),r*sin(th)*.5,(a_s.z-.5)*.05); col=u_col[6]; alpha=.2; sz=.9; } else { float r=.3+2.9*sqrt(a_s.x); float th=a_s.y*6.2832; q=vec3(r*cos(th),0.,r*sin(th)); col=u_col[0]*.6; alpha=.05*step(R,r)+.02; sz=.8; } p=rotY(rotX(q,.25),u_t*.03); alpha*=smoothstep(0.,.05,T)*smoothstep(1.,.94,T); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
