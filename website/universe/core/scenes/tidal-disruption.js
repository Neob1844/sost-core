/* SOST Universe scene module: tidal-disruption (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("tidal-disruption", {
 "p": " if(kind<=.92){ float T=fract(u_t/16.); float q=.42; float RS=.16; float nuS=mix(-2.4,2.2,clamp(T/.4,0.,1.)); float st=smoothstep(.17,.32,T); float d=a_s.x-.5; float cyc=clamp((T-.3)/.7,0.,1.); float cz=2.*a_s.z-1.; float sz0=sqrt(1.-cz*cz); vec3 sp=vec3(sz0*cos(a_s.y*6.2832),cz,sz0*sin(a_s.y*6.2832))*pow(fract(a_s.w*7.3),.33); float nu; float r; if(d>0.){ nu=nuS+d*.9*st; float rr=2.*q/(1.+cos(clamp(nu,-2.9,2.9))); r=rr*(1.+d*st*cyc*3.); } else { float e=mix(.95,.35,cyc); nu=nuS+(-d)*st*(1.5+cyc*cyc*40.); float aa=q/(1.-e)*mix(1.,.6,cyc); r=aa*(1.-e*e)/(1.+e*cos(nu)); } vec3 c0=vec3(r*cos(nu),0.,r*sin(nu)); float rad0=.22*(1.-st*.85)+.03; p=c0+sp*rad0*vec3(1.,1.-st*.8,1.); float hot=clamp(.5/r,0.,1.); col=mix(u_col[5],mix(u_col[6],u_col[d>0.?2:1],st),st)*(1.+hot*.6); col=mix(col,u_col[3],hot*hot*st); alpha=(.10+.25*hot*st)*smoothstep(1.,.92,T)*smoothstep(0.,.04,T); sz=1.; if(kind<.03){ float a2=a_s.y*6.2832; p=vec3(.17*cos(a2),0.,.17*sin(a2)); col=u_col[0]; alpha=.5; sz=.8; } vec3 vv=rotY(rotX(p,u_tilt),u_yaw); if(vv.z<0.&&length(vv.xy)*4.6/(4.6-vv.z)<RS) alpha=0.; }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "rad": 0,
 "la": 0,
 "rc": "vec3(0.)"
});
