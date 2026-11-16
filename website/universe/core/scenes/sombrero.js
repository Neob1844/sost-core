/* SOST Universe scene module: sombrero (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("sombrero", {
 "p": " if(kind<=.92){ vec3 q; if(kind<.45){ float r=.05*pow(-log(1.-a_s.x*.995),2.3); r=min(r,2.4); float cz=2.*a_s.z-1.; float s0=sqrt(1.-cz*cz); float ph=a_s.y*6.2832; q=vec3(s0*cos(ph),cz*.72,s0*sin(ph))*r; col=mix(u_col[5],u_col[6],smoothstep(.1,1.4,r))*.95; alpha=.05+.05*smoothstep(.2,1.,r); sz=1.2; } else { float r=1.05+1.6*pow(a_s.x,.8); float th=a_s.y*6.2832+u_t*.12/(r); q=vec3(r*cos(th),(a_s.z-.5)*.05,r*sin(th)); float rim=exp(-pow((r-1.9)*2.2,2.)); col=mix(u_col[6],u_col[5],rim)*1.1; alpha=.08+.22*rim; sz=.9; } q=rotX(q,.09); if(abs(q.y)<.085*(1.+.2*sin(q.x*3.))&&q.z>0.&&length(q.xz)>.6) alpha*=.06; if(abs(q.y)<.06&&q.z>0.) alpha*=.12; p=rotX(rotY(q,-u_yaw*.6),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
