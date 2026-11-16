/* SOST Universe scene module: protoplanetary (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("protoplanetary", {
 "p": " if(kind<=.92){ vec3 q; if(kind<.86){ float r=.18+2.5*pow(a_s.x,.8); float gap=exp(-pow((r-.78)/.05,2.))+exp(-pow((r-1.25)/.06,2.))+exp(-pow((r-1.7)/.05,2.))+exp(-pow((r-2.15)/.07,2.)); float th=a_s.y*6.2832+u_t*.4*pow(r,-1.5); q=vec3(r*cos(th),(a_s.z-.5)*.02*r,r*sin(th)); float t=r/2.7; col=mix(u_col[5],mix(u_col[6],u_col[1],t),smoothstep(.1,.8,t))*1.1; alpha=(.22*(1.-min(gap,1.)*.97))*(1.-t*.4); sz=1.; } else if(kind<.90){ float k=floor(a_s.x*4.); float R=k<.5?.78:k<1.5?1.25:k<2.5?1.7:2.15; float th=u_t*.4*pow(R,-1.5)+k*1.7; q=vec3(R*cos(th),0.,R*sin(th))+.04*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[3]*1.2; alpha=.5; sz=1.; } else { q=.09*pow(a_s.x,.5)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[5]; alpha=.35; sz=1.; } p=rotX(q,.25); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
