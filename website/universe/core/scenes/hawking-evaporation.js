/* SOST Universe scene module: hawking-evaporation (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("hawking-evaporation", {
 "p": " if(kind<=.92){ float T=fract(u_t/15.); float R=.55*pow(1.-T*.985,.333); float temp=clamp(T*1.1,0.,1.); vec3 dir=normalize(vec3(a_s.z-.5,fract(a_s.x*17.3)-.5,fract(a_s.y*23.7)-.5)+1e-4); if(kind<.12){ p=dir*R; col=u_col[int(clamp(floor(temp*6.99),0.,6.))]*.6; alpha=.22; sz=.7; } else { float sp=.35*(1.+temp*2.); float f=fract(u_t*sp+a_s.x*7.); float ou=step(.5,fract(a_s.y*9.1)); float rate=.35+.6*temp*temp; float emit=step(fract(a_s.y*3.7+floor(u_t*sp+a_s.x*7.)*.37),rate); float r=ou>.5?R*(1.+.08*smoothstep(0.,.1,f))+f*f*3.5*smoothstep(.04,.3,f):R*(1.+.08*(1.-f))-R*f; p=dir*max(r,0.)+normalize(cross(dir,vec3(0.,1.,0.))+1e-4)*.04*(ou>.5?1.:-1.)*(1.-f); col=mix(u_col[int(clamp(floor(temp*6.99+a_s.z*1.5),0.,6.))],vec3(1.),.1)*1.2; alpha=emit*(ou>.5?(1.-f):max(0.,1.-f*4.))*.6; sz=1.5; } float fl=smoothstep(.975,.99,T)*(1.-smoothstep(.99,1.,T)); if(kind>.7&&fl>0.){ p=dir*(T-.975)*120.*(.5+a_s.x); col=u_col[int(band)]*1.2; alpha=fl*.5; sz=1.2; } }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "rad": 0,
 "la": 0,
 "rc": "vec3(0.)"
});
