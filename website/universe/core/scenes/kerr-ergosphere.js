/* SOST Universe scene module: kerr-ergosphere (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("kerr-ergosphere", {
 "p": " if(kind<=.92){ float sp=.80+.18*clamp(.5+.5*sin(u_t*.07)+u_ptr.x*u_ptrA*.6,0.,1.); float M=.62; float rh=M*(1.+sqrt(1.-sp*sp)); if(kind<.24){ float th,ph; if(fract(a_s.x*2.)<.5){ th=floor(a_s.y*18.)/18.*6.2832; ph=a_s.z*3.1416; } else { ph=(floor(a_s.z*9.)+.5)/9.*3.1416; th=a_s.y*6.2832; } float re=M*(1.+sqrt(max(0.,1.-sp*sp*cos(ph)*cos(ph)))); th+=u_t*.35*sp; p=vec3(re*sin(ph)*cos(th),re*cos(ph),re*sin(ph)*sin(th)); col=mix(u_col[0],u_col[3],.5+.5*cos(ph*2.))*1.1; alpha=.30; sz=.75; } else { float f=fract(u_t*.06+a_s.x); float r=mix(3.3,rh*1.02,pow(f,.8)); float om=.22*pow(r,-1.5)+1.6*sp*pow(rh/r,3.); float ang=a_s.y*6.2832+u_t*om*3.+f*6.*sp; float y=(a_s.z-.5)*.9*r*(1.-f)*(1.-f); p=vec3(r*cos(ang),y,r*sin(ang)); float hot=smoothstep(.55,1.,f); col=mix(u_col[int(band)],u_col[5],hot*.6)*(1.+hot*.4); alpha=(.16+.45*hot)*smoothstep(0.,.08,f); sz=.8+.6*hot; } vec3 vv=rotY(rotX(p,u_tilt),u_yaw); if(vv.z<0.&&length(vv.xy)*4.6/(4.6-vv.z)<rh) alpha=0.; }",
 "l": " { float sp=.80+.18*clamp(.5+.5*sin(u_t*.07)+u_ptr.x*u_ptrA*.6,0.,1.); float rh=.62*(1.+sqrt(1.-sp*sp)); float rr=mix(3.3,rh*1.02,u); float ang=j1*6.2832+u_t*.15+u*(4.+8.*sp); p=vec3(rr*cos(ang),(j2-.5)*.1*rr*(1.-u),rr*sin(ang)); vec3 vv=rotY(rotX(p,u_tilt),u_yaw); float hid=(vv.z<0.&&length(vv.xy)*4.6/(4.6-vv.z)<rh)?0.:1.; col=u_col[int(band)]*(.5+u)*hid; }",
 "rc": "u_col[0]*.55",
 "rad": 0.74,
 "la": 0.45
});
