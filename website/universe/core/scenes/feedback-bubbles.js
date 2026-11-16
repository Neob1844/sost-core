/* SOST Universe scene module: feedback-bubbles (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("feedback-bubbles", {
 "p": " if(kind<=.92){ vec3 q; float T=fract(u_t*.04); vec2 b1=vec2(-.75,.55+T*1.6), b2=vec2(.8,-.5-T*1.5); float rb=.42+T*.25; if(kind<.80){ vec2 xy=(vec2(a_s.x+fract(a_s.x*7.3),a_s.y+fract(a_s.y*5.1))-1.)*vec2(4.4,3.); float r=length(xy); float wave=.5+.5*sin(r*7.-u_t*1.6); float fall=exp(-r*.55); float d1=length(xy-b1)/rb, d2=length(xy-b2)/rb; float cav=(1.-smoothstep(.85,1.,d1))+(1.-smoothstep(.85,1.,d2)); float rim=exp(-pow((d1-1.)*9.,2.))+exp(-pow((d2-1.)*9.,2.)); q=vec3(xy,(a_s.z-.5)*.3); col=mix(u_col[0],u_col[2],wave)*1.05; col=mix(col,u_col[3],min(rim,1.)*.7); alpha=(.18+.40*fall*(.4+.6*wave))*(1.-min(cav,1.))+.40*min(rim,1.); sz=1.15; } else if(kind<.83){ q=vec3(0.,0.,0.)+.07*pow(a_s.x,.5)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[5]; alpha=.45; sz=1.; } else { float r=.05*pow(-log(1.-a_s.x*.99),2.); q=min(r,1.2)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(u_col[5],u_col[6],a_s.x); alpha=.05; sz=1.1; } p=rotX(rotY(q,-u_yaw),-u_tilt+.15); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
