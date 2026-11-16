/* SOST Universe scene module: zeldovich (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("zeldovich", {
 "p": " if(kind<=.92){ float T=.62+.38*sin(u_t*.12); float D=T*1.25; vec2 qL=(a_s.xy-.5)*6.; float z=(a_s.z-.5)*.3; vec2 dsp=vec2(sin(qL.x*1.3)+.5*sin(qL.x*2.1+qL.y*1.4+1.),sin(qL.y*1.2+.7)+.5*sin(qL.y*2.3-qL.x*1.1))*.55; vec2 x=qL-D*dsp; float J=(1.-D*.55*(1.3*cos(qL.x*1.3)+1.05*cos(qL.x*2.1+qL.y*1.4+1.)))*(1.-D*.55*(1.2*cos(qL.y*1.2+.7)+1.15*cos(qL.y*2.3-qL.x*1.1))); float den=1./max(abs(J),.08); vec3 q=vec3(x,z); col=mix(u_col[0],mix(u_col[2],u_col[5],smoothstep(4.,12.,den)),smoothstep(1.,5.,den))*1.05; alpha=.03+.05*min(den,9.); sz=1.; p=rotX(rotY(q,-u_yaw*.4),-u_tilt+.1); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
