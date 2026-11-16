/* SOST Universe scene module: redshift-wedge (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("redshift-wedge", {
 "p": " if(kind<=.92){ float sd=a_s.x<.5?1.:-1.; float r=.3+3.4*sqrt(fract(a_s.x*2.)); float an=(a_s.y-.5)*.55; float rr=r; float k=floor(r*3.2+fract(a_s.z*5.)*1.3); float wall=step(.55,fract(r*1.6+sin(an*9.+sd)*.25)); float cl=exp(-pow(fract(r*.9+an*2.)-.5,2.)*40.); float fog=fract(a_s.w*13.); float an2=an+(fog-.5)*.015; vec3 q=vec3(sd*rr*sin(an2+1.5708)*0.+rr*cos(an2)*sd,rr*sin(an2),(a_s.z-.5)*.08); q.xy=vec2(q.x,q.y); float vis=max(wall*.5,cl); float sweep=smoothstep(0.,.1,fract(u_t*.05)*4.-r*0.); col=mix(u_col[0],mix(u_col[3],u_col[1],cl),vis)*1.05; alpha=(.03+.17*vis)*(1.-r/4.)*smoothstep(fract(u_t*.04)*5.,fract(u_t*.04)*5.-.6,r)*0.+(.10+.45*vis)*(1.-r/4.2); sz=1.; if(kind<.02){ q=.05*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[3]; alpha=.5; } p=rotX(rotY(vec3(q.x,q.y,q.z),-u_yaw*.4+u_t*.0),-u_tilt+.2+.0); p=rotY(p,0.); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
