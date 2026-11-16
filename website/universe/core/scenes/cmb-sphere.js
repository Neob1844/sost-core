/* SOST Universe scene module: cmb-sphere (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("cmb-sphere", {
 "p": " if(kind<=.92){ vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float n=0.; float a=1.; vec3 dd=d; for(int i=0;i<5;i++){ n+=a*sin(dd.x*3.1+float(i))*sin(dd.y*3.7+float(i)*1.7)*sin(dd.z*3.3+float(i)*2.3); dd=dd.yzx*2.03+.3; a*=.55; } float t=clamp(.5+n*.55,0.,1.); vec3 q=d*1.75; col=t<.5?mix(u_col[2],u_col[1],t*2.):mix(u_col[1],u_col[3],(t-.5)*2.); col=mix(col,u_col[5],smoothstep(.85,1.,t)); col*=1.1; float front=dot(normalize(rotY(rotX(q,u_tilt),u_yaw)),vec3(0.,0.,1.)); alpha=(.30+.20*abs(n))*(.25+.75*smoothstep(-.2,.6,front)); sz=1.1; p=rotY(q,u_t*.06); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
