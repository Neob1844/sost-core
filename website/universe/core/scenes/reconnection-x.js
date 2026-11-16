/* SOST Universe scene module: reconnection-x (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("reconnection-x", {
 "p": " if(kind<=.92){ vec3 q; vec2 X0=u_ptr*vec2(2.,1.5)*u_ptrA*.5; if(kind<.50){ float sd=a_s.x<.5?1.:-1.; float f=fract(a_s.y+u_t*.15); float y=sd*mix(2.,.05,f); float x=(a_s.z-.5)*mix(3.,.4,f); vec2 v=vec2(x,y); if(f>.8){ float g=(f-.8)/.2; v=vec2(sign(x+1e-3)*g*3.5,y*(1.-g)); } q=vec3(v+X0,0.); col=sd>0.?u_col[2]:u_col[1]; col*=1.1; alpha=(.03+.10*smoothstep(.5,.85,f))*step(abs(x),1.2+1.2*(1.-f)); sz=.9; } else { float sd=a_s.x<.5?1.:-1.; float f=fract(u_t*.12+floor(a_s.y*3.)/3.); float cx=sd*f*3.6; float r=.12+.18*f; q=vec3(cx,0.,0.)+vec3(r,r*.6,r*.3)*pow(fract(a_s.w*13.),.4)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832))+vec3(X0,0.); col=mix(u_col[5],u_col[6],f)*1.2; alpha=.25*(1.-f); sz=1.; } p=rotX(rotY(q,-u_yaw*.6),-u_tilt); }",
 "l": " { float k=mod(cid,28.); float c=(mod(k,14.)+.5)/14.*1.9*(1.-.35*fract(u_t*.15)); float sd=k<14.?1.:-1.; float x=(u-.5)*5.; float y=sd*sqrt(x*x+c*c*.8); if(fract(u_t*.15)>.8&&c<.4){ y=sd*sqrt(abs(x*x-c*c)); } vec2 X0=u_ptr*vec2(2.,1.5)*u_ptrA*.5; vec2 v=k<14.?vec2(x,y):vec2(y*.0+x,y); p=rotX(rotY(vec3((k<14.?vec2(x,y):vec2(y,x))+X0,0.),-u_yaw*.6),-u_tilt); col=(k<14.?u_col[3]:u_col[0])*.8*(1.-abs(x)/2.6); }",
 "la": 1.5,
 "rc": "vec3(0.)",
 "rad": 0
});
