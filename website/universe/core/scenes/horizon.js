/* SOST Universe scene module: horizon (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('horizon', {
  "p": " if(kind<=.92){  if(kind<.66){ float r=mix(.64,2.8,pow(a_s.x,1.7)); float th=a_s.y*6.2832+u_t*1.15*pow(r,-1.5); p=vec3(r*cos(th),(a_s.z-.5)*.03*r,r*sin(th));   float tr=clamp((r-.64)/2.16,0.,1.); col=mix(vec3(1.,.74,.42),u_col[int(band)],smoothstep(.02,.4,tr)); float dop=.5+.5*sin(th); alpha=(.38+.62*(1.-tr))*(.45+.85*dop); sz=.75+.7*(1.-tr);  } else { float r=mix(.60,1.02,pow(a_s.x,2.2)); float th=a_s.y*6.2832+u_t*.22; vec3 sp=vec3(r*cos(th)*1.04,r*sin(th),0.); p=rotX(rotY(sp,-u_yaw),-u_tilt);   col=mix(vec3(1.,.8,.55),u_col[int(mod(floor(th/6.2832*7.+7.),7.))],smoothstep(.62,.9,r)); alpha=.30+.5*(1.-smoothstep(.6,1.,r)); sz=.75; } }",
  "l": " { float rr=mix(2.9,.66,u); float a=u*9.+cid*.61+u_t*.5*pow(rr,-1.5); p=vec3(rr*cos(a),(j1-.5)*.04,rr*sin(a)); }",
  "rc": "mix(u_col[int(floor(fract(an/6.2832+u_t*.02)*7.))],u_col[int(mod(floor(fract(an/6.2832+u_t*.02)*7.)+1.,7.))],fract(fract(an/6.2832+u_t*.02)*7.))*1.2",
  "rad": 0.62,
  "la": 1
 });
