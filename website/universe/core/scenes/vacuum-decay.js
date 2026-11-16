/* SOST Universe scene module: vacuum-decay (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("vacuum-decay", {
 "p": " if(kind<=.92){ float T=fract(u_t/12.+.3); vec2 g=floor(a_s.xy*vec2(96.,60.)); vec2 xy=(g/vec2(96.,60.)-.5)*vec2(8.,5.)+(fract(a_s.xy*vec2(96.,60.))-.5)*.02; vec2 C=vec2(-.4,.1); float R=max(T-.08,0.)*5.2; float d=length(xy-C); float wall=exp(-pow((d-R)*6.,2.)); float inside=step(d,R); float osc=sin(xy.x*5.+u_t*2.3)*sin(xy.y*5.-u_t*1.9); vec3 q=vec3(xy,(1.-inside)*.18*osc+wall*.25); col=inside>.5?mix(u_col[3],u_col[2],.5+.5*sin(d*6.-u_t)):mix(u_col[0],u_col[1],.5+.5*osc); col=mix(col,u_col[5],min(wall*1.2,1.)); col*=1.1; alpha=(inside>.5?.10:.16+.10*abs(osc))+.40*wall; sz=1.+.6*wall; alpha*=smoothstep(1.,.93,T)*smoothstep(0.,.04,T); p=rotX(rotY(q,-u_yaw*.5),-u_tilt+.35); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
