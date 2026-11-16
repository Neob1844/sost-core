/* SOST Universe scene module: particle-convergence (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('particle-convergence', {
  "p": " if(kind<=.92){ if(fract(a_s.y*17.)<.1){ float e=fract(u_t*.22+a_s.x*.03); float rr=.15+e*2.7; float a=a_s.x*6.2832+u_t*.2; p=vec3(rr*cos(a),(a_s.z-.5)*.04,rr*sin(a)); col=u_col[int(mod(floor(a_s.x*7.)+floor(u_t*.22),7.))]*1.3; alpha=(1.-e)*(1.-e)*.95; sz=1.25; } else { float f=fract(u_t*.075+a_s.x); float r=3.1*pow(1.-f,1.25)+.03; float th=band*.8976+f*7.5+(a_s.y-.5)*.5+u_t*.1; p=vec3(r*cos(th),(a_s.z-.5)*.45*(1.-f)+.38*sin(band*1.7+f*6.)*(1.-f),r*sin(th)); col=u_col[int(band)]*1.3; col=mix(col,vec3(1.,.96,.9),smoothstep(.95,1.,f)*.75); alpha=smoothstep(0.,.08,f)*(.5+.5*f); sz=1.05+1.4*f*f; } }",
  "l": " { float r=3.1*pow(1.-u,1.25)+.03; float th=band*.8976+u*7.5+(j1-.5)*.5+u_t*.1; p=vec3(r*cos(th),(j2-.5)*.45*(1.-u)+.38*sin(band*1.7+u*6.)*(1.-u),r*sin(th)); col=u_col[int(band)]*1.45; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 1.1
 });
