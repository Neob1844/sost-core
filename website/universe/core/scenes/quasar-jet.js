/* SOST Universe scene module: quasar-jet (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("quasar-jet", {
 "p": " if(kind<=.92){ vec3 q; if(kind<.38){ float r=mix(.18,1.6,pow(a_s.x,1.3)); float th=a_s.y*6.2832+u_t*.9*pow(r,-1.5); q=vec3(r*cos(th),(a_s.z-.5)*.03*r,r*sin(th)); float tr=(r-.18)/1.42; col=mix(u_col[5],mix(u_col[6],u_col[0],tr),smoothstep(0.,.5,tr))*1.15; float dop=.6+.4*sin(th); alpha=(.20+.40*(1.-tr))*dop; sz=1.; } else if(kind<.80){ float sd=a_s.x<.5?1.:-1.; float s=fract(a_s.y*1.+u_t*.08*(sd>0.?1.:.6)); float L=s*3.4; float w=.03+.07*s; float kn=pow(.5+.5*sin(L*7.-u_t*4.*(sd>0.?1.:.7)),6.); float an=a_s.z*6.2832; q=vec3(w*cos(an)*sqrt(fract(a_s.w*13.)),sd*(L+.1),w*sin(an)*sqrt(fract(a_s.w*13.))); col=mix(u_col[3],u_col[2],s)*(1.+kn*.5); col=mix(col,u_col[0],step(sd,0.)*.5); alpha=(sd>0.?.6:.25)*(.35+.65*kn)*(1.-s*.6); sz=1.+kn*.5; } else { float r=2.+2.2*a_s.x; float th=a_s.y*6.2832+u_t*.02; q=vec3(r*cos(th),(a_s.z-.5)*.25,r*sin(th)*.9); q.xz+=flow(q.xz*.4,u_t*.05)*.25; col=mix(u_col[0],u_col[6],fract(a_s.z*5.))*.9; alpha=.10; sz=1.1; } p=rotY(rotX(q,.22),.4); }",
 "l": " { float sd=mod(cid,2.)<.5?1.:-1.; float L=u*3.4; float an=L*5.+j1*6.2832+u_t*1.5; float w=.05+.09*u; p=rotY(rotX(vec3(w*cos(an),sd*(L+.1),w*sin(an)),.22),.4); col=mix(u_col[1],u_col[2],u)*(1.-u)*1.2; }",
 "la": 0.5,
 "rc": "vec3(0.)",
 "rad": 0
});
