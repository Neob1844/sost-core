/* SOST Universe scene module: galaxy-cluster (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("galaxy-cluster", {
 "p": " if(kind<=.92){ vec3 q; if(kind<.45){ float k=floor(a_s.x*220.); vec3 d=normalize(fibp(k,220.)+(vec3(fract(sin(k*12.9898)*43758.5),fract(sin(k*78.233)*43758.5),fract(sin(k*39.425)*43758.5))-.5)); float r=.15+1.9*pow(fract(k*.618),1.6); vec3 c=d*r; c=rotY(c,u_t*.25/(r+.4)); float ty=fract(k*.377); vec3 o=(vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)))*.035*pow(fract(a_s.w*7.),.5); if(ty<.5) o.y*=.25; q=c+o; col=ty<.5?mix(u_col[2],u_col[3],fract(k*.2)):mix(u_col[5],u_col[6],fract(k*.3)); col*=1.15; alpha=.25; sz=.9; } else if(kind<.88){ float r=.9*pow(-log(1.-a_s.x*.995),.8); q=min(r,2.8)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(u_col[1],u_col[0],min(r/2.5,1.))*.9; alpha=.035*exp(-r*.4); sz=1.4; } else { float an=a_s.y*6.2832; float rr=1.55+(a_s.z-.5)*.06; float arcA=floor(a_s.x*4.)*1.57+.4; float sp=.32; float a2=arcA+(fract(a_s.x*4.)-.5)*sp*2.; q=rotX(rotY(vec3(rr*cos(a2),rr*sin(a2),0.),-u_yaw),-u_tilt); col=u_col[3]*1.2; alpha=.22*sin(3.1416*fract(a_s.x*4.)); sz=.9; } p=q; }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
