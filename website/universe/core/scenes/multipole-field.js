/* SOST Universe scene module: multipole-field (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("multipole-field", {
 "p": " if(kind<=.92){ vec3 q; float mx=.5+.5*sin(u_t*.15); if(kind<.35){ vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float sp=0.; for(int i=0;i<6;i++){ vec3 c=fibp(float(i),6.); sp+=exp(-pow(length(d-c)*6.,2.)); } q=d*.6; col=mix(u_col[0]*.6,u_col[5],min(sp,1.))*1.1; alpha=.10+.4*min(sp,1.); sz=.9; } else { float k=floor(a_s.x*15.); vec3 A=fibp(mod(k,6.),6.), B=fibp(mod(k*5.+2.,6.),6.); if(length(A-B)<.1) B=normalize(-A+vec3(.4,.3,-.2)); if(length(A+B)<.2) B=normalize(B+vec3(.5,-.3,.4)); float s=fract(a_s.y+u_t*.15*(mod(k,2.)<.5?1.:-1.)); float h=(.4+.7*length(A-B))*(1.+.2*mx*fract(k*.618)); vec3 m=normalize(mix(A,B,s)+1e-4); q=m*(.6+h*sin(s*3.1416)); col=u_col[int(mod(k,7.))]*1.15; float hot=pow(.5+.5*sin(s*18.-u_t*3.),6.); alpha=.18+.3*hot; sz=.9; } p=rotY(q,u_t*.12); }",
 "l": " { float k=mod(cid,15.); vec3 A=fibp(mod(k,6.),6.), B=fibp(mod(k*5.+2.,6.),6.); if(length(A-B)<.1) B=normalize(-A+vec3(.4,.3,-.2)); if(length(A+B)<.2) B=normalize(B+vec3(.5,-.3,.4)); float mx=.5+.5*sin(u_t*.15); float h=(.4+.7*length(A-B))*(1.+.2*mx*fract(k*.618))*(1.+(j1-.5)*.12); vec3 m=normalize(mix(A,B,u)+1e-4); p=rotY(m*(.6+h*sin(u*3.1416)),u_t*.12); col=u_col[int(mod(k,7.))]*.8; }",
 "la": 1.2,
 "rc": "vec3(0.)",
 "rad": 0
});
