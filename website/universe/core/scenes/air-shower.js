/* SOST Universe scene module: air-shower (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("air-shower", {
 "p": " if(kind<=.92){ float T=fract(u_t/6.+.5); float gen=floor(a_s.x*7.); float d=(gen+fract(a_s.y))/7.; float y=2.2-d*4.6; float n=pow(2.,gen); float br=floor(fract(a_s.z*1.)*n); float sp=0.; float bb=br; for(int i=0;i<7;i++){ if(float(i)>=gen) break; sp+=((mod(bb,2.)<.5)?-1.:1.)*.35*pow(.62,float(i)); bb=floor(bb/2.); } float zsp=sp*(fract(br*.618)-.5)*1.2; vec3 q=vec3(sp*d*2.2+(fract(a_s.w*7.)-.5)*.02,y,zsp*d*2.2); float vis=smoothstep(d-.02,d,T*1.15)*(1.-smoothstep(d,d+.35,T*1.15)*.7); col=mix(u_col[5],mix(u_col[2],u_col[1],d),d)*1.15; alpha=.30*vis; sz=.9; if(kind<.10){ q=vec3((a_s.x-.5)*5.,-2.45,(a_s.y-.5)*2.); float hit=exp(-pow(length(q.xz)*1.,2.))*smoothstep(.8,.95,T*1.15); col=u_col[3]; alpha=.04+.5*hit*step(.97,fract(a_s.z*37.)); } p=rotX(rotY(q,-u_yaw*.4+u_t*.05),-u_tilt+.25); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
