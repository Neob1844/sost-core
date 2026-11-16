/* SOST Universe scene module: hourglass (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("hourglass", {
 "p": " if(kind<=.92){ vec3 q; if(kind<.80){ float sd=a_s.x<.5?1.:-1.; float h=a_s.y; float y=sd*h*2.5; float R=.12+1.05*sin(3.1416*pow(h,.8))*(1.-.15*h); float an=a_s.z*6.2832; float rings=pow(.5+.5*sin(h*28.-u_t*.6),6.); q=vec3(R*cos(an),y,R*sin(an))*(1.+.03*sin(an*5.+h*9.)); col=(sd>0.?mix(u_col[1],u_col[3],h):mix(u_col[3],u_col[2],h))*1.1; alpha=(.12+.30*rings)*(1.-h*.4); sz=1.; } else { float an=a_s.y*6.2832; float r=.32+(a_s.z-.5)*.08; q=vec3(r*cos(an),(a_s.x-.5)*.05,r*sin(an)); col=u_col[5]*1.1; alpha=.25; sz=1.; } q*=.72; p=rotX(rotY(rotY(vec3(q.x*cos(.45)-q.y*sin(.45),q.x*sin(.45)+q.y*cos(.45),q.z),u_t*.06),-u_yaw),-u_tilt); }",
 "l": " { float sd=mod(cid,2.)<.5?1.:-1.; float h=(floor(cid/2.)+.5)/40.; float R=.12+1.05*sin(3.1416*pow(h,.8))*(1.-.15*h); float an=u*6.2832; vec3 q=vec3(R*cos(an),sd*h*2.5,R*sin(an)); q*=.72; p=rotX(rotY(rotY(vec3(q.x*cos(.45)-q.y*sin(.45),q.x*sin(.45)+q.y*cos(.45),q.z),u_t*.06),-u_yaw),-u_tilt); col=(sd>0.?u_col[1]:u_col[2])*.45; }",
 "la": 0.9,
 "rc": "vec3(0.)",
 "rad": 0
});
