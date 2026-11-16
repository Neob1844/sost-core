/* SOST Universe scene module: frb-chirp (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("frb-chirp", {
 "p": " if(kind<=.92){ float T=fract(u_t/7.+.5); vec3 q; if(kind<.55){ float b=floor(a_s.x*7.); float nu=1.+b*.22; float x=-2.4+T*5.6-.7*T*T*4./(nu*nu); float an=(a_s.y-.5)*1.3; float R=1.6+x*.3; q=vec3(x+R*(1.-cos(an))*-.3,R*sin(an)*.9,(a_s.z-.5)*.06); col=u_col[int(6.-b)]*1.1; alpha=.22*smoothstep(.12,.35,T)*(1.-smoothstep(.8,1.,T)); sz=1.; } else if(kind<.65){ q=vec3(-2.8,0.,0.)+.16*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=u_col[1]*1.1; alpha=.3; sz=.9; } else { q=vec3((a_s.x-.5)*8.,(a_s.y-.5)*3.6,(a_s.z-.5)*2.); col=mix(u_col[0],u_col[2],a_s.z)*.8; alpha=.04*(.5+.5*sin(q.x*3.+u_t)); sz=1.; } p=rotX(rotY(q,-u_yaw*.4),-u_tilt+.1); }",
 "l": " { float k=mod(cid,12.); float L=.25+.06*k; float az=k*.52+u_t*.4; float th_=mix(.2,2.94,u); float rr_=L*sin(th_)*sin(th_); vec3 dq=vec3(rr_*sin(th_)*cos(az),rr_*cos(th_),rr_*sin(th_)*sin(az)); p=rotX(rotY(vec3(-2.8,0.,0.)+dq,-u_yaw*.4),-u_tilt+.1); col=u_col[1]*.7; }",
 "la": 1.0,
 "rc": "vec3(0.)",
 "rad": 0
});
