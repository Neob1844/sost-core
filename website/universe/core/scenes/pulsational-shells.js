/* SOST Universe scene module: pulsational-shells (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("pulsational-shells", {
 "p": " if(kind<=.92){ float P=3.2; float k=floor(a_s.x*6.); float n=floor(u_t/P)-k; float age=u_t-n*P; float v=.28+.30*fract(sin(n*12.9898)*43758.5); float r=.12+v*age; float vo=.28+.30*fract(sin((n-1.)*12.9898)*43758.5); float ro=.12+vo*(age+P); float hit=exp(-pow((r-ro)*6.,2.))*step(vo,v); vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float lob=1.+.12*d.y*d.y; vec3 q=d*r*lob*(1.+.02*sin(d.x*20.+n)); col=mix(u_col[int(mod(n,7.))],u_col[5],hit)*1.1; alpha=(.22+.5*hit)*smoothstep(0.,.5,age)*(1.-smoothstep(3.,3.4,r)); sz=.9+hit; if(kind<.04){ q=d*.14*pow(a_s.x*20.,.3); col=u_col[3]; alpha=.35+.3*exp(-fract(u_t/P)*6.); sz=1.; } p=rotY(q,u_t*.05); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
