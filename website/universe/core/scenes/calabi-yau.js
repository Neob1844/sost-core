/* SOST Universe scene module: calabi-yau (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("calabi-yau", {
 "p": " if(kind<=.92){ float n=5.; float k1=floor(a_s.x*n), k2=floor(fract(a_s.x*n)*n); float a=(a_s.y-.5)*2.4, b=a_s.z*1.5708; vec2 z=vec2(cos(a)*cos(b)-0.,0.); float ch=.5*(exp(a)+exp(-a)), sh=.5*(exp(a)-exp(-a)); vec2 u1=vec2(ch*cos(b),sh*sin(b)), u2=vec2(-sh*sin(b)*0.+sh*cos(b)*0.+(-ch*sin(b))*0.,0.); vec2 c1=vec2(.5*(exp(a)+exp(-a))*cos(b),.5*(exp(a)-exp(-a))*sin(b)); vec2 s1=vec2(.5*(exp(a)-exp(-a))*cos(b),.5*(exp(a)+exp(-a))*sin(b)); float r1=pow(dot(c1,c1),1./n), t1=atan(c1.y,c1.x)*2./n+k1*6.2832/n; float r2=pow(dot(s1,s1),1./n), t2=atan(s1.y,s1.x)*2./n+k2*6.2832/n; vec2 z1=r1*vec2(cos(t1),sin(t1)), z2=r2*vec2(cos(t2),sin(t2)); float al=u_t*.15; vec3 q=vec3(z1.x,z2.x,cos(al)*z1.y+sin(al)*z2.y)*1.05; col=u_col[int(mod(k1+k2,7.))]*1.15; alpha=.26; sz=1.; p=rotY(rotX(q,.3),u_t*.08); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
