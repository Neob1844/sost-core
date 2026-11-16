/* SOST Universe scene module: orbital-geometry (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('orbital-geometry', {
  "p": " if(kind<=.92){ if(kind<.72){ float n=floor(a_s.x*14.); float R=.72+.14*mod(n,5.); float a=a_s.y*6.2832+u_t*(.3+.04*n)*(mod(n,2.)<.5?1.:-1.); p=rotY(rotX(vec3(R*cos(a),(a_s.z-.5)*.025,R*sin(a)),n*.2244),n*2.39996); float hot=pow(max(0.,cos(a*3.-u_t*(1.+.1*n))),24.); col=mix(u_col[int(mod(n,7.))]*1.4,vec3(1.),hot*.22); alpha=.55+.55*hot; sz=.95+1.5*hot; } else { float t=a_s.y*6.2832*7.; float R=1.9,r=.68,d=.95; float x=(R-r)*cos(t)+d*cos((R-r)/r*t), z=(R-r)*sin(t)-d*sin((R-r)/r*t); p=rotY(vec3(x*.82,(a_s.z-.5)*.03,z*.82),u_t*.05); col=u_col[int(mod(floor(a_s.y*7.*7.)+floor(u_t*.4),7.))]*1.2; alpha=.3; sz=.85; } }",
  "l": " { if(j1<.55){ float n=mod(cid,14.); float R=.72+.14*mod(n,5.); float a=u*6.2832; p=rotY(rotX(vec3(R*cos(a),0.,R*sin(a)),n*.2244),n*2.39996); col=u_col[int(mod(n,7.))]*1.4; } else { float t=u*6.2832*(3.+mod(cid,4.)); float R=1.9,r=1.9/(3.+mod(cid,4.))*(1.+j2*.1),d=.6+j3*.5; float x=(R-r)*cos(t)+d*cos((R-r)/r*t), z=(R-r)*sin(t)-d*sin((R-r)/r*t); p=rotY(vec3(x*.82,0.,z*.82),u_t*.05+j2*6.28); col=u_col[int(mod(cid,7.))]*.9; } }",
  "rc": "mix(u_col[int(floor(fract(an/6.2832+u_t*.05)*7.))],u_col[int(mod(floor(fract(an/6.2832+u_t*.05)*7.)+1.,7.))],fract(fract(an/6.2832+u_t*.05)*7.))*1.3",
  "rad": 0.17,
  "la": 0.8
 });
