/* SOST Universe scene module: bok-globule (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("bok-globule", {
 "p": " if(kind<=.92){ vec3 q; vec2 G=vec2(.2*sin(u_t*.05),.1); float R=1.0*(1.+.04*sin(u_t*.3)); if(kind<.72){ vec2 xy=(a_s.xy-.5)*vec2(15.,7.4); vec2 rel=xy-G; float an=atan(rel.y,rel.x); float Rs=R*(1.+.13*sin(an*3.+1.)+.07*sin(an*5.-u_t*.1)+.35*smoothstep(.6,1.,cos(an+2.4))); float d=length(rel*vec2(1.,1.15)); float hid=smoothstep(Rs*.93,Rs*1.05,d); float rim=exp(-pow((d-Rs*1.06)*7.,2.)); float neb=.5+.5*sin(xy.x*1.3+sin(xy.y*1.7)*1.2)*sin(xy.y*1.1-cos(xy.x*.9)); neb=pow(neb,1.4); float br=step(.986,fract(a_s.z*97.)); q=vec3(xy,-1.); col=mix(mix(u_col[1],u_col[6],neb),u_col[5],min(rim*1.3,1.))*1.35; col=mix(col,vec3(1.,.95,.9),br*.6); alpha=(.30+.95*neb+.85*rim)*hid*exp(-length(xy)*.07)+br*.55*(hid+.2*(1.-hid)); sz=1.7+1.3*br+.5*rim; } else { vec2 xy=(vec2(a_s.x+fract(a_s.x*7.3),a_s.y+fract(a_s.y*3.7))-1.)*vec2(4.2,2.8); float d=length((xy-G)*vec2(1.,1.15)); q=vec3(xy,-1.3); col=mix(u_col[1],u_col[6],a_s.z)*1.1; alpha=.40*smoothstep(R*.95,R*1.25,d)*exp(-length(xy)*.22); sz=1.9; } p=rotX(rotY(q,-u_yaw*.6),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
