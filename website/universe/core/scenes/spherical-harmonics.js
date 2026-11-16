/* SOST Universe scene module: spherical-harmonics (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('spherical-harmonics', {
  "p": " if(kind<=.92){ float th=a_s.y*6.2832, ph=acos(2.*a_s.z-1.); vec3 n=vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); float T=u_t*.25; float Y=.5*sin(3.*th+T)*pow(sin(ph),3.)*sin(T*.37)+.4*cos(2.*ph-T*1.3)*cos(4.*th)*cos(T*.29)+.25*sin(5.*ph+T*.7); p=rotY(n*(1.05+.45*Y+(a_s.x-.5)*.02),u_t*.1); col=u_col[int(clamp(floor((Y+1.)*3.5),0.,6.))]*1.3; alpha=.55+.4*abs(Y); sz=1.; }",
  "l": " { float ph=(mod(cid,18.)+.5)/18.*3.1416; float th=u*6.2832; vec3 n=vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); float T=u_t*.25; float Y=.5*sin(3.*th+T)*pow(sin(ph),3.)*sin(T*.37)+.4*cos(2.*ph-T*1.3)*cos(4.*th)*cos(T*.29)+.25*sin(5.*ph+T*.7); p=rotY(n*(1.05+.45*Y),u_t*.1); col=u_col[int(clamp(floor((Y+1.)*3.5),0.,6.))]*1.1; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.45
 });
