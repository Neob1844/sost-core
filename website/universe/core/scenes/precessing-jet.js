/* SOST Universe scene module: precessing-jet (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("precessing-jet", {
 "p": " if(kind<=.92){ vec3 q; float P=9.; float cone=.36; if(kind<.70){ float sd=a_s.x<.5?1.:-1.; float f=a_s.y; float tl=u_t-f*P*.55; float az=tl*6.2832/P; vec3 d=normalize(vec3(sin(cone)*cos(az),cos(cone),sin(cone)*sin(az))); q=sd*d*(.15+f*3.)+(vec3(fract(a_s.z*7.),fract(a_s.z*13.),fract(a_s.z*3.))-.5)*(.02+.08*f); col=u_col[int(mod(floor(tl/P*7.)+(sd>0.?0.:3.),7.))]*1.15; alpha=.28*(1.-f*.7); sz=.9+.4*f; } else if(kind<.85){ float r=mix(.08,.55,a_s.x); float th=a_s.y*6.2832+u_t*1.2/(r+.1); q=vec3(r*cos(th),(a_s.z-.5)*.02,r*sin(th)); col=mix(u_col[5],u_col[6],a_s.x); alpha=.18; sz=.9; } else { q=vec3(-.9,0.,0.)+.22*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[2]*1.1; alpha=.15; sz=1.; } p=rotX(q,-.25); }",
 "l": " { float P=9.; float cone=.36; float sd=mod(cid,2.)<.5?1.:-1.; float f=u; float tl=u_t-f*P*.55-j1*.1; float az=tl*6.2832/P; vec3 d=normalize(vec3(sin(cone)*cos(az),cos(cone),sin(cone)*sin(az))); p=rotX(sd*d*(.15+f*3.),-.25); col=u_col[int(mod(floor(tl/P*7.)+(sd>0.?0.:3.),7.))]*(1.-f)*.8; }",
 "la": 0.5,
 "rc": "vec3(0.)",
 "rad": 0
});
