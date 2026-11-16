/* SOST Universe scene module: ledger-rain (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('ledger-rain', {
  "p": " if(kind<=.92){ vec2 cell=floor(a_s.xy*vec2(34.,7.)); float rnd=fract(sin(cell.x*12.9898+cell.y*78.233)*43758.55); float x=(cell.x/33.-.5)*7.2; float z=(cell.y/6.-.5)*5.-1.; float s=floor(a_s.z*42.)/42.; float hp=fract(u_t*(.08+.12*rnd)+rnd*7.); float tr=fract(hp-s); float hd=step(tr,.03); p=rotX(vec3(x+(a_s.w-.46)*.02,1.9-s*4.2,z),-u_tilt+.12); col=mix(u_col[int(mod(cell.x*.5+cell.y,7.))]*1.2,vec3(1.),hd*.7); alpha=exp(-tr*3.)*1.3*step(tr,.6); sz=1.6+1.2*hd; }",
  "l": " { float c=mod(cid,34.); float x=(c/33.-.5)*7.2; float z=(mod(floor(cid/34.)*3.+c,7.)/6.-.5)*5.-1.; p=rotX(vec3(x,1.9-u*4.2,z),-u_tilt+.12); col=u_col[int(mod(c,7.))]*.35; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.4
 });
