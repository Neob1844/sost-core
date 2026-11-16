/* SOST Universe scene module: cosmic-strings (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("cosmic-strings", {
 "p": " if(kind<=.92){ float k=floor(a_s.x*4.); float s=a_s.y*6.2832; float w=u_t*.5*(1.+.2*k); vec3 q=vec3(sin(s+w)+.3*sin(3.*s-w),cos(s-w)+.25*cos(2.*s+w*.7),sin(2.*s+w*.5)*.6)*(.55+.12*k); q+=(vec3(fract(sin(k*12.9)*43758.5),fract(sin(k*78.2)*43758.5),fract(sin(k*39.4)*43758.5))-.5)*vec3(2.6,1.6,1.4); float cu=pow(.5+.5*sin(3.*s-2.*w),40.); col=mix(u_col[int(mod(k*2.+1.,7.))],u_col[5],cu)*1.2; alpha=.30+.4*cu; sz=.9; if(fract(a_s.z*5.)<.25){ q+=normalize(q+1e-3)*0.+vec3(0.,(fract(a_s.w*13.)-.5)*.3*cu,0.)+.2*cu*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); alpha=.25*cu; } p=rotY(q,u_t*.04); }",
 "l": " { float k=mod(cid,4.); float s=(u+j1*.002)*6.2832; float w=u_t*.5*(1.+.2*k); vec3 q=vec3(sin(s+w)+.3*sin(3.*s-w),cos(s-w)+.25*cos(2.*s+w*.7),sin(2.*s+w*.5)*.6)*(.55+.12*k); q+=(vec3(fract(sin(k*12.9)*43758.5),fract(sin(k*78.2)*43758.5),fract(sin(k*39.4)*43758.5))-.5)*vec3(2.6,1.6,1.4); p=rotY(q,u_t*.04); col=u_col[int(mod(k*2.+1.,7.))]*.9; }",
 "la": 1.8,
 "rc": "vec3(0.)",
 "rad": 0
});
