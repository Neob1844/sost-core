/* SOST Universe scene module: reflection-wisps (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("reflection-wisps", {
 "p": " if(kind<=.92){ vec3 q; vec2 S0=vec2(-.8,.4),S1=vec2(.6,.6),S2=vec2(.1,-.3),S3=vec2(1.1,-.4),S4=vec2(-.4,-.8),S5=vec2(-1.4,-.1),S6=vec2(.9,1.1); S0+=u_ptr*u_ptrA*.4; if(kind<.82){ vec2 xy=(a_s.xy-.5)*vec2(6.,4.); float st=.5+.5*sin((xy.x*.5+xy.y*.87)*16.+sin(xy.x*2.)*1.5+u_t*.05); st=pow(st,3.); float dd=min(min(min(length(xy-S0),length(xy-S1)),min(length(xy-S2),length(xy-S3))),min(min(length(xy-S4),length(xy-S5)),length(xy-S6))); q=vec3(xy,(a_s.z-.5)*.6); col=mix(u_col[2],u_col[3],exp(-dd*2.))*1.1; alpha=(.08+.40*st)*exp(-dd*.9); sz=1.4; } else { float k=floor(a_s.x*7.); vec2 s=k<.5?S0:k<1.5?S1:k<2.5?S2:k<3.5?S3:k<4.5?S4:k<5.5?S5:S6; float r=.09*pow(fract(a_s.w*13.),2.); q=vec3(s,0.)+r*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(vec3(.8,.9,1.),u_col[3],.5); alpha=.3; sz=1.; } p=rotX(rotY(q,-u_yaw*.6),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
