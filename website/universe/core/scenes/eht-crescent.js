/* SOST Universe scene module: eht-crescent (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("eht-crescent", {
 "p": " if(kind<=.92){ float an=a_s.y*6.2832; float th0=u_t*.06+.6; float g=(a_s.x+fract(a_s.x*13.1)+fract(a_s.x*7.7)-1.5)*.7; float sub=step(kind,.14); float r; if(sub>.5){ r=1.0+(fract(a_s.z*3.)<.5?-.02:.016)+g*.008; } else { r=1.07+g*.24; } float br=pow(.5+.5*cos(an-th0),2.2); float turb=.72+.28*sin(an*7.+u_t*1.3+a_s.z*6.)*sin(an*3.-u_t*.7); vec3 q=vec3(r*cos(an),r*sin(an)*.97,(a_s.z-.5)*.05); p=rotX(rotY(q,-u_yaw),-u_tilt); float e=br*turb; col=mix(u_col[0],mix(u_col[6],u_col[5],smoothstep(.55,1.,e)),smoothstep(.08,.6,e)); alpha=sub>.5?.05+.25*e:(.035+.12*e); sz=sub>.5?1.:3.4; }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "rad": 0,
 "la": 0,
 "rc": "vec3(0.)"
});
