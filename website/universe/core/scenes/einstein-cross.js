/* SOST Universe scene module: einstein-cross (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("einstein-cross", {
 "p": " if(kind<=.92){ vec3 q; float rot=.5+u_ptr.x*u_ptrA*.8+u_t*.02; float sh=.15+.1*sin(u_t*.11)+u_ptr.y*u_ptrA*.2; if(kind<.40){ float r=.05*pow(-log(1.-a_s.x*.99),2.); r=min(r,1.6); q=r*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832))*vec3(1.,.75,.5); col=mix(u_col[5],u_col[6],min(r,1.)); alpha=.09; sz=1.3; } else if(kind<.80){ float im=floor(a_s.x*4.); float an=rot+im*1.5708; float rr=1.05*(mod(im,2.)<.5?1.+sh:1.-sh); vec3 c0=vec3(rr*cos(an),rr*sin(an),0.); float bl=.55+.45*sin(u_t*.7+im*1.9); q=c0+.05*pow(a_s.w,.4)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(u_col[3],u_col[2],fract(im*.37))*1.2; alpha=.35+.45*bl; sz=1.3; } else { float an=a_s.x*6.2832; float rr=1.05*(1.+sh*cos(2.*(an-rot)))+(a_s.y-.5)*.04; q=vec3(rr*cos(an),rr*sin(an),0.); col=u_col[0]*1.1; alpha=.10+.22*pow(abs(cos(2.*(an-rot))),8.); sz=1.; } p=rotX(rotY(q*1.4,-u_yaw),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
