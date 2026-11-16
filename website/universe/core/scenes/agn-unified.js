/* SOST Universe scene module: agn-unified (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("agn-unified", {
 "p": " if(kind<=.92){ vec3 q; float view=.5+.5*sin(u_t*.07); if(kind<.45){ float th=a_s.y*6.2832, ph=a_s.z*6.2832; float R=1.35, r=.55*(.85+.15*a_s.x); q=vec3((R+r*cos(ph))*cos(th),r*sin(ph)*.8,(R+r*cos(ph))*sin(th)); float lit=clamp(-cos(ph),0.,1.); col=mix(u_col[0]*.6,u_col[6],lit*.7); alpha=.05+.10*lit; sz=1.2; } else if(kind<.75){ float id=floor(a_s.x*90.); vec3 c0=fibp(id,90.)*(.35+.4*fract(id*.618)); c0.y*=.55; c0=rotY(c0,u_t*(.4/(length(c0)+.2))); q=c0+.045*pow(a_s.w,.3)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(u_col[3],u_col[2],fract(id*.3))*1.2; alpha=.25*mix(.15,1.,view); sz=.9; } else if(kind<.83){ float r=mix(.05,.3,a_s.x); float th=a_s.y*6.2832+u_t*2./(r+.05); q=vec3(r*cos(th),0.,r*sin(th)); col=mix(u_col[5],u_col[3],a_s.x); alpha=.28*mix(.2,1.,view); sz=.9; } else { float sd=a_s.x<.5?1.:-1.; float s=fract(a_s.y+u_t*.1); q=vec3((a_s.z-.5)*.05*(1.+s),sd*(.1+s*2.6),(fract(a_s.z*7.)-.5)*.05*(1.+s)); col=mix(u_col[1],u_col[0],s)*1.1; alpha=.25*(1.-s); sz=.9; } p=rotY(rotX(q,mix(-.55,.75,view)),u_t*.05); }",
 "l": " { float view=.5+.5*sin(u_t*.07); float th=u*6.2832; float ph=j1*6.2832; float R=1.35, r=.56; p=rotY(rotX(vec3((R+r*cos(ph))*cos(th),r*sin(ph)*.8,(R+r*cos(ph))*sin(th)),mix(-.55,.75,view)),u_t*.05); col=u_col[0]*.35; }",
 "la": 0.4,
 "rc": "vec3(0.)",
 "rad": 0
});
