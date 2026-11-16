/* SOST Universe scene module: veil-filaments (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("veil-filaments", {
 "p": " if(kind<=.92){ float k=floor(a_s.x*36.); float s=(a_s.y-.5)*1.9; float hh=fract(sin(k*12.9898)*43758.5); float R=3.2+hh*.5; float set_=step(.5,fract(k*.5)); float wv=.10*sin(s*9.+k*1.7+u_t*.25)+.05*sin(s*23.-k+u_t*.4); float an=s+.1*hh; vec3 q=vec3((R+wv)*sin(an),(R+wv)*cos(an)-3.4,(hh-.5)*1.4+.15*sin(s*5.+k)); q.y+=set_*.10; q+=(vec3(fract(a_s.z*7.),fract(a_s.z*13.),fract(a_s.z*3.))-.5)*.025; col=set_>.5?mix(u_col[3],u_col[2],hh):mix(u_col[6],u_col[1],hh); col*=1.1; alpha=.16*smoothstep(.95,.5,abs(s)); sz=.85; p=rotX(rotY(q,-u_yaw*.5),-u_tilt+.1); }",
 "l": " { float k=mod(cid,36.); float s=(u-.5)*1.9; float hh=fract(sin(k*12.9898)*43758.5); float R=3.2+hh*.5; float set_=step(.5,fract(k*.5)); float wv=.10*sin(s*9.+k*1.7+u_t*.25)+.05*sin(s*23.-k+u_t*.4); float an=s+.1*hh; vec3 q=vec3((R+wv)*sin(an),(R+wv)*cos(an)-3.4+set_*.1,(hh-.5)*1.4+.15*sin(s*5.+k)); p=rotX(rotY(q,-u_yaw*.5),-u_tilt+.1); col=(set_>.5?u_col[3]:u_col[6])*smoothstep(.95,.5,abs(s))*1.1; }",
 "la": 1.4,
 "rc": "vec3(0.)",
 "rad": 0
});
