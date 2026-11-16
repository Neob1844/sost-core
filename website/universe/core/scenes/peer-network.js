/* SOST Universe scene module: peer-network (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('peer-network', {
  "p": " if(kind<=.92){ float na=floor(a_s.x*40.); float nb=mod(na+1.+mod(na*7.,9.),40.); vec3 A=fibp(na,40.), B=fibp(nb,40.); if(kind<.3){ p=A*1.35+(a_s.yzw-.5)*.05; float fire=pow(max(0.,sin(u_t*1.3+na*1.7)),12.); col=mix(u_col[int(mod(na,7.))],vec3(1.),fire*.5)*1.3; alpha=.6+.4*fire; sz=1.3+1.5*fire; } else { float s=a_s.y; p=normalize(mix(A,B,s)+1e-4)*(1.35+.25*sin(s*3.1416)); float pu=fract(u_t*.35+na*.13); float hit=exp(-pow((s-pu)*14.,2.)); col=mix(u_col[int(mod(na+nb,7.))]*.9,vec3(1.),hit*.6)*1.2; alpha=.18+.8*hit; sz=.8+1.4*hit; } p=rotY(p,u_t*.08); }",
  "l": " { float na=mod(cid,40.); float nb=mod(na+1.+mod(na*7.,9.)+floor(cid/40.)*3.,40.); p=rotY(normalize(mix(fibp(na,40.),fibp(nb,40.),u)+1e-4)*(1.35+.25*sin(u*3.1416)),u_t*.08); col=u_col[int(mod(na+nb,7.))]; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.45
 });
