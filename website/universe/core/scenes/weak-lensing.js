/* SOST Universe scene module: weak-lensing (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("weak-lensing", {
 "p": " if(kind<=.92){ vec2 M1=vec2(-1.2+.3*sin(u_t*.07),.4)+u_ptr*u_ptrA*1.2, M2=vec2(1.4,-.6+.3*cos(u_t*.05)); vec3 q; if(kind<.78){ float g_=floor(a_s.x*1400.); vec2 c=(vec2(fract(sin(g_*12.9898)*43758.5),fract(sin(g_*78.233)*43758.5))-.5)*vec2(8.4,5.2); vec2 d1=c-M1, d2=c-M2; float r1=dot(d1,d1)+.25, r2=dot(d2,d2)+.25; vec2 g=-(vec2(d1.x*d1.x-d1.y*d1.y,2.*d1.x*d1.y)/(r1*r1)*1.1+vec2(d2.x*d2.x-d2.y*d2.y,2.*d2.x*d2.y)/(r2*r2)*.8); float ia=fract(g_*.618)*3.1416; float e0=.25*fract(g_*.377); vec2 ei=vec2(cos(2.*ia),sin(2.*ia))*e0; vec2 e=ei+g*1.6; float el=min(length(e),.85); float pa=.5*atan(e.y,e.x+1e-5); float an=a_s.y*6.2832; float rr=.055*(.6+.6*fract(g_*.71))*sqrt(a_s.z); vec2 v=vec2(cos(an)*(1.+el),sin(an)*(1.-el))*rr; v=vec2(v.x*cos(pa)-v.y*sin(pa),v.x*sin(pa)+v.y*cos(pa)); q=vec3(c+v,0.); float gs=min(length(g)*1.5,1.); col=mix(u_col[2],u_col[3],gs)*1.15; alpha=.30*(1.-a_s.z*.6); sz=.9; } else { vec2 xy=(a_s.xy-.5)*vec2(8.4,5.2); vec2 e1=xy-M1, e2=xy-M2; float kk=1.1/(dot(e1,e1)+.3)+.8/(dot(e2,e2)+.3); q=vec3(xy,-.4); col=mix(u_col[0],u_col[1],min(kk*.3,1.)); alpha=.05*min(kk,2.5); sz=1.4; } p=rotX(rotY(q,-u_yaw*.5),-u_tilt+.05); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
