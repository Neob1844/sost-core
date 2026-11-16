/* SOST Universe scene module: ringed-planet (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('ringed-planet', {
  "p": " if(kind<=.92){ if(kind<.45){ float th=a_s.y*6.2832+u_t*.06, ph=acos(2.*a_s.z-1.); vec3 n=vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); p=n*.95; float lit=clamp(dot(rotY(n,-u_t*.06),normalize(vec3(-.6,.5,.6))),0.,1.); col=u_col[int(mod(floor((cos(ph)+1.)*5.)+2.,7.))]*(.15+1.1*lit); alpha=.25+.7*lit; sz=.95; } else if(kind<.88){ float r=mix(1.35,2.5,pow(a_s.x,.8)); float gap=step(.06,abs(r-1.9))*step(.03,abs(r-2.2)); float a=a_s.y*6.2832+u_t*.25*pow(r,-1.5); p=rotX(vec3(r*cos(a),(a_s.z-.5)*.012,r*sin(a)),.32); col=u_col[int(clamp(floor((r-1.35)/1.15*7.),0.,6.))]*1.2; alpha=.55*gap; sz=.8; } else { float a=u_t*.3; float th=a_s.y*6.2832, ph=acos(2.*a_s.z-1.); p=vec3(3.*cos(a),.5*sin(a*.7),3.*sin(a))+.12*vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); col=vec3(.9,.9,1.); alpha=.6; sz=.8; } }",
  "l": " { float r=1.35+mod(cid,30.)/30.*1.15; float a=u*6.2832+u_t*.25*pow(r,-1.5); p=rotX(vec3(r*cos(a),0.,r*sin(a)),.32); col=u_col[int(clamp(floor((r-1.35)/1.15*7.),0.,6.))]*.8; }",
  "rc": "vec3(.35,.65,1.)",
  "rad": 0.93,
  "la": 0.4
 });
