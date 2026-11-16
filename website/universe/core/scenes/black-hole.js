/* SOST Universe scene module: black-hole (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('black-hole', {
  "p": " if(kind<=.92){ if(kind<.62){ float r=mix(.6,3.,pow(a_s.x,1.6)); float th=a_s.y*6.2832+u_t*.95*pow(r,-1.5); p=rotX(vec3(r*cos(th),(a_s.z-.5)*.02*r,r*sin(th)),-u_tilt+.09); float tr=clamp((r-.6)/2.4,0.,1.); col=mix(vec3(1.,.74,.42),u_col[int(band)],smoothstep(.04,.45,tr)); float dop=.5+.5*cos(th); alpha=(.3+.7*(1.-tr))*(.2+1.4*dop*dop); sz=.7+.9*(1.-tr); } else { float r=mix(.47,1.12,pow(a_s.x,2.)); float th=a_s.y*6.2832+u_t*.3; float up=step(0.,sin(th)); vec3 sp=vec3(r*cos(th)*1.1,r*sin(th)*mix(.55,1.05,up),0.); p=rotX(rotY(sp,-u_yaw),-u_tilt); col=mix(vec3(1.,.8,.55),u_col[int(mod(floor(th/6.2832*7.+7.),7.))],smoothstep(.5,1.,r)); alpha=(.25+.6*(1.-smoothstep(.47,1.1,r)))*mix(.55,1.,up); sz=.7; } }",
  "l": " { if(j3<.45){ float rr=.47+j1*.10; float a=u*6.2832+u_t*(.25+j2*.3); p=rotX(rotY(vec3(rr*cos(a)*1.06,rr*sin(a),0.),-u_yaw),-u_tilt); } else { float rr=mix(3.,.62,u); float a=u*7.+cid*.53+u_t*.45*pow(rr,-1.5); p=rotX(vec3(rr*cos(a),(j1-.5)*.02,rr*sin(a)),-u_tilt+.09); } }",
  "rc": "vec3(1.,.86,.62)",
  "rad": 0.47,
  "la": 0.7
 });
