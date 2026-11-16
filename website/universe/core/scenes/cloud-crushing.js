/* SOST Universe scene module: cloud-crushing (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("cloud-crushing", {
 "p": " if(kind<=.92){ float T=fract(u_t/14.); float X=mix(-3.6,3.6,T); vec3 q; if(kind<.25){ float y=(a_s.x-.5)*4., z=(a_s.y-.5)*3.; float rip=.08*sin(y*3.+u_t)+.06*sin(z*4.-u_t*1.3); q=vec3(X+rip-(a_s.z)*.06,y,z); col=mix(u_col[3],u_col[2],a_s.z)*1.15; alpha=.16*(1.-a_s.z); sz=.9; } else if(kind<.75){ float id=floor(a_s.x*7.); vec3 c0=vec3(-2.6+id*.85,(fract(sin(id*12.9)*43758.5)-.5)*2.4,(fract(sin(id*78.2)*43758.5)-.5)*1.6); float rc=.28+.12*fract(id*.618); vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float rr=rc*pow(fract(a_s.w*13.),.33); float hit=max(0.,X-c0.x+rc); float str=hit*.9; vec3 off=vec3(-(1.-a_s.x*7.+id)*0.+0.,0.,0.); float tail=fract(a_s.w*29.)*str; q=c0+d*rr*vec3(1.,1./(1.+str*.6),1./(1.+str*.6))+vec3(tail*1.4,.15*sin(tail*6.+u_t*2.+id)*tail,0.); float heat=smoothstep(0.,.3,hit)*(.5+.5*smoothstep(.5,1.,length(d*rr)/rc)); col=mix(u_col[0],mix(u_col[6],u_col[5],heat),smoothstep(0.,.2,hit))*1.1; alpha=.16+.22*heat; sz=1.; } else { vec3 g=vec3(mix(-3.6,X,a_s.x),(a_s.y-.5)*4.,(a_s.z-.5)*3.); q=g; col=u_col[2]*.8; alpha=.025; sz=1.1; } p=rotX(rotY(q,-u_yaw*.5+.2),-u_tilt+.15); alpha*=smoothstep(0.,.04,T)*smoothstep(1.,.96,T); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
