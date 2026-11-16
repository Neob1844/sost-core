/* SOST Universe scene module: ledger-helix (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('ledger-helix', {
  "p": " if(kind<=.92){ float y=(a_s.x*2.-1.)*2.6; vec3 q; if(kind<.62){ float a=y*2.4+u_t*.9+step(.5,fract(a_s.y*2.))*3.1416; q=vec3(.55*cos(a),y,.55*sin(a))+(a_s.zyx-.5)*.05; col=u_col[int(mod(floor((y+2.6)*1.6+u_t*.5),7.))]*1.3; alpha=.5; sz=1.05; } else { float rung=floor((y+2.6)*3.)/3.-2.6; float a=rung*2.4+u_t*.9; float tt=a_s.z*2.-1.; q=vec3(.55*tt*cos(a),rung,.55*tt*sin(a)); float lit=pow(max(0.,sin(rung*1.3-u_t*2.)),6.); col=mix(u_col[int(mod(rung*3.+8.,7.))],vec3(1.),lit*.6)*1.2; alpha=.35+.6*lit; sz=.9+lit; } float c=cos(.6),s=sin(.6); p=rotX(vec3(q.x*c-q.y*s,q.x*s+q.y*c,q.z),-u_tilt+.1); }",
  "l": " { float y=(u*2.-1.)*2.6; float a=y*2.4+u_t*.9+mod(cid,2.)*3.1416; float rr=.55+(j1-.5)*.12; vec3 q=vec3(rr*cos(a),y,rr*sin(a)); float c=cos(.6),s=sin(.6); p=rotX(vec3(q.x*c-q.y*s,q.x*s+q.y*c,q.z),-u_tilt+.1); col=u_col[int(mod(cid,7.))]*1.2; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.5
 });
