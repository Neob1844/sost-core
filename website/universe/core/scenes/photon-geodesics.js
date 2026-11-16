/* SOST Universe scene module: photon-geodesics (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("photon-geodesics", {
 "p": " if(kind<=.92){ if(kind<.22){ float an=a_s.y*6.2832+u_t*(.35+.3*a_s.z); float rr=1.04*(1.+.006*(a_s.x+fract(a_s.x*7.31)+fract(a_s.x*3.17)-1.5)); vec3 q=vec3(rr*cos(an),rr*sin(an),0.); p=rotX(rotY(q,-u_yaw*.3),-u_tilt*.6); col=u_col[int(mod(floor(a_s.y*14.+u_t*.3),7.))]*1.1; col=mix(col,vec3(1.),.25); alpha=.13; sz=.7; } else { p=vec3(0.,0.,-80.); alpha=0.; sz=0.; } }",
 "l": " { float M=.2; float k=mod(cid,21.); float b=(k/20.-.5)*5.4; float ab=max(abs(b),.03); float pl=floor(cid/21.); float ph=asin(min(ab/9.,1.)); float uu=sin(ph)/ab; float du=cos(ph)/ab; int n=int(u*520.); for(int i=0;i<520;i++){ if(i>=n) break; float dd=.012; du+=(-uu+3.*M*uu*uu)*dd; uu+=du*dd; ph+=dd; if(uu>1./(3.*M)){ uu=1./(3.*M); break; } if(uu<1e-3){ uu=1e-3; break; } } float r=1./uu; vec3 q=vec3(-r*cos(ph),r*sin(ph)*sign(b+1e-4),0.); float al=pl*.6283+u_t*.05; q=vec3(q.x,q.y*cos(al),q.y*sin(al)); p=rotX(rotY(q,-u_yaw*.3),-u_tilt*.6); float fr=fract(u_t*.12+j1*.5); float pul=exp(-pow((u-fr)*7.,2.)); col=u_col[int(mod(k,7.))]*(.45+1.8*pul); }",
 "rad": 0,
 "la": 1.9,
 "rc": "vec3(0.)"
});
