/* SOST Universe scene module: twisted-magnetosphere (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("twisted-magnetosphere", {
 "p": " if(kind<=.92){ float tw=1.4+1.1*sin(u_t*.2)+u_ptr.x*u_ptrA*1.2; vec3 q; if(kind<.30){ q=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832))*.42; col=mix(u_col[0],u_col[2],.5)*.9; alpha=.12; sz=.9; } else { float k=floor(a_s.x*24.); float L=1.3+.5*fract(k*.618); float az=k/24.*1.4-.7; float s=fract(a_s.y+u_t*.12*(mod(k,2.)<.5?1.:-1.)); float th=mix(.35,2.79,s); float rr=L*sin(th)*sin(th); float phi=az+tw*cos(th); q=vec3(rr*sin(th)*cos(phi),rr*cos(th),rr*sin(th)*sin(phi))+(vec3(fract(a_s.z*7.),fract(a_s.z*13.),fract(a_s.z*3.))-.5)*.02; float hot=pow(.5+.5*sin(s*20.-u_t*3.),6.); col=mix(u_col[int(mod(k,3.))+1],u_col[5],hot*.6)*1.15; alpha=.20+.3*hot; sz=.9; } p=rotY(rotX(q,1.3),.4+u_t*.05); }",
 "l": " { float tw=1.4+1.1*sin(u_t*.2)+u_ptr.x*u_ptrA*1.2; float k=mod(cid,24.); float L=1.3+.5*fract(k*.618); float az=k/24.*1.4-.7+(j1-.5)*.05; float th=mix(.35,2.79,u); float rr=L*sin(th)*sin(th); float phi=az+tw*cos(th); p=rotY(rotX(vec3(rr*sin(th)*cos(phi),rr*cos(th),rr*sin(th)*sin(phi)),1.3),.4+u_t*.05); col=u_col[int(mod(k,3.))+1]*.9; }",
 "la": 1.2,
 "rc": "vec3(0.)",
 "rad": 0
});
