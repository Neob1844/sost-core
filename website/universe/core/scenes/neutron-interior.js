/* SOST Universe scene module: neutron-interior (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("neutron-interior", {
 "p": " if(kind<=.92){ float spin=u_t*.35; float T=fract(u_t/12.); float gl=exp(-pow((T-.5)*30.,2.)); spin+=smoothstep(.48,.52,T)*.4; float cz=2.*a_s.z-1.; float s0=sqrt(1.-cz*cz); float ph=a_s.y*6.2832; vec3 n=vec3(s0*cos(ph),cz,s0*sin(ph)); vec3 q; float cut=step(0.,n.x)*step(0.,n.z); if(kind<.45){ float L=floor(a_s.x*4.); float R=mix(1.15,.45,L/3.); q=n*R; if(L<.5){ q=floor(n*R*26.)/26.; } col=u_col[int(mod(L*2.+1.,7.))]*1.1; alpha=(.16+.06*L)*(1.-cut); sz=.9; } else { float pl=step(.5,fract(a_s.x*2.)); float u1=a_s.y*1.15, v1=(a_s.z*2.-1.)*1.15; q=pl>.5?vec3(0.,v1,u1):vec3(u1,v1,0.); float rr=length(q); float layer=rr>1.05?0.:rr>.85?1.:rr>.6?2.:3.; col=u_col[int(mod(layer*2.+1.,7.))]*1.1; alpha=rr>1.15?0.:.10; sz=.9; } p=rotY(q*1.5,spin); col=mix(col,u_col[5],gl*.6); alpha*=1.+gl*2.; }",
 "l": " { float spin=u_t*.35; float T=fract(u_t/12.); spin+=smoothstep(.48,.52,T)*.4; float k=mod(cid,60.); float gx=mod(k,8.), gz=floor(k/8.); vec2 xz=vec2(gx+.5*mod(gz,2.),gz*.866)*.13+.05; if(length(xz)>.95) xz*=.95/length(xz); float hh=sqrt(max(0.,1.21-dot(xz,xz)))*.98; vec3 q=vec3(xz.x,(u*2.-1.)*hh,xz.y)+vec3(.012*sin(u*30.+u_t*2.+k),0.,.012*cos(u*30.+u_t*2.+k)); p=rotY(q*1.5,spin); col=mix(u_col[3],u_col[0],u)*.9; }",
 "rc": "vec3(0.)",
 "la": 0.9,
 "rad": 0
});
