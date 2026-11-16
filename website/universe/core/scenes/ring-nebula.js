/* SOST Universe scene module: ring-nebula (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("ring-nebula", {
 "p": " if(kind<=.92){ vec3 q; float an=a_s.y*6.2832; if(kind<.80){ float g=(a_s.x+fract(a_s.x*7.3)+fract(a_s.x*3.1)-1.5)*.32; float r=1.4+g*(1.+.15*sin(an*7.))*(1.+.03*sin(u_t*.3)); float fil=.6+.4*pow(abs(sin(an*23.+sin(an*5.)*2.)),3.); float t=clamp((r-.9)/1.1,0.,1.); col=t<.45?mix(u_col[2],u_col[3],t/.45):t<.7?mix(u_col[4],u_col[5],(t-.45)/.25):mix(u_col[6],u_col[1],(t-.7)/.3); q=vec3(r*cos(an),r*sin(an)*.86,(a_s.z-.5)*.5); col*=1.1; alpha=(.08+.12*fil)*(1.-abs(g)*1.5); sz=1.2; } else if(kind<.90){ float r=2.1+.7*a_s.x; q=vec3(r*cos(an),r*sin(an)*.86,(a_s.z-.5)*.6); col=u_col[0]*.9; alpha=.03*(.6+.4*sin(an*15.)); sz=1.2; } else { q=.05*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[3]*1.2; alpha=.5; sz=1.; } p=rotX(rotY(q,-u_yaw*.6),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
