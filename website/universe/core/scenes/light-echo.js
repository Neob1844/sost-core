/* SOST Universe scene module: light-echo (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("light-echo", {
 "p": " if(kind<=.92){ float T=fract(u_t/8.+.45); float R=T*3.6; float id=floor(a_s.x*700.); vec3 c0=normalize(fibp(id,700.)+(vec3(fract(id*.31),fract(id*.71),fract(id*.13))-.5)*.5)*(.5+2.1*pow(fract(id*.618),.7)); c0=rotY(c0,u_t*.12/(length(c0)+.3)); vec3 q=c0+.05*pow(a_s.w,.3)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float d=length(c0); float hit=exp(-pow((d-R)/.18,2.)); float after=smoothstep(R,R-.5,d)*(1.-T)*.5; col=mix(u_col[0],mix(u_col[3],u_col[5],hit),hit+after)*1.15; alpha=.08+.45*hit+.16*after; sz=.9+.6*hit; if(kind<.03){ q=.06*pow(a_s.x,.5)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[5]; alpha=.2+.6*exp(-T*14.); } p=q; }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
