/* SOST Universe scene module: barred-spiral (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("barred-spiral", {
 "p": " if(kind<=.92){ float pat=u_t*.12; vec3 q; if(kind<.32){ float a=1.25*pow(a_s.x,.6); float ph=a_s.y*6.2832+u_t*(.9/(a+.25)); q=vec3(a*cos(ph),(a_s.z-.5)*.06,a*.32*sin(ph)); col=mix(u_col[5],u_col[6],a/1.25)*1.05; alpha=.16; sz=.9; } else if(kind<.46){ float ph=a_s.y*6.2832+u_t*.2; float r=1.32+(a_s.z-.5)*.10; q=vec3(r*cos(ph),(a_s.x-.5)*.04,r*.78*sin(ph)); col=u_col[3]*1.05; alpha=.18; sz=.9; } else { float m=step(.5,fract(a_s.y*2.)); float s=pow(a_s.x,.9); float r=1.32+s*1.7; float g=(a_s.z+fract(a_s.z*7.31)-1.)*.32; float th=m*3.1416+s*3.2+g; q=vec3(r*cos(th),(fract(a_s.y*91.7)-.5)*.05,r*sin(th)*.92); col=mix(u_col[2],u_col[0],s)*1.1; col=mix(col,u_col[1]*1.2,step(.2,g)*step(fract(a_s.y*17.),.3)); alpha=.24*(1.-s*.4); sz=.9; } p=rotY(rotX(q,.55),pat); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
