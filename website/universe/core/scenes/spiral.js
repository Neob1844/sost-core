/* SOST Universe scene module: spiral (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('spiral', {
  "p": " if(kind<=.92){  if(kind<.78){ float arm=floor(a_s.z*3.); float t0=a_s.x*6.4; float r=.22*exp(.385*t0); float th=t0+arm*2.0944; th+=u_t*.11+.18*sin(u_t*.21+r*1.3)/(1.+r); float w=(a_s.y-.5)*(.2+.2*r);   p=vec3(r*cos(th)-w*sin(th),(fract(a_s.y*13.7)-.5)*.06,r*sin(th)+w*cos(th)); col=u_col[int(mod(floor(a_s.x*7.)+arm*2.,7.))]; col=mix(col,vec3(1.),smoothstep(.6,.2,r)*.7); alpha=.55+.4*smoothstep(1.5,.3,r); sz=.85;  } else { float n=floor(a_s.x*2400.); float r=.92*sqrt(n/2400.); float th=n*2.39996+u_t*.12; p=vec3(r*cos(th),0.,r*sin(th)); col=u_col[int(mod(n,7.))]; alpha=.5; sz=.7; } }",
  "l": " { float a=u*6.2832; float kk=2.+mod(cid,2.); float Rr=1.2+j1*.8; float rr=Rr*cos(kk*a+u_t*.15); p=rotY(rotX(vec3(rr*cos(a),0.,rr*sin(a)),j2*3.1416),j3*6.2832+u_t*.05); }",
  "rc": "vec3(1.,.78,.35)",
  "rad": 0.36,
  "la": 0.45
 });
