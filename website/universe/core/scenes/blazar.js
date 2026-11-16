/* SOST Universe scene module: blazar (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("blazar", {
 "p": " if(kind<=.92){ float fl=.7+.3*sin(u_t*.9)*sin(u_t*2.3+1.); vec3 v; if(kind<.60){ float k=floor(a_s.x*9.); float f=fract(u_t*.11+k/9.); float z=mix(-7.,3.8,f); float an=a_s.y*6.2832+k*.7; float R=.18+.55*f*f+(a_s.z-.5)*.05; v=vec3(R*cos(an),R*sin(an),z); float kn=step(fract(a_s.y*7.+k*.3),.45); col=mix(u_col[int(mod(k,7.))],mix(u_col[3],u_col[2],f),f*.6)*1.15; alpha=(.10+.25*kn)*smoothstep(0.,.15,f)*(1.-smoothstep(.85,1.,f))*fl; sz=.9+.6*f; } else if(kind<.85){ float s=a_s.x; float an=a_s.y*6.2832; float R=.05+.35*s*s; v=vec3(R*cos(an),R*sin(an),mix(-7.,3.,fract(s+u_t*.3))); col=mix(u_col[1],u_col[3],s)*1.1; alpha=.07*fl; sz=.9; } else { float r=.05*pow(a_s.x,.5); v=vec3(r*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)).xy,-1.); col=mix(u_col[5],u_col[3],a_s.x); alpha=.5*fl; sz=1.; } v.xy+=u_ptr*u_ptrA*vec2(.5,.3)*(1.-clamp((v.z+7.)/11.,0.,1.)); p=rotX(rotY(v,-u_yaw),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
