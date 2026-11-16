/* SOST Universe scene module: pulsar (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('pulsar', {
  "p": " if(kind<=.92){ float spin=u_t*1.4; vec3 ax=rotY(rotX(vec3(0.,1.,0.),.5),spin); if(kind<.55){ float s=a_s.x; float sd=a_s.y<.5?1.:-1.; vec3 t1=normalize(cross(ax,vec3(0.,0.,1.))); vec3 t2=cross(ax,t1); float an=a_s.z*6.2832; float rr=(.03+.28*s)*sqrt(fract(a_s.w*13.)); p=ax*sd*(s*3.2+.2)+(t1*cos(an)+t2*sin(an))*rr; float fl=fract(s*4.-u_t*2.); col=mix(u_col[sd>0.?3:1],vec3(1.),(1.-s)*.3)*1.25; alpha=(1.-s)*(.45+.55*pow(fl,3.)); sz=.8+1.2*(1.-s); } else if(kind<.8){ float th=a_s.y*6.2832+u_t*.3, ph=acos(2.*a_s.z-1.); p=.22*vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); col=vec3(.62,.78,1.); alpha=.42; sz=1.1; } else { float L=.5+a_s.z*1.3; float th=mix(.2,2.94,a_s.x); float az=a_s.y*6.2832; float r=L*sin(th)*sin(th); p=rotY(rotX(vec3(r*sin(th)*cos(az),r*cos(th),r*sin(th)*sin(az)),.5),spin); col=u_col[int(mod(floor(a_s.z*6.)+2.,7.))]*.9; alpha=.25; sz=.7; } }",
  "l": " { float spin=u_t*1.4; vec3 ax=rotY(rotX(vec3(0.,1.,0.),.5),spin); vec3 t1=normalize(cross(ax,vec3(0.,0.,1.))); vec3 t2=cross(ax,t1); float sd=mod(cid,2.)<.5?1.:-1.; float an=j1*6.2832; p=ax*sd*(u*3.2+.2)+(t1*cos(an)+t2*sin(an))*(.03+.28*u); col=u_col[sd>0.?3:1]*1.2*(1.-u); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.6
 });
