/* SOST Universe scene module: torus-knot (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('torus-knot', {
  "p": " if(kind<=.92){ float cyc=floor(u_t*.07), fc=fract(u_t*.07); float P=2.+mod(cyc,3.), Qn=3.+mod(cyc+1.,4.); float m=smoothstep(0.,.15,fc)*(1.-smoothstep(.85,1.,fc)); float t=a_s.x*6.2832; float rr=1.1+.42*cos(Qn*t); vec3 c0=vec3(rr*cos(P*t),.5*sin(Qn*t),rr*sin(P*t)); vec3 tg=normalize(vec3(-P*rr*sin(P*t),.5*Qn*cos(Qn*t),P*rr*cos(P*t))); vec3 nb=normalize(cross(tg,vec3(0.,1.,0.))+1e-4); vec3 bb=cross(tg,nb); float an=a_s.z*6.2832; p=c0+(nb*cos(an)+bb*sin(an))*(.08+.1*a_s.y); p=mix(normalize(p+1e-4)*1.3,p,m); p=rotY(p,u_t*.15); float fl=fract(a_s.x*Qn-u_t*.3); col=mix(u_col[int(mod(floor(a_s.x*14.),7.))]*1.25,vec3(1.),pow(fl,12.)*.6); alpha=.6+.4*pow(fl,6.); sz=.95; }",
  "l": " { float cyc=floor(u_t*.07), fc=fract(u_t*.07); float P=2.+mod(cyc,3.), Qn=3.+mod(cyc+1.,4.); float m=smoothstep(0.,.15,fc)*(1.-smoothstep(.85,1.,fc)); float t=u*6.2832; float rr=1.1+.42*cos(Qn*t); vec3 c0=vec3(rr*cos(P*t),.5*sin(Qn*t),rr*sin(P*t))*(1.+(j1-.5)*.25); p=rotY(mix(normalize(c0+1e-4)*1.3,c0,m),u_t*.15+j2*.2); col=u_col[int(mod(cid,7.))]*1.3*m; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.5
 });
