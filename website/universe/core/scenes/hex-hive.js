/* SOST Universe scene module: hex-hive (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register('hex-hive', {
  "p": " if(kind<=.92){ float h=.24; float qx=floor(a_s.x*16.)-8., rz=floor(a_s.y*10.)-5.; vec2 c=vec2(qx*1.5*h,(rz+mod(qx,2.)*.5)*1.732*h); float hc=fract(sin(qx*12.9898+rz*78.233)*43758.55); float side=floor(a_s.z*6.), ft=fract(a_s.z*6.); float a0=side*1.0472, a1=a0+1.0472; vec2 e=mix(vec2(cos(a0),sin(a0)),vec2(cos(a1),sin(a1)),ft)*h*.92; if(a_s.w<.25) e*=fract(a_s.x*31.); float fl=exp(-fract(u_t*.11+hc)*7.); vec2 pw=u_ptr*vec2(2.6,1.6); float near=u_ptrA*exp(-dot(c-pw,c-pw)*3.); float on=max(fl,near); p=vec3(c.x+e.x,on*.18-.3,c.y+e.y); col=mix(u_col[int(mod(qx+rz*2.+28.,7.))]*.7,u_col[int(mod(hc*7.,7.))]*1.4,on)+vec3(on*.25); alpha=(.42+.7*on)*smoothstep(3.2,2.,length(c)); sz=1.05+1.*on; }",
  "l": " { float h=.24; float qx=mod(cid,14.)-7., rz=floor(cid/14.)-4.; vec2 c=vec2(qx*1.5*h,(rz+mod(qx,2.)*.5)*1.732*h); float side=floor(u*6.), ft=fract(u*6.); float a0=side*1.0472, a1=a0+1.0472; vec2 e=mix(vec2(cos(a0),sin(a0)),vec2(cos(a1),sin(a1)),ft)*h*.92; float hc=fract(sin(qx*12.9898+rz*78.233)*43758.55); float fl=exp(-fract(u_t*.11+hc)*7.); p=vec3(c.x+e.x,fl*.18-.3,c.y+e.y); col=u_col[int(mod(hc*7.,7.))]*(.3+1.5*fl); }",
  "rc": "vec3(0.)",
  "rad": 0,
  "la": 0.6
 });
