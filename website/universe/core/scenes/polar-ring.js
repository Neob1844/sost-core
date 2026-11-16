/* SOST Universe scene module: polar-ring (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("polar-ring", {
 "p": " if(kind<=.92){ vec3 q; if(kind<.40){ float r=.9*pow(a_s.x,1.3); float th=a_s.y*6.2832+u_t*.3; q=vec3(r*cos(th),(a_s.z-.5)*.12*(1.-r),r*sin(th)); col=mix(u_col[5],u_col[6],r)*.95; alpha=.10; sz=1.; } else { float th=a_s.y*6.2832+u_t*.12; float r=1.75+(a_s.z+fract(a_s.z*7.3)-1.)*.28; float wv=.12*sin(th*2.+u_t*.2); q=vec3((a_s.x-.5)*.18+wv,r*cos(th),r*sin(th)); float kn=step(fract(a_s.x*23.+floor(th*8.)*.41),.22); col=mix(u_col[2],u_col[3],.5+.5*sin(th*3.))*1.1; col=mix(col,u_col[1]*1.2,kn); alpha=.16+.14*kn; sz=.9; } p=rotY(rotX(q,.25),.7+u_t*.04); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
