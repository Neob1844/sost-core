/* SOST Universe scene module: holographic-cloud (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('holographic-cloud', {
  "p": " if(kind<=.92){ float th=a_s.y*6.2832, ph=acos(2.*a_s.z-1.); float r=1.45*(kind<.62?.9+.1*a_s.x:pow(a_s.x,.5))*(1.+.22*sin(3.*th+u_t*.3)*sin(2.*ph)); p=vec3(r*sin(ph)*cos(th),r*cos(ph)*.9+.15,r*sin(ph)*sin(th)); p.xz+=flow(p.xz*.6,u_t*.3)*.07; float sl=floor((p.y+2.)*3.2)/3.2-2.; p.y=mix(p.y,sl,.97); p=rotY(p,u_t*.15); float scan=fract(u_t*.22)*3.4-1.55; float sb=exp(-pow((p.y-scan)*10.,2.)); float si=clamp(floor((sl+1.55)/3.3*7.),0.,6.); col=u_col[int(si)]*1.25; col=mix(col,vec3(1.),sb*.3); alpha=(.38+.8*sb)*(.85+.15*sin(u_t*2.+a_s.x*40.)); sz=1.55+.8*sb; }",
  "l": " { if(j1<.62){ float rr=.35+j2*1.9; float a=u*6.2832+u_t*(.1+j3*.2); p=vec3(rr*cos(a),-1.78+j3*.04,rr*sin(a)); col=u_col[int(mod(floor(j2*7.),7.))]*1.4; } else { float a=j2*6.2832+u_t*.15; float rb=j3*1.5; p=vec3(rb*cos(a)*(1.-u*.3),mix(-1.78,1.2,u),rb*sin(a)*(1.-u*.3)); col=u_col[int(mod(cid,7.))]*1.2; } }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.8
 });
