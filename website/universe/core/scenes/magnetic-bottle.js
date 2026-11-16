/* SOST Universe scene module: magnetic-bottle (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("magnetic-bottle", {
 "p": " if(kind<=.92){ float mr=.55+.25*clamp(.5+u_ptr.x*u_ptrA*.6,0.,1.); float k=floor(a_s.x*40.); float hh=fract(sin(k*12.9898)*43758.5); float xm=1.0+1.4*hh; float ph=u_t*(.6+.5*hh)+k; float x=xm*sin(ph*1.)*mix(1.,.9,mr); float Rb=1.-mr*pow(x/2.6,2.); float rg=(.05+.12*hh)*Rb; float tail=a_s.y; float g=u_t*9.-tail*4.+k; float xx=xm*sin(ph-tail*.35)*mix(1.,.9,mr); float Rb2=1.-mr*pow(xx/2.6,2.); vec3 gc=vec3(xx,(hh-.5)*.9*Rb2,(fract(hh*7.)-.5)*.9*Rb2); vec3 q=gc+vec3(0.,rg*cos(g),rg*sin(g))*Rb2/Rb; col=u_col[int(mod(k,7.))]*1.15; alpha=.30*(1.-tail)*(1.-tail); sz=.9+.4*(1.-tail); p=rotX(rotY(q,.3),-.15); }",
 "l": " { float mr=.55+.25*clamp(.5+u_ptr.x*u_ptrA*.6,0.,1.); float k=mod(cid,14.); float an=k/14.*6.2832; float x=(u-.5)*5.6; float R=1.0*(1.-mr*pow(x/2.6,2.))+(j1-.5)*.02; p=rotX(rotY(vec3(x,R*cos(an),R*sin(an)),.3),-.15); col=mix(u_col[2],u_col[0],abs(x)/2.8)*.6; }",
 "la": 1.0,
 "rc": "vec3(0.)",
 "rad": 0
});
