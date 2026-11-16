/* SOST Universe scene module: binary-stars (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('binary-stars', {
  "p": " if(kind<=.92){ float ph=u_t*.35; vec3 A=vec3(cos(ph),0.,sin(ph))*1.6, B=-vec3(cos(ph),0.,sin(ph))*.85; if(kind<.3){ float th=a_s.y*6.2832, pp=acos(2.*a_s.z-1.); p=A+.65*vec3(sin(pp)*cos(th),cos(pp),sin(pp)*sin(th))*(1.+.12*pow(a_s.x,3.)); col=u_col[5]*1.3; alpha=.45; sz=1.; } else if(kind<.62){ float r=mix(.14,.85,pow(a_s.x,.7)); float a=a_s.y*6.2832+u_t*.33*pow(r,-1.5); p=B+vec3(r*cos(a),(a_s.z-.5)*.015,r*sin(a)); col=mix(vec3(1.),u_col[int(clamp(floor(r*12.),0.,6.))],smoothstep(.14,.6,r))*1.25; alpha=.6; sz=.8+.6*(1.-r); } else { float s=fract(a_s.x+u_t*.25); vec3 dir=normalize(B-A); vec3 sd=vec3(-dir.z,0.,dir.x); p=mix(A+dir*.6,B+sd*.75,s)+sd*sin(s*3.1416)*.5+(a_s.yzw-.5)*.05*(1.-s); col=mix(u_col[5],u_col[1],s)*1.3; alpha=.55*smoothstep(0.,.1,s)*(1.-smoothstep(.85,1.,s)); sz=.9; } }",
  "l": " { float ph=u_t*.35-u*1.5; float w=mod(cid,2.); vec3 c=w<.5?vec3(cos(ph),0.,sin(ph))*1.6:-vec3(cos(ph),0.,sin(ph))*.85; p=c+(vec3(j1,j2,j3)-.5)*.06; col=u_col[w<.5?5:1]*(1.-u)*1.2; }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.5
 });
