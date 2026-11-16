/* SOST Universe scene module: supernova (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('supernova', {
  "p": " if(kind<=.92){ float T=fract(u_t*.1); float th=a_s.y*6.2832, ph=acos(2.*a_s.z-1.); vec3 dir=vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); float spd=a_s.x<.7?.95+.1*a_s.x:.3+a_s.x*.6; float burst=smoothstep(.18,.22,T); float r=mix(.25+.08*sin(u_t*9.+a_s.x*20.),(T-.2)*5.*spd+.25,burst); float lobes=1.+.35*pow(abs(dir.y),3.); p=dir*r*lobes; float heat=1.-clamp((T-.2)*2.,0.,1.); col=mix(u_col[int(mod(floor(a_s.x*7.)+floor(dir.y*3.+3.),7.))]*1.3,vec3(1.,.95,.85),heat*burst*.8+(1.-burst)*.6); alpha=mix(.9,.75*(1.-smoothstep(.75,1.,T)),burst); sz=mix(1.,1.2+heat,burst); }",
  "l": " { float T=fract(u_t*.1); float th=j1*6.2832, ph=acos(2.*j2-1.); vec3 dir=vec3(sin(ph)*cos(th),cos(ph),sin(ph)*sin(th)); float r=max(0.,T-.2)*5.*(.5+j3*.9)*u+.25; p=dir*r; col=u_col[int(band)]*1.3*smoothstep(.2,.3,T)*(1.-smoothstep(.75,1.,T)); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.9
 });
