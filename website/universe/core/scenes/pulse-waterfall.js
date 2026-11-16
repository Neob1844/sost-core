/* SOST Universe scene module: pulse-waterfall (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("pulse-waterfall", {
 "p": " if(kind<=.92){ float NR=64.; float row=floor(a_s.x*NR); float sp=u_t*1.3; float age=fract((row+sp)/NR); float rk=floor((row+sp)/NR)*NR+row; float hh=fract(sin(rk*12.9898)*43758.5); float x=(a_s.y-.5); float pk=exp(-pow((x-.03*sin(rk*.7))/.07,2.))*(.55+.45*sin(rk*1.7+x*38.))+.35*exp(-pow((x+.05-.02*hh)/.03,2.))*hh+.04*sin(x*90.+rk); float A=max(pk,0.)*.55; vec3 q=vec3(x*4.4,mix(-1.3,1.25,age)+A,mix(1.4,-3.4,age)); p=rotX(rotY(q,-u_yaw*.4),-u_tilt+.18); col=mix(u_col[0],mix(u_col[3],u_col[5],smoothstep(.25,.55,A)),smoothstep(.02,.25,A))*1.15; alpha=(.10+.9*smoothstep(.0,.3,A))*smoothstep(0.,.08,age)*smoothstep(1.,.85,age)*.45; sz=.9; }",
 "l": " { float NR=64.; float row=mod(cid,NR); float sp=u_t*1.3; float age=fract((row+sp)/NR); float rk=floor((row+sp)/NR)*NR+row; float hh=fract(sin(rk*12.9898)*43758.5); float x=u-.5; float pk=exp(-pow((x-.03*sin(rk*.7))/.07,2.))*(.55+.45*sin(rk*1.7+x*38.))+.35*exp(-pow((x+.05-.02*hh)/.03,2.))*hh+.04*sin(x*90.+rk); float A=max(pk,0.)*.55; p=rotX(rotY(vec3(x*4.4,mix(-1.3,1.25,age)+A,mix(1.4,-3.4,age)),-u_yaw*.4),-u_tilt+.18); col=mix(u_col[2],u_col[5],smoothstep(.1,.5,A))*1.2*smoothstep(0.,.08,age)*smoothstep(1.,.85,age); }",
 "la": 1.6,
 "rc": "vec3(0.)",
 "rad": 0
});
