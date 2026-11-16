/* SOST Universe scene module: white-hole (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("white-hole", {
 "p": " if(kind<=.92){ vec3 q; float r0=.55; if(kind<.80){ float f=fract(a_s.x+u_t*.12); float r=r0+f*f*3.6; float th=a_s.y*6.2832-u_t*.4*pow(r,-1.)+f*2.; q=vec3(r*cos(th),(a_s.z-.5)*.08*r,r*sin(th)); float t=f; col=mix(u_col[3],mix(u_col[2],u_col[1],t),t)*1.15; alpha=(.30*(1.-t)+.04)*smoothstep(0.,.03,f); sz=.9+.4*(1.-t); } else { vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); q=d*r0*(1.+.02*sin(u_t*3.+d.x*10.)); col=u_col[3]*1.2; alpha=.12; sz=.9; } p=rotX(q,-.1); }",
 "l": " { float k=mod(cid,24.); float f=u; float r=.55+f*f*3.6; float th=k/24.*6.2832-u_t*.4/r+f*2.+fract(u_t*.12)*0.; p=rotX(vec3(r*cos(th),0.,r*sin(th)),-.1); col=mix(u_col[3],u_col[1],f)*(1.-f)*.9; }",
 "la": 0.7,
 "rc": "vec3(0.)",
 "rad": 0
});
